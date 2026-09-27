# Deployment Assumption & Environment Audit — SkyGuard AI

## Runtime Architecture
- **Backend**: FastAPI 0.115+ running on Python 3.14 with Uvicorn and WebSockets.
- **Frontend**: React 18 + Vite 5 + TypeScript in strict mode.
- **Persistence**: TimescaleDB connection with seamless automatic fallback to local CSV history store (`data/processed_tamilnadu_weather.csv`).
- **Dependencies**: All required backend packages (`fastapi`, `uvicorn`, `websockets`, `pandas`, `numpy`, `scipy`) verified.
