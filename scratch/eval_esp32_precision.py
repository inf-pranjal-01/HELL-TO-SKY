import math
from pathlib import Path
import pandas as pd

ROOT_DIR = Path("c:/Users/PRANJAL TIWARI/Desktop/HELL TO SKY")

def detect_certain_faults(temp_c, pressure_hpa, humidity_pct):
    """
    ESP32 Level 1 Edge Engine - Certain Fault Classifier
    Marks CERTAIN_FAULT (is_anomaly = True) ONLY for edge-certifiable hardware faults:
    1. Electrical hardware disconnect / NaN dropout
    2. Electrical rail floor fail-low (temp <= -35, pressure <= 150, humidity < 0)
    3. Unphysical bounds (temp < -50 or > 60, pressure < 800 or > 1100, humidity > 100)
    """
    # 1. NaN / Dropout
    if temp_c is None or pressure_hpa is None or humidity_pct is None or math.isnan(temp_c) or math.isnan(pressure_hpa) or math.isnan(humidity_pct):
        return True, "dropout"

    # 2. Electrical Rail Fail-Low
    if temp_c <= -35.0 or pressure_hpa <= 150.0 or humidity_pct < 0.0:
        return True, "sensor_fail_low"

    # 3. Gross Unphysical Bounds
    if temp_c < -50.0 or temp_c > 60.0 or pressure_hpa < 800.0 or pressure_hpa > 1100.0 or humidity_pct > 100.0:
        return True, "physical_bounds"

    return False, "nominal"

def run_evaluation():
    print("=================================================================")
    print("  ESP32 Edge Inference Precision & Reliability Evaluation Engine  ")
    print("=================================================================")

    esp32_dir = ROOT_DIR / "data_esp32"
    files = list(esp32_dir.glob("*.csv"))

    print(f"Evaluating {len(files)} files in data_esp32/...")

    for csv_file in files:
        df = pd.read_csv(csv_file)
        if "is_anomaly" not in df.columns:
            continue
        
        tp, fp, fn, tn = 0, 0, 0, 0
        fp_details = []

        for idx, row in df.iterrows():
            t = float(row["temperature_c"]) if pd.notna(row.get("temperature_c")) else None
            p = float(row["pressure_hpa"]) if pd.notna(row.get("pressure_hpa")) else None
            h = float(row["humidity_pct"]) if pd.notna(row.get("humidity_pct")) else None
            
            gt_anomaly = bool(row["is_anomaly"])
            gt_fault = str(row.get("fault_type", "nominal"))
            is_edge_anomaly, edge_fault = detect_certain_faults(t, p, h)

            if is_edge_anomaly:
                if gt_anomaly:
                    tp += 1
                else:
                    fp += 1
                    fp_details.append((idx, t, p, h, edge_fault, gt_fault))
            else:
                if gt_anomaly:
                    fn += 1
                else:
                    tn += 1

        precision = (tp / (tp + fp)) * 100.0 if (tp + fp) > 0 else 100.0
        recall = (tp / (tp + fn)) * 100.0 if (tp + fn) > 0 else 0.0
        fpr = (fp / (fp + tn)) * 100.0 if (fp + tn) > 0 else 0.0

        print(f"\nResults for {csv_file.name}:")
        print(f"  * Total Observations  : {len(df)}")
        print(f"  * True Positives (TP) : {tp}")
        print(f"  * False Positives(FP) : {fp}")
        print(f"  * False Negatives(FN) : {fn} (Deferred to Central)")
        print(f"  * True Negatives (TN) : {tn}")
        print(f"  * ESP32 Precision     : {precision:.2f}%")
        print(f"  * ESP32 Recall        : {recall:.2f}%")
        print(f"  * False Positive Rate : {fpr:.4f}%")

        if fp_details:
            print(f"  FP Sample Breakdown (first 5):")
            for fp_item in fp_details[:5]:
                print(f"    Row {fp_item[0]}: T={fp_item[1]}, P={fp_item[2]}, H={fp_item[3]} -> Edge: {fp_item[4]}, GT: {fp_item[5]}")

    print("\n=================================================================")

if __name__ == "__main__":
    run_evaluation()
