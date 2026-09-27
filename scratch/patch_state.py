with open('model/state.py', 'r', encoding='utf-8') as f:
    content = f.read()

target1 = """        for p in self.health.param_status:
            self.health.param_status[p] = "WARNING"
            self.health.param_offline_reason[p] = None
            self.health._param_clean_streak[p] = 0
            self.health._param_recent_10h[p].clear()
            self.health._param_recent_24h[p].clear()"""

replacement1 = """        for p in self.health.param_status:
            self.health.param_status[p] = "WARNING"
            if hasattr(self.health, "param_offline_reason") and p in self.health.param_offline_reason:
                self.health.param_offline_reason[p] = None
            if hasattr(self.health, "_param_clean_streak") and p in self.health._param_clean_streak:
                self.health._param_clean_streak[p] = 0
            if p in self.health._param_recent_10h:
                self.health._param_recent_10h[p].clear()
            if p in self.health._param_recent_24h:
                self.health._param_recent_24h[p].clear()"""

target2 = """        for p in self.health.param_status:
            self.health.param_status[p] = "HEALTHY"
            self.health.param_offline_reason[p] = None
            self.health._param_clean_streak[p] = 0
            self.health._param_recent_10h[p].clear()
            self.health._param_recent_24h[p].clear()"""

replacement2 = """        for p in self.health.param_status:
            self.health.param_status[p] = "HEALTHY"
            if hasattr(self.health, "param_offline_reason") and p in self.health.param_offline_reason:
                self.health.param_offline_reason[p] = None
            if hasattr(self.health, "_param_clean_streak") and p in self.health._param_clean_streak:
                self.health._param_clean_streak[p] = 0
            if p in self.health._param_recent_10h:
                self.health._param_recent_10h[p].clear()
            if p in self.health._param_recent_24h:
                self.health._param_recent_24h[p].clear()"""

# Normalize line endings for replacement
norm_content = content.replace('\r\n', '\n')
norm_target1 = target1.replace('\r\n', '\n')
norm_target2 = target2.replace('\r\n', '\n')

assert norm_target1 in norm_content, "target1 not found"
assert norm_target2 in norm_content, "target2 not found"

norm_content = norm_content.replace(norm_target1, replacement1)
norm_content = norm_content.replace(norm_target2, replacement2)

# Preserve original line endings if CRLF was present
if '\r\n' in content:
    norm_content = norm_content.replace('\n', '\r\n')

with open('model/state.py', 'w', encoding='utf-8') as f:
    f.write(norm_content)

print("Successfully updated model/state.py")
