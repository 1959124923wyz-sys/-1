#!/usr/bin/env python3
from __future__ import annotations
import csv, io, json, math, re, time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/berlin_heatmap.json"
CENTROIDS=ROOT/"data/berlin_lor_centroids.json"

BIKE_URL="https://www.polizei-berlin.eu/Fahrraddiebstahl/Fahrraddiebstahl.csv"
VEHICLE_URL="https://www.polizei-berlin.eu/Kfzdiebstahl/Kfzdiebstahl.csv"
WFS_URL="https://gdi.berlin.de/services/wfs/lor_2021"
WFS_PARAMS={
    "service":"wfs",
    "version":"2.0.0",
    "request":"GetFeature",
    "typeNames":"lor_2021:a_lor_plr_2021",
    "outputFormat":"application/json",
    "srsName":"EPSG:4326",
}
HEAD={"User-Agent":"GermanyCrimeMonitorBerlinHeat/1.0 (+https://github.com/1959124923wyz-sys/-1)"}
TODAY=datetime.now(timezone.utc).date()
WINDOWS=(90,)

def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def polite_get(session,url,*,params=None,timeout=45):
    last=None
    for attempt in range(5):
        r=session.get(url,params=params,headers=HEAD,timeout=timeout)
        last=r
        if r.status_code==429:
            raw=r.headers.get("Retry-After","").strip()
            try: wait=float(raw)
            except ValueError: wait=min(40,4*(2**attempt))
            wait=max(3,min(wait,60))
            print("WARN throttled",url,"sleep",wait)
            time.sleep(wait)
            continue
        if 500<=r.status_code<600:
            wait=min(30,2*(2**attempt))
            print("WARN server",r.status_code,url,"sleep",wait)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r
    if last is not None:
        last.raise_for_status()
    raise RuntimeError(f"failed to fetch {url}")

def decode_bytes(content:bytes)->str:
    for enc in ("utf-8-sig","utf-8","cp1252","latin1"):
        try:return content.decode(enc)
        except UnicodeDecodeError:pass
    return content.decode("latin1","replace")

def norm(s:str)->str:
    return re.sub(r"[^A-Z0-9]","",str(s or "").upper())

def parse_csv(content:bytes):
    text=decode_bytes(content).replace("\x00","")
    sample=text[:20000]
    try:
        dialect=csv.Sniffer().sniff(sample,delimiters=";,|\t")
        delim=dialect.delimiter
    except Exception:
        # Berlin police CSV exports are commonly comma-separated.
        counts={d:sample.count(d) for d in (",",";","|","\t")}
        delim=max(counts,key=counts.get)
    reader=csv.DictReader(io.StringIO(text),delimiter=delim)
    rows=list(reader)
    headers=reader.fieldnames or []
    return headers,rows,delim

def find_field(headers,*wanted):
    nmap={norm(h):h for h in headers}
    for w in wanted:
        nw=norm(w)
        if nw in nmap:return nmap[nw]
    for h in headers:
        nh=norm(h)
        if all(piece in nh for piece in wanted):
            return h
    return None

def parse_date(v):
    s=str(v or "").strip()
    if not s:return None
    s=s.split()[0]
    for fmt in ("%d.%m.%Y","%Y-%m-%d","%d/%m/%Y"):
        try:return datetime.strptime(s,fmt).date()
        except ValueError:pass
    m=re.search(r"(\d{1,2})\.(\d{1,2})\.(20\d{2})",s)
    if m:
        try:return date(int(m.group(3)),int(m.group(2)),int(m.group(1)))
        except ValueError:return None
    return None

def normalize_lor(v):
    s=str(v or "").strip()
    if not s:return None
    s=re.sub(r"\.0+$","",s)
    digits=re.sub(r"\D","",s)
    if not digits:return None
    if len(digits)<8:digits=digits.zfill(8)
    if len(digits)>8:digits=digits[-8:]
    return digits

def polygon_centroid(ring):
    pts=[(float(p[0]),float(p[1])) for p in ring if len(p)>=2]
    if len(pts)<3:return (0,0,0)
    if pts[0]!=pts[-1]:pts.append(pts[0])
    cross_sum=cx=cy=0.0
    for (x1,y1),(x2,y2) in zip(pts,pts[1:]):
        cross=x1*y2-x2*y1
        cross_sum+=cross
        cx+=(x1+x2)*cross
        cy+=(y1+y2)*cross
    if abs(cross_sum)<1e-12:
        xs=[p[0] for p in pts[:-1]];ys=[p[1] for p in pts[:-1]]
        return (sum(xs)/len(xs),sum(ys)/len(ys),1e-12)
    return (cx/(3*cross_sum),cy/(3*cross_sum),abs(cross_sum))

def geometry_centroid(geom):
    typ=geom.get("type")
    coords=geom.get("coordinates") or []
    if typ=="Polygon":
        return polygon_centroid(coords[0])[:2] if coords else (None,None)
    if typ=="MultiPolygon":
        accx=accy=weight=0.0
        for poly in coords:
            if not poly:continue
            x,y,w=polygon_centroid(poly[0])
            accx+=x*w;accy+=y*w;weight+=w
        if weight>0:return (accx/weight,accy/weight)
    return (None,None)

def property_value(props,*candidates):
    for c in candidates:
        if c in props and props[c] not in (None,""):return props[c]
    normmap={norm(k):v for k,v in props.items()}
    for c in candidates:
        v=normmap.get(norm(c))
        if v not in (None,""):return v
    return None

def build_centroids(session):
    if CENTROIDS.exists():
        try:
            obj=json.loads(CENTROIDS.read_text(encoding="utf-8"))
            if len(obj.get("centroids",{}))>=500:
                return obj
        except Exception:pass

    print("Fetching Berlin LOR Planungsraum geometry")
    r=polite_get(session,WFS_URL,params=WFS_PARAMS,timeout=90)
    try:geo=r.json()
    except Exception:
        raise RuntimeError(f"LOR WFS did not return JSON; content-type={r.headers.get('content-type')} head={r.text[:200]!r}")
    feats=geo.get("features",[])
    if len(feats)<500:
        raise RuntimeError(f"expected >=500 LOR features, got {len(feats)}")

    centroids={}
    skipped=0
    for f in feats:
        props=f.get("properties") or {}
        raw_id=property_value(props,"PLR_ID","RAUMID","PLR","LOR")
        lor=normalize_lor(raw_id)
        lon,lat=geometry_centroid(f.get("geometry") or {})
        if not lor or lat is None or lon is None:
            skipped+=1;continue
        name=property_value(props,"PLR_NAME","PLRNAME","PLANUNGSRAUM","NAME") or ""
        district=property_value(props,"BEZNAME","BEZIRK","BEZ_NAME") or ""
        centroids[lor]={"lat":round(lat,6),"lon":round(lon,6),"name":str(name),"district":str(district)}
    if len(centroids)<500:
        sample=(feats[0].get("properties") if feats else {})
        raise RuntimeError(f"only {len(centroids)} LOR centroids built; skipped={skipped}; sample keys={list(sample or {})[:30]}")
    obj={
        "meta":{
            "generated_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
            "source":"Berlin Open Data / LOR 2021 WFS",
            "source_url":"https://daten.berlin.de/datensaetze/lebensweltlich-orientierte-raume-lor-01-01-2021-wfs-34c86848",
            "feature_count":len(centroids)
        },
        "centroids":centroids
    }
    save(CENTROIDS,obj)
    print("LOR centroids",len(centroids))
    return obj

def read_source(session,url,label):
    r=polite_get(session,url,timeout=90)
    headers,rows,delim=parse_csv(r.content)
    date_field=find_field(headers,"TATZEIT","ANFANG","DATUM") or find_field(headers,"TATZEITANFANGDATUM")
    lor_field=find_field(headers,"LOR")
    attempt_field=find_field(headers,"VERSUCH")
    if not date_field or not lor_field:
        raise RuntimeError(f"{label}: could not resolve date/LOR columns; headers={headers}")
    print(label,"rows",len(rows),"delimiter",repr(delim),"date_field",date_field,"lor_field",lor_field,"attempt_field",attempt_field)
    return rows,date_field,lor_field,attempt_field,headers

session=requests.Session()
centroid_obj=build_centroids(session)
centroids=centroid_obj["centroids"]

sources={}
for key,url in (("bike",BIKE_URL),("vehicle",VEHICLE_URL)):
    rows,date_field,lor_field,attempt_field,headers=read_source(session,url,key)
    sources[key]={
        "rows":rows,"date_field":date_field,"lor_field":lor_field,"attempt_field":attempt_field,
        "headers":headers,"url":url
    }

window_counts={days:defaultdict(lambda:{"bike":0,"vehicle":0}) for days in WINDOWS}
source_stats={}
for key,src in sources.items():
    parsed=0;bad_date=0;bad_lor=0;unmatched=0;attempts=0
    latest=None;earliest=None
    for row in src["rows"]:
        d=parse_date(row.get(src["date_field"]))
        lor=normalize_lor(row.get(src["lor_field"]))
        if not d:
            bad_date+=1;continue
        if not lor:
            bad_lor+=1;continue
        if lor not in centroids:
            unmatched+=1;continue
        parsed+=1
        latest=d if latest is None or d>latest else latest
        earliest=d if earliest is None or d<earliest else earliest
        av=str(row.get(src["attempt_field"],"")).strip().lower() if src["attempt_field"] else ""
        if av in ("ja","yes","1","true"):attempts+=1
        for days in WINDOWS:
            cutoff=TODAY-timedelta(days=days)
            if cutoff<=d<=TODAY:
                window_counts[days][lor][key]+=1
    source_stats[key]={
        "raw_rows":len(src["rows"]),"parsed_rows":parsed,"bad_date":bad_date,
        "bad_lor":bad_lor,"unmatched_lor":unmatched,"attempts_all_data":attempts,
        "earliest_date":earliest.isoformat() if earliest else None,
        "latest_date":latest.isoformat() if latest else None,
        "source_url":src["url"]
    }

windows={}
for days in WINDOWS:
    pts=[]
    bike_total=vehicle_total=0
    for lor,c in window_counts[days].items():
        bike=int(c["bike"]);vehicle=int(c["vehicle"]);total=bike+vehicle
        if total<=0:continue
        p=centroids[lor]
        bike_total+=bike;vehicle_total+=vehicle
        pts.append({
            "lor":lor,"lat":p["lat"],"lon":p["lon"],
            "bike":bike,"vehicle":vehicle,"total":total,
            "name":p.get("name",""),"district":p.get("district","")
        })
    pts.sort(key=lambda x:x["total"],reverse=True)
    windows[str(days)]={
        "bike":bike_total,"vehicle":vehicle_total,"total":bike_total+vehicle_total,
        "active_lor":len(pts),"points":pts
    }

out={
    "meta":{
        "generated_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
        "today":TODAY.isoformat(),
        "scope":"Berlin",
        "window_days":90,
        "coverage":"Official Berlin Police open-data heat layer: bicycle theft plus theft from/on motor vehicles. This is much denser than press-release points but still not every property-crime category.",
        "sources":{
            "bike":{
                "title":"Fahrraddiebstahl in Berlin",
                "dataset_url":"https://daten.berlin.de/datensaetze/fahrraddiebstahl-in-berlin",
                "csv_url":BIKE_URL,
                "license":"CC BY"
            },
            "vehicle":{
                "title":"Diebstahl an/aus Kfz",
                "dataset_url":"https://daten.berlin.de/datensaetze/diebstahl-an-aus-kfz",
                "csv_url":VEHICLE_URL,
                "license":"CC BY"
            },
            "lor":{
                "title":"Lebensweltlich orientierte Räume (LOR) 2021",
                "dataset_url":"https://daten.berlin.de/datensaetze/lebensweltlich-orientierte-raume-lor-01-01-2021-wfs-34c86848",
                "license":"CC BY 3.0 DE"
            }
        },
        "source_stats":source_stats,
        "centroid_count":len(centroids)
    },
    "windows":windows
}
save(OUT,out)
print(json.dumps({
    "centroids":len(centroids),
    "bike_rows":source_stats["bike"]["raw_rows"],
    "vehicle_rows":source_stats["vehicle"]["raw_rows"],
    "window90":windows["90"]["total"],
    "bike90":windows["90"]["bike"],
    "vehicle90":windows["90"]["vehicle"],
    "active_lor90":windows["90"]["active_lor"],
    "unmatched_bike":source_stats["bike"]["unmatched_lor"],
    "unmatched_vehicle":source_stats["vehicle"]["unmatched_lor"]
},ensure_ascii=False))
