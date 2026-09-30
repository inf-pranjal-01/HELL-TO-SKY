
from __future__ import annotations
TEMP_PHYSICAL_MIN    = -50.0
TEMP_PHYSICAL_MAX    = 60.0
PRESSURE_PHYSICAL_MIN = 870.0
PRESSURE_PHYSICAL_MAX = 1085.0
HUMIDITY_PHYSICAL_MIN = 0.0
HUMIDITY_PHYSICAL_MAX = 100.0
TEMP_FAIL_LOW     = -8.0
PRESSURE_FAIL_LOW = 150.0
HUMIDITY_FAIL_LOW = 3.0
class EdgeVerdict:
    __slots__ = ("flag", "fault_type", "affected", "reason")
    def __init__(self, flag: bool, fault_type: str, affected: list, reason: str):
        self.flag = flag
        self.fault_type = fault_type
        self.affected = affected
        self.reason = reason
    def __repr__(self):
        return (
            f"EdgeVerdict(flag={self.flag}, fault_type={self.fault_type!r}, "
            f"affected={self.affected!r}, reason={self.reason!r})"
        )
def check_reading_edge(
    temp_c: float | None,
    pressure_hpa: float | None,
    humidity_pct: float | None,
) -> EdgeVerdict:
    affected = []
    reasons  = []
    if temp_c is None or temp_c != temp_c:
        affected.append("temperature_c")
        reasons.append("temperature missing/NaN")
    if pressure_hpa is None or pressure_hpa != pressure_hpa:
        affected.append("pressure_hpa")
        reasons.append("pressure missing/NaN")
    if humidity_pct is None or humidity_pct != humidity_pct:
        affected.append("humidity_pct")
        reasons.append("humidity missing/NaN")
    if affected:
        return EdgeVerdict(
            flag=True,
            fault_type="dropout",
            affected=affected,
            reason="; ".join(reasons),
        )
    fail_low_affected = []
    fail_low_reasons  = []
    if temp_c <= TEMP_FAIL_LOW:
        fail_low_affected.append("temperature_c")
        fail_low_reasons.append(f"temp {temp_c:.1f}°C <= fail-low floor {TEMP_FAIL_LOW}°C")
    if pressure_hpa <= PRESSURE_FAIL_LOW:
        fail_low_affected.append("pressure_hpa")
        fail_low_reasons.append(f"pressure {pressure_hpa:.1f} hPa <= fail-low floor {PRESSURE_FAIL_LOW} hPa")
    if humidity_pct <= HUMIDITY_FAIL_LOW:
        fail_low_affected.append("humidity_pct")
        fail_low_reasons.append(f"humidity {humidity_pct:.1f}% <= fail-low floor {HUMIDITY_FAIL_LOW}%")
    if fail_low_affected:
        return EdgeVerdict(
            flag=True,
            fault_type="sensor_fail_low",
            affected=fail_low_affected,
            reason="; ".join(fail_low_reasons),
        )
    pb_affected = []
    pb_reasons  = []
    if not (TEMP_PHYSICAL_MIN <= temp_c <= TEMP_PHYSICAL_MAX):
        pb_affected.append("temperature_c")
        pb_reasons.append(
            f"temp {temp_c:.1f}°C outside [{TEMP_PHYSICAL_MIN}, {TEMP_PHYSICAL_MAX}]°C"
        )
    if not (PRESSURE_PHYSICAL_MIN <= pressure_hpa <= PRESSURE_PHYSICAL_MAX):
        pb_affected.append("pressure_hpa")
        pb_reasons.append(
            f"pressure {pressure_hpa:.1f} hPa outside [{PRESSURE_PHYSICAL_MIN}, {PRESSURE_PHYSICAL_MAX}] hPa"
        )
    if not (HUMIDITY_PHYSICAL_MIN <= humidity_pct <= HUMIDITY_PHYSICAL_MAX):
        pb_affected.append("humidity_pct")
        pb_reasons.append(
            f"humidity {humidity_pct:.1f}% outside [{HUMIDITY_PHYSICAL_MIN}, {HUMIDITY_PHYSICAL_MAX}]%"
        )
    if pb_affected:
        return EdgeVerdict(
            flag=True,
            fault_type="physical_bounds",
            affected=pb_affected,
            reason="; ".join(pb_reasons),
        )
    return EdgeVerdict(
        flag=False,
        fault_type="",
        affected=[],
        reason="Reading within physical bounds — forward to server for full analysis.",
    )
if __name__ == "__main__":
    tests = [
        (25.0, 1013.0, 65.0,   False, "",               "Normal reading"),
        (None, 1013.0, 65.0,   True,  "dropout",        "Dropout (temp None)"),
        (25.0, None,   65.0,   True,  "dropout",        "Dropout (pressure None)"),
        (-40.0, 0.0,   0.0,   True,  "sensor_fail_low", "Fail-low (all rail)"),
        (-40.0, 1013.0, 65.0, True,  "sensor_fail_low", "Fail-low (temp rail)"),
        (99.0, 1013.0, 65.0,  True,  "physical_bounds", "Physical bounds (temp > 60)"),
        (25.0, 500.0,  65.0,  True,  "physical_bounds", "Physical bounds (pressure < 870)"),
        (25.0, 1013.0, 105.0, True,  "physical_bounds", "Physical bounds (humidity > 100)"),
    ]
    all_pass = True
    for temp, pressure, humidity, exp_flag, exp_fault, label in tests:
        v = check_reading_edge(temp, pressure, humidity)
        ok = (v.flag == exp_flag) and (v.fault_type == exp_fault)
        status = "PASS" if ok else f"FAIL (got flag={v.flag} fault={v.fault_type!r})"
        print(f"  {status:6} | {label}")
        all_pass = all_pass and ok
    print()
    print("edge_rules self-test: ALL PASS" if all_pass else "edge_rules self-test: SOME FAILURES")
