# SkyGuard AI — ESP32 Level 1 Edge Node Firmware

## 1. Overview

This directory contains the production firmware for the **SkyGuard AI Level 1 Edge Node** running on the ESP32 microcontroller. The edge node is responsible for:
1. Interfacing directly with physical atmospheric transducers (BMP280 and DHT22).
2. Executing deterministic Level 1 edge inference (dropout, sensor fail-low, physical bounds).
3. Assembling and serializing canonical `ObservationPacket` JSON payloads.
4. Securely transmitting observations to the central backend via `POST /api/ingest/observation`.
5. Managing Wi-Fi connectivity, SNTP UTC time synchronization, and bounded retries.

---

## 2. Hardware Architecture & Transducer Selection

- **Microcontroller**: ESP32-WROOM-32 (Tensilica Xtensa Dual-Core 240MHz, 520KB SRAM, 4MB Flash).
- **Barometric Pressure & Temperature Sensor**: Bosch **BMP280** (I2C interface).
- **Relative Humidity & Secondary Temperature Sensor**: Aosong **DHT22 / AM2302** (Single-wire digital interface).

---

## 3. Hardware Pinout & Wiring Table

| ESP32 GPIO Pin | Sensor / Module | Sensor Pin | Description / Purpose |
|:---|:---|:---|:---|
| **GPIO 21** | BMP280 | **SDA** | I2C Serial Data (pull-up required, typically onboard BMP280 module) |
| **GPIO 22** | BMP280 | **SCL** | I2C Serial Clock |
| **GPIO 4** | DHT22 | **DATA** | Digital 1-wire bidirectional signal (4.7kΩ - 10kΩ pull-up to 3.3V) |
| **3.3V (VCC)** | BMP280 & DHT22 | **VCC / VIN** | Regulated 3.3V DC power rail |
| **GND** | BMP280 & DHT22 | **GND** | Common ground reference |

---

## 4. Project Structure

```
edge/esp32/
├── README.md               # Hardware & firmware guide (this file)
├── platformio.ini          # PlatformIO project configuration & dependencies
├── include/
│   └── config.h            # Centralized GPIO, Wi-Fi, NTP, and endpoint configuration
└── src/
    ├── main.cpp            # Application setup and continuous observation loop
    ├── edge/
    │   ├── edge_engine.h   # C/C++ Level 1 deterministic edge inference definitions
    │   └── edge_engine.cpp # Implementation of dropout, fail-low, and bounds rules
    ├── sensors/
    │   ├── sensor_manager.h# Hardware driver abstractions for BMP280 and DHT22
    │   └── sensor_manager.cpp
    ├── protocol/
    │   ├── packet_builder.h# UUIDv4 generator and canonical JSON serializer
    │   └── packet_builder.cpp
    └── network/
        ├── wifi_manager.h  # Wi-Fi link and SNTP UTC synchronization
        ├── wifi_manager.cpp
        ├── http_poster.h   # Bounded retry HTTP POST client
        └── http_poster.cpp
```

---

## 5. Configuration Guide

All deployment-specific parameters are centralized in [`include/config.h`](include/config.h):

1. **Wi-Fi Settings**:
   ```cpp
   #define WIFI_SSID "YOUR_WIFI_SSID"
   #define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
   ```

2. **Backend Server Endpoint**:
   ```cpp
   #define BACKEND_BASE_URL "http://192.168.1.100:8000"
   #define INGESTION_ENDPOINT_PATH "/api/ingest/observation"
   ```

3. **Station Identity**:
   ```cpp
   #define DEFAULT_STATION_ID "AWS-CHN-024"
   ```

---

## 6. How to Build and Flash

### Using PlatformIO (Recommended)
```bash
# Navigate to the firmware directory
cd edge/esp32

# Build the firmware
pio run

# Flash to connected ESP32 over USB/UART
pio run --target upload

# Open the serial monitor (115200 baud)
pio device monitor -b 115200
```

### Using Arduino IDE
1. Install ESP32 board support in Board Manager.
2. Install required libraries from Library Manager:
   - `Adafruit BMP280 Library`
   - `Adafruit Unified Sensor`
   - `DHT sensor library`
3. Open `src/main.cpp` or copy sources into an `.ino` sketch directory.
4. Select **ESP32 Dev Module**, set baud to **115200**, and click **Upload**.

---

## 7. Verification via Serial Monitor

On boot, the serial monitor prints diagnostic startup logs:
```
==================================================
  SkyGuard AI — ESP32 Level 1 Edge Node Firmware  
  Version: esp32_edge_v1.0.0 | Model: edge_rules_v1.0.0
==================================================
[Setup] Initializing hardware transducers...
[SensorManager] BMP280 initialized successfully at 0x76.
[SensorManager] DHT22 initialized.
[Setup] Establishing Wi-Fi connection...
[WiFi] Connected! IP address: 192.168.1.145, RSSI: -54 dBm
[NTP] Initializing UTC time synchronization via SNTP...
[NTP] Time synchronized successfully: 2026-09-23T18:00:00Z
[Setup] Hardware Device ID: esp32-node-246F2801A2B4 | Station: AWS-CHN-024
[Setup] Target Ingestion URL: http://192.168.1.100:8000/api/ingest/observation
[Setup] Level 1 Edge Node initialization complete. Starting observation loop.

[Sensor] T: 29.85 °C | P: 1012.30 hPa | RH: 64.20 %
[Edge AI] Status: ok | Flag: FALSE | Type: none
[Packet #1] Transmitting canonical payload (342 bytes)...
[HttpPoster] Success (200 OK): {"accepted":true,"event_id":"...","sequence_status":"initial",...}
```
