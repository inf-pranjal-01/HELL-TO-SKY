import re
with open('config.py', 'r', encoding='utf-8') as f:
    content = f.read()
func = 
if "def get_station_normal_ranges" not in content:
    content += func
with open('config.py', 'w', encoding='utf-8') as f:
    f.write(content)
