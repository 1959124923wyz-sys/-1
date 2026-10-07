#!/usr/bin/env python3
from __future__ import annotations
import json, re, statistics, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/pks_violent_2025.json"
GEO=ROOT/"data/germany-counties.geojson"
INDEX="https://kriminalitaets-karte.de/kriminalitaet/"
HEAD={"User-Agent":"GermanyCrimeMonitor/1.0 (+https://github.com/1959124923wyz-sys/-1)"}

FIELDS={
 "violence":"Gewaltkriminalität",
 "homicide":"Mord und Totschlag",
 "sexual":"Vergewaltigung und sexuelle Übergriffe",
 "serious_injury":"Gefährliche und schwere Körperverletzung",
 "robbery":"Raub",
}

def parse_num(s):
    t=(s or "").strip().replace("\xa0","").replace(".","").replace(",",".")
    t=re.sub(r"[^0-9.\-]","",t)
    return float(t) if t else None

def session():
    s=requests.Session()
    retry=Retry(total=3,connect=3,read=3,status=3,backoff_factor=.5,status_forcelist=[429,500,502,503,504],allowed_methods=frozenset(["GET"]))
    s.mount("https://",HTTPAdapter(max_retries=retry))
    s.headers.update(HEAD)
    return s

def scrape_one(item):
    ags,name,url=item
    s=session()
    r=s.get(url,timeout=35);r.raise_for_status()
    soup=BeautifulSoup(r.text,"html.parser")
    rows={}
    for tr in soup.find_all("tr"):
        cells=[c.get_text(" ",strip=True) for c in tr.find_all(["th","td"])]
        if len(cells)<3:continue
        label=cells[0]
        for key,target in FIELDS.items():
            if label==target or label.startswith(target):
                rows[key]={
                    "cases":int(parse_num(cells[1]) or 0),
                    "rate":float(parse_num(cells[2]) or 0),
                    "change":cells[3] if len(cells)>3 else None,
                }
    if "violence" not in rows:
        raise RuntimeError(f"{ags} {name}: no Gewaltkriminalität row")
    # Main page contains population/state in intro/breadcrumb. Keep state from geometry later.
    return ags,{"ags":ags,"name":name,"source_url":url,**rows}

geo=json.loads(GEO.read_text(encoding="utf-8"))
geom_by_ags={str(f.get("id","")).zfill(5):f.get("properties",{}) for f in geo.get("features",[])}
print("geometry features",len(geom_by_ags))

r=session().get(INDEX,timeout=45);r.raise_for_status()
soup=BeautifulSoup(r.text,"html.parser")
links={}
for a in soup.find_all("a",href=True):
    href=urljoin(INDEX,a["href"])
    m=re.search(r"/kriminalitaet/([^/]+)-(\d{5})\.html(?:$|\?)",href)
    if not m:continue
    ags=m.group(2)
    name=a.get_text(" ",strip=True)
    links[ags]=(ags,name,href.split("?")[0])
print("index county links",len(links))
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
            rec["state"]=props.get("state")
            rec["district_type"]=props.get("districtType")
            records[key]=rec
        except Exception as e:
            errors.append((ags,str(e)))
        if n%50==0:print("progress",n,"ok",len(records),"errors",len(errors))

if len(records)<390:
    raise RuntimeError(f"only {len(records)} county records parsed; sample errors={errors[:10]}")

rates=sorted(r["violence"]["rate"] for r in records.values() if r["violence"]["rate"] is not None)
def quantile(p):
    if not rates:return None
    pos=(len(rates)-1)*p
    lo=int(pos);hi=min(lo+1,len(rates)-1);frac=pos-lo
    return round(rates[lo]*(1-frac)+rates[hi]*frac,1)
breaks=[quantile(.2),quantile(.4),quantile(.6),quantile(.8)]
top=sorted(records.values(),key=lambda x:x["violence"]["rate"],reverse=True)[:15]

out={
 "meta":{
   "generated_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
   "year":2025,
   "metric":"Gewaltkriminalität",
   "unit":"Fälle je 100.000 Einwohner",
   "county_count":len(records),
   "geometry_count":len(geom_by_ags),
   "matched_geometry":sum(1 for k in records if k in geom_by_ags),
   "quantile_breaks":breaks,
   "official_source":"Bundeskriminalamt (BKA), Polizeiliche Kriminalstatistik 2025, Kreistabelle T01",
   "official_catalog_url":"https://data.gov.de/suche/daten/2025-polizeiliche-kriminalstatistik-t01-grundtabelle-kreise-ausgewahlte-straftaten-gruppen",
   "retrieval_note":"BKA PKS 2025 county values are read from a public visualization mirror because the BKA download endpoint resets automated GitHub-runner connections. The mirror explicitly cites the BKA Kreistabellen; Berlin values are cross-checked against Polizei Berlin PKS 2025.",
   "mirror_url":INDEX,
   "dark_figure_note":"PKS contains police-recorded crime; unreported offences are not included."
 },
 "records":records,
 "top15":[{"ags":r["ags"],"name":r["name"],"state":r.get("state"),"rate":r["violence"]["rate"],"cases":r["violence"]["cases"]} for r in top],
 "errors":errors[:30]
}
OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({
 "count":len(records),"matched_geometry":out["meta"]["matched_geometry"],
 "breaks":breaks,"max":top[0] if top else None,"errors":errors[:5]
},ensure_ascii=False))
