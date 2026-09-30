
import sys
import json
import time
import subprocess
from pathlib import Path
import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from model.state import StateManager
ARTIFACTS_PATH = PROJECT_ROOT / 'model_artifacts' / 'isolation_forest.pkl'
DATA_DIR = PROJECT_ROOT / "data"
PER_SENSOR_LOG_PATH = DATA_DIR / "eval_per_sensor_fault_log.csv"
def evaluate_station(args):
    station_id, df, artifact = args
    df = df.sort_values("timestamp")
    return [], []
