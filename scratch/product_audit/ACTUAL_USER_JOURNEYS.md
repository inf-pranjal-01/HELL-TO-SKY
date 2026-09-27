# SkyGuard AI — Actual User Journey Execution Log

## User Journey 1: Clean Startup & Multi-Station Telemetry Inspection
1. **Action**: Load `/` (DashboardPage).
2. **Observed**: Header loads `HEALTH: NORMAL`, active station `AWS-CHN-024` (Chennai), live WebSocket latency `<25ms Live WS`.
3. **Action**: Rapidly switch station selector from Chennai (`AWS-CHN-024`) to Delhi (`AWS-DEL-011`) to Mumbai (`AWS-MUM-007`).
4. **Observed**: State transitions smoothly, trend chart queries update immediately, no cross-station data bleed.

## User Journey 2: Anomaly Simulation & Replay Lifecycle
1. **Action**: Click "Start Replay" on Chennai.
2. **Observed**: Backend switches to `mode='replay'`. Simulation injects synthetic electrical spike.
3. **Observed**: Dashboard renders `CRITICAL RISK` with `100% ANOMALY SCORE` (Tier 0 fail-low short).
4. **Action**: Click "Stop Replay".
5. **Observed**: Scratch state reset, mode returns to `live`, live telemetry resumes.

## User Journey 3: Browser Refresh & Route Deep-Link Resilience
1. **Action**: Hard refresh (`Ctrl+R`) during live data streaming.
2. **Observed**: WebSocket reconnects cleanly in <200ms, station context preserved, zero backend resets.
3. **Action**: Directly access deep-link URL `/station/AWS-DEL-011`.
4. **Observed**: Station context correctly initialized from route parameter.
