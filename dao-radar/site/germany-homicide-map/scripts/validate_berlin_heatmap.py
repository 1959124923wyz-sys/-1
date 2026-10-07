#!/usr/bin/env python3
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
path=root/"data/berlin_heatmap.json"
data=json.loads(path.read_text(encoding="utf-8"))
meta=data["meta"]
windows=data["windows"]

assert meta.get("centroid_count",0)>=500, meta
for d in ("30","60","90"):
    assert d in windows, windows.keys()
    w=windows[d]
    assert w["total"]==w["bike"]+w["vehicle"], (d,w)
    assert w["active_lor"]==len(w["points"]), (d,w["active_lor"],len(w["points"]))
    assert all(52.2<=p["lat"]<=52.8 and 12.9<=p["lon"]<=13.9 for p in w["points"]), d
    assert len({p["lor"] for p in w["points"]})==len(w["points"]), d

assert windows["90"]["total"]>=windows["60"]["total"]>=windows["30"]["total"]>=1, windows
assert windows["90"]["bike"]>=500, windows["90"]
assert windows["90"]["vehicle"]>=500, windows["90"]
assert windows["90"]["total"]>=1500, windows["90"]
assert windows["90"]["active_lor"]>=100, windows["90"]

stats=meta.get("source_stats",{})
assert stats.get("bike",{}).get("raw_rows",0)>1000, stats
assert stats.get("vehicle",{}).get("raw_rows",0)>1000, stats

print(json.dumps({
  "centroids":meta["centroid_count"],
  "window30":windows["30"]["total"],
  "window60":windows["60"]["total"],
  "window90":windows["90"]["total"],
  "bike90":windows["90"]["bike"],
  "vehicle90":windows["90"]["vehicle"],
  "active_lor90":windows["90"]["active_lor"],
  "bike_raw":stats["bike"]["raw_rows"],
  "vehicle_raw":stats["vehicle"]["raw_rows"]
},ensure_ascii=False))
