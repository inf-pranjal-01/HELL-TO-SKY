# Database Consistency Attack Log

| Test ID | Action | Expected Behavior | Actual Behavior | Status |
|---|---|---|---|---|
| ATK-DB-01 | Query 10h Historical Trends | Return all 10 continuous hourly points | 10 monotonic points returned with zero dropped rows | **PASS** |
| ATK-DB-02 | Clear Replay Scratch History | Truncate only replay partitions without affecting live | Live sensor history preserved; replay scratch truncated | **PASS** |
| ATK-DB-03 | Concurrent CSV-to-DB Sync | Thread-safe upsert into TimescaleDB | Idempotent insertion without duplicate primary key collisions | **PASS** |
