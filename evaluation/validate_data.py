
import pandas as pd
import numpy as np
from pathlib import Path
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PHYSICAL_BOUNDS = {
    "temperature_c": (-10.0, 55.0),
    "pressure_hpa": (850.0, 1080.0),
    "humidity_pct": (0.0, 100.0),
}
MAX_INTERPOLATABLE_GAP = 3
def validate_station(df: pd.DataFrame, station_id: str) -> tuple[pd.DataFrame, dict]:
    report = {"station_id": station_id, "issues": []}
    df = df.copy()
    n_before = len(df)
    df = df.drop_duplicates(subset="timestamp", keep="first")
    n_dupes = n_before - len(df)
    if n_dupes > 0:
        report["issues"].append(f"{n_dupes} duplicate timestamp rows dropped")
    df = df.sort_values("timestamp").reset_index(drop=True)
    full_range = pd.date_range(df["timestamp"].min(), df["timestamp"].max(), freq="h")
    missing_count = len(full_range) - len(df)
    if missing_count > 0:
        report["issues"].append(f"{missing_count} missing hourly timestamps in sequence (reindexed, left as NaN for step 3)")
        df = df.set_index("timestamp").reindex(full_range).rename_axis("timestamp").reset_index()
    for col in ["temperature_c", "pressure_hpa", "humidity_pct"]:
        n_nan = df[col].isna().sum()
        if n_nan > 0:
            is_na = df[col].isna()
            run_lengths = is_na.groupby((~is_na).cumsum()).sum()
            max_run = run_lengths.max() if len(run_lengths) else 0
            if max_run <= MAX_INTERPOLATABLE_GAP:
                df[col] = df[col].interpolate(method="linear", limit=MAX_INTERPOLATABLE_GAP)
                report["issues"].append(f"{col}: {n_nan} NaNs, longest gap {max_run}h -> linearly interpolated")
            else:
                report["issues"].append(
                    f"{col}: {n_nan} NaNs, longest gap {max_run}h -- EXCEEDS auto-fill threshold, "
                    f"left as NaN, needs manual review"
                )
    for col, (low, high) in PHYSICAL_BOUNDS.items():
        out_of_bounds = df[(df[col] < low) | (df[col] > high)]
        if len(out_of_bounds) > 0:
            report["issues"].append(
                f"{col}: {len(out_of_bounds)} rows outside physical bounds ({low}, {high}) -- NEEDS MANUAL REVIEW, not auto-fixed"
            )
    if not report["issues"]:
        report["issues"].append("clean -- no issues found")
    return df, report
def main():
    reports = []
    for csv_path in sorted(DATA_DIR.glob("AWS-*.csv")):
        if "_labeled" in csv_path.name:
            continue
        station_id = csv_path.stem
        df = pd.read_csv(csv_path, parse_dates=["timestamp"])
        cleaned_df, report = validate_station(df, station_id)
        reports.append(report)
        cleaned_df.to_csv(csv_path, index=False)
    print(f"{'Station':<16} Issues")
    print("-" * 70)
    for r in reports:
        for issue in r["issues"]:
            print(f"{r['station_id']:<16} {issue}")
    needs_review = [r for r in reports if any("MANUAL REVIEW" in i for i in r["issues"])]
    if needs_review:
        print(f"\n[WARNING] {len(needs_review)} station(s) have issues that need your manual review before training.")
    else:
        print(f"\n[OK] All {len(reports)} stations passed validation (or were safely auto-repaired).")
if __name__ == "__main__":
    main()
