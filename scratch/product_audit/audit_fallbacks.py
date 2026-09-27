import os

patterns = ["|| 'anomaly'", '|| "anomaly"', "?? 'anomaly'", '?? "anomaly"', "|| 'ANOMALY'", '|| "ANOMALY"', '|| "Unknown"', "|| 'Unknown'"]
for root, dirs, files in os.walk('frontend/src'):
    for f in files:
        if f.endswith(('.tsx', '.ts')):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
                for i, line in enumerate(fh):
                    for p in patterns:
                        if p in line:
                            print(f'{path}:{i+1}: {line.strip()}')
