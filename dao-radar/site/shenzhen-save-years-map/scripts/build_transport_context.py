#!/usr/bin/env python3
"""Build a lightweight, self-hosted Shenzhen transport context layer from OSM.

This is a low-frequency/static context build, not a live map dependency.
It queries a public Overpass endpoint without an API key, simplifies the returned
major-road/rail geometry, and writes a compact JS bundle for the SVG map.
"""
from __future__ import annotations
import json, math, re, sys, time
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data"/"transport_context.js"
JSON_OUT=ROOT/"data"/"transport_context.json"
BBOX=(22.35,113.70,22.90,114.68)  # south, west, north, east
ENDPOINTS=[
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
]
UA="ShenzhenSaveYearsMap/1.0 (+GitHub Pages static visualization)"
ROAD_TYPES=("motorway","trunk","primary","secondary")
BOUNDARY=ROOT/"data"/"shenzhen-boundary.js"
QUERY=f"""
[out:json][timeout:120];
(
  way["highway"~"^({'|'.join(ROAD_TYPES)})$"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  way["railway"="rail"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  nwr["aeroway"="aerodrome"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  nwr["railway"="station"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  nwr["amenity"="ferry_terminal"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  nwr["industrial"="port"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  nwr["harbour"="yes"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  nwr["barrier"="border_control"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  nwr["name"~"口岸"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
);
out tags center geom;
"""

def fetch():
    headers={"User-Agent":UA,"Accept":"application/json"}
    errs=[]
    for ep in ENDPOINTS:
        try:
            r=requests.post(ep,data={"data":QUERY},headers=headers,timeout=150)
            if r.status_code in (429,504):
                errs.append(f"{ep}: HTTP {r.status_code}"); time.sleep(2); continue
            r.raise_for_status()
            obj=r.json()
            if len(obj.get("elements",[]))<50:
                errs.append(f"{ep}: suspiciously small result"); continue
            print("Overpass source:",ep,"elements:",len(obj["elements"]))
            return obj,ep
        except Exception as e:
            errs.append(f"{ep}: {type(e).__name__}: {e}")
    raise RuntimeError("All Overpass endpoints failed: "+" | ".join(errs))

def dist_point_line(p,a,b):
    x,y=p; x1,y1=a; x2,y2=b
    dx=x2-x1; dy=y2-y1
    if dx==0 and dy==0: return math.hypot(x-x1,y-y1)
    t=max(0,min(1,((x-x1)*dx+(y-y1)*dy)/(dx*dx+dy*dy)))
    return math.hypot(x-(x1+t*dx),y-(y1+t*dy))

def simplify(points,tol):
    if len(points)<=2:return points
    a,b=points[0],points[-1]; maxd=-1; idx=-1
    for i,p in enumerate(points[1:-1],1):
        d=dist_point_line(p,a,b)
        if d>maxd:maxd=d;idx=i
    if maxd>tol:
        l=simplify(points[:idx+1],tol); r=simplify(points[idx:],tol)
        return l[:-1]+r
    return [a,b]

def line_length(pts):
    total=0
    for (x1,y1),(x2,y2) in zip(pts,pts[1:]):
        total+=math.hypot((x2-x1)*math.cos(math.radians((y1+y2)/2)),y2-y1)
    return total

def load_city_polygons():
    txt=BOUNDARY.read_text(encoding="utf-8")
    raw=txt.split("=",1)[1].strip().rstrip(";")
    geo=json.loads(raw)
    polys=[]
    for f in geo.get("features",[]):
        g=f.get("geometry") or {}
        coords=g.get("coordinates") or []
        if g.get("type")=="Polygon":
            if coords: polys.append(coords[0])
        elif g.get("type")=="MultiPolygon":
            for p in coords:
                if p: polys.append(p[0])
    return polys

CITY_POLYS=None

def point_in_ring(x,y,ring):
    inside=False
    j=len(ring)-1
    for i in range(len(ring)):
        xi,yi=ring[i]; xj,yj=ring[j]
        if ((yi>y)!=(yj>y)) and (x < (xj-xi)*(y-yi)/((yj-yi) or 1e-12)+xi):
            inside=not inside
        j=i
    return inside

def in_city(lng,lat):
    global CITY_POLYS
    if CITY_POLYS is None:CITY_POLYS=load_city_polygons()
    return any(point_in_ring(lng,lat,r) for r in CITY_POLYS)

def center_of(el):
    if "lat" in el and "lon" in el:return [el["lon"],el["lat"]]
    c=el.get("center")
    if c:return [c["lon"],c["lat"]]
    geom=el.get("geometry") or []
    if geom:
        return [sum(p["lon"] for p in geom)/len(geom),sum(p["lat"] for p in geom)/len(geom)]
    return None

def norm_name(s):
    return re.sub(r"\s+","",(s or "")).lower()

def poi_category(tags):
    name=tags.get("name") or tags.get("name:zh") or tags.get("name:en") or ""
    if tags.get("aeroway")=="aerodrome": return "airport"
    if tags.get("barrier")=="border_control" or "口岸" in name: return "border"
    if tags.get("industrial")=="port" or tags.get("harbour")=="yes": return "port"
    if tags.get("amenity")=="ferry_terminal": return "ferry"
    if tags.get("railway")=="station":
        if tags.get("station")=="subway" or tags.get("subway")=="yes": return None
        return "rail"
    return None

def poi_priority(cat,name):
    base={"airport":100,"border":92,"port":88,"ferry":82,"rail":68}.get(cat,50)
    major=("深圳北","福田站","深圳站","深圳东","深圳坪山","光明城","平湖","西丽")
    if cat=="rail" and any(x in name for x in major):base=86
    return base

def build(raw,source):
    roads=[]; rails=[]; pois=[]
    for el in raw.get("elements",[]):
        tags=el.get("tags") or {}
        geom=el.get("geometry") or []
        if el.get("type")=="way" and tags.get("highway") in ROAD_TYPES and len(geom)>=2:
            cls=tags["highway"]
            rawpts=[[p["lon"],p["lat"]] for p in geom]
            if not any(in_city(x,y) for x,y in rawpts): continue
            name=tags.get("name:zh") or tags.get("name") or tags.get("ref") or ""
            tol={"motorway":0.00018,"trunk":0.00022,"primary":0.00030,"secondary":0.00048}[cls]
            pts=simplify(rawpts,tol)
            if cls=="secondary" and (not name or line_length(pts)<0.00075): continue
            if len(pts)>=2:
                roads.append({"c":cls,"n":name,"p":pts})
            continue
        if el.get("type")=="way" and tags.get("railway")=="rail" and len(geom)>=2:
            rawpts=[[p["lon"],p["lat"]] for p in geom]
            if not any(in_city(x,y) for x,y in rawpts): continue
            pts=simplify(rawpts,0.00032)
            if len(pts)>=2:rails.append({"n":tags.get("name:zh") or tags.get("name") or "铁路","p":pts})
            continue
        cat=poi_category(tags)
        if cat:
            pos=center_of(el)
            if not pos or not in_city(pos[0],pos[1]):continue
            name=tags.get("name:zh") or tags.get("name") or tags.get("name:en") or ""
            if not name:continue
            noise=("社区","公交","上客","下客","停车","地铁","巴士","警岗","派出所")
            if cat=="border" and (any(x in name for x in noise) or not ("口岸" in name or "管制站" in name)): continue
            if cat=="airport" and not ("宝安" in name or "深圳机场" in name): continue
            if cat in ("port","ferry") and not any(x.lower() in name.lower() for x in ("港","码头","port","terminal","蛇口","赤湾","大铲湾","盐田")): continue
            pois.append({"t":cat,"n":name,"p":pos,"q":poi_priority(cat,name)})

    # Deduplicate POIs by normalized name, preferring the higher-priority representation.
    dedup={}
    for p in sorted(pois,key=lambda x:-x["q"]):
        k=norm_name(p["n"])
        if not k:continue
        if k not in dedup:dedup[k]=p
    pois=list(dedup.values())

    # Prefer the canonical Shenzhen-side representation of duplicated crossings.
    compact=[]
    seen_spatial=[]
    for p in sorted(pois,key=lambda x:-x["q"]):
        if any(p["t"]==q["t"] and math.hypot(p["p"][0]-q["p"][0],p["p"][1]-q["p"][1])<0.0012 for q in seen_spatial):
            continue
        seen_spatial.append(p); compact.append(p)
    pois=compact

    # Limit minor rail stations to prevent a POI cloud; always keep high-priority hubs.
    rail_pois=sorted([p for p in pois if p["t"]=="rail"],key=lambda x:-x["q"])
    keep_rail=rail_pois[:18]
    keep_ids={id(p) for p in keep_rail}
    pois=[p for p in pois if p["t"]!="rail" or id(p) in keep_ids]

    # Pick one label anchor per important named road, choosing its longest segment.
    best={}
    for r in roads:
        if not r["n"] or r["c"] not in ("motorway","trunk","primary"):continue
        L=line_length(r["p"])
        if r["n"] not in best or L>best[r["n"]][0]:best[r["n"]]=(L,r)
    road_labels=[]
    for name,(L,r) in sorted(best.items(),key=lambda kv:-kv[1][0])[:36]:
        pts=r["p"]; idx=len(pts)//2
        road_labels.append({"n":name,"p":pts[idx],"c":r["c"]})

    result={
      "meta":{"source":"OpenStreetMap contributors via Overpass","generated_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"roads":len(roads),"rails":len(rails),"pois":len(pois)},
      "roads":roads,"rails":rails,"road_labels":road_labels,"pois":sorted(pois,key=lambda x:-x["q"])
    }
    return result

def main():
    raw,source=fetch()
    out=build(raw,source)
    JSON_OUT.write_text(json.dumps(out,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    OUT.write_text("window.SHENZHEN_TRANSPORT = "+json.dumps(out,ensure_ascii=False,separators=(",",":"))+";\n",encoding="utf-8")
    print(json.dumps(out["meta"],ensure_ascii=False))
    print("road labels:",len(out["road_labels"]))
    print("POIs:",[p["n"] for p in out["pois"][:30]])

if __name__=="__main__":
    main()
