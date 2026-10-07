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

def match_name(props):
    # First, exact normalized value match to a crime-atlas Stadtteil.
    for v in props.values():
        if isinstance(v,str) and norm(v) in all_names:
            return norm(v),v
    # Then common key names.
    for k,v in props.items():
        nk=norm(k)
        if isinstance(v,str) and ("stadtteil" in nk or nk in ("name","bezirkname")):
            nv=norm(v)
            if nv in all_names:return nv,v
    return None,None

def population(props):
    cand=[]
    for k,v in props.items():
        nk=norm(k)
        if not any(x in nk for x in ("einwohner","bevolkerung","bevoelkerung")):continue
        try:
            num=float(str(v).replace(".","").replace(",","."))
        except:continue
        if not 1<=num<=300000:continue
        score=0
        if "2025" in nk:score+=5
        elif "2024" in nk:score+=4
        if "gesamt" in nk:score+=2
        if "dichte" in nk or "anteil" in nk:score-=10
        cand.append((score,num,k))
    if not cand:return None,None
    cand.sort(reverse=True)
    return int(round(cand[0][1])),cand[0][2]

features=[];matched=set();pop_keys={}
for f in geo.get("features",[]):
    props=f.get("properties") or {}
    nk,display=match_name(props)
    if not nk:continue
    pop,popkey=population(props)
    if not pop:
        continue
    p={"city":"Hamburg","state":"Hamburg","name":tables["crime_total"].get(nk,{}).get("name",display),"population":pop}
    found=False
    for key in METRIC_PAGES:
        row=tables[key].get(nk)
        if row:
            cases=row["cases"]
            p[key]={"cases":cases,"rate":round(cases/pop*100000,1),"change":row["change"]}
            found=True
    if not found:continue
    p["source_population_field"]=popkey
    features.append({"type":"Feature","id":"hamburg-"+nk,"properties":p,"geometry":f.get("geometry")})
    matched.add(nk);pop_keys[popkey]=pop_keys.get(popkey,0)+1

if len(matched)<95:
    missing=sorted(all_names-matched)
    sample=(geo.get("features") or [{}])[0].get("properties",{})
    raise RuntimeError(f"Hamburg join too small: matched={len(matched)} features={len(features)} missing_sample={missing[:25]} geo_keys={list(sample)[:60]} pop_keys={pop_keys}")

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
   "note":"Local rates are computed from official 2025 police case counts and the official Stadtteil population attribute from the Hamburg geodata snapshot."
 },
 "features":features
}
OUT.write_text(json.dumps(out,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
print(json.dumps({"features":len(features),"stadtteile":len(matched),"metric_rows":{k:len(v) for k,v in tables.items()},"pop_keys":pop_keys},ensure_ascii=False,indent=2))
