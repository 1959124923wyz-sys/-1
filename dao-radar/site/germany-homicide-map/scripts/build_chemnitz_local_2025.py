#!/usr/bin/env python3
from __future__ import annotations
import io,json,re
from pathlib import Path
from city_build_common import download_bytes as get, write_geojson
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/chemnitz_local_2025.geojson"
PDF="https://www.polizei.sachsen.de/de/download/PKS-Atlas25_Grossstaedte.pdf"
ARC="https://services6.arcgis.com/jiszdsDupTUO3fSM/arcgis/rest/services/Stadtteile_FL_1/FeatureServer/0/query"

def nint(s):
    s=str(s).strip()
    if s in ("-","–","—",""):return 0
    return int(re.sub(r"[^0-9-]","",s))

def parse(text):
    rows={}
    for raw in text.splitlines():
        line=re.sub(r"\s+"," ",raw).strip()
        m=re.match(r"^(\d{2})\s+(.+)$",line)
        if not m:continue
        code,rest=m.groups();t=rest.split()
        j=next((i for i,x in enumerate(t) if re.fullmatch(r"[\d.]+",x)),None)
        if j is None or len(t)-j<10:continue
        name=" ".join(t[:j])
        if "Stadtteile" in name or "insgesamt" in name.lower(): continue
        total=nint(t[j]);tail=t[-9:]
        if not re.fullmatch(r"[\d.]+",tail[0]):continue
        rate=nint(tail[0]);v=[nint(x) for x in tail[1:]]
        if len(v)!=8:continue
        life,sexual,rough,ts,ta,fraud,other,aux=v
        pop=round(total/rate*100000) if rate else 0
        def metric(c):return {"cases":c,"rate":round(c/pop*100000,1) if pop else None}
        rows[code]={
          "name_atlas":name,"population_est":pop,
          "crime_total":{"cases":total,"rate":float(rate)},
          "homicide":metric(life),"sexual":metric(sexual),"violence_proxy":metric(rough),
          "property_total":metric(ts+ta),"simple_theft":metric(ts),"aggravated_theft":metric(ta),
          "fraud":metric(fraud),"other_stgb":metric(other),"secondary_law":metric(aux)
        }
    return rows

pdf=PdfReader(io.BytesIO(get(PDF)))
rows=parse(pdf.pages[0].extract_text() or "")
if len(rows)!=39:raise RuntimeError(f"expected 39 Chemnitz Stadtteile, got {len(rows)}")

geo=json.loads(get(ARC,{"where":"1=1","outFields":"*","f":"geojson","outSR":"4326"}).decode("utf-8"))
features=[];seen=set()
for f in geo.get("features",[]):
    p=f.get("properties") or {};code=str(p.get("STADTTS","")).zfill(2)
    if code not in rows:continue
    props={"city":"Chemnitz","state":"Sachsen","code":code,"name":p.get("STADTTNAME") or rows[code]["name_atlas"],**rows[code]}
    features.append({"type":"Feature","id":"chemnitz-"+code,"properties":props,"geometry":f.get("geometry")})
    seen.add(code)
if len(seen)!=39:raise RuntimeError(f"Chemnitz geometry join incomplete {len(seen)}/39 missing={sorted(set(rows)-seen)}")

out={"type":"FeatureCollection","meta":{
    "schema_version":1,
  "year":2025,"scope":"Chemnitz Stadtteile","feature_count":len(features),"district_count":len(seen),
 "crime_source":"Polizei Sachsen: Kriminalitätsatlas 2025 – Großstädte","crime_source_url":PDF,
 "geometry_source":"Stadt Chemnitz Open Data: Stadtteile","geometry_source_url":ARC,
 "note":"Local violence uses 'Rohheitsdelikte und Straftaten gegen die persönliche Freiheit' as a proxy; it is not identical to BKA Gewaltkriminalität. Population is back-calculated from the atlas total-case frequency."
},"features":features}
write_geojson(OUT,out)
print(json.dumps({"features":len(features),"sample":[f["properties"] for f in features[:3]]},ensure_ascii=False,indent=2))
