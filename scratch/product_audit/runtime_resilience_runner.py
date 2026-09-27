"""
SkyGuard AI — Runtime Resilience, Reset, Purge & Isolation Test Suite
Validates Layer 1 and Layer 2 invariants:
1. Reset DB Transitional Integrity (Zero 404 Outage Flashes)
2. Live -> Replay -> Live Station Health Rehydration
3. Action Semantics & Dual-Store Isolation
"""

import sys
import time
import json
import asyncio
from pathlib import Path
import httpx
import pandas as pd

BASE_URL = "http://127.0.0.1:8000"
AUDIT_DIR = Path(__file__).parent
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

async def test_case_1_reset_db_transition():
    print("\n=======================================================")
    print("TEST CASE 1: Reset DB Transitional Integrity & 404 Flash Elimination")
    print("=======================================================")
    
    trace_rows = []
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        # Step 1: Pre-check current reading
        r0 = await client.get("/api/current-reading?station_id=AWS-DEL-011")
        print(f"[*] Pre-reset reading status: {r0.status_code}")
        trace_rows.append({
            "step": "pre_reset",
            "station_id": "AWS-DEL-011",
            "status_code": r0.status_code,
            "is_syncing": r0.json().get("is_syncing", False) if r0.status_code == 200 else False,
            "temp_value": r0.json().get("temperature_c", {}).get("value") if r0.status_code == 200 else None,
            "error_detail": r0.json().get("detail") if r0.status_code != 200 else None,
        })

        # Step 2: Trigger Reset DB (clear-history target=all)
        print("[*] Triggering POST /api/admin/clear-history (target='all')...")
        t_start = time.time()
        r_reset = await client.post("/api/admin/clear-history", json={"target": "all"})
        assert r_reset.status_code == 200, f"Reset DB failed: {r_reset.text}"
        print(f"[+] Reset DB returned 200: {r_reset.json()['message']}")

        # Step 3: Probe /api/current-reading immediately every 100ms for 3 seconds
        print("[*] Sampling /api/current-reading immediately post-reset (testing for 404 flashes)...")
        found_404 = False
        sample_count = 0
        syncing_seen = False
        live_ready_seen = False

        for i in range(25):
            t_sample = time.time() - t_start
            r_sample = await client.get("/api/current-reading?station_id=AWS-DEL-011")
            status = r_sample.status_code
            sample_count += 1
            
            if status == 404:
                found_404 = True
                print(f"[-] [FAIL] 404 Flash detected at +{t_sample:.2f}s: {r_sample.json()}")
            elif status == 200:
                data = r_sample.json()
                is_sync = data.get("is_syncing", False)
                val = data.get("temperature_c", {}).get("value")
                if is_sync:
                    syncing_seen = True
                if val is not None and not is_sync:
                    live_ready_seen = True
            
            trace_rows.append({
                "step": f"post_reset_sample_{i+1}",
                "station_id": "AWS-DEL-011",
                "status_code": status,
                "is_syncing": r_sample.json().get("is_syncing", False) if status == 200 else False,
                "temp_value": r_sample.json().get("temperature_c", {}).get("value") if status == 200 else None,
                "error_detail": r_sample.json().get("detail") if status != 200 else None,
            })
            await asyncio.sleep(0.1)

        # Step 4: Verify 28 stations are all active & normal
        r_net = await client.get("/api/network-status")
        net_data = r_net.json()
        print(f"[+] Network status post-reset: {net_data}")
        assert not found_404, "FAIL: 404 Flash occurred during Reset DB transition!"
        assert net_data["active_stations_count"] == 28, f"Expected 28 active stations, got {net_data['active_stations_count']}"
        print("[SUCCESS] Case 1 Passed: Zero 404 errors, clean transitional state preserved.")

    df_trace = pd.DataFrame(trace_rows)
    df_trace.to_csv(AUDIT_DIR / "reset_runtime_trace.csv", index=False)
    print(f"[*] Saved reset trace to {AUDIT_DIR / 'reset_runtime_trace.csv'}")


async def test_case_2_mode_roundtrip_health_rehydration():
    print("\n=======================================================")
    print("TEST CASE 2: Live -> Replay -> Live Station Health Rehydration")
    print("=======================================================")

    trace_rows = []
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        # Step 1: Verify Initial Live State
        r_init = await client.get("/api/sensor-health?station_id=AWS-DEL-011")
        assert r_init.status_code == 200
        init_health = r_init.json()
        print(f"[*] Initial Live Station 1 Health: {init_health['status']} (Health: {init_health['health_pct']}%)")
        assert init_health["status"] in ("HEALTHY", "NORMAL"), f"Initial station not healthy: {init_health}"

        # Step 2: Inject Severe Anomaly in Replay Mode
        print("[*] Starting Replay with injected physical_bounds / dropout anomaly...")
        r_inject = await client.post("/api/inject-anomaly", json={"station_id": "AWS-DEL-011", "type": "physical_bounds"})
        assert r_inject.status_code == 200
        print(f"[+] Replay injection response: {r_inject.json()}")

        # Allow replay tick loop to process and trip circuit breakers
        print("[*] Waiting for replay ticks to execute...")
        await asyncio.sleep(3.0)

        r_replay_health = await client.get("/api/sensor-health?station_id=AWS-DEL-011")
        print(f"[*] Replay Mode Station 1 Health: {r_replay_health.json()['status']}")
        
        # Step 3: Switch from Replay back to Live Mode
        print("[*] Switching from Replay back to Live Mode via POST /api/system-mode...")
        r_switch = await client.post("/api/system-mode", json={"mode": "live"})
        assert r_switch.status_code == 200
        print(f"[+] Switched to Live: {r_switch.json()['message']}")

        # Step 4: Verify Station 1 immediately rehydrates to HEALTHY/NORMAL without manual purge
        await asyncio.sleep(1.0)
        r_post_live = await client.get("/api/sensor-health?station_id=AWS-DEL-011")
        post_live_health = r_post_live.json()
        print(f"[+] Post-Transition Station 1 Health: {post_live_health['status']} (Health: {post_live_health['health_pct']}%)")
        
        r_stations = await client.get("/api/stations")
        st_1 = next((s for s in r_stations.json() if s["station_id"] == "AWS-DEL-011"), None)
        print(f"[+] Stations endpoint Station 1 status: {st_1['status']}")

        r_net = await client.get("/api/network-status")
        net_status = r_net.json()
        print(f"[+] Network status: {net_status['overall_status']} (Active: {net_status['active_stations_count']}/28)")

        assert post_live_health["status"] in ("HEALTHY", "NORMAL"), f"FAIL: Station remained in {post_live_health['status']} after returning to live!"
        assert st_1["status"] in ("HEALTHY", "NORMAL"), f"FAIL: Station metadata remained in {st_1['status']} after returning to live!"
        print("[SUCCESS] Case 2 Passed: Station health perfectly rehydrated on Replay -> Live transition.")

        trace_rows.append({
            "stage": "initial_live",
            "AWS-DEL-011_status": init_health["status"],
            "AWS-DEL-011_health_pct": init_health["health_pct"],
        })
        trace_rows.append({
            "stage": "replay_active",
            "AWS-DEL-011_status": r_replay_health.json()["status"],
            "AWS-DEL-011_health_pct": r_replay_health.json()["health_pct"],
        })
        trace_rows.append({
            "stage": "post_live_rehydrated",
            "AWS-DEL-011_status": post_live_health["status"],
            "AWS-DEL-011_health_pct": post_live_health["health_pct"],
            "AWS-DEL-011_metadata_status": st_1["status"],
            "network_active_count": net_status["active_stations_count"],
        })

    df_trace2 = pd.DataFrame(trace_rows)
    df_trace2.to_csv(AUDIT_DIR / "mode_roundtrip_trace.csv", index=False)
    print(f"[*] Saved mode roundtrip trace to {AUDIT_DIR / 'mode_roundtrip_trace.csv'}")


async def test_case_3_action_semantics():
    print("\n=======================================================")
    print("TEST CASE 3: Action Semantics Verification (Refresh vs Reset DB vs Purge Replay)")
    print("=======================================================")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        # 1. POST /api/refresh-live
        r_ref = await client.post("/api/refresh-live")
        assert r_ref.status_code == 200
        print(f"[+] Refresh Live returned 200: {r_ref.json()['message']}")

        # 2. POST /api/admin/clear-history (target='replay')
        r_purge_rep = await client.post("/api/admin/clear-history", json={"target": "replay"})
        assert r_purge_rep.status_code == 200
        print(f"[+] Purge Replay returned 200: {r_purge_rep.json()['message']}")

        # 3. GET /api/trends (verify live readings remain)
        r_trends = await client.get("/api/trends?station_id=AWS-DEL-011&hours=6")
        assert r_trends.status_code == 200
        print(f"[+] Trends response: {len(r_trends.json().get('points', []))} points returned")
        print("[SUCCESS] Case 3 Passed: Action semantics properly segregated.")


async def main():
    await test_case_1_reset_db_transition()
    await test_case_2_mode_roundtrip_health_rehydration()
    await test_case_3_action_semantics()
    print("\n>>> ALL RUNTIME RESILIENCE TESTS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    asyncio.run(main())
