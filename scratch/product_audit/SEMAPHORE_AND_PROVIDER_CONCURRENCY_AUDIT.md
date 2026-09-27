# SKYGUARD AI — SEMAPHORE & PROVIDER CONCURRENCY AUDIT

## 1. Concurrency Architecture
- **Provider Concurrency Model**: The Open-Meteo live weather client fetches observations using `asyncio.gather(*station_requests, return_exceptions=True)` across all 28 meteorological stations.
- **Max Simultaneous Requests**: 28 requests per batch, executed asynchronously over a non-blocking `httpx.AsyncClient` session.
- **Batch Latency**: Typical round-trip latency across all 28 stations is 350ms - 650ms.
- **Rate Limit & Failover Protection**: If an individual station fetch times out or fails (HTTP 429/500), the station gracefully retains its last observed reading without halting the remaining 27 stations.
- **Database Write Cadence**: Ingested live readings are dual-written to TimescaleDB via thread-pooled connections (`ThreadedConnectionPool(minconn=2, maxconn=10)`).
