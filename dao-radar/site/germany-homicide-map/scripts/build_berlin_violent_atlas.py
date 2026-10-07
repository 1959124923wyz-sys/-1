#!/usr/bin/env python3
from __future__ import annotations
import io,json,re,time
from datetime import datetime,timezone
from pathlib import Path
import requests,openpyxl

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/berlin_violent_2025.geojson"
XLSX="https://www.berlin.de/polizei/_assets/dienststellen/lka/fallzahlen_hz-2016-2025.xlsx?ts=1790656142"
WFS="https://gdi.berlin.de/services/wfs/lor_2021"
PARAMS={"service":"wfs","version":"2.0.0","request":"GetFeature","typeNames":"lor_2021:a_lor_plr_2021","outputFormat":"application/json","srsName":"EPSG:4326"}
HEAD={"User-Agent":"GermanyCrimeMonitor/1.0 (+https://github.com/1959124923wyz-sys/-1)"}

def norm(s):
    return re.sub(r"\s+"," ",str(s or "").replace("\n"," ")).strip().lower()

def prop(props,*names):
    m={re.sub(r"[^a-z0-9]","",str(k).lower()):v for k,v in props.items()}
    for n in names:
        v=m.get(re.sub(r"[^a-z0-9]","",n.lower()))
        if v not in (None,""):return v
    return None

def polite_get(url,*,params=None,timeout=90):
    last=None
    for attempt in range(6):
        r=requests.get(url,params=params,headers=HEAD,timeout=timeout)
        last=r
        if r.status_code==429:
            raw=r.headers.get("Retry-After","").strip()
            try:wait=float(raw)
            except ValueError:wait=min(75,8*(2**attempt))
            wait=max(5,min(wait,90))
            print("WARN throttled",url,"sleep",wait)
            time.sleep(wait)
            continue
        if 500<=r.status_code<600:
            wait=min(30,3*(2**attempt));time.sleep(wait);continue
        r.raise_for_status();return r
    last.raise_for_status()

r=polite_get(XLSX)
wb=openpyxl.load_workbook(io.BytesIO(r.content),read_only=True,data_only=True)

def read_sheet(name):
    ws=wb[name]
    header=None
    rows=[]
    for row in ws.iter_rows(values_only=True):
        vals=list(row)
        if header is None and vals and norm(vals[0]).startswith("lor-schlüssel"):
            header=[norm(v) for v in vals]
            continue
        if header is None:continue
        if not vals or vals[0] is None:continue
        code=str(vals[0]).strip().split(".")[0].zfill(6)
        if not re.fullmatch(r"\d{6}",code):continue
        rec={header[i]:vals[i] for i in range(min(len(header),len(vals)))}
        rows.append((code,rec))
    return dict(rows)

cases=read_sheet("Fallzahlen_2025")
rates=read_sheet("HZ_2025")
print("atlas rows",len(cases),len(rates))

def col(rec,*needles):
    for k,v in rec.items():
        nk=norm(k)
        if all(n in nk for n in needles):return v
    return None

def num(v):
    if v in (None,"","-","–","—"):return 0.0
    try:return float(v)
    except Exception:
        t=str(v).strip().replace(".","").replace(",",".")
        t=re.sub(r"[^0-9.\-]","",t)
        try:return float(t) if t not in ("","-",".") else 0.0
        except Exception:return 0.0

# Bezirksregion rows: district summary codes end 0000; BZR rows do not.
stats={}
for code,rec in cases.items():
    if code.endswith("0000"):continue
    rr=rates.get(code,{})
    name=col(rec,"bezeichnung","bezirksregion") or code
    robbery=int(num(col(rec,"raub")))
    serious=int(num(col(rec,"gefährl.","schwere","körper")))
    injury=int(num(col(rec,"körper","insgesamt")))
    robbery_hz=num(col(rr,"raub"))
    serious_hz=num(col(rr,"gefährl.","schwere","körper"))
    injury_hz=num(col(rr,"körper","insgesamt"))
    stats[code]={
      "bZR":code,"name":str(name),"robbery_cases":robbery,"robbery_rate":robbery_hz,
      "serious_injury_cases":serious,"serious_injury_rate":serious_hz,
      "bodily_injury_cases":injury,"bodily_injury_rate":injury_hz,
      "combined_cases":robbery+serious,"combined_rate":round(robbery_hz+serious_hz,1)
    }
print("BZR stats",len(stats))

g=polite_get(WFS,params=PARAMS)
geo=g.json();features=[]
unmatched=[];matched_bzr=set()
for f in geo.get("features",[]):
    props=f.get("properties") or {}
    raw=prop(props,"BZR","BZR_ID")
    digits=re.sub(r"\D","",str(raw or ""))
    code=digits[-6:].zfill(6) if digits else ""
    st=stats.get(code)
    if not st:
        unmatched.append((code,props));continue
    plr_raw=prop(props,"PLR","PLR_ID","RAUMID")
    p=dict(st)
    p["plr"]=str(plr_raw or "")
    features.append({"type":"Feature","id":str(plr_raw or code),"properties":p,"geometry":f.get("geometry")})
    matched_bzr.add(code)

if len(features)<530 or len(matched_bzr)<140:
    sample_keys=list((geo.get("features") or [{}])[0].get("properties",{}).keys())
    raise RuntimeError(f"matched only {len(features)} PLR / {len(matched_bzr)} BZR; unmatched={len(unmatched)} sample WFS keys={sample_keys}")

vals=sorted(f["properties"]["combined_rate"] for f in features)
def q(p):
    pos=(len(vals)-1)*p;lo=int(pos);hi=min(lo+1,len(vals)-1);fr=pos-lo
    return round(vals[lo]*(1-fr)+vals[hi]*fr,1)
breaks=[q(.2),q(.4),q(.6),q(.8)]
out={
 "type":"FeatureCollection",
 "meta":{
   "generated_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
   "year":2025,
   "scope":"Berlin Bezirksregionen",
   "feature_count":len(features),
   "bzr_count":len(matched_bzr),
   "metric":"Raub + gefährliche/schwere Körperverletzung",
   "unit":"Fälle je 100.000 Einwohner",
   "quantile_breaks":breaks,
   "source":"Polizei Berlin Kriminalitätsatlas 2025",
   "source_url":"https://www.berlin.de/polizei/service/kriminalitaetsatlas/",
   "note":"Local high-coverage proxy for serious violence: robbery plus dangerous/serious bodily injury. It is not identical to the BKA composite Gewaltkriminalität definition."
 },
 "features":features
}
OUT.write_text(json.dumps(out,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
print(json.dumps({"features":len(features),"bzr_count":len(matched_bzr),"breaks":breaks,"unmatched":len(unmatched),"max":max(vals)},ensure_ascii=False))
