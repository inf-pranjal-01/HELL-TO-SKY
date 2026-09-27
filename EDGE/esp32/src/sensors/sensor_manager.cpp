#include "sensor_manager.h"
#include <math.h>

#ifdef ARDUINO

SensorManager::SensorManager()
    : _dht(nullptr),
      _bmpInitialized(false),
      _dhtInitialized(false),
      _dhtPin(4) {
}

bool SensorManager::begin(uint8_t sda_pin, uint8_t scl_pin, uint8_t dht_pin) {
    _dhtPin = dht_pin;

    // 1. Initialize I2C Bus for BMP280
    Wire.begin(sda_pin, scl_pin);

    // 2. Initialize BMP280 Barometric Pressure & Temperature Transducer
    if (_bmp.begin(0x76)) {
        _bmpInitialized = true;
        _bmp.setSampling(
            Adafruit_BMP280::MODE_NORMAL,     // Operating Mode
            Adafruit_BMP280::SAMPLING_X2,     // Temp. oversampling
            Adafruit_BMP280::SAMPLING_X16,    // Pressure oversampling
            Adafruit_BMP280::FILTER_X16,      // Filtering
            Adafruit_BMP280::STANDBY_MS_500   // Standby time
        );
        Serial.println(F("[SensorManager] BMP280 initialized successfully at 0x76."));
    } else if (_bmp.begin(0x77)) {
        _bmpInitialized = true;
        _bmp.setSampling(
            Adafruit_BMP280::MODE_NORMAL,
            Adafruit_BMP280::SAMPLING_X2,
            Adafruit_BMP280::SAMPLING_X16,
            Adafruit_BMP280::FILTER_X16,
            Adafruit_BMP280::STANDBY_MS_500
        );
        Serial.println(F("[SensorManager] BMP280 initialized successfully at 0x77."));
    } else {
        _bmpInitialized = false;
        Serial.println(F("[SensorManager] WARNING: BMP280 not detected on I2C bus!"));
    }

    // 3. Initialize DHT22 Humidity Transducer
    if (_dht) {
        delete _dht;
    }
    _dht = new DHT(_dhtPin, DHT22);
    _dht->begin();
    _dhtInitialized = true;
    Serial.println(F("[SensorManager] DHT22 initialized."));

    return (_bmpInitialized && _dhtInitialized);
}

SensorReadings SensorManager::readSensors() {
    SensorReadings readings;
    readings.temperature_c = NAN;
    readings.pressure_hpa = NAN;
    readings.humidity_pct = NAN;
    readings.bmp_ok = false;
    readings.dht_ok = false;

    // 1. Read BMP280 (Temperature & Pressure)
    if (_bmpInitialized) {
        float t = _bmp.readTemperature();
        float p = _bmp.readPressure() / 100.0f; // Convert Pa to hPa

        if (!isnan(t) && !isnan(p) && p > 0.0f) {
            readings.temperature_c = t;
            readings.pressure_hpa = p;
            readings.bmp_ok = true;
        } else {
            Serial.println(F("[SensorManager] Failed to read valid data from BMP280."));
        }
    }

    // 2. Read DHT22 (Relative Humidity)
    if (_dhtInitialized && _dht != nullptr) {
        float h = _dht->readHumidity();

        if (!isnan(h)) {
            readings.humidity_pct = h;
            readings.dht_ok = true;
        } else {
            Serial.println(F("[SensorManager] Failed to read valid humidity from DHT22."));
        }

        // If BMP280 failed for temperature, fallback to DHT22 temperature reading
        if (isnan(readings.temperature_c)) {
            float dht_t = _dht->readTemperature();
            if (!isnan(dht_t)) {
                readings.temperature_c = dht_t;
            }
        }
    }

    return readings;
}

#endif
