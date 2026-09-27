from pathlib import Path
import pandas as pd

history_dir = Path("runtime/history")
cleaned = 0
for path in history_dir.glob("*_history.csv"):
    df = pd.read_csv(path)
    if not df.empty and "timestamp" in df.columns:
        parsed = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        # Keep replay rows or live rows with year >= 2026
        mask = (df["source"] == "replay") | (parsed.dt.year >= 2026)
        if not mask.all():
            df = df[mask]
            df.to_csv(path, index=False)
            cleaned += 1
print(f"Cleaned {cleaned} local CSV files.")
