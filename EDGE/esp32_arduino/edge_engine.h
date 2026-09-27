#pragma once

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <math.h>

#ifdef __cplusplus
extern "C" {
#endif

// =============================================================================
// SKYGUARD AI — HIGH-CONFIDENCE FIRST-ENTRY EDGE PROTECTION LAYER (ESP32 C/C++)
// ARCHITECTURAL PARADIGM: 3-WAY DECISION ENGINE (CERTAIN_FAULT | SAFE_FORWARD | DEFER_TO_CENTRAL)
// =============================================================================

#define EDGE_CLEAN_BUFFER_CAPACITY 512
#define EDGE_CLEAN_BUFFER_MASK (EDGE_CLEAN_BUFFER_CAPACITY - 1)

// --- Tier 0 Electrical Fail-Low / Rail Floors ---
#define TIER0_TEMP_FAIL_LOW -35.0f
#define TIER0_PRES_FAIL_LOW 150.0f
#define TIER0_HUM_FAIL_LOW  0.0f

// --- Gross Physical Limits ---
#define TIER0_TEMP_PHYS_MIN -50.0f
#define TIER0_TEMP_PHYS_MAX 60.0f
#define TIER0_PRES_PHYS_MIN 800.0f
#define TIER0_PRES_PHYS_MAX 1100.0f
#define TIER0_HUM_PHYS_MIN  0.0f
#define TIER0_HUM_PHYS_MAX  100.0f

// --- Electrical Impossible Step Jumps (2s interval) ---
#define IMPOSSIBLE_JUMP_TEMP 30.0f  // >30°C in 2s
#define IMPOSSIBLE_JUMP_PRES 50.0f  // >50 hPa in 2s
#define IMPOSSIBLE_JUMP_HUM  50.0f  // >50% RH in 2s

// --- Moderate Step Jump Thresholds (Deferred to Central) ---
#define DEFER_SPIKE_TEMP 4.0f       // 4.0°C step jump -> DEFER_TO_CENTRAL
#define DEFER_SPIKE_PRES 6.0f       // 6.0 hPa step jump -> DEFER_TO_CENTRAL
#define DEFER_SPIKE_HUM  20.0f      // 20.0% RH step jump -> DEFER_TO_CENTRAL

// --- Physical Time Freeze Threshold ---
#define FREEZE_DURATION_THRESHOLD_S 3600  // 3600 physical seconds (1 hour) of zero variance required for CERTAIN_FAULT

typedef enum {
    EDGE_DECISION_SAFE_FORWARD = 0,     // Clear / certified normal -> transmit as normal observation
    EDGE_DECISION_CERTAIN_FAULT = 1,    // Certifiable fault -> local quarantine / fault report
    EDGE_DECISION_DEFER_TO_CENTRAL = 2  // Ambiguous / context-dependent -> forward to Central SkyGuard
} EdgeDecision;

typedef enum {
    FAULT_NONE = 0,
    FAULT_DROPOUT,              // Missing / NaN sample
    FAULT_FAIL_LOW,             // Electrical rail floor (-35°C / 150hPa / 0% RH)
    FAULT_PHYSICAL_BOUNDS,      // Gross physical range violation
    FAULT_IMPOSSIBLE_JUMP,      // Electrical step jump discontinuity
    FAULT_FROZEN_STUCK,         // Long-duration physical zero-variance freeze
    FAULT_SENSOR_DISCONNECT,    // Transducer disconnection
    FAULT_SATURATION,           // Constant ADC saturation (0% or 100% RH rail)
    FAULT_TIMESTAMP_CORRUPT,    // Monotonic regression or invalid RTC timestamp
    FAULT_MODERATE_SPIKE,       // DEFER: Moderate step jump (requires peer/temporal context)
    FAULT_DRIFT_SUSPECTED,      // DEFER: Slow calibration drift
    FAULT_MULTIVARIATE_DEFER,   // DEFER: Vapor deficit / thermodynamic inconsistency
    FAULT_TINYML_ADVISORY       // DEFER: Isolation Forest advisory
} SkyGuardFaultType;

typedef struct __attribute__((aligned(4))) {
    float temp_c;
    float pressure_hpa;
    float humidity_pct;
    uint32_t timestamp_s;
} CleanSample;

typedef struct __attribute__((aligned(4))) {
    // 1. Physical Time Freeze Tracking
    float last_raw_t;
    float last_raw_p;
    float last_raw_h;
    uint32_t last_raw_ts_s;
    uint32_t stuck_start_ts_s;
    uint32_t stuck_sample_count;
    bool has_raw_prev;

    // 2. Monotonic Timestamp State
    uint32_t last_valid_ts_s;
    bool has_valid_ts;

    // 3. Ring Buffer for Local Windowing
    CleanSample history[EDGE_CLEAN_BUFFER_CAPACITY];
    uint32_t head;
    uint32_t count;

    // 4. Device Health Metrics
    uint32_t total_observations;
    uint32_t certain_fault_count;
    uint32_t deferred_count;
    uint32_t safe_forward_count;
    uint8_t boot_reason_code;      // 0=PowerOn, 1=Watchdog, 2=Brownout
} SkyGuardNodeState;

typedef struct {
    EdgeDecision decision;        // EDGE_DECISION_SAFE_FORWARD | CERTAIN_FAULT | DEFER_TO_CENTRAL
    bool is_anomaly;              // true if CERTAIN_FAULT or DEFER_TO_CENTRAL advisory
    const char* status;           // "SAFE_FORWARD" | "CERTAIN_FAULT" | "DEFER_TO_CENTRAL"
    const char* edge_status;      // "SAFE_FORWARD" | "CERTAIN_FAULT" | "DEFER_TO_CENTRAL"
    const char* fault_type;       // Canonical string name or "none"
    const char* affected_param;   // Affected parameter string
    const char* severity;         // "nominal", "low", "medium", "high", "critical"
    float confidence_llr;         // Confidence score
    uint8_t tier_fired;           // 0=Electrical/Bounds, 1=Physical Freeze, 2=Step Jump, 3=TinyML Advisory, 4=Thermodynamic Defer, 5=Nominal
    const char* local_evidence;   // Direct explanation string
    const char* model_advisory;   // "none" | "iforest_outlier" | "vapor_deficit_inconsistency" | "moderate_spike"
    const char* device_health;    // "HEALTHY" | "BROWNOUT_WARNING" | "WATCHDOG_RESET"
    const char* model_version;
    const char* inference_method;
} SkyGuardVerdict;

void skyguard_state_init(SkyGuardNodeState* state);

SkyGuardVerdict skyguard_detect_reading(
    SkyGuardNodeState* state,
    float temp_c,
    float pressure_hpa,
    float humidity_pct,
    uint32_t current_timestamp_s
);

#ifdef __cplusplus
}
#endif
