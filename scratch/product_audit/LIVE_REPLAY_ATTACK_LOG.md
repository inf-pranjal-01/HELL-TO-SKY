# Live <-> Replay Attack Log

| Test ID | Action | Target Station | Peer Station | Observed Result | Status |
|---|---|---|---|---|---|
| ATK-LR-01 | Start Replay with synthetic spike | AWS-CHN-024 | AWS-DEL-011 | Target entered replay mode; Peer remained on live stream | **PASS** |
| ATK-LR-02 | Verify Database Live Table Isolation | AWS-CHN-024 | — | Synthetic replay timestamps were tagged source='replay' and never overwritten into live production tables | **PASS** |
| ATK-LR-03 | Stop Replay & Reset Buffers | AWS-CHN-024 | — | In-memory scratch deques cleared; clean live baseline restored | **PASS** |
