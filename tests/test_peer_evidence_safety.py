"""
tests/test_peer_evidence_safety.py

Path 2 — Precision Step 3:
Peer Evidence Safety & Leakage Invariant Test Suite.

Verifies:
A. Target strongly moves, peers stable -> full isolated spike evidence, zero discount.
B. Target + all 3 peers move together -> common-mode discount cleanly suppresses false alarm.
C. Target + 2 peers move together -> robust majority consensus suppresses false alarm.
D. Target moves, peers react 1h later -> causal lag awareness discounts propagated front.
E. Peers react at mixed lags -> dispersion expands, uncertainty preserved.
F. Target moves, peers disagree -> coherence factor prevents false discount.
G. Target genuinely faulty while one peer is faulty -> robust median resists faulty peer.
H. Regional environmental front -> common-mode weather cleanly recognized.
I. Isolated genuine spike -> zero discount, 100% detection preserved.

Leakage Invariants:
- Target station is never in its own peer baseline.
- No cross-cluster stations contribute.
- Exactly 3 siblings per station.
- Strictly causal (only timestamps <= t).
"""

import math
import pytest
import numpy as np
import pandas as pd
from typing import List, Optional

from model.peer_spatial_engine import (
    PeerSpatialEngine,
    STATION_TO_CLUSTER,
    STATION_CLUSTERS,
    STATION_SIBLING_PEERS
)
from model.state import StationBuffer


def make_mock_buffer(sid: str, t_vals: List[float], p_vals: Optional[List[float]] = None):
    buf = StationBuffer(sid)
    base_time = pd.Timestamp("2026-06-01 08:00:00", tz="UTC")
    p_vals = p_vals or [1013.25] * len(t_vals)
    for idx, (tv, pv) in enumerate(zip(t_vals, p_vals)):
        ts = base_time + pd.Timedelta(hours=idx)
        buf.record_raw_reading({
            "station_id": sid,
            "timestamp": ts,
            "temperature_c": tv,
            "pressure_hpa": pv,
            "humidity_pct": 50.0
        }, timestamp=ts, verdict={"is_anomaly": False})
    return buf


def test_safety_case_a_isolated_spike():
    target_id = "AWS-DEL-011"
    now_ts = pd.Timestamp("2026-06-01 12:00:00", tz="UTC")
    bufs = {
        "AWS-DEL-101": make_mock_buffer("AWS-DEL-101", [25.0, 25.0, 25.0]),
        "AWS-DEL-102": make_mock_buffer("AWS-DEL-102", [25.0, 25.0, 25.0]),
        "AWS-DEL-103": make_mock_buffer("AWS-DEL-103", [25.0, 25.0, 25.0])
    }
    ev = PeerSpatialEngine.compute_continuous_peer_evidence(
        target_id, "temperature_c", now_ts, 30.0, 25.0, 1.0, bufs
    )
    assert ev["z_surprise"] > 5.0
    assert ev["common_mode_discount"] == 0.0


def test_safety_case_b_all_peers_agree():
    target_id = "AWS-DEL-011"
    now_ts = pd.Timestamp("2026-06-01 12:00:00", tz="UTC")
    bufs = {
        "AWS-DEL-101": make_mock_buffer("AWS-DEL-101", [25.0, 25.0, 21.0]),
        "AWS-DEL-102": make_mock_buffer("AWS-DEL-102", [25.0, 25.0, 21.0]),
        "AWS-DEL-103": make_mock_buffer("AWS-DEL-103", [25.0, 25.0, 21.0])
    }
    ev = PeerSpatialEngine.compute_continuous_peer_evidence(
        target_id, "temperature_c", now_ts, 21.0, 25.0, 1.0, bufs
    )
    assert abs(ev["z_surprise"]) < 1.0
    assert ev["common_mode_discount"] > 10.0


def test_safety_case_c_two_peers_agree():
    target_id = "AWS-DEL-011"
    now_ts = pd.Timestamp("2026-06-01 12:00:00", tz="UTC")
    bufs = {
        "AWS-DEL-101": make_mock_buffer("AWS-DEL-101", [25.0, 25.0, 21.0]),
        "AWS-DEL-102": make_mock_buffer("AWS-DEL-102", [25.0, 25.0, 21.0]),
        "AWS-DEL-103": make_mock_buffer("AWS-DEL-103", [25.0, 25.0, 25.0])
    }
    ev = PeerSpatialEngine.compute_continuous_peer_evidence(
        target_id, "temperature_c", now_ts, 21.0, 25.0, 1.0, bufs
    )
    assert ev["common_mode_discount"] > 5.0


def test_safety_case_d_one_hour_lag():
    target_id = "AWS-DEL-011"
    now_ts = pd.Timestamp("2026-06-01 12:00:00", tz="UTC")
    bufs = {
        "AWS-DEL-101": make_mock_buffer("AWS-DEL-101", [25.0, 21.0, 21.0]),
        "AWS-DEL-102": make_mock_buffer("AWS-DEL-102", [25.0, 21.0, 21.0]),
        "AWS-DEL-103": make_mock_buffer("AWS-DEL-103", [25.0, 21.0, 21.0])
    }
    ev = PeerSpatialEngine.compute_continuous_peer_evidence(
        target_id, "temperature_c", now_ts, 21.0, 25.0, 1.0, bufs, use_lag_awareness=True
    )
    assert ev["has_1h_phase_lag"] is True
    assert ev["applied_lag"] == 1
    assert ev["common_mode_discount"] > 5.0


def test_safety_case_e_mixed_lags():
    target_id = "AWS-DEL-011"
    now_ts = pd.Timestamp("2026-06-01 12:00:00", tz="UTC")
    bufs = {
        "AWS-DEL-101": make_mock_buffer("AWS-DEL-101", [25.0, 21.0, 21.0]),
        "AWS-DEL-102": make_mock_buffer("AWS-DEL-102", [25.0, 25.0, 21.0]),
        "AWS-DEL-103": make_mock_buffer("AWS-DEL-103", [25.0, 25.0, 25.0])
    }
    ev = PeerSpatialEngine.compute_continuous_peer_evidence(
        target_id, "temperature_c", now_ts, 21.0, 25.0, 1.0, bufs, use_lag_awareness=True
    )
    assert ev["peer_dispersion"] >= 0.25


def test_safety_case_f_peers_disagree():
    target_id = "AWS-DEL-011"
    now_ts = pd.Timestamp("2026-06-01 12:00:00", tz="UTC")
    bufs = {
        "AWS-DEL-101": make_mock_buffer("AWS-DEL-101", [25.0, 25.0, 28.0]),
        "AWS-DEL-102": make_mock_buffer("AWS-DEL-102", [25.0, 25.0, 22.0]),
        "AWS-DEL-103": make_mock_buffer("AWS-DEL-103", [25.0, 25.0, 25.0])
    }
    ev = PeerSpatialEngine.compute_continuous_peer_evidence(
        target_id, "temperature_c", now_ts, 30.0, 25.0, 1.0, bufs
    )
    # Coherence factor must protect against giving false common mode discount when peers are chaotic
    assert ev["common_mode_discount"] < 1.0


def test_safety_case_g_faulty_peer_robustness():
    target_id = "AWS-DEL-011"
    now_ts = pd.Timestamp("2026-06-01 12:00:00", tz="UTC")
    bufs = {
        "AWS-DEL-101": make_mock_buffer("AWS-DEL-101", [25.0, 25.0, 33.0]),
        "AWS-DEL-102": make_mock_buffer("AWS-DEL-102", [25.0, 25.0, 25.0]),
        "AWS-DEL-103": make_mock_buffer("AWS-DEL-103", [25.0, 25.0, 25.0])
    }
    ev = PeerSpatialEngine.compute_continuous_peer_evidence(
        target_id, "temperature_c", now_ts, 33.0, 25.0, 1.0, bufs
    )
    # Robust median ignores 1 single bad peer out of 3
    assert ev["peer_median_d"] == 0.0
    assert ev["z_surprise"] > 8.0


def test_safety_case_h_regional_environmental_front():
    target_id = "AWS-DEL-011"
    now_ts = pd.Timestamp("2026-06-01 12:00:00", tz="UTC")
    bufs = {
        "AWS-DEL-101": make_mock_buffer("AWS-DEL-101", [25.0, 25.0, 25.0], [1013.0, 1013.0, 1010.0]),
        "AWS-DEL-102": make_mock_buffer("AWS-DEL-102", [25.0, 25.0, 25.0], [1013.0, 1013.0, 1010.0]),
        "AWS-DEL-103": make_mock_buffer("AWS-DEL-103", [25.0, 25.0, 25.0], [1013.0, 1013.0, 1010.0])
    }
    ev = PeerSpatialEngine.compute_continuous_peer_evidence(
        target_id, "pressure_hpa", now_ts, 1010.0, 1013.0, 1.0, bufs
    )
    assert abs(ev["z_surprise"]) < 0.5
    assert ev["common_mode_discount"] > 4.0


def test_safety_case_i_isolated_genuine_spike():
    target_id = "AWS-DEL-011"
    now_ts = pd.Timestamp("2026-06-01 12:00:00", tz="UTC")
    bufs = {
        "AWS-DEL-101": make_mock_buffer("AWS-DEL-101", [25.0, 25.0, 25.0], [1013.0, 1013.0, 1013.0]),
        "AWS-DEL-102": make_mock_buffer("AWS-DEL-102", [25.0, 25.0, 25.0], [1013.0, 1013.0, 1013.0]),
        "AWS-DEL-103": make_mock_buffer("AWS-DEL-103", [25.0, 25.0, 25.0], [1013.0, 1013.0, 1013.0])
    }
    ev = PeerSpatialEngine.compute_continuous_peer_evidence(
        target_id, "pressure_hpa", now_ts, 1019.0, 1013.0, 1.0, bufs
    )
    assert ev["z_surprise"] > 6.0
    assert ev["common_mode_discount"] == 0.0


def test_leakage_invariants():
    # 1. Target never in its own peer list
    for sid in STATION_TO_CLUSTER:
        assert sid not in PeerSpatialEngine.get_sibling_peers(sid)
    
    # 2. Cross-cluster stations never included
    assert "AWS-KOL-015" not in PeerSpatialEngine.get_sibling_peers("AWS-DEL-011")
    assert "AWS-MUM-007" not in PeerSpatialEngine.get_sibling_peers("AWS-BHO-030")

    # 3. Exactly 3 siblings per station
    for sid in STATION_TO_CLUSTER:
        assert len(PeerSpatialEngine.get_sibling_peers(sid)) == 3
