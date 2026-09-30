
with open("data/anomaly_injector.py", "r", encoding="utf-8") as f:
    code = f.read()
new_spike_frozen_block = 
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
