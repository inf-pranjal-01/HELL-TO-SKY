# Stale Copy & UI Semantic Audit — SkyGuard AI

## Overview
Audit of user-facing copy, labels, tooltips, and operational status indicators across the frontend codebase.

### Identified Issues & Remediation
1. **Low-Level Database Names in UI**:
   - *Observation*: Header displayed "TimescaleDB Connected / Disconnected" even when running in resilient local CSV fallback mode.
   - *Resolution*: Updated to operational status indicator reflecting data engine readiness without leaking infrastructure vendor names.
2. **AI Confidence Terminology**:
   - *Observation*: Tooltips claimed "100% Calibrated AI Confidence" for deterministic statistical bound checks.
   - *Resolution*: Replaced with "Statistical Innovation & Residual Score" to maintain scientific rigor and avoid false certainty claims.
3. **Outlier Algorithm Discrepancy**:
   - *Observation*: Mentioned Isolation Forest scoring when Tier 1 (ROC/Bounds) and Tier 2 (SPRT Drift) detectors are active.
   - *Resolution*: Normalized terminology to reflect statistical and cross-channel sensor validation mechanisms.
