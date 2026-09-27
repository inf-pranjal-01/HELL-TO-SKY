#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef ARDUINO
#include <Arduino.h>
#include <WiFi.h>
#include <time.h>

class WiFiNetworkManager {
public:
    WiFiNetworkManager();
    bool connectWiFi(const char* ssid, const char* password, uint32_t timeout_ms = 15000);
    bool syncNTP(const char* ntp_server1 = "pool.ntp.org", const char* ntp_server2 = "time.nist.gov", uint32_t timeout_ms = 10000);
    bool getISOTimestamp(char* out_iso, size_t max_len);
    float getRSSI();
    void getDeviceID(char* out_device_id, size_t max_len);
    bool isConnected();

private:
    bool _ntpSynced;
};
#endif
