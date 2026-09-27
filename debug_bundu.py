import pandas as pd
import io
from model.engine import CanonicalDecisionEngine
from model.state import StationStateManager

data = '''2025-01-01 05:00:00,10.0,979.9,93,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 06:00:00,9.9,981.1,94,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 07:00:00,12.3,981.7,85,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 08:00:00,14.3,982.5,74,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 09:00:00,16.4,982.9,64,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 10:00:00,18.8,982.4,53,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 11:00:00,21.2,981.6,42,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 12:00:00,23.0,980.3,34,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 13:00:00,24.0,979.0,30,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 14:00:00,24.2,978.1,28,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 15:00:00,24.0,977.8,27,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 16:00:00,22.3,977.9,33,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 17:00:00,18.3,977.9,43,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 18:00:00,17.2,979.3,55,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 19:00:00,16.0,980.0,63,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 20:00:00,14.7,980.4,69,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 21:00:00,13.2,980.6,75,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 22:00:00,11.9,980.8,78,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-01 23:00:00,10.9,980.7,80,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-02 00:00:00,10.2,980.3,81,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-02 01:00:00,9.7,979.7,84,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-02 02:00:00,9.2,978.8,87,AWS-RAN-103,Bundu,RAN,neighbor,False,
2025-01-02 03:00:00,9.0,978.5,88,AWS-RAN-103,Bundu,RAN,neighbor,False,'''

cols = ['timestamp', 'temperature_c', 'pressure_hpa', 'humidity_pct', 'station_id', 'station_name', 'cluster', 'role', 'is_anomaly_gt', 'extra']
df = pd.read_csv(io.StringIO(data.strip()), header=None, names=cols)

engine = CanonicalDecisionEngine()
state_manager = StationStateManager()

for idx, row in df.iterrows():
    ts = pd.to_datetime(row['timestamp'], utc=True)
    raw_reading = {
        'temperature_c': float(row['temperature_c']),
        'pressure_hpa': float(row['pressure_hpa']),
        'humidity_pct': float(row['humidity_pct'])
    }
    verdict = engine.score_reading(
        station_id='AWS-RAN-103',
        timestamp=ts,
        raw_reading=raw_reading,
        state_mgr=state_manager
    )
    print(f"{ts.strftime('%Y-%m-%d %H:%M')} | T={raw_reading['temperature_c']} | Anomaly={verdict.get('is_anomaly')} | Fault={verdict.get('fault_type')} | Score={verdict.get('anomaly_score_pct', 0.0):.1f} | Basis={verdict.get('decision_basis')}")
