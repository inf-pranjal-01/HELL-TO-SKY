#pragma once

#include <stdint.h>

// =============================================================================
// SkyGuard AI ESP32 Edge Node — Hardware, Network & Protocol Configuration
// =============================================================================

// --- Virtual Sensor Mode ---
// Set to 1 to read telemetry from USB Serial (streaming CSV data without physical sensors)
// Set to 0 to read from physical I2C BMP280 and GPIO DHT22 sensors
#define ENABLE_VIRTUAL_SENSOR_MODE 1

// --- Hardware Pin Definitions ---
// BMP280 (Temperature & Atmospheric Pressure): Connected via I2C
#define PIN_I2C_SDA 21
#define PIN_I2C_SCL 22
#define BMP280_I2C_ADDR 0x76  // Default I2C address (0x76 or 0x77)

// DHT22 (Relative Humidity): Connected via single-wire digital GPIO
#define PIN_DHT22_DATA 4

// --- Station & Device Identity ---
#define DEFAULT_STATION_ID "AWS-CHN-024"  // Target meteorological station
#define FIRMWARE_VERSION "esp32_edge_v1.0.0"
#define EDGE_MODEL_VERSION "edge_rules_v1.0.0"
#define EDGE_INFERENCE_METHOD "rules"

// --- Wi-Fi Credentials (Configure for your 2.4GHz Wi-Fi network or Mobile Hotspot) ---
#define WIFI_SSID "Redmi 10 Prime"
#define WIFI_PASSWORD "tomatox000"
#define WIFI_CONNECT_TIMEOUT_MS 15000

// --- NTP Time Server Configuration ---
#define NTP_SERVER_PRIMARY "pool.ntp.org"
#define NTP_SERVER_SECONDARY "time.nist.gov"
#define NTP_TIMEOUT_MS 10000

// --- Backend Ingestion API ---
// Override with your PC's actual local IPv4 address (e.g. "http://192.168.1.100:8000")
#define BACKEND_BASE_URL "http://192.168.1.49:8000"
#define INGESTION_ENDPOINT_PATH "/api/ingest/observation"
#define HTTP_REQUEST_TIMEOUT_MS 10000

// --- Sampling Cadence & Transmission Policy ---
#define SAMPLING_INTERVAL_MS 2000      // 2 seconds per observation cycle
#define MAX_TRANSMISSION_RETRIES 3     // Bounded retries per packet
#define RETRY_BACKOFF_BASE_MS 500      // Backoff delay between retries

// --- Memory & Buffer Limits ---
#define MAX_JSON_PAYLOAD_SIZE 768
#define EVENT_ID_BUFFER_SIZE 40
#define DEVICE_ID_BUFFER_SIZE 48
#define TIMESTAMP_BUFFER_SIZE 32
