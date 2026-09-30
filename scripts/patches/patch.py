with open('model/state.py', 'r') as f:
    text = f.read()
old_text =         self.history = history_store or HistoryStore()
        self.neighbor_map = {}
        for sid in metadata["station_id"]:
            cluster = metadata[metadata["station_id"] == sid]["cluster_id"].iloc[0]
            self.neighbor_map[sid] = metadata[(metadata["cluster_id"] == cluster) & (metadata["station_id"] != sid)]["station_id"].tolist()
if old_text in text:
    text = text.replace(old_text, new_text)
    print("Found and replaced block 1")
else:
    print("Block 1 not found")
old_text2 = 
new_text2 = 
if old_text2 in text:
    text = text.replace(old_text2, new_text2)
    print("Found and replaced block 2")
else:
    print("Block 2 not found")
with open('model/state.py', 'w') as f:
    f.write(text)
