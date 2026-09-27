#pragma once

#ifdef ARDUINO
#include <WiFi.h>
#include <time.h>
#endif

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

#ifdef ARDUINO

class WiFiNetworkManager {
public:
    WiFiNetworkManager();
    bool connectWiFi(const char* ssid, const char* password, uint32_t timeout_ms);
    bool syncNTP(const char* ntp_server1, const char* ntp_server2, uint32_t timeout_ms);
    bool getISOTimestamp(char* out_iso, size_t max_len);
    float getRSSI();
    void getDeviceID(char* out_device_id, size_t max_len);
    bool isConnected();

private:
    bool _ntpSynced;
};

#endif
