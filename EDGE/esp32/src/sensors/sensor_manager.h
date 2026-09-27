#pragma once

#include <stdint.h>
#include <stdbool.h>

struct SensorReadings {
    float temperature_c;   // Temperature in °C (NAN if unavailable)
    float pressure_hpa;    // Pressure in hPa (NAN if unavailable)
    float humidity_pct;    // Relative humidity in % (NAN if unavailable)
    bool bmp_ok;           // BMP280 hardware health status
    bool dht_ok;           // DHT22 hardware health status
};

#ifdef ARDUINO
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_BMP280.h>
#include <DHT.h>

class SensorManager {
public:
    SensorManager();
    bool begin(uint8_t sda_pin = 21, uint8_t scl_pin = 22, uint8_t dht_pin = 4);
    SensorReadings readSensors();
    bool isBmpAvailable() const { return _bmpInitialized; }
    bool isDhtAvailable() const { return _dhtInitialized; }

private:
    Adafruit_BMP280 _bmp;
    DHT* _dht;
    bool _bmpInitialized;
    bool _dhtInitialized;
    uint8_t _dhtPin;
};
#endif
