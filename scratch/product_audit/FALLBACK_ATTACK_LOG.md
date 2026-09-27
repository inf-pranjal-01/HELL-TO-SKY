# Fallback & Silent Failure Attack Log

| Test Case | Scenario | Expected Fallback | Truthful UI Representation |
|---|---|---|---|
| FB-01 | WebSocket Disconnected | Drop to HTTP Polling | Badge flips from `Live WS` to `⚡ Polling Fallback` |
| FB-02 | TimescaleDB Offline | Read from Local SSD CSV Mirror | Seamless data continuity without crashing REST API |
| FB-03 | Invalid Station ID | Return HTTP 404 | Frontend renders `EmptyState` ("No Station Selected") rather than fake data |
