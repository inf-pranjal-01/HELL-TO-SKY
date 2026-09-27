#ifdef ARDUINO

#include <Arduino.h>
#include "../include/config.h"
#include "sensors/sensor_manager.h"
#include "edge/edge_engine.h"
#include "protocol/packet_builder.h"
#include "network/wifi_manager.h"
#include "network/http_poster.h"
#include <ArduinoJson.h>

// ── Global Module Instances ──────────────────────────────────────────────────
static SensorManager sensorMgr;
static WiFiNetworkManager wifiMgr;
static HttpPoster httpPoster;

static char deviceId[DEVICE_ID_BUFFER_SIZE] = "esp32-node-uninitialized";
static uint32_t sequenceNumber = 1;
static char endpointUrl[128];

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println();
    Serial.println(F("=================================================="));
    Serial.println(F("  SkyGuard AI — ESP32 Level 1 Edge Node Firmware  "));
    Serial.printf( "  Version: %s | Model: %s\n", FIRMWARE_VERSION, EDGE_MODEL_VERSION);
    Serial.println(F("=================================================="));

#if !ENABLE_VIRTUAL_SENSOR_MODE
    // 1. Initialize Physical Sensors (BMP280 on I2C SDA=21/SCL=22, DHT22 on GPIO 4)
    Serial.println(F("[Setup] Initializing hardware transducers..."));
    sensorMgr.begin(PIN_I2C_SDA, PIN_I2C_SCL, PIN_DHT22_DATA);
#else
    Serial.println(F("[Setup] VIRTUAL SENSOR MODE ENABLED (Reading from USB Serial)"));
#endif

    // 2. Connect to Local Wi-Fi Network
    Serial.println(F("[Setup] Establishing Wi-Fi connection..."));
    wifiMgr.connectWiFi(WIFI_SSID, WIFI_PASSWORD, WIFI_CONNECT_TIMEOUT_MS);

    // 3. Synchronize Time with Global NTP Servers
    if (wifiMgr.isConnected()) {
        wifiMgr.syncNTP(NTP_SERVER_PRIMARY, NTP_SERVER_SECONDARY, NTP_TIMEOUT_MS);
        wifiMgr.getDeviceID(deviceId, sizeof(deviceId));
    }
    Serial.printf("[Setup] Hardware Device ID: %s | Station: %s\n", deviceId, DEFAULT_STATION_ID);

    // 4. Construct Backend Ingestion Endpoint URL
    snprintf(endpointUrl, sizeof(endpointUrl), "%s%s", BACKEND_BASE_URL, INGESTION_ENDPOINT_PATH);
    Serial.printf("[Setup] Target Ingestion URL: %s\n", endpointUrl);
    Serial.println(F("[Setup] Level 1 Edge Node initialization complete. Starting observation loop.\n"));
}

void loop() {
    uint32_t loopStartMs = millis();

    // 1. Ensure Wi-Fi Connectivity
    if (!wifiMgr.isConnected()) {
        Serial.println(F("[Loop] Wi-Fi link lost. Attempting reconnection..."));
        wifiMgr.connectWiFi(WIFI_SSID, WIFI_PASSWORD, 5000);
    }

#if ENABLE_VIRTUAL_SENSOR_MODE
    if (!Serial.available()) {
        delay(10);
        return;
    }
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) return;

    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, line);
    if (error) {
        Serial.printf("[VirtualSensor] JSON Parse Error: %s\n", error.c_str());
        return;
    }

    SensorReadings readings;
    readings.temperature_c = doc["temperature_c"].is<float>() ? doc["temperature_c"].as<float>() : NAN;
    readings.pressure_hpa = doc["pressure_hpa"].is<float>() ? doc["pressure_hpa"].as<float>() : NAN;
    readings.humidity_pct = doc["humidity_pct"].is<float>() ? doc["humidity_pct"].as<float>() : NAN;

    const char* virtual_ts = doc["timestamp"].is<const char*>() ? doc["timestamp"].as<const char*>() : nullptr;
    const char* current_station_id = doc["station_id"].is<const char*>() ? doc["station_id"].as<const char*>() : DEFAULT_STATION_ID;

    Serial.printf("[VirtualSensor] T: %.2f °C | P: %.2f hPa | RH: %.2f %%\n",
                  readings.temperature_c, readings.pressure_hpa, readings.humidity_pct);
#else
    // 2. Sample Physical Sensors
    SensorReadings readings = sensorMgr.readSensors();
    Serial.printf("[Sensor] T: %.2f °C | P: %.2f hPa | RH: %.2f %%\n",
                  readings.temperature_c, readings.pressure_hpa, readings.humidity_pct);
    const char* current_station_id = DEFAULT_STATION_ID;
    const char* virtual_ts = nullptr;
#endif

    // 3. Execute Level 1 Deterministic Edge Inference
    EdgeInferenceResult edgeResult = run_edge_inference_c(
        readings.temperature_c,
        readings.pressure_hpa,
        readings.humidity_pct
    );
    Serial.printf("[Edge AI] Status: %s | Flag: %s | Type: %s\n",
                  edgeResult.status,
                  edgeResult.anomaly_flag ? "TRUE" : "FALSE",
                  edgeResult.anomaly_type ? edgeResult.anomaly_type : "none");

    // 4. Generate Unique UUIDv4 Event Identifier
    char eventId[EVENT_ID_BUFFER_SIZE];
    generate_uuid_v4(eventId);

    // 5. Obtain ISO-8601 UTC Observation Timestamp
    char timestampIso[TIMESTAMP_BUFFER_SIZE];
#if ENABLE_VIRTUAL_SENSOR_MODE
    if (virtual_ts != nullptr) {
        strncpy(timestampIso, virtual_ts, sizeof(timestampIso));
        timestampIso[sizeof(timestampIso) - 1] = '\0';
    } else {
        wifiMgr.getISOTimestamp(timestampIso, sizeof(timestampIso));
    }
#else
    wifiMgr.getISOTimestamp(timestampIso, sizeof(timestampIso));
#endif

    // 6. Assemble and Serialize Canonical ObservationPacket JSON
    char payloadBuffer[MAX_JSON_PAYLOAD_SIZE];
    float rssi = wifiMgr.getRSSI();

    bool serialized = build_observation_packet_json(
        eventId,
        current_station_id,
        deviceId,
        timestampIso,
        sequenceNumber,
        &readings,
        &edgeResult,
        FIRMWARE_VERSION,
        rssi,
        payloadBuffer,
        sizeof(payloadBuffer)
    );

    if (serialized) {
        Serial.printf("[Packet #%u] Transmitting canonical payload (%d bytes)...\n",
                      sequenceNumber, (int)strlen(payloadBuffer));

        // 7. Submit to Backend Ingestion API with Bounded Retries
        if (wifiMgr.isConnected()) {
            IngestResult res = httpPoster.sendObservation(
                endpointUrl,
                payloadBuffer,
                MAX_TRANSMISSION_RETRIES,
                RETRY_BACKOFF_BASE_MS
            );

            if (res == INGEST_SUCCESS || res == INGEST_DUPLICATE_ACCEPTED) {
                // Advance sequence number only after successful delivery or duplicate acknowledgment
                sequenceNumber++;
            }
        } else {
            Serial.println(F("[Loop] Cannot transmit packet: No Wi-Fi connection."));
        }
    } else {
        Serial.println(F("[Loop] ERROR: Failed to serialize ObservationPacket JSON!"));
    }

    // 8. Maintain Sampling Cadence (only if physical sensors)
#if !ENABLE_VIRTUAL_SENSOR_MODE
    uint32_t elapsedMs = millis() - loopStartMs;
    if (elapsedMs < SAMPLING_INTERVAL_MS) {
        delay(SAMPLING_INTERVAL_MS - elapsedMs);
    }
#endif
}

#endif
