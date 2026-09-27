#pragma once

#ifdef ARDUINO
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_BMP280.h>
#include <DHT.h>
#endif

#include <stdint.h>

typedef struct {
    float temperature_c;
    float pressure_hpa;
    float humidity_pct;
    bool bmp_ok;
    bool dht_ok;
} SensorReadings;

#ifdef ARDUINO

class SensorManager {
public:
    SensorManager();
    bool begin(uint8_t sda_pin, uint8_t scl_pin, uint8_t dht_pin);
    SensorReadings readSensors();

private:
    Adafruit_BMP280 _bmp;
    DHT* _dht;
    bool _bmpInitialized;
    bool _dhtInitialized;
    uint8_t _dhtPin;
};

#endif
