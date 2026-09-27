#include <Arduino.h>
#include <ArduinoJson.h>
#include "config.h"
#include "sensor_manager.h"
#include "edge_engine.h"
#include "packet_builder.h"
#include "wifi_manager.h"
#include "http_poster.h"
#include "embedded_test_dataset.h"

// ── Offline Store-and-Forward Buffer Configuration ───────────────────────────
#define OFFLINE_QUEUE_CAPACITY 64
struct OfflinePacket {
    char json[MAX_JSON_PAYLOAD_SIZE];
    bool valid;
};
static OfflinePacket offlineQueue[OFFLINE_QUEUE_CAPACITY];
static size_t queueHead = 0;
static size_t queueTail = 0;
static size_t queueCount = 0;

void enqueue_offline_packet(const char* json) {
    if (queueCount < OFFLINE_QUEUE_CAPACITY) {
        strncpy(offlineQueue[queueHead].json, json, MAX_JSON_PAYLOAD_SIZE - 1);
        offlineQueue[queueHead].json[MAX_JSON_PAYLOAD_SIZE - 1] = '\0';
        offlineQueue[queueHead].valid = true;
        queueHead = (queueHead + 1) % OFFLINE_QUEUE_CAPACITY;
        queueCount++;
        Serial.printf("[Store&Forward] Network offline. Packet enqueued (Buffer: %u/%u).\n",
                      (unsigned int)queueCount, OFFLINE_QUEUE_CAPACITY);
    } else {
        Serial.println(F("[Store&Forward] WARNING: Offline queue full! Overwriting oldest packet."));
        strncpy(offlineQueue[queueHead].json, json, MAX_JSON_PAYLOAD_SIZE - 1);
        queueHead = (queueHead + 1) % OFFLINE_QUEUE_CAPACITY;
        queueTail = (queueTail + 1) % OFFLINE_QUEUE_CAPACITY;
    }
}

void flush_offline_queue(HttpPoster* poster, const char* endpoint) {
    while (queueCount > 0) {
        if (!offlineQueue[queueTail].valid) {
            queueTail = (queueTail + 1) % OFFLINE_QUEUE_CAPACITY;
            queueCount--;
            continue;
        }

        Serial.printf("[Store&Forward] Flushing buffered packet (%u remaining)...\n", (unsigned int)queueCount);
        IngestResult res = poster->sendObservation(endpoint, offlineQueue[queueTail].json, 2, 200);
        if (res == INGEST_SUCCESS || res == INGEST_DUPLICATE_ACCEPTED) {
            offlineQueue[queueTail].valid = false;
            queueTail = (queueTail + 1) % OFFLINE_QUEUE_CAPACITY;
            queueCount--;
            delay(50);
        } else {
            Serial.println(F("[Store&Forward] Flush paused: Network error."));
            break;
        }
    }
}

// ── Global Module Instances ──────────────────────────────────────────────────
static SensorManager sensorMgr;
static WiFiNetworkManager wifiMgr;
static HttpPoster httpPoster;
static SkyGuardNodeState nodeState;

static char deviceId[DEVICE_ID_BUFFER_SIZE] = "esp32-node-uninitialized";
static uint32_t sequenceNumber = 1;
static char endpointUrl[128];

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println();
    Serial.println(F("================================================================="));
    Serial.println(F("  SkyGuard AI — ESP32 Level 1 Causal Continuous-Time Edge Node   "));
    Serial.printf( "  Firmware: %s | Model: %s\n", FIRMWARE_VERSION, EDGE_MODEL_VERSION);
    Serial.println(F("================================================================="));
    Serial.println(F("\n[PAUSED] Waiting for user confirmation."));
    Serial.println(F(">>> Type '1' in the Serial Monitor and press ENTER to start execution... <<<"));
    
    // Wait until user types '1' into Serial Monitor
    bool started = false;
    while (!started) {
        if (Serial.available() > 0) {
            char ch = Serial.read();
            if (ch == '1') {
                started = true;
                Serial.println(F("\n[System] START TRIGGER RECEIVED ('1'). Initializing Edge AI Node...\n"));
            }
        }
        delay(100);
    }

    // 1. Initialize Causal Edge State & Welford Online Accumulators
    skyguard_state_init(&nodeState);
    Serial.printf("[Setup] Initialized zero-leakage dual buffer state (%u bytes RAM).\n",
                  (unsigned int)sizeof(SkyGuardNodeState));

#if !ENABLE_VIRTUAL_SENSOR_MODE
    // 2. Initialize Physical Sensors (BMP280 on I2C SDA=21/SCL=22, DHT22 on GPIO 4)
    Serial.println(F("[Setup] Initializing hardware transducers..."));
    sensorMgr.begin(PIN_I2C_SDA, PIN_I2C_SCL, PIN_DHT22_DATA);
#else
    Serial.println(F("[Setup] VIRTUAL SENSOR MODE ENABLED (Streaming from USB Serial)"));
#endif

    // 3. Connect to Local Wi-Fi Network
    Serial.println(F("[Setup] Establishing Wi-Fi connection..."));
    wifiMgr.connectWiFi(WIFI_SSID, WIFI_PASSWORD, WIFI_CONNECT_TIMEOUT_MS);

    // 4. Synchronize Time with Global NTP Servers
    if (wifiMgr.isConnected()) {
        wifiMgr.syncNTP(NTP_SERVER_PRIMARY, NTP_SERVER_SECONDARY, NTP_TIMEOUT_MS);
        wifiMgr.getDeviceID(deviceId, sizeof(deviceId));
    }
    Serial.printf("[Setup] Hardware Device ID: %s | Station: %s\n", deviceId, DEFAULT_STATION_ID);

    // 5. Construct Backend Ingestion Endpoint URL
    snprintf(endpointUrl, sizeof(endpointUrl), "%s%s", BACKEND_BASE_URL, INGESTION_ENDPOINT_PATH);
    Serial.printf("[Setup] Target Ingestion URL: %s\n", endpointUrl);
    Serial.println(F("[Setup] Level 1 Edge Node initialization complete. Starting loop.\n"));
}

void loop() {
    uint32_t loopStartMs = millis();
    uint32_t currentTs_s = loopStartMs / 1000;

    // 1. Ensure Wi-Fi Connectivity (rate-limited check)
    static uint32_t lastWiFiCheckMs = 0;
    if (!wifiMgr.isConnected()) {
        if (millis() - lastWiFiCheckMs > 10000) {
            lastWiFiCheckMs = millis();
            wifiMgr.connectWiFi(WIFI_SSID, WIFI_PASSWORD, 3000);
        }
    } else if (queueCount > 0) {
        flush_offline_queue(&httpPoster, endpointUrl);
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

    // 3. Execute 5-Tier Causal Continuous-Time Edge Detection
    SkyGuardVerdict verdict = skyguard_detect_reading(
        &nodeState,
        readings.temperature_c,
        readings.pressure_hpa,
        readings.humidity_pct,
        currentTs_s
    );

    Serial.printf("[Edge AI] Status: %s | Flag: %s | Tier: %u | Type: %s | LLR: %.2f\n",
                  verdict.status,
                  verdict.is_anomaly ? "TRUE" : "FALSE",
                  verdict.tier_fired,
                  verdict.fault_type ? verdict.fault_type : "none",
                  verdict.confidence_llr);

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
        &verdict,
        FIRMWARE_VERSION,
        rssi,
        payloadBuffer,
        sizeof(payloadBuffer)
    );

    if (serialized) {
        Serial.printf("[Packet #%u] Serialized canonical payload (%d bytes)...\n",
                      sequenceNumber, (int)strlen(payloadBuffer));

        // 7. Submit to Backend or Enqueue if Offline
        if (wifiMgr.isConnected()) {
            IngestResult res = httpPoster.sendObservation(
                endpointUrl,
                payloadBuffer,
                MAX_TRANSMISSION_RETRIES,
                RETRY_BACKOFF_BASE_MS
            );

            if (res == INGEST_SUCCESS || res == INGEST_DUPLICATE_ACCEPTED) {
                sequenceNumber++;
            } else {
                enqueue_offline_packet(payloadBuffer);
                sequenceNumber++;
            }
        } else {
            enqueue_offline_packet(payloadBuffer);
            sequenceNumber++;
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
