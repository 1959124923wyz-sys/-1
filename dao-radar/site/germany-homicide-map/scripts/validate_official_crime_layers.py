#!/usr/bin/env python3
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
national=json.loads((root/"data/germany_official_violence.json").read_text(encoding="utf-8"))
berlin=json.loads((root/"data/berlin_official_violence.geojson").read_text(encoding="utf-8"))

assert national["meta"]["year"]==2025,national["meta"]
assert national["meta"]["metric_key"]=="892000",national["meta"]
assert len(national["states"])==16,len(national["states"])
assert all(v["cases"]>0 and 50<v["hz"]<2000 for v in national["states"].values()),national["states"]

assert berlin["meta"]["year"]==2025,berlin["meta"]
assert len(berlin["features"])>=120,len(berlin["features"])
ids=[f["properties"]["bzg_id"] for f in berlin["features"]]
assert len(ids)==len(set(ids)),len(ids)
for f in berlin["features"]:
    p=f["properties"]
    assert p["robbery_hz"]>=0 and p["severe_injury_hz"]>=0,p
    assert abs(p["violence_proxy_hz"]-(p["robbery_hz"]+p["severe_injury_hz"]))<0.03,p
    assert f.get("geometry"),p["bzg_name"]

vals=sorted(v["hz"] for v in national["states"].values())
bvals=sorted(f["properties"]["violence_proxy_hz"] for f in berlin["features"])
print(json.dumps({
  "national_states":len(national["states"]),
  "national_min_hz":vals[0],
  "national_median_hz":vals[len(vals)//2],
  "national_max_hz":vals[-1],
  "berlin_regions":len(berlin["features"]),
  "berlin_proxy_min":bvals[0],
  "berlin_proxy_median":bvals[len(bvals)//2],
  "berlin_proxy_max":bvals[-1],
},ensure_ascii=False))
