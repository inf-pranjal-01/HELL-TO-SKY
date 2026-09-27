"""
Unit & Regression Test Suite for Contextual-Innovation Spike Detector
Validates the 10 required regression cases on the production detect.py implementation.
"""

import math
import numpy as np
import pandas as pd
import pytest

from model.detect import evaluate_spike_evidence, SENSOR_QUANTIZATION_FLOORS, WALD_UPPER_ALERT

def test_smooth_environmental_movement():
    # 1. Natural smooth temperature movement (0.5 C change with 0.5 C expected diurnal rate)
    llr, r, diag = evaluate_spike_evidence("temperature_c", 25.5, 25.0, 25.0, 1.5, 1.0, expected_roc=0.5)
    assert not diag["is_spike"], "Smooth natural movement must not trigger a spike"

def test_peer_agreed_pressure_front():
    # 2. Large natural pressure drop (-2.0 hPa) with all sibling peers corroborating
    llr, r, diag = evaluate_spike_evidence(
        "pressure_hpa", 1010.0, 1012.0, 1012.0, 1.0, 1.0,
        expected_roc=-0.2, sibling_peer_deltas=[-2.0, -1.9, -2.1]
    )
    assert not diag["is_spike"], "Peer-corroborated pressure front must not trigger a spike"

def test_isolated_pressure_spike():
    # 3. Large pressure jump (+8.0 hPa) isolated to target station (peers at ~0)
    llr, r, diag = evaluate_spike_evidence(
        "pressure_hpa", 1018.0, 1010.0, 1010.0, 1.0, 1.0,
        expected_roc=0.0, sibling_peer_deltas=[0.0, 0.1, -0.1]
    )
    assert diag["is_spike"], "Isolated large pressure jump must trigger a spike"

def test_strong_diurnal_heating():
    # 4. Strong morning diurnal heating (+3.0 C/h) matching expected diurnal rate
    llr, r, diag = evaluate_spike_evidence(
        "temperature_c", 28.0, 25.0, 25.0, 1.5, 1.0,
        expected_roc=2.8, sibling_peer_deltas=[2.7, 2.9, 2.8]
    )
    assert not diag["is_spike"], "Expected morning diurnal heating must not trigger a spike"

def test_strong_diurnal_drying():
    # 5. Strong afternoon humidity drop (-10%/h) matching expected psychrometric drying
    llr, r, diag = evaluate_spike_evidence(
        "humidity_pct", 50.0, 60.0, 60.0, 5.0, 1.0,
        expected_roc=-9.5, sibling_peer_deltas=[-9.0, -10.0, -9.5]
    )
    assert not diag["is_spike"], "Expected diurnal humidity drying must not trigger a spike"

def test_localized_microclimate():
    # 6. Local microclimatic swing with high peer disagreement
    llr, r, diag = evaluate_spike_evidence(
        "temperature_c", 22.0, 25.0, 25.0, 1.5, 1.0,
        expected_roc=-0.5, sibling_peer_deltas=[+1.0, -0.5, +2.0]
    )
    # Peer disagreement expands uncertainty envelope, preventing false alarm
    assert not diag["is_spike"], "Microclimatic swing under high peer dispersion should not trigger false spike"

def test_genuine_isolated_spike():
    # 7. Real electrical impulse jump (+12 C)
    llr, r, diag = evaluate_spike_evidence(
        "temperature_c", 37.0, 25.0, 25.0, 1.5, 1.0,
        expected_roc=0.5, sibling_peer_deltas=[0.4, 0.6, 0.5]
    )
    assert diag["is_spike"], "Real electrical transducer spike must trigger"

def test_spike_during_weather_front():
    # 8. Transducer spike (+10 C) occurring during cold front passage (-3 C)
    llr, r, diag = evaluate_spike_evidence(
        "temperature_c", 32.0, 25.0, 25.0, 1.5, 1.0,
        expected_roc=-3.0, sibling_peer_deltas=[-3.0, -3.1, -2.9]
    )
    assert diag["is_spike"], "Spike occurring during weather front must be detected"

def test_missing_history_cold_start():
    # 9. Cold start / missing prior reading
    llr, r, diag = evaluate_spike_evidence("temperature_c", 25.0, 25.0, None, 1.5, 1.0)
    assert not diag["is_spike"]
    assert diag.get("status") == "INSUFFICIENT_CONTEXT"

def test_irregular_dt():
    # 10. Sub-hour sampling interval (5 min = 0.083 hours)
    llr, r, diag = evaluate_spike_evidence(
        "temperature_c", 25.05, 25.0, 25.0, 1.5, 0.083, expected_roc=0.5
    )
    assert not diag["is_spike"], "5-minute normal reading must not trigger spike"
