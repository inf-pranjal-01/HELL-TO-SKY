#include "edge_engine.h"
#include "tinyml_iforest.h"
#include <string.h>
#include <math.h>

static const char* STR_SAFE_FORWARD = "SAFE_FORWARD";
static const char* STR_CERTAIN_FAULT = "CERTAIN_FAULT";
static const char* STR_DEFER_TO_CENTRAL = "DEFER_TO_CENTRAL";

static const char* STR_FAULT_NONE = "none";
static const char* STR_FAULT_DROPOUT = "dropout";
static const char* STR_FAULT_FAIL_LOW = "sensor_fail_low";
static const char* STR_FAULT_BOUNDS = "physical_bounds";
static const char* STR_FAULT_IMPOSSIBLE_JUMP = "impossible_jump";
static const char* STR_FAULT_FROZEN = "frozen_value";
static const char* STR_FAULT_SATURATION = "sensor_saturation";
static const char* STR_FAULT_TIMESTAMP = "timestamp_corruption";

static const char* STR_FAULT_MODERATE_SPIKE = "moderate_spike";
static const char* STR_FAULT_DRIFT = "drift";
static const char* STR_FAULT_MULTIVARIATE = "multivariate_inconsistency";
static const char* STR_FAULT_TINYML_ADVISORY = "tinyml_iforest_advisory";

static const char* MODEL_VERSION_STR = "skyguard_edge_v5.0.0_first_entry";
static const char* INFERENCE_METHOD_STR = "first_entry_3way_protection";

void skyguard_state_init(SkyGuardNodeState* state) {
    if (!state) return;
    memset(state, 0, sizeof(SkyGuardNodeState));
}

// ── TinyML Isolation Forest Evaluator (Shadow Evidence Only) ────────────────
static float evaluate_tinyml(const float feats[16]) {
    int16_t feats_q8[16];
    for (int i = 0; i < 16; i++) {
        float f = feats[i] * 256.0f;
        if (f > 32767.0f) f = 32767.0f;
        if (f < -32768.0f) f = -32768.0f;
        feats_q8[i] = (int16_t)f;
    }

    uint32_t total_depth = 0;
    for (int t = 0; t < TINYML_NUM_TREES; t++) {
        uint16_t cur_node = pgm_read_word(&TINYML_TREE_ROOTS[t]);
        uint8_t depth = 0;
        while (depth < 24) { // Upgraded max depth traversal up to 24 splits
            uint8_t f_idx = pgm_read_byte(&TINYML_NODES[cur_node].feature_idx);
            if (f_idx == 255) break; // Leaf
            
            int16_t thresh = (int16_t)pgm_read_word(&TINYML_NODES[cur_node].threshold_q8);
            uint16_t left_child = pgm_read_word(&TINYML_NODES[cur_node].left_child);
            uint16_t right_child = pgm_read_word(&TINYML_NODES[cur_node].right_child);

            if (feats_q8[f_idx] <= thresh) {
                cur_node = left_child;
            } else {
                cur_node = right_child;
            }
            depth++;
        }
        total_depth += depth;
    }
    return (float)total_depth / (float)TINYML_NUM_TREES;
}

SkyGuardVerdict skyguard_detect_reading(
    SkyGuardNodeState* state,
    float temp_c,
    float pressure_hpa,
    float humidity_pct,
    uint32_t current_ts_s
) {
    SkyGuardVerdict v;
    v.decision = EDGE_DECISION_SAFE_FORWARD;
    v.is_anomaly = false;
    v.status = STR_SAFE_FORWARD;
    v.edge_status = STR_SAFE_FORWARD;
    v.fault_type = STR_FAULT_NONE;
    v.affected_param = "none";
    v.severity = "nominal";
    v.confidence_llr = 0.5f;
    v.tier_fired = 5;
    v.local_evidence = "All primary sensor parameters within certified nominal bounds.";
    v.model_advisory = "none";
    v.device_health = "HEALTHY";
    v.model_version = MODEL_VERSION_STR;
    v.inference_method = INFERENCE_METHOD_STR;

    if (!state) return v;
    state->total_observations++;

    // =========================================================================
    // STEP 1: Monotonic & RTC Timestamp Integrity Check
    // =========================================================================
    if (state->has_valid_ts) {
        if (current_ts_s < state->last_valid_ts_s) {
            // Backward timestamp regression -> CERTAIN_FAULT
        v.decision = EDGE_DECISION_DEFER_TO_CENTRAL;
        v.is_anomaly = true;
        v.status = STR_DEFER_TO_CENTRAL;
        v.edge_status = STR_DEFER_TO_CENTRAL;
            v.fault_type = STR_FAULT_TIMESTAMP;
            v.affected_param = "timestamp";
            v.severity = "critical";
            v.confidence_llr = 10.0f;
            v.tier_fired = 0;
            v.local_evidence = "Timestamp regression detected (RTC rollback or corrupt system clock).";
            state->certain_fault_count++;
            return v;
        }
    }
    state->last_valid_ts_s = current_ts_s;
    state->has_valid_ts = true;

    // =========================================================================
    // STEP 2: GROUP A — Edge-Certifiable Electrical, Bounds & Dropout Checks
    // =========================================================================
    
    // 2.1 NaN / Missing Sensor Sample / Dropout
    if (isnan(temp_c) || isnan(pressure_hpa) || isnan(humidity_pct)) {
        v.decision = EDGE_DECISION_CERTAIN_FAULT;
        v.is_anomaly = true;
        v.status = STR_CERTAIN_FAULT;
        v.edge_status = STR_CERTAIN_FAULT;
        v.fault_type = STR_FAULT_DROPOUT;
        v.affected_param = isnan(temp_c) ? "temperature_c" : (isnan(pressure_hpa) ? "pressure_hpa" : "humidity_pct");
        v.severity = "critical";
        v.confidence_llr = 10.0f;
        v.tier_fired = 0;
        v.local_evidence = "Missing sensor sample / NaN ADC conversion (hardware disconnect).";
        state->certain_fault_count++;
        state->has_raw_prev = false;
        return v;
    }

    // 2.2 Electrical Rail Floor / Fail-Low
    if (temp_c <= TIER0_TEMP_FAIL_LOW || pressure_hpa <= TIER0_PRES_FAIL_LOW || humidity_pct <= TIER0_HUM_FAIL_LOW) {
        v.decision = EDGE_DECISION_DEFER_TO_CENTRAL;
        v.is_anomaly = true;
        v.status = STR_DEFER_TO_CENTRAL;
        v.edge_status = STR_DEFER_TO_CENTRAL;
        v.fault_type = STR_FAULT_FAIL_LOW;
        v.affected_param = (temp_c <= TIER0_TEMP_FAIL_LOW) ? "temperature_c" : ((pressure_hpa <= TIER0_PRES_FAIL_LOW) ? "pressure_hpa" : "humidity_pct");
        v.severity = "critical";
        v.confidence_llr = 10.0f;
        v.tier_fired = 0;
        v.local_evidence = "Electrical rail floor fail-low (Forwarded — Central SkyGuard Decides).";
        state->deferred_count++;
        state->last_raw_t = temp_c; state->last_raw_p = pressure_hpa; state->last_raw_h = humidity_pct;
        state->has_raw_prev = true;
        return v;
    }

    // 2.3 Gross Physical Bounds Violation
    if (temp_c < TIER0_TEMP_PHYS_MIN || temp_c > TIER0_TEMP_PHYS_MAX ||
        pressure_hpa < TIER0_PRES_PHYS_MIN || pressure_hpa > TIER0_PRES_PHYS_MAX ||
        humidity_pct < TIER0_HUM_PHYS_MIN || humidity_pct > TIER0_HUM_PHYS_MAX) {
        v.decision = EDGE_DECISION_DEFER_TO_CENTRAL;
        v.is_anomaly = true;
        v.status = STR_DEFER_TO_CENTRAL;
        v.edge_status = STR_DEFER_TO_CENTRAL;
        v.fault_type = STR_FAULT_BOUNDS;
        v.affected_param = (temp_c < TIER0_TEMP_PHYS_MIN || temp_c > TIER0_TEMP_PHYS_MAX) ? "temperature_c" : "pressure_hpa";
        v.severity = "high";
        v.confidence_llr = 9.5f;
        v.tier_fired = 0;
        v.local_evidence = "Gross physical limit violation (Forwarded — Central SkyGuard Decides).";
        state->deferred_count++;
        state->last_raw_t = temp_c; state->last_raw_p = pressure_hpa; state->last_raw_h = humidity_pct;
        state->has_raw_prev = true;
        return v;
    }

    // 2.4 Sensor Rail Saturation / Clipping (e.g. constant 0% or 100% RH rail)
    if (humidity_pct == 0.0f || humidity_pct == 100.0f) {
        if (state->has_raw_prev && state->last_raw_h == humidity_pct) {
        v.decision = EDGE_DECISION_DEFER_TO_CENTRAL;
        v.is_anomaly = true;
        v.status = STR_DEFER_TO_CENTRAL;
        v.edge_status = STR_DEFER_TO_CENTRAL;
            v.fault_type = STR_FAULT_SATURATION;
            v.affected_param = "humidity_pct";
            v.severity = "high";
            v.confidence_llr = 9.0f;
            v.tier_fired = 0;
            v.local_evidence = "Transducer output hard-saturated at rail boundary (0% or 100% RH).";
            state->certain_fault_count++;
            return v;
        }
    }

    // 2.5 Impossible Electrical Step Jump Discontinuity (>30°C, >50hPa, >50% in 2s)
    if (state->has_raw_prev) {
        float dt_t = fabsf(temp_c - state->last_raw_t);
        float dt_p = fabsf(pressure_hpa - state->last_raw_p);
        float dt_h = fabsf(humidity_pct - state->last_raw_h);

        if (dt_t > IMPOSSIBLE_JUMP_TEMP || dt_p > IMPOSSIBLE_JUMP_PRES || dt_h > IMPOSSIBLE_JUMP_HUM) {
        v.decision = EDGE_DECISION_DEFER_TO_CENTRAL;
        v.is_anomaly = true;
        v.status = STR_DEFER_TO_CENTRAL;
        v.edge_status = STR_DEFER_TO_CENTRAL;
            v.fault_type = STR_FAULT_IMPOSSIBLE_JUMP;
            v.affected_param = (dt_t > IMPOSSIBLE_JUMP_TEMP) ? "temperature_c" : ((dt_p > IMPOSSIBLE_JUMP_PRES) ? "pressure_hpa" : "humidity_pct");
            v.severity = "critical";
            v.confidence_llr = 10.0f;
            v.tier_fired = 0;
            v.local_evidence = "Unphysical electrical jump discontinuity (>30C or >50hPa step in 2s).";
            state->certain_fault_count++;
            state->last_raw_t = temp_c; state->last_raw_p = pressure_hpa; state->last_raw_h = humidity_pct;
            return v;
        }
    }

    // =========================================================================
    // =========================================================================
    // STEP 3: PHYSICAL TIME FREEZE TRACKING (Edge marking disabled for hourly data)
    // =========================================================================
    if (state->has_raw_prev) {
        bool is_exactly_equal = (fabsf(temp_c - state->last_raw_t) < 0.001f &&
                                 fabsf(pressure_hpa - state->last_raw_p) < 0.001f &&
                                 fabsf(humidity_pct - state->last_raw_h) < 0.001f);
        if (is_exactly_equal) {
            state->stuck_sample_count++;
        } else {
            state->stuck_sample_count = 0;
            state->stuck_start_ts_s = 0;
        }
    }

    // Update raw previous state
    state->last_raw_t = temp_c;
    state->last_raw_p = pressure_hpa;
    state->last_raw_h = humidity_pct;
    state->last_raw_ts_s = current_ts_s;
    state->has_raw_prev = true;

    // =========================================================================
    // STEP 4: GROUP B — Edge-Deferred Conditions (Advisories ONLY -> is_anomaly = false)
    // =========================================================================
    
    // 4.1 Moderate Step Spike (DEFER to Central SkyGuard for peer/weather context)
    float dt_t = fabsf(temp_c - state->last_raw_t);
    float dt_p = fabsf(pressure_hpa - state->last_raw_p);
    float dt_h = fabsf(humidity_pct - state->last_raw_h);

    if (dt_t > DEFER_SPIKE_TEMP || dt_p > DEFER_SPIKE_PRES || dt_h > DEFER_SPIKE_HUM) {
        v.decision = EDGE_DECISION_DEFER_TO_CENTRAL;
        v.is_anomaly = false;
        v.status = STR_DEFER_TO_CENTRAL;
        v.edge_status = STR_DEFER_TO_CENTRAL;
        v.fault_type = STR_FAULT_MODERATE_SPIKE;
        v.affected_param = (dt_t > DEFER_SPIKE_TEMP) ? "temperature_c" : ((dt_p > DEFER_SPIKE_PRES) ? "pressure_hpa" : "humidity_pct");
        v.severity = "nominal";
        v.confidence_llr = 1.0f;
        v.tier_fired = 2;
        v.local_evidence = "Moderate step change detected; deferred to Central SkyGuard for peer/regional arbitration.";
        v.model_advisory = "moderate_spike";
        state->deferred_count++;
        return v;
    }

    // 4.2 Thermodynamic Vapor Deficit Inconsistency (DEFER to Central)
    float t_dew = temp_c - ((100.0f - humidity_pct) / 5.0f);
    float es = 0.6112f * expf((17.67f * temp_c) / (temp_c + 243.5f));
    float vpd = es * (1.0f - (humidity_pct / 100.0f));

    if (t_dew > (temp_c + 0.5f) || (temp_c > 44.0f && humidity_pct > 60.0f) || (temp_c > 40.0f && vpd < 0.10f && humidity_pct > 85.0f)) {
        v.decision = EDGE_DECISION_DEFER_TO_CENTRAL;
        v.is_anomaly = false;
        v.status = STR_DEFER_TO_CENTRAL;
        v.edge_status = STR_DEFER_TO_CENTRAL;
        v.fault_type = STR_FAULT_MULTIVARIATE;
        v.affected_param = "temperature_c,humidity_pct";
        v.severity = "nominal";
        v.confidence_llr = 1.0f;
        v.tier_fired = 3;
        v.local_evidence = "Thermodynamic vapor deficit inconsistency; deferred to Central SkyGuard for deep model scoring.";
        v.model_advisory = "vapor_deficit_inconsistency";
        state->deferred_count++;
        return v;
    }

    // 4.3 TinyML Isolation Forest Evaluation (ADVISORY / SHADOW EVIDENCE -> DEFER)
    float dt_t_val = state->has_raw_prev ? (temp_c - state->last_raw_t) / 2.0f : 0.0f;
    float dt_p_val = state->has_raw_prev ? (pressure_hpa - state->last_raw_p) / 2.0f : 0.0f;
    float dt_h_val = state->has_raw_prev ? (humidity_pct - state->last_raw_h) / 2.0f : 0.0f;
    float t_spread = (temp_c - t_dew) / 20.0f;
    float p_ratio = dt_p_val / (pressure_hpa > 0.0f ? pressure_hpa : 1000.0f);
    float actual_vp = es * (humidity_pct / 100.0f);
    float hydro_thermal_comovement = dt_t_val * dt_h_val;

    float feats[16] = {
        temp_c / 50.0f,                       // f0: Temp normalized
        (pressure_hpa - 1000.0f) / 100.0f,     // f1: Pressure normalized
        humidity_pct / 100.0f,                // f2: Humidity normalized
        dt_t_val,                             // f3: Temperature 2s step rate
        dt_p_val,                             // f4: Pressure 2s step rate
        dt_h_val,                             // f5: Humidity 2s step rate
        vpd / 10.0f,                          // f6: Vapor pressure deficit
        t_dew / 50.0f,                        // f7: Dewpoint normalized
        t_spread,                             // f8: Temp-to-Dewpoint spread
        p_ratio * 1000.0f,                    // f9: Barometric pressure trend ratio
        es / 10.0f,                           // f10: Saturated vapor pressure
        actual_vp / 10.0f,                    // f11: Actual vapor pressure
        (temp_c - 25.0f) / 20.0f,             // f12: Temp baseline deviation
        (pressure_hpa - 1013.25f) / 50.0f,    // f13: Pressure sea-level deviation
        (humidity_pct - 50.0f) / 50.0f,       // f14: Humidity baseline deviation
        hydro_thermal_comovement              // f15: Coupled hydro-thermal co-movement
    };
    float avg_depth = evaluate_tinyml(feats);

    if (avg_depth < 3.2f) { // TinyML Isolation Forest Advisory
        v.decision = EDGE_DECISION_DEFER_TO_CENTRAL;
        v.is_anomaly = false;
        v.status = STR_DEFER_TO_CENTRAL;
        v.edge_status = STR_DEFER_TO_CENTRAL;
        v.fault_type = STR_FAULT_TINYML_ADVISORY;
        v.affected_param = "multivariate";
        v.severity = "nominal";
        v.confidence_llr = 1.0f;
        v.tier_fired = 3;
        v.local_evidence = "TinyML Isolation Forest flagged low path depth; shadow advisory deferred to Central SkyGuard.";
        v.model_advisory = "iforest_outlier";
        state->deferred_count++;
        return v;
    }

    // =========================================================================
    // STEP 5: SAFE_FORWARD — Certified Clear Observation
    // =========================================================================
    uint32_t idx = state->head;
    state->history[idx].temp_c = temp_c;
    state->history[idx].pressure_hpa = pressure_hpa;
    state->history[idx].humidity_pct = humidity_pct;
    state->history[idx].timestamp_s = current_ts_s;

    state->head = (idx + 1) & EDGE_CLEAN_BUFFER_MASK;
    if (state->count < EDGE_CLEAN_BUFFER_CAPACITY) state->count++;
    state->safe_forward_count++;

    v.decision = EDGE_DECISION_SAFE_FORWARD;
    v.is_anomaly = false;
    v.status = STR_SAFE_FORWARD;
    v.edge_status = STR_SAFE_FORWARD;
    v.fault_type = STR_FAULT_NONE;
    v.affected_param = "none";
    v.severity = "nominal";
    v.confidence_llr = 0.5f;
    v.tier_fired = 5;
    v.local_evidence = "All primary sensor parameters within certified nominal bounds.";
    v.model_advisory = "none";
    return v;
}
