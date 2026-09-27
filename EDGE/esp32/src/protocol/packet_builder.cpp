#include "packet_builder.h"
#include <stdio.h>
#include <string.h>
#include <math.h>

#ifdef ARDUINO
#include <esp_system.h>
#else
#include <stdlib.h>
#endif

void generate_uuid_v4(char* out_uuid) {
    uint32_t r0, r1, r2, r3;

#ifdef ARDUINO
    r0 = esp_random();
    r1 = esp_random();
    r2 = esp_random();
    r3 = esp_random();
#else
    r0 = (uint32_t)rand() ^ ((uint32_t)rand() << 16);
    r1 = (uint32_t)rand() ^ ((uint32_t)rand() << 16);
    r2 = (uint32_t)rand() ^ ((uint32_t)rand() << 16);
    r3 = (uint32_t)rand() ^ ((uint32_t)rand() << 16);
#endif

    uint16_t time_hi_and_version = (uint16_t)((r1 & 0x0FFF) | 0x4000);
    uint8_t clock_seq_hi = (uint8_t)(((r2 >> 24) & 0x3F) | 0x80);
    uint8_t clock_seq_low = (uint8_t)((r2 >> 16) & 0xFF);

    snprintf(
        out_uuid,
        37,
        "%08x-%04x-%04x-%02x%02x-%04x%08x",
        (unsigned int)r0,
        (unsigned int)(r1 >> 16),
        time_hi_and_version,
        clock_seq_hi,
        clock_seq_low,
        (unsigned int)(r2 & 0xFFFF),
        (unsigned int)r3
    );
}

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
) {
    if (!event_id || !station_id || !device_id || !observed_at_iso8601 ||
        !readings || !verdict || !firmware_version || !out_json || max_out_len == 0) {
        return false;
    }

    char temp_str[32];
    char pres_str[32];
    char hum_str[32];

    if (isnan(readings->temperature_c)) {
        snprintf(temp_str, sizeof(temp_str), "null");
    } else {
        snprintf(temp_str, sizeof(temp_str), "%.2f", readings->temperature_c);
    }

    if (isnan(readings->pressure_hpa)) {
        snprintf(pres_str, sizeof(pres_str), "null");
    } else {
        snprintf(pres_str, sizeof(pres_str), "%.2f", readings->pressure_hpa);
    }

    if (isnan(readings->humidity_pct)) {
        snprintf(hum_str, sizeof(hum_str), "null");
    } else {
        snprintf(hum_str, sizeof(hum_str), "%.2f", readings->humidity_pct);
    }

    char anom_type_str[64];
    if (verdict->fault_type != NULL) {
        snprintf(anom_type_str, sizeof(anom_type_str), "\"%s\"", verdict->fault_type);
    } else {
        snprintf(anom_type_str, sizeof(anom_type_str), "null");
    }

    char affected_str[64];
    if (verdict->affected_param != NULL) {
        snprintf(affected_str, sizeof(affected_str), "\"%s\"", verdict->affected_param);
    } else {
        snprintf(affected_str, sizeof(affected_str), "null");
    }

    char rssi_str[32];
    if (isnan(signal_strength_rssi) || signal_strength_rssi == 0.0f) {
        snprintf(rssi_str, sizeof(rssi_str), "null");
    } else {
        snprintf(rssi_str, sizeof(rssi_str), "%.1f", signal_strength_rssi);
    }

    int written = snprintf(
        out_json,
        max_out_len,
        "{"
        "\"event_id\":\"%s\","
        "\"station_id\":\"%s\","
        "\"device_id\":\"%s\","
        "\"observed_at\":\"%s\","
        "\"sequence_number\":%u,"
        "\"readings\":{"
        "\"temperature_c\":%s,"
        "\"pressure_hpa\":%s,"
        "\"humidity_pct\":%s"
        "},"
        "\"edge_inference\":{"
        "\"edge_status\":\"%s\","
        "\"status\":\"%s\","
        "\"decision\":\"%s\","
        "\"anomaly_flag\":%s,"
        "\"anomaly_type\":%s,"
        "\"affected_parameter\":%s,"
        "\"confidence_llr\":%.2f,"
        "\"tier_fired\":%u,"
        "\"severity\":\"%s\","
        "\"local_evidence\":\"%s\","
        "\"model_advisory\":\"%s\","
        "\"device_health\":\"%s\","
        "\"model_version\":\"%s\","
        "\"inference_method\":\"%s\""
        "},"
        "\"device_metadata\":{"
        "\"firmware_version\":\"%s\","
        "\"battery_voltage\":null,"
        "\"signal_strength\":%s"
        "}"
        "}",
        event_id,
        station_id,
        device_id,
        observed_at_iso8601,
        (unsigned int)sequence_number,
        temp_str,
        pres_str,
        hum_str,
        verdict->edge_status ? verdict->edge_status : verdict->status,
        verdict->status,
        verdict->status,
        verdict->is_anomaly ? "true" : "false",
        anom_type_str,
        affected_str,
        verdict->confidence_llr,
        (unsigned int)verdict->tier_fired,
        verdict->severity,
        verdict->local_evidence ? verdict->local_evidence : "none",
        verdict->model_advisory ? verdict->model_advisory : "none",
        verdict->device_health ? verdict->device_health : "HEALTHY",
        verdict->model_version,
        verdict->inference_method,
        firmware_version,
        rssi_str
    );

    return (written > 0 && (size_t)written < max_out_len);
}
