#!/usr/bin/env python3
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
data=json.loads((root/"data/berlin_heatmap.json").read_text(encoding="utf-8"))
meta=data["meta"]; windows=data["windows"]

assert meta.get("centroid_count",0)>=500,meta
assert set(windows)=={"90"},windows.keys()
w=windows["90"]
assert w["total"]==w["bike"]+w["vehicle"],w
assert w["active_lor"]==len(w["points"]),(w["active_lor"],len(w["points"]))
assert all(52.2<=p["lat"]<=52.8 and 12.9<=p["lon"]<=13.9 for p in w["points"])
assert len({p["lor"] for p in w["points"]})==len(w["points"])
assert w["bike"]>=500,w
assert w["vehicle"]>=500,w
assert w["total"]>=1500,w
assert w["active_lor"]>=100,w
stats=meta.get("source_stats",{})
assert stats.get("bike",{}).get("raw_rows",0)>1000,stats
assert stats.get("vehicle",{}).get("raw_rows",0)>1000,stats
print(json.dumps({
  "centroids":meta["centroid_count"],"window90":w["total"],
  "bike90":w["bike"],"vehicle90":w["vehicle"],"active_lor90":w["active_lor"],
  "bike_raw":stats["bike"]["raw_rows"],"vehicle_raw":stats["vehicle"]["raw_rows"]
},ensure_ascii=False))
