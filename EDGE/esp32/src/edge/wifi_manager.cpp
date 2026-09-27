#include "wifi_manager.h"
#include <stdio.h>
#include <string.h>

#ifdef ARDUINO

WiFiNetworkManager::WiFiNetworkManager() : _ntpSynced(false) {}

bool WiFiNetworkManager::connectWiFi(const char* ssid, const char* password, uint32_t timeout_ms) {
    if (WiFi.status() == WL_CONNECTED) {
        return true;
    }

    Serial.printf("[WiFi] Connecting to %s...\n", ssid);
    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);

    uint32_t start_ms = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - start_ms) < timeout_ms) {
        delay(500);
        Serial.print('.');
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("[WiFi] Connected! IP address: %s, RSSI: %d dBm\n",
                      WiFi.localIP().toString().c_str(), WiFi.RSSI());
        return true;
    }

    Serial.println(F("[WiFi] Connection failed / timed out."));
    return false;
}

bool WiFiNetworkManager::syncNTP(const char* ntp_server1, const char* ntp_server2, uint32_t timeout_ms) {
    Serial.println(F("[NTP] Initializing UTC time synchronization via SNTP..."));
    configTime(0, 0, ntp_server1, ntp_server2);

    struct tm timeinfo;
    uint32_t start_ms = millis();

    while ((millis() - start_ms) < timeout_ms) {
        if (getLocalTime(&timeinfo, 500)) {
            // Check that year is reasonable (> 2024)
            if (timeinfo.tm_year > (2024 - 1900)) {
                _ntpSynced = true;
                char buf[32];
                strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);
                Serial.printf("[NTP] Time synchronized successfully: %s\n", buf);
                return true;
            }
        }
        delay(200);
    }

    Serial.println(F("[NTP] WARNING: Time synchronization failed."));
    _ntpSynced = false;
    return false;
}

bool WiFiNetworkManager::getISOTimestamp(char* out_iso, size_t max_len) {
    if (!out_iso || max_len < 25) {
        return false;
    }

    struct tm timeinfo;
    if (getLocalTime(&timeinfo, 100)) {
        strftime(out_iso, max_len, "%Y-%m-%dT%H:%M:%SZ", &timeinfo);
        return true;
    }

    // Fallback if NTP sync failed: generate an un-synchronized placeholder
    snprintf(out_iso, max_len, "1970-01-01T00:00:00Z");
    return false;
}

float WiFiNetworkManager::getRSSI() {
    if (WiFi.status() == WL_CONNECTED) {
        return (float)WiFi.RSSI();
    }
    return 0.0f;
}

void WiFiNetworkManager::getDeviceID(char* out_device_id, size_t max_len) {
    uint8_t mac[6];
    WiFi.macAddress(mac);
    snprintf(out_device_id, max_len, "esp32-node-%02X%02X%02X%02X%02X%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

bool WiFiNetworkManager::isConnected() {
    return (WiFi.status() == WL_CONNECTED);
}

#endif
