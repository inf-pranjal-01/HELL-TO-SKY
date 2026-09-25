"""
Update data/anomaly_injector.py with full low-stress spike trajectories (A/B/C) and frozen modes (A/B).
"""

with open("data/anomaly_injector.py", "r", encoding="utf-8") as f:
    code = f.read()

new_spike_frozen_block = '''def inject_spike(df: pd.DataFrame, idx: int, column: str, rng: np.random.Generator):
    """
    Path 2 Low-Stress Spike Injector:
    Generates physically plausible sudden sensor discontinuities bounded above
    measurement uncertainty floor, selecting among:
      - Trajectory A: Discontinuity + progressive departure away from baseline
      - Trajectory B: Discontinuity + persistent level shift (displaced offset)
      - Trajectory C: Discontinuity + smooth exponential relaxation (voltage/thermal transient)
      - Single-point: Digital bit-flip / instant transient
    """
    mean, std, upper, lower = compute_bounds(df[column])
    low, high = HARD_PHYSICAL_LIMITS.get(column, (-np.inf, np.inf))
    
    # Bounded magnitude: 3.0 to 4.5 sigma
    magnitude = rng.uniform(3.0, 4.5)
    sign = float(rng.choice([-1.0, 1.0]))
    delta0 = sign * magnitude * max(std, 0.5)
    
    subtype = rng.choice(["single", "trajectory_a", "trajectory_b", "trajectory_c"], p=[0.25, 0.25, 0.25, 0.25])
    
    if subtype == "single":
        cand = float(df.loc[idx, column]) + delta0
        if not (low <= cand <= high):
            return None
        df.loc[idx, column] = cand
        return "spike"
        
    elif subtype == "trajectory_a":
        # Diverging departure
        tail_len = int(rng.integers(2, 5))
        end_idx = min(idx + tail_len, len(df) - 1)
        n_steps = end_idx - idx + 1
        baseline = df.loc[idx:end_idx, column].to_numpy(dtype=float)
        t = np.arange(n_steps)
        offset = delta0 * (1.0 + 0.3 * t)
        vals = baseline + offset
        if not (low <= vals[0] <= high):
            return None
        df.loc[idx:end_idx, column] = np.clip(vals, low, high)
        return "spike", idx, end_idx
        
    elif subtype == "trajectory_b":
        # Persistent level shift
        tail_len = int(rng.integers(3, 6))
        end_idx = min(idx + tail_len, len(df) - 1)
        n_steps = end_idx - idx + 1
        baseline = df.loc[idx:end_idx, column].to_numpy(dtype=float)
        vals = baseline + delta0
        if not (low <= vals[0] <= high):
            return None
        df.loc[idx:end_idx, column] = np.clip(vals, low, high)
        return "spike", idx, end_idx
        
    else:  # trajectory_c
        # Exponential return / relaxation
        tail_len = int(rng.integers(2, 5))
        end_idx = min(idx + tail_len, len(df) - 1)
        n_steps = end_idx - idx + 1
        tau = rng.uniform(0.7, 1.8)
        baseline = df.loc[idx:end_idx, column].to_numpy(dtype=float)
        t = np.arange(n_steps)
        decayed = baseline + delta0 * np.exp(-t / tau)
        if not (low <= decayed[0] <= high):
            return None
        df.loc[idx:end_idx, column] = np.clip(decayed, low, high)
        return "spike", idx, end_idx


def inject_frozen(df: pd.DataFrame, idx: int, column: str, rng: np.random.Generator):
    """
    Path 2 Low-Stress Frozen Sensor Injector:
    Supports:
      - Mode A: Exact / Quantized repeat (bit-exact hold across K=5..8 readings)
      - Mode B: Frozen + Measurement-Scale Jitter (ADC quantization noise floor walk)
    """
    freeze_length = rng.integers(5, 9)
    end_idx = min(idx + freeze_length, len(df) - 1)
    n_steps = end_idx - idx + 1
    anchor = float(df.loc[idx, column])
    
    mode = rng.choice(["mode_a_exact", "mode_b_jitter"], p=[0.4, 0.6])
    
    if mode == "mode_a_exact":
        df.loc[idx:end_idx, column] = anchor
    else:
        noise_std = ADC_NOISE_FLOOR_STD[column]
        max_dev = FROZEN_MAX_DEVIATION[column]
        walk = np.cumsum(rng.normal(0, noise_std, n_steps))
        walk = np.clip(walk, -max_dev, max_dev)
        walk[0] = 0.0
        df.loc[idx:end_idx, column] = anchor + walk
        
    clip_to_physical_limits(df, column, idx, end_idx)
    return "frozen_value", idx, end_idx
'''

# Find block to replace: from 'def inject_spike(' to 'return "frozen_value", idx, end_idx\n'
start_str = "def inject_spike("
end_str = 'return "frozen_value", idx, end_idx'
start_pos = code.find(start_str)
end_pos = code.find(end_str) + len(end_str)

if start_pos != -1 and end_pos != -1:
    code = code[:start_pos] + new_spike_frozen_block + code[end_pos:]
    with open("data/anomaly_injector.py", "w", encoding="utf-8") as f:
        f.write(code)
    print("Spike trajectories A/B/C and Frozen Modes A/B successfully patched.")
else:
    print("Could not find start/end positions in anomaly_injector.py")
