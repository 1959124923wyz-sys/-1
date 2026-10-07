#!/usr/bin/env python3
import json,re
from collections import Counter
from datetime import date,timedelta
from pathlib import Path

root=Path(__file__).resolve().parents[1]
data=json.loads((root/"data/cases.json").read_text(encoding="utf-8"))
cases=data["cases"]
today=date.today()
cut=today-timedelta(days=90)
allowed={"homicide","violence","robbery","sexual","property"}

assert data["meta"].get("window_days")==90, data["meta"]
assert len(cases)>=44, len(cases)
assert all(c.get("category") in allowed for c in cases), Counter(c.get("category") for c in cases)

counts=Counter(c["category"] for c in cases)
assert counts["homicide"]>=40, counts
assert counts["robbery"]>=10, counts
assert counts["sexual"]>=2, counts
assert counts["violence"]>=3, counts
assert counts["property"]>=30, counts

for c in cases:
    d=date.fromisoformat(c["event_date"])
    assert cut<=d<=today, (c["id"],c["event_date"])
    assert c.get("source_url","").startswith("https://"), c.get("id")
    city=c.get("city","")
    assert 1<len(city)<=65, (c.get("id"),city)
    assert not re.search(r"Mordkommission|Polizei|Tatverdächtig|Medieninhalte|Bild-Infos|Download",city,re.I), (c.get("id"),city)

urls=[c["source_url"] for c in cases]
dups=[u for u,n in Counter(urls).items() if n>1]
assert not dups, dups[:10]

sexual=[c for c in cases if c["category"]=="sexual"]
assert all(c.get("privacy_protected") is True for c in sexual), [c["id"] for c in sexual if not c.get("privacy_protected")]
allowed_privacy_precision={"city-privacy","district-privacy"}
assert all(c.get("precision") in allowed_privacy_precision for c in sexual), [
    (c["id"],c.get("precision")) for c in sexual if c.get("precision") not in allowed_privacy_precision
]

geocoded=sum(isinstance(c.get("lat"),(int,float)) and isinstance(c.get("lon"),(int,float)) for c in cases)
ratio=geocoded/len(cases)
assert ratio>=0.90, (geocoded,len(cases),ratio)

berlin=[c for c in cases if c.get("city")=="Berlin"]
berlin_counts=Counter(c["category"] for c in berlin)
assert berlin_counts["property"]>=1, berlin_counts
assert berlin_counts["robbery"]>=1, berlin_counts
assert berlin_counts["violence"]>=1, berlin_counts

meta_counts=data["meta"].get("category_counts",{})
assert all(meta_counts.get(k)==counts[k] for k in allowed), (meta_counts,counts)

print(json.dumps({
    "total":len(cases),
    "counts":dict(counts),
    "geocoded":geocoded,
    "geocode_ratio":round(ratio,4),
    "sexual_privacy":len(sexual),
    "duplicate_urls":len(dups),
    "berlin_total":len(berlin),
    "berlin_counts":dict(berlin_counts)
},ensure_ascii=False))
