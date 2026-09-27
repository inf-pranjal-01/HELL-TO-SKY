# Timestamp & Timezone Audit Report — SkyGuard AI

## Overview
Comprehensive verification of timestamp serialization, timezone offsets, and chart time continuity across all 28 AWS stations in Tamil Nadu.

### Root Cause & Fix for Historical Truncation (BUG-002)
- **Problem**: `history_store.py` read CSV rows with mixed ISO8601 timestamps (`YYYY-MM-DD HH:MM:SS+05:30` vs `YYYY-MM-DDTHH:MM:SS+05:30`). Pandas 3.0 coerced non-matching formats into `NaT`, leaving only 1 historical point in the trend array.
- **Fix**: Updated `_read_csv` in `history_store.py` to specify `format="mixed"`.
- **Verification**: Verified across all 28 stations that 10-hour history queries return full continuous curves (10 points each representing hourly readings).
- **Timezone Standardization**: All timestamps are formatted in ISO8601 with explicit Indian Standard Time (`+05:30`) offset.
