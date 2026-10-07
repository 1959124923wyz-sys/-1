#!/usr/bin/env python3
from __future__ import annotations
import io,json,re,zipfile
from datetime import datetime,timezone
from pathlib import Path
import requests
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/hamburg_local_2025.geojson"
PDF="https://daten.transparenz.hamburg.de/Dataport.HmbTG.ZS.Webservice.GetRessource100/GetRessource100.svc/8c90d027-c52d-45f4-8bdc-d3e2dde784e6/Upload__Stadtteilatlas-pks-2025_do.PDF"
GEOZIP="https://archiv.transparenz.hamburg.de/hmbtgarchive/HMDK/regionalstatistische_daten_stadtteile_json_245681_snap_4.zip"
HEAD={"User-Agent":"GermanyCrimeMonitor/1.0 (+https://github.com/1959124923wyz-sys/-1)"}

# One metric occupies four citywide pages; numbers below are human PDF page numbers.
METRIC_PAGES={
 "crime_total":137,
 "robbery":141,
 "serious_injury":153,
 "violence":157,
 "property_total":161,
 "burglary":165,
 "vehicle_theft":169,
 "theft_from_vehicle":173,
 "bicycle_theft":177,
}
METRIC_LABELS={
 "crime_total":"Straftaten insgesamt",
 "robbery":"Raubdelikte",
 "serious_injury":"Gefährliche und schwere Körperverletzung",
 "violence":"Gewaltkriminalität",
 "property_total":"Diebstahl insgesamt",
 "burglary":"Wohnungseinbruchdiebstahl",
 "vehicle_theft":"Diebstahl von Kraftwagen",
 "theft_from_vehicle":"Diebstahl an/aus Kraftfahrzeugen",
 "bicycle_theft":"Fahrraddiebstahl",
}

def get(url):
    r=requests.get(url,headers=HEAD,timeout=120);r.raise_for_status();return r.content

def norm(s):
    return re.sub(r"[^a-z0-9]+","",str(s or "").lower()
      .replace("ä","ae").replace("ö","oe").replace("ü","ue").replace("ß","ss"))

def nint(s):
    s=str(s or "").strip()
    if s in ("","-","–","—"): return 0
    s=re.sub(r"[^0-9-]","",s)
    try:return int(s)
    except:return 0

ROW=re.compile(
 r"^(?P<name>.+?)\s+"
 r"(?P<c24>[\d.]+)\s+(?P<s24>[\d.]+|-)\s+(?P<q24>[\d,]+%|-)\s+"
 r"(?P<c25>[\d.]+)\s+(?P<s25>[\d.]+|-)\s+(?P<q25>[\d,]+%|-)\s+"
 r"(?P<delta>-?[\d.]+)\s+(?P<pct>-?[\d,]+%|-)$"
)

pdf=PdfReader(io.BytesIO(get(PDF)))
print("hamburg atlas pages",len(pdf.pages))
tables={}
for key,start_page in METRIC_PAGES.items():
    rows={}
    for page_no in range(start_page,start_page+4):
        txt=(pdf.pages[page_no-1].extract_text() or "").replace("\x00","")
        for raw in txt.splitlines():
            line=re.sub(r"\s+"," ",raw).strip()
            m=ROW.match(line)
            if not m:continue
            name=m.group("name").strip()
            # Exclude aggregate rows; geometry join below is the final authority.
            if name.startswith("Bezirk ") or name.startswith("Hamburg ") or name.startswith("Bezirke "):
                continue
            rows[norm(name)]={"name":name,"cases":nint(m.group("c25")),"change":m.group("pct")}
    tables[key]=rows
    print(key,"parsed",len(rows),"rows")

# Load official Hamburg Stadtteil GeoJSON snapshot.
zb=get(GEOZIP)
with zipfile.ZipFile(io.BytesIO(zb)) as z:
    names=z.namelist()
    candidates=[n for n in names if n.lower().endswith((".geojson",".json"))]
    if not candidates:
        raise RuntimeError(f"no geojson/json in Hamburg zip: {names[:20]}")
    # Prefer the largest JSON member.
    member=max(candidates,key=lambda n:z.getinfo(n).file_size)
    geo=json.loads(z.read(member).decode("utf-8-sig"))
print("geo member",member,"features",len(geo.get("features",[])))

all_names=set()
for rows in tables.values(): all_names.update(rows.keys())
all_names.discard("tatortunbekannt")

# Regional-statistical geometry contains one record per Stadtteil per year.
# Keep exactly the latest record for each Stadtteil, and use the explicit
# population field instead of heuristically scanning demographic attributes.
latest={}
for f in geo.get("features",[]):
    props=f.get("properties") or {}
    raw_name=str(props.get("stadtteil") or "").strip()
    if not raw_name:continue
    try:year=int(str(props.get("jahr") or "0")[:4])
    except:year=0
    key=norm(raw_name)
    prev=latest.get(key)
    if prev is None or year>prev[0]:
        latest[key]=(year,f)

ALIASES={
  "hamburgaltstadt":"altstadt",
  "neuwerk":"inselneuwerk",
}

def crime_key_for_geo(name):
    n=norm(name)
    candidates=[n,ALIASES.get(n)]
    if n.startswith("hamburg"):candidates.append(n[len("hamburg"):])
    for k in candidates:
        if k and k in all_names:return k
    return None

features=[];matched=set();geo_unmatched=[]
for _,(_,f) in sorted(latest.items()):
    props=f.get("properties") or {}
    raw_name=str(props.get("stadtteil") or "").strip()
    nk=crime_key_for_geo(raw_name)
    if not nk:
        geo_unmatched.append(raw_name);continue

    raw_pop=props.get("bev_insgesamt")
    try:pop=int(round(float(str(raw_pop).replace(".","").replace(",",".")))) if raw_pop not in (None,"","-") else 0
    except:pop=0

    p={"city":"Hamburg","state":"Hamburg","name":tables["crime_total"].get(nk,{}).get("name",raw_name),"population":pop}
    found=False
    for key in METRIC_PAGES:
        row=tables[key].get(nk)
        if row:
            cases=row["cases"]
            p[key]={
              "cases":cases,
              "rate":round(cases/pop*100000,1) if pop>0 else None,
              "change":row["change"]
            }
            found=True
    if not found:continue
    p["source_population_field"]="bev_insgesamt"
    p["population_year"]=props.get("jahr")
    features.append({"type":"Feature","id":"hamburg-"+nk,"properties":p,"geometry":f.get("geometry")})
    matched.add(nk)

missing=sorted(all_names-matched)
# Some port / industrial Stadtteile are absent from the regional-statistical
# population geometry because they have no or almost no residents. We retain
# only areas with official geometry; require that essentially all populated
# Stadtteile are present.
if len(matched)<94 or len(features)<94:
    sample=(geo.get("features") or [{}])[0].get("properties",{})
    raise RuntimeError(
      f"Hamburg join too small: matched={len(matched)} latest_geo={len(latest)} "
      f"missing={missing[:25]} geo_unmatched={geo_unmatched[:25]} geo_keys={list(sample)[:40]}"
    )


out={
 "type":"FeatureCollection",
 "meta":{
   "generated_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
   "year":2025,"scope":"Hamburg Stadtteile","feature_count":len(features),"stadtteil_count":len(matched),
   "crime_source":"Polizei Hamburg / LKA: Stadtteilatlas PKS 2025",
   "crime_source_url":PDF,
   "geometry_population_source":"Statistikamt Nord / Hamburg Transparenzportal: Regionalstatistische Daten der Stadtteile",
   "geometry_population_source_url":GEOZIP,
   "metrics":METRIC_LABELS,
   "note":"Local rates are computed from official 2025 police case counts and the latest official Stadtteil population attribute. Port/industrial areas without usable resident-population geometry are omitted from rate shading."
 },
 "features":features
}
OUT.write_text(json.dumps(out,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
print(json.dumps({"features":len(features),"stadtteile":len(matched),"latest_geo":len(latest),"missing":missing,"geo_unmatched":geo_unmatched,"metric_rows":{k:len(v) for k,v in tables.items()}},ensure_ascii=False,indent=2))
