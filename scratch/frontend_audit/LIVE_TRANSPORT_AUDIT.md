# Live Transport & Streaming Audit Report — SkyGuard AI

## Transport Mechanisms
SkyGuard AI implements dual-transport live data streaming:
1. **Primary Transport**: Real-time WebSockets over `ws://localhost:8000/ws/live`.
2. **Fallback Transport**: Adaptive HTTP polling over `GET /api/current-reading?station_id=...` every 2000ms.

### Defect Remediation (BUG-003)
- **Defect**: Uvicorn server started without the optional `websockets` dependency installed in the environment, causing FastAPI WebSocket endpoints to return 404 Not Found.
- **Remediation**: Installed `websockets` library in the Python runtime environment.
- **Verification**: WebSocket handshake established at `ws://127.0.0.1:8000/ws/live` and verified live streaming of simulated and recorded sensor frames.
