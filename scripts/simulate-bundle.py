import json, pathlib, sys, tempfile
src=pathlib.Path.home()/ "mnemos-export.json"
raw=json.loads(src.read_text())
data=raw if "format" in raw else {"format":"mnemos-export-v1","memories":raw.get("memories",[]),"links":raw.get("links",[])}
mems=data.get("memories",[])
print(f"INPUT: {len(mems)} memories")
seen=set()
for m in mems:
    seen.add(m['id'])
print(f"Unique IDs: {len(seen)}")
sys.path.insert(0, str(pathlib.Path.home()/"mnemos-RLI"/"src"))
from mnemos.store import MemoryStore
tmp=pathlib.Path(tempfile.mktemp(suffix=".sqlite3"))
store=MemoryStore(tmp)
a,_=store.import_data(data)
print(f"1st import: {a}")
b,_=store.import_data(data)
print(f"2nd import same file (should be 0): {b}")
print(f"Final count: {len(store.list(limit=10000))} expected 640")
tmp.unlink(missing_ok=True)
