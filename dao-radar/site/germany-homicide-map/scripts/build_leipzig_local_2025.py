#!/usr/bin/env python3
from __future__ import annotations
import io,json,re
from pathlib import Path
from city_build_common import download_bytes as get, write_geojson
from pypdf import PdfReader
from pyproj import Transformer

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/leipzig_local_2025.geojson"
PDF="https://www.polizei.sachsen.de/de/download/PKS-Atlas25_Grossstaedte.pdf"
GEO="https://static.leipzig.de/fileadmin/mediendatenbank/leipzig-de/Stadt/02.1_Dez1_Allgemeine_Verwaltung/12_Statistik_und_Wahlen/Geodaten/Ortsteile_Leipzig_UTM33N.json"

def nint(s):
    s=str(s).strip()
    if s in ("-","–","—",""): return 0
    return int(re.sub(r"[^0-9-]","",s))

def parse_city_page(text):
    rows={}
    for raw in text.splitlines():
        line=re.sub(r"\s+"," ",raw).strip()
        m=re.match(r"^(\d{2})\s+(.+)$",line)
        if not m: continue
        code,rest=m.groups()
        toks=rest.split()
        # first numeric token after the name is total cases
        j=None
        for i,t in enumerate(toks):
            if re.fullmatch(r"[\d.]+",t):
                j=i;break
        if j is None or len(toks)-j<10: continue
        name=" ".join(toks[:j])
        if "Stadtteile" in name or "insgesamt" in name.lower(): continue
        total=nint(toks[j])
        tail=toks[-9:]
        if not re.fullmatch(r"[\d.]+",tail[0]): continue
        rate=nint(tail[0])
        vals=[nint(x) for x in tail[1:]]
        if len(vals)!=8: continue
        life,sexual,rough,theft_simple,theft_aggr,fraud,other,aux=vals
        pop=round(total/rate*100000) if rate>0 else 0
        def metric(cases):
            return {"cases":cases,"rate":round(cases/pop*100000,1) if pop else None}
        rows[code]={
            "name_atlas":name,"population_est":pop,
            "crime_total":{"cases":total,"rate":float(rate)},
            "homicide":metric(life),"sexual":metric(sexual),
            "violence_proxy":metric(rough),
            "property_total":metric(theft_simple+theft_aggr),
            "simple_theft":metric(theft_simple),"aggravated_theft":metric(theft_aggr),
            "fraud":metric(fraud),"other_stgb":metric(other),"secondary_law":metric(aux)
        }
    return rows

pdf=PdfReader(io.BytesIO(get(PDF)))
text=pdf.pages[4].extract_text() or ""
rows=parse_city_page(text)
if len(rows)!=63:
    raise RuntimeError(f"expected 63 Leipzig Ortsteile, got {len(rows)} codes={sorted(rows)[:8]}..{sorted(rows)[-8:]}")

geo=json.loads(get(GEO).decode("utf-8-sig"))
tr=Transformer.from_crs(25833,4326,always_xy=True)
def tx(v):
    if isinstance(v,list) and len(v)>=2 and isinstance(v[0],(int,float)) and isinstance(v[1],(int,float)):
        x,y=tr.transform(v[0],v[1]); return [round(x,6),round(y,6)]+v[2:]
    if isinstance(v,list): return [tx(x) for x in v]
    return v

features=[];seen=set()
for f in geo.get("features",[]):
    p=f.get("properties") or {}
    code=str(p.get("OT","")).zfill(2)
    if code not in rows: continue
    props={"city":"Leipzig","state":"Sachsen","code":code,"name":p.get("Name") or rows[code]["name_atlas"],**rows[code]}
    g=f.get("geometry") or {}
    geom={"type":g.get("type"),"coordinates":tx(g.get("coordinates"))}
    features.append({"type":"Feature","id":"leipzig-"+code,"properties":props,"geometry":geom})
    seen.add(code)

if len(seen)!=63:
    raise RuntimeError(f"Leipzig geometry join incomplete: {len(seen)}/63 missing={sorted(set(rows)-seen)}")

out={"type":"FeatureCollection","meta":{
    "schema_version":1,
        "year":2025,"scope":"Leipzig Ortsteile","feature_count":len(features),"district_count":len(seen),
    "crime_source":"Polizei Sachsen: Kriminalitätsatlas 2025 – Großstädte",
    "crime_source_url":PDF,
    "geometry_source":"Stadt Leipzig Open Data: Geodaten der Ortsteile",
    "geometry_source_url":GEO,
    "note":"Local violence uses 'Rohheitsdelikte und Straftaten gegen die persönliche Freiheit' as a proxy; it is not identical to BKA Gewaltkriminalität. Population is back-calculated from the atlas total-case frequency."
},"features":features}
write_geojson(OUT,out)
print(json.dumps({"features":len(features),"sample":[f["properties"] for f in features[:3]]},ensure_ascii=False,indent=2))
