"""
SkyGuard AI — history_store.py: persistent, long-horizon sensor history.

============================================================================
WHY THIS FILE EXISTS (separate from state.py's short-window buffer)
============================================================================
state.py's StationBuffer._raw_rows is a ~60h in-memory deque that feeds
detect.py's rolling-window math. It is SCRATCH state, mode-scoped, and
gets wiped on every StateManager.switch_to_live() / start_replay() call
(see state.py's module docstring) -- that's the actual fix for the
replay-bleeding-into-live bug you reported.

But that means the in-memory buffer can NEVER be what the frontend reads
for "show me this sensor's last N days" or "what did this anomalous
point's suggested value look like" -- it gets thrown away exactly when
you'd want to look back at it (right after a replay run, or any time a
mode switch happens). THIS file is the answer: an append-only,
per-station CSV log that is:
  - written to on EVERY ingested reading, live or replay, tagged by a
    `source` column so the two are distinguishable after the fact
  - NEVER reset by a mode switch (only state.py's short-window buffer is)
  - capped at MAX_HISTORY_DAYS (30) via periodic trimming, so it doesn't
    grow unbounded
  - the thing get_station_history() in state.py actually reads from for
    any frontend query

============================================================================
FRONTEND HOVER-TOOLTIP GAP -- THIS IS THE FIX
============================================================================
Every row written here includes `fault_type` and one `suggested_<param>`
column per parameter (temperature_c/pressure_hpa/humidity_pct), sourced
directly from score_reading()'s verdict dict (verdict["fault_type"],
verdict["suggested_values"]). Previously these were only ever returned
to whichever caller made that ONE live ingest_reading() call -- there
was no way to re-fetch them for a past point when the frontend graph
gets a hover event on an anomaly that already scrolled off screen. Now
every retained point on disk carries both, so a hover on ANY point
within the retention window can show "what type of fault, what value
would we have used instead" without state.py needing to keep the whole
history in memory.

============================================================================
CSV vs a real database -- flagged, not decided here
============================================================================
CSV-per-station was chosen because it's zero extra infra and matches
this project's existing all-file-based data layer (data_fetch.py /
anomaly_injector.py already write plain CSVs). The real cost is trim():
enforcing the 30-day cap means reading and rewriting the whole file,
which gets linearly slower as history grows (a station logging hourly
for 30 days is ~720 rows -- fine; if this ever moves to minute-level
readings or many more stations, that stops being fine). If/when that
happens, the natural upgrade is one SQLite file (or table) per station
with an index on timestamp, so trimming is a single indexed DELETE
instead of a full rewrite, and get_recent() becomes an indexed range
query instead of a full CSV parse. Not done here -- CSV is enough for
the current 20-station, hourly-cadence scale, but this is the specific
thing to revisit first if that scale changes.
"""

import csv
import threading
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data" / "history"
# A replay dataset covers roughly three months. Retain that complete
# diagnostic window, plus the independently retained live window.
MAX_HISTORY_DAYS = 90

# How often (in appends, per station) to run the trim check. Trimming
# is a full read+rewrite of that station's CSV, so it's deliberately
# NOT done on every single append -- only checked periodically. A
# missed trim just means the file is briefly a bit over MAX_HISTORY_DAYS
# until the next check; never a correctness problem, only a size one.
TRIM_CHECK_INTERVAL = 200

RAW_PARAMS = ["temperature_c", "pressure_hpa", "humidity_pct"]

# Single source of truth for the on-disk schema -- get_recent()'s
# returned records and any frontend contract should match this exactly.
HISTORY_COLUMNS = (
    ["timestamp", "station_id"]
    + RAW_PARAMS
    + ["is_anomaly", "fault_type", "severity", "anomaly_score_pct", "decision_basis"]
    + [f"suggested_{p}" for p in RAW_PARAMS]
    + ["health_status", "source"]
)


class HistoryStore:
    """
    One append-only CSV per station under DATA_DIR. Thread-safe per
    station (a lock per station_id, not a single global lock -- writes
    to different stations should never block each other).
    """

    def __init__(self, base_dir: Path = DATA_DIR, max_days: int = MAX_HISTORY_DAYS):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.max_days = max_days
        self._locks: dict[str, threading.Lock] = {}
        self._append_counts: dict[str, int] = {}

    def _path(self, station_id: str) -> Path:
        return self.base_dir / f"{station_id}_history.csv"

    def _lock_for(self, station_id: str) -> threading.Lock:
        return self._locks.setdefault(station_id, threading.Lock())

    @staticmethod
    def _read_csv(path: Path) -> pd.DataFrame:
        """Read history with one canonical, timezone-aware timestamp type.

        Tolerates schema evolution: old files may have fewer columns than the
        current HISTORY_COLUMNS list (e.g. missing ``decision_basis``).
        Missing columns are filled with NaN so the rest of the codebase never
        sees a KeyError.  Bad/extra-field rows are silently skipped.
        """
        try:
            df = pd.read_csv(path, on_bad_lines="skip")
        except Exception:
            return pd.DataFrame(columns=HISTORY_COLUMNS)
        if df.empty or "timestamp" not in df.columns:
            return df
        # Back-fill any columns added after this CSV was written.
        for col in HISTORY_COLUMNS:
            if col not in df.columns:
                df[col] = None
        parsed = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        if parsed.isna().any():
            df = df.loc[parsed.notna()].copy()
            parsed = parsed.loc[parsed.notna()]
        df["timestamp"] = parsed
        return df

    def append(self, station_id: str, timestamp, raw_reading: dict, verdict: dict, source: str):
        """
        Writes ONE row per ingested reading (live or replay). `source`
        should be the StateManager's current mode ("live"/"replay") at
        the moment this reading was ingested -- NOT re-derived later,
        since the point is to be able to tell, after the fact, which
        mode produced which stretch of history.
        """
        suggested = verdict.get("suggested_values", {}) or {}
        row = {
            "timestamp": pd.Timestamp(timestamp).isoformat(),
            "station_id": station_id,
            **{p: raw_reading.get(p) for p in RAW_PARAMS},
            "is_anomaly": bool(verdict.get("is_anomaly", False)),
            "fault_type": verdict.get("fault_type"),
            "severity": verdict.get("severity"),
            "anomaly_score_pct": verdict.get("anomaly_score_pct"),
            "decision_basis": verdict.get("decision_basis"),
            **{f"suggested_{p}": suggested.get(p) for p in RAW_PARAMS},
            "health_status": verdict.get("health_status"),
            "source": source,
        }

        path = self._path(station_id)
        write_header = not path.exists()
        with self._lock_for(station_id):
            # Re-fetching the same Open-Meteo hourly observation after a
            # backend restart is not a new sensor event.  Keep the audit CSV
            # one row per source timestamp, while allowing replay and live
            # records at different timestamps to coexist.
            if path.exists():
                existing = pd.read_csv(path, usecols=["timestamp", "source"])
                duplicate = (
                    (existing["timestamp"].astype(str) == row["timestamp"])
                    & (existing["source"].astype(str) == source)
                )
                if duplicate.any():
                    return
            with open(path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=HISTORY_COLUMNS)
                if write_header:
                    writer.writeheader()
                writer.writerow(row)

        count = self._append_counts.get(station_id, 0) + 1
        self._append_counts[station_id] = count
        if count % TRIM_CHECK_INTERVAL == 0:
            self.trim(station_id)

    def log_health_transition(self, station_id: str, timestamp, old_state: str, new_state: str, reason: str):
        path = self.base_dir / f"{station_id}_health_events.csv"
        write_header = not path.exists()
        
        row = {
            "timestamp": pd.Timestamp(timestamp).isoformat(),
            "station_id": station_id,
            "old_state": old_state,
            "new_state": new_state,
            "reason": reason
        }
        
        with self._lock_for(station_id):
            with open(path, "a", newline="") as f:
                import csv
                writer = csv.DictWriter(f, fieldnames=["timestamp", "station_id", "old_state", "new_state", "reason"])
                if write_header:
                    writer.writeheader()
                writer.writerow(row)

    def trim(self, station_id: str):
        """
        Enforces MAX_HISTORY_DAYS independently for each source. Live
        observations and replay observations sit on different calendars;
        a 2026 live timestamp must never trim a 2025 replay audit record.
        """
        path = self._path(station_id)
        if not path.exists():
            return
        with self._lock_for(station_id):
            df = self._read_csv(path)
            if df.empty:
                return
            if "source" not in df.columns:
                cutoff = df["timestamp"].max() - pd.Timedelta(days=self.max_days)
                trimmed = df[df["timestamp"] >= cutoff]
            else:
                retained = []
                for _, source_rows in df.groupby("source", dropna=False):
                    cutoff = source_rows["timestamp"].max() - pd.Timedelta(days=self.max_days)
                    retained.append(source_rows[source_rows["timestamp"] >= cutoff])
                trimmed = pd.concat(retained, ignore_index=True) if retained else df.iloc[0:0]
            if len(trimmed) < len(df):
                trimmed.to_csv(path, index=False)

    def mark_spike(self, station_id: str, timestamp, parameter: str, suggested_value: float, source: str):
        """Retroactively annotate the original one-reading spike."""
        path = self._path(station_id)
        if not path.exists():
            return
        target = pd.to_datetime(timestamp, utc=True)
        with self._lock_for(station_id):
            df = self._read_csv(path)
            mask = (df["timestamp"] == target) & (df["source"] == source)
            if not mask.any():
                return
            df.loc[mask, "is_anomaly"] = True
            df.loc[mask, "fault_type"] = "spike"
            df.loc[mask, "severity"] = "medium"
            df.loc[mask, f"suggested_{parameter}"] = suggested_value
            df.to_csv(path, index=False)

    def get_recent(
        self,
        station_id: str,
        hours: float = 24,
        relative_to: str = "latest",
        source: str | None = None,
    ) -> pd.DataFrame:
        """
        Returns retained rows for one station as a DataFrame matching
        HISTORY_COLUMNS.

        relative_to:
          "latest" (default) -- cutoff = this station's OWN latest
            retained timestamp minus `hours`. Correct for BOTH live
            data (latest == roughly now) and replay data (latest ==
            wherever the replay run ended, which may be far from
            wall-clock now) without the caller needing to know which.
          "now" -- cutoff = wall-clock now minus `hours`. Use this only
            when you specifically want "true real-time last N hours"
            regardless of what's actually in the file (e.g. an empty
            result is meaningful here, unlike with "latest").
        """
        path = self._path(station_id)
        if not path.exists():
            return pd.DataFrame(columns=HISTORY_COLUMNS)
        df = self._read_csv(path)
        # Source filtering comes BEFORE the latest-time anchor. Live data and
        # replay data live on different calendars, so anchoring a replay view
        # against the newest live row would otherwise return an empty window.
        if source is not None and "source" in df.columns:
            df = df[df["source"] == source]
        if df.empty:
            return df
        anchor = df["timestamp"].max() if relative_to == "latest" else pd.Timestamp.now(tz="UTC")
        cutoff = anchor - pd.Timedelta(hours=hours)
        return df[df["timestamp"] >= cutoff].reset_index(drop=True)

    def get_all(self, station_id: str) -> pd.DataFrame:
        """Full retained window (up to max_days) for one station."""
        path = self._path(station_id)
        if not path.exists():
            return pd.DataFrame(columns=HISTORY_COLUMNS)
        return self._read_csv(path)

    def clear_source(self, station_id: str, source: str):
        """
        PURGES (not filters) every row tagged `source` from one
        station's persisted file, rewriting it with only the rows that
        don't match. This is a real deletion, not a query-time filter
        -- see state.py's switch_to_live() for why that distinction
        matters: replay reuses the SAME station_id keys live data
        uses, so a replay run's synthetic-anomaly rows sit in the exact
        same file live rows do. Filtering at read time would work too,
        but purging means there is no code path anywhere -- current or
        future -- that can accidentally serve a stale replay row back
        as if it were live.
        """
        path = self._path(station_id)
        if not path.exists():
            return
        with self._lock_for(station_id):
            df = self._read_csv(path)
            if df.empty or "source" not in df.columns:
                return
            remaining = df[df["source"] != source]
            if len(remaining) == len(df):
                return  # nothing tagged with this source -- nothing to do
            if remaining.empty:
                path.unlink()
            else:
                remaining.to_csv(path, index=False)

    def clear_all(self, source: str = None):
        """
        Purges `source` rows (or, if source is None, the ENTIRE file)
        across every station this store currently has a file for.
        Iterates the files on disk directly rather than requiring a
        station list from the caller, so it works even before/without
        StateManager's own station list being available.
        """
        for path in self.base_dir.glob("*_history.csv"):
            station_id = path.stem[: -len("_history")] if path.stem.endswith("_history") else path.stem
            if source is None:
                with self._lock_for(station_id):
                    path.unlink(missing_ok=True)
            else:
                self.clear_source(station_id, source)
