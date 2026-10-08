#!/usr/bin/env python3
from __future__ import annotations
import io,json,re,xml.etree.ElementTree as ET
from pathlib import Path
from city_build_common import download_bytes, write_geojson

def get(url,params=None):
    return download_bytes(url, params=params, timeout=180)
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/dresden_local_2025.geojson"
PDF="https://www.polizei.sachsen.de/de/download/PKS-Atlas25_Grossstaedte.pdf"
WFS="https://kommisdd.dresden.de/net3/public/ogc.ashx"
NS={"wfs":"http://www.opengis.net/wfs/2.0","cls":"http://www.cardogis.com/kommisdd","gml":"http://www.opengis.net/gml/3.2"}

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
        if j is None or len(t)-j<9:continue
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

def parse_ring(pos):
    vals=[float(x) for x in re.split(r"\s+",(pos.text or "").strip()) if x]
    if len(vals)%2: raise ValueError("odd Dresden posList")
    # WFS EPSG:4326 uses lat lon axis order; GeoJSON requires lon lat.
    return [[round(vals[i+1],6),round(vals[i],6)] for i in range(0,len(vals),2)]

def polygon_coords(poly):
    ext=poly.find("./gml:exterior/gml:LinearRing/gml:posList",NS)
    if ext is None:return None
    rings=[parse_ring(ext)]
    for pos in poly.findall("./gml:interior/gml:LinearRing/gml:posList",NS):
        rings.append(parse_ring(pos))
    return rings

pdf=PdfReader(io.BytesIO(get(PDF)))
rows=parse(pdf.pages[2].extract_text() or "")
if len(rows)!=61:raise RuntimeError(f"expected 61 Dresden Stadtteile, got {len(rows)} missing? codes={sorted(rows)}")

xml=get(WFS,{
 "NODEID":"188","SERVICE":"WFS","VERSION":"2.0.0","REQUEST":"GetFeature",
 "TYPENAMES":"cls:L137","SRSNAME":"EPSG:4326"
})
root=ET.fromstring(xml)
features=[];seen=set()
for member in root.findall(".//wfs:member",NS):
    feat=list(member)[0]
    p={}
    for ch in list(feat):
        tag=ch.tag.split("}")[-1]
        if tag!="PrimaryGeometry":p[tag]=(ch.text or "").strip()
    code=str(p.get("blocknr","")).zfill(2)
    if code not in rows:continue
    polys=[]
    for poly in feat.findall(".//gml:Polygon",NS):
        rings=polygon_coords(poly)
        if rings:polys.append(rings)
    if not polys:
        raise RuntimeError(f"no geometry for Dresden {code} {p.get('bez')}")
    geom={"type":"Polygon","coordinates":polys[0]} if len(polys)==1 else {"type":"MultiPolygon","coordinates":polys}
    props={"city":"Dresden","state":"Sachsen","code":code,"name":p.get("bez_lang") or p.get("bez") or rows[code]["name_atlas"],**rows[code]}
    features.append({"type":"Feature","id":"dresden-"+code,"properties":props,"geometry":geom})
    seen.add(code)

if len(seen)!=61:raise RuntimeError(f"Dresden geometry join incomplete {len(seen)}/61 missing={sorted(set(rows)-seen)}")
out={"type":"FeatureCollection","meta":{
    "schema_version":1,
  "year":2025,"scope":"Dresden Stadtteile","feature_count":len(features),"district_count":len(seen),
 "crime_source":"Polizei Sachsen: Kriminalitätsatlas 2025 – Großstädte","crime_source_url":PDF,
 "geometry_source":"Landeshauptstadt Dresden OpenData WFS: Stadtteile","geometry_source_url":WFS+"?NODEID=188&SERVICE=WFS",
 "note":"Local violence uses 'Rohheitsdelikte und Straftaten gegen die persönliche Freiheit' as a proxy; it is not identical to BKA Gewaltkriminalität. Population is back-calculated from the atlas total-case frequency."
},"features":features}
write_geojson(OUT,out)
print(json.dumps({"features":len(features),"sample":[f["properties"] for f in features[:3]]},ensure_ascii=False,indent=2))
