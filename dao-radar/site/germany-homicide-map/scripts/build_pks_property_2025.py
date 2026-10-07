#!/usr/bin/env python3
from __future__ import annotations
import json, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/pks_property_2025.json"
GEO=ROOT/"data/germany-counties.geojson"
INDEX="https://kriminalitaets-karte.de/kriminalitaet/"
HEAD={"User-Agent":"GermanyCrimeMonitor/1.0 (+https://github.com/1959124923wyz-sys/-1)"}

FIELDS={
    "property_total":"Diebstahl insgesamt",
    "burglary":"Wohnungseinbruchdiebstahl",
    "bicycle_theft":"Fahrraddiebstahl",
    "vehicle_theft":"Diebstahl von Kraftwagen",
    "theft_from_vehicle":"Diebstahl an/aus Kraftfahrzeugen",
}

def parse_num(s):
    t=(s or "").strip().replace("\xa0","").replace(".","").replace(",",".")
    t=re.sub(r"[^0-9.\-]","",t)
    return float(t) if t else None

def session():
    s=requests.Session()
    retry=Retry(
        total=3,connect=3,read=3,status=3,backoff_factor=.5,
        status_forcelist=[429,500,502,503,504],
        allowed_methods=frozenset(["GET"])
    )
    s.mount("https://",HTTPAdapter(max_retries=retry))
    s.headers.update(HEAD)
    return s

def scrape_one(item):
    ags,name,url=item
    s=session()
    r=s.get(url,timeout=35);r.raise_for_status()
    soup=BeautifulSoup(r.content.decode("utf-8","replace"),"html.parser")
    rows={}
    for tr in soup.find_all("tr"):
        cells=[c.get_text(" ",strip=True) for c in tr.find_all(["th","td"])]
        if len(cells)<3:
            continue
        label=cells[0]
        for key,target in FIELDS.items():
            if label==target or label.startswith(target):
                rows[key]={
                    "cases":int(parse_num(cells[1]) or 0),
                    "rate":float(parse_num(cells[2]) or 0),
                    "change":cells[3] if len(cells)>3 else None,
                }
    if "property_total" not in rows:
        raise RuntimeError(f"{ags} {name}: no Diebstahl insgesamt row")
    return ags,{"ags":ags,"name":name,"source_url":url,**rows}

geo=json.loads(GEO.read_text(encoding="utf-8"))
geom_by_ags={str(f.get("id","")).zfill(5):f.get("properties",{}) for f in geo.get("features",[])}
LEGACY_TO_CURRENT={"03152":"03159","03156":"03159","16056":"16063"}
CURRENT_TO_LEGACY={"03159":"03152","16063":"16056"}

r=session().get(INDEX,timeout=45);r.raise_for_status()
soup=BeautifulSoup(r.content.decode("utf-8","replace"),"html.parser")
links={}
for a in soup.find_all("a",href=True):
    href=urljoin(INDEX,a["href"])
    m=re.search(r"/kriminalitaet/([^/]+)-(\d{5})\.html(?:$|\?)",href)
    if not m:
        continue
    ags=m.group(2)
    name=a.get_text(" ",strip=True)
    links[ags]=(ags,name,href.split("?")[0])

if len(links)<390:
    raise RuntimeError(f"expected ~400 county pages, got {len(links)}")

records={}
errors=[]
with ThreadPoolExecutor(max_workers=8) as ex:
    futures={ex.submit(scrape_one,item):ags for ags,item in links.items()}
    for n,f in enumerate(as_completed(futures),1):
        ags=futures[f]
        try:
            key,rec=f.result()
            props=geom_by_ags.get(key,{})
            if not props and key in CURRENT_TO_LEGACY:
                props=geom_by_ags.get(CURRENT_TO_LEGACY[key],{})
            rec["state"]=props.get("state")
            rec["district_type"]=props.get("districtType")
            records[key]=rec
        except Exception as e:
            errors.append((ags,str(e)))
        if n%50==0:
            print("progress",n,"ok",len(records),"errors",len(errors))

if len(records)<390:
    raise RuntimeError(f"only {len(records)} county records parsed; sample errors={errors[:10]}")

def quantiles(field):
    vals=sorted(
        rec[field]["rate"] for rec in records.values()
        if field in rec and rec[field].get("rate") is not None
    )
    out=[]
    for p in (.2,.4,.6,.8):
        pos=(len(vals)-1)*p
        lo=int(pos);hi=min(lo+1,len(vals)-1);frac=pos-lo
        out.append(round(vals[lo]*(1-frac)+vals[hi]*frac,1))
    return out

quantile_breaks={k:quantiles(k) for k in FIELDS}
coverage={
    k:sum(1 for rec in records.values() if k in rec and rec[k].get("rate") is not None)
    for k in FIELDS
}
tops={}
for k in FIELDS:
    tops[k]=[
        {"ags":r["ags"],"name":r["name"],"state":r.get("state"),"rate":r[k]["rate"],"cases":r[k]["cases"]}
        for r in sorted(
            (x for x in records.values() if k in x),
            key=lambda x:x[k]["rate"],reverse=True
        )[:15]
    ]

out={
    "meta":{
        "generated_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
        "year":2025,
        "metric":"Diebstahl / Eigentumsdelikte",
        "unit":"Fälle je 100.000 Einwohner",
        "county_count":len(records),
        "geometry_count":len(geom_by_ags),
        "matched_geometry":sum(1 for g in geom_by_ags if (g in records or LEGACY_TO_CURRENT.get(g) in records)),
        "geometry_aliases":LEGACY_TO_CURRENT,
        "coverage_by_metric":coverage,
        "quantile_breaks":quantile_breaks,
        "official_source":"Bundeskriminalamt (BKA), Polizeiliche Kriminalstatistik 2025, Kreistabellen",
        "official_catalog_url":"https://data.gov.de/suche/daten/2025-polizeiliche-kriminalstatistik-t01-grundtabelle-kreise-ausgewahlte-straftaten-gruppen",
        "retrieval_note":"County values are parsed from kriminalitaets-karte.de, which states that its county tables come from the BKA PKS Kreistabellen. The same source is already used for the nationwide violent-crime layer.",
        "mirror_url":INDEX,
        "dark_figure_note":"PKS contains police-recorded crime; unreported offences are not included.",
        "fields":{
            "property_total":"Diebstahl insgesamt",
            "burglary":"Wohnungseinbruchdiebstahl",
            "bicycle_theft":"Fahrraddiebstahl",
            "vehicle_theft":"Diebstahl von Kraftwagen",
            "theft_from_vehicle":"Diebstahl an/aus Kraftfahrzeugen"
        }
    },
    "records":records,
    "top15":tops,
    "errors":errors[:30]
}
OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({
    "count":len(records),
    "matched_geometry":out["meta"]["matched_geometry"],
    "coverage_by_metric":coverage,
    "quantile_breaks":quantile_breaks,
    "errors":errors[:5]
},ensure_ascii=False,indent=2))
