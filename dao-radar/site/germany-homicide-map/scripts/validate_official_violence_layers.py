#!/usr/bin/env python3
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
pks=json.loads((root/"data/pks_violent_2025.json").read_text(encoding="utf-8"))
berlin=json.loads((root/"data/berlin_violent_2025.geojson").read_text(encoding="utf-8"))

m=pks["meta"]
records=pks["records"]
assert m["year"]==2025,m
assert m["county_count"]>=400,m
assert m["matched_geometry"]>=399,m
assert len(records)>=400,len(records)
assert len(m["quantile_breaks"])==4,m
assert all(v["violence"]["rate"]>=0 for v in records.values())
assert all(k in records for k in ("11000","06412","02000")),list(records)[:10]
assert records["11000"]["state"]=="Berlin",records["11000"]
assert records["11000"]["violence"]["rate"]>300,records["11000"]

bm=berlin["meta"]
features=berlin["features"]
assert berlin["type"]=="FeatureCollection"
assert bm["year"]==2025,bm
assert bm["feature_count"]>=540,bm
assert bm["bzr_count"]>=143,bm
assert len(features)>=540,len(features)
assert len({f["properties"]["bZR"] for f in features})>=143
assert all(f["properties"]["combined_rate"]>=0 for f in features)
assert all(f.get("geometry") for f in features)

print(json.dumps({
  "pks_counties":m["county_count"],
  "pks_matched_geometry":m["matched_geometry"],
  "pks_breaks":m["quantile_breaks"],
  "berlin_plr_features":bm["feature_count"],
  "berlin_bzr_count":bm["bzr_count"],
  "berlin_breaks":bm["quantile_breaks"]
},ensure_ascii=False))
