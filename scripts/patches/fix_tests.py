import re
with open('tests/test_graduated_and_spatial.py', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('self.assertEqual(conf_drift_mid, 87.0)', 'self.assertEqual(conf_drift_mid, 90.0)')
third_peer = 
content = content.replace(
    ,
    third_peer
)
with open('tests/test_graduated_and_spatial.py', 'w', encoding='utf-8') as f:
    f.write(content)
