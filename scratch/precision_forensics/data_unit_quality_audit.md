# Data Unit & Quality Audit Report
Generated during Path 2 — Precision Step 5

## 1. Executive Summary: Resolution of the ~135 hPa Dispersion Anomaly
In Step 4, a reported standard deviation of $\approx 135.86\text{ hPa}$ for hourly pressure movements arose from an un-partitioned diff across the entire concatenated `data/all_stations.csv` DataFrame.
Because the 28 weather stations are deployed at varying elevations across different terrains, their baseline barometric pressures differ substantially:
- **Minimum Station Mean Pressure**: 941.54 hPa
- **Maximum Station Mean Pressure**: 1012.14 hPa
- **Elevation / Baseline Offset**: 70.61 hPa

When computing raw `.diff()` across station boundaries without grouping by `station_id`, artificial boundary jumps of $50\text{ to }140\text{ hPa}$ occurred at every station boundary.

## 2. True Intra-Station Clean Movement Statistics (1-Hour Sampling)
When partitioned correctly by `station_id` with $\Delta t \le 1.5\text{ h}$:

| Parameter | Sensor Floor $\sigma_{\text{floor}}$ | Intra-Station Clean Mean $\mu(\Delta y)$ | Intra-Station Clean Std $\sigma(\Delta y)$ | 95th Percentile $|\Delta y|$ | 99th Percentile $|\Delta y|$ | Max Clean Observed $|\Delta y|$ |
|---|---|---|---|---|---|---|
| **Temperature ($^\circ\text{C}$)** | 0.52 | 0.0048 | 1.3785 | 2.90 | 3.70 | 11.50 |
| **Pressure (hPa)** | 0.87 | -0.0034 | 0.6812 | 1.30 | 1.50 | 2.60 |
| **Humidity (%)** | 1.50 | -0.0221 | 5.6421 | 12.00 | 16.00 | 51.00 |

## 3. Key Findings on Atmospheric Dynamic Scales
1. **Pressure ($\Delta P$)**:
   - Natural hourly barometric variation $\sigma(\Delta P) = 0.68\text{ hPa}$.
   - $99\%$ of all natural hourly pressure changes are under $1.50\text{ hPa}$.
   - Maximum clean natural 1h change observed is $2.60\text{ hPa}$ (during intense storm front passages).
   - The instrument quantization floor $\sigma_{\text{floor}} = 0.87\text{ hPa}$ is well aligned with single-hour atmospheric variance, but $\sigma_{\text{jump}} = \sqrt{2 \cdot 0.87^2 + 0.25} = 1.33\text{ hPa}$ was tight enough that normal $3\sigma$ weather movements occasionally tripped the $z \ge 3.0$ threshold.

2. **Temperature ($\Delta T$)**:
   - Natural hourly atmospheric variation $\sigma(\Delta T) = 1.38^\circ\text{C}$.
   - The instrument floor $\sigma_{\text{floor}} = 0.52^\circ\text{C}$ is $3\times$ smaller than diurnal atmospheric hourly rate of change ($1.38^\circ\text{C}$).
   - In the morning/evening solar transitions, $|\Delta T|$ routinely reaches $2.5\text{ to }4.0^\circ\text{C/h}$. Under the old formula $\sigma_{\text{jump}} = 0.88^\circ\text{C}$, $z_{\text{jump}} = 4.0 / 0.88 = 4.54$, triggering false positive spikes.

3. **Humidity ($\Delta RH$)**:
   - Natural hourly humidity variation $\sigma(\Delta RH) = 5.64\%$.
   - The instrument floor is $1.5\%$, while atmospheric rate of change std is $5.64\%$, and 99th percentile is $16.0\%$.

## 4. Per-Station Pressure and Elevation Distribution
Total stations audited: 28 across 7 spatial clusters.
All stations demonstrate stationary, clean intra-station distributions without corrupt unit scaling.

