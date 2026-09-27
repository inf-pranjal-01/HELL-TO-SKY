#pragma once

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include "sensor_manager.h"
#include "edge_engine.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Generates a RFC 4122 compliant Version 4 UUID string.
 * Output buffer must be at least 37 bytes.
 */
void generate_uuid_v4(char* out_uuid);

/**
 * Serializes observation and edge telemetry into canonical JSON payload.
 */
bool build_observation_packet_json(
    const char* event_id,
    const char* station_id,
    const char* device_id,
    const char* observed_at_iso8601,
    uint32_t sequence_number,
    const SensorReadings* readings,
    const SkyGuardVerdict* verdict,
    const char* firmware_version,
    float signal_strength_rssi,
    char* out_json,
    size_t max_out_len
);

#ifdef __cplusplus
}
#endif
