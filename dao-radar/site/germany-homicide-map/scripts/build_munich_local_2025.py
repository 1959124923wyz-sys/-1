#!/usr/bin/env python3
from __future__ import annotations
import csv, io, json, re
from pathlib import Path
from pyproj import Transformer
from city_build_common import download_json as get_json, download_text as get_text, write_geojson


ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/munich_local_2025.geojson"
WFS="https://geoportal.muenchen.de/geoserver/gsm_wfs/ows?outputFormat=application%2Fjson&request=GetFeature&service=WFS&typeName=gsm_wfs%3Avablock_stadtbezirk&version=1.0.0"
POP_RESOURCE="a641ce6a-4e01-4f4b-9976-1ae6a47e3762"
POP_API=f"https://opendata.muenchen.de/de/api/3/action/datastore_search?resource_id={POP_RESOURCE}&limit=100"
CRIME_SOURCE="https://stadt.muenchen.de/dam/jcr:6291ac42-463d-4267-b436-c4b1a3313454/jt260904.pdf"

# Official Statistisches Amt München / Polizeipräsidium München table:
# total, life, sexual, violence-broad (Rohheitsdelikte + offences against personal freedom),
# simple theft, aggravated theft, fraud/forgery, adjusted total.
RAW={
1:("Altstadt - Lehel",[6863,1,145,1273,2209,538,964,6756]),
2:("Ludwigsvorstadt - Isarvorstadt",[9852,6,251,1791,1700,508,1392,8576]),
3:("Maxvorstadt",[4454,0,106,968,882,455,423,4352]),
4:("Schwabing West",[1859,1,64,368,326,291,304,1852]),
5:("Au - Haidhausen",[3628,2,92,679,777,468,482,3550]),
6:("Sendling",[1658,1,72,334,262,275,225,1648]),
7:("Sendling - Westpark",[2007,0,79,409,293,359,278,1996]),
8:("Schwanthalerhöhe",[1960,1,39,350,235,186,267,1512]),
9:("Neuhausen - Nymphenburg",[3496,4,110,639,709,703,443,3482]),
10:("Moosach",[3024,0,78,508,916,454,487,3021]),
11:("Milbertshofen - Am Hart",[3254,2,118,717,594,432,591,3242]),
12:("Schwabing - Freimann",[6012,1,119,984,999,453,902,4775]),
13:("Bogenhausen",[2818,1,119,528,480,565,381,2800]),
14:("Berg am Laim",[2335,0,70,591,315,305,298,2310]),
15:("Trudering - Riem",[2993,2,96,548,691,418,416,2979]),
16:("Ramersdorf - Perlach",[4863,5,155,1087,978,542,944,4822]),
17:("Obergiesing - Fasangarten",[2550,0,68,518,466,321,480,2538]),
18:("Untergiesing - Harlaching",[2008,0,65,370,312,334,294,1938]),
19:("Thalkirchen - Obersendling - Forstenried - Fürstenried - Solln",[2698,6,126,559,488,427,409,2683]),
20:("Hadern",[1357,0,61,279,202,248,153,1350]),
21:("Pasing - Obermenzing",[2962,2,94,583,656,534,324,2912]),
22:("Aubing - Lochhausen - Langwied",[1779,1,73,474,324,303,155,1764]),
23:("Allach - Untermenzing",[938,3,36,245,139,149,125,933]),
24:("Feldmoching - Hasenbergl",[2064,2,104,485,412,326,222,2052]),
25:("Laim",[2178,0,69,446,462,359,290,2151]),
}

def norm(s):
    return re.sub(r"[^a-z0-9]+","",str(s or "").lower()
        .replace("ä","ae").replace("ö","oe").replace("ü","ue").replace("ß","ss"))

def parse_population():
    payload=get_json(POP_API)
    records=(payload.get("result") or {}).get("records") or []
    out={}
    for row in records:
        # Find district number from any value; official table contains 25 district rows.
        joined=" ".join(str(v or "") for v in row.values())
        m=re.search(r"\b(\d{1,2})\b",joined)
        if not m:continue
        n=int(m.group(1))
        if not 1<=n<=25:continue
        pop=None
        for k,v in row.items():
            nk=norm(k)
            if ("einwohner" in nk or nk=="bevolkerung" or nk=="bevoelkerung") and "dichte" not in nk and "anteil" not in nk:
                raw=re.sub(r"[^0-9]","",str(v or ""))
                if raw:
                    candidate=int(raw)
                    if candidate>1000:pop=candidate;break
        if pop:out[n]=pop
    if len(out)<24:
        raise RuntimeError(f"population join incomplete: {len(out)} districts; fields={list(records[0].keys()) if records else []}; sample={records[:2]}")
    return out

def district_no(props):
    # Prefer explicit number-like fields.
    for k,v in props.items():
        nk=norm(k)
        if any(x in nk for x in ("bezirk", "nummer", "nr")):
            m=re.fullmatch(r"0*(\d{1,2})",str(v or "").strip())
            if m and 1<=int(m.group(1))<=25:return int(m.group(1))
    # Fallback to name matching.
    strings=" | ".join(str(v or "") for v in props.values())
    ns=norm(strings)
    for n,(name,_) in RAW.items():
        if norm(name) and norm(name) in ns:return n
    return None

# The WFS publishes metre-based ETRS89/UTM zone 32 coordinates (EPSG:25832).
# Leaflet/GeoJSON require longitude/latitude in EPSG:4326. Merely placing the
# UTM numbers into a GeoJSON Polygon makes the entire Munich layer invisible.
TO_WGS84=Transformer.from_crs("EPSG:25832","EPSG:4326",always_xy=True)

def to_wgs84_coordinates(node):
    """Recursively convert a Polygon/MultiPolygon coordinate tree."""
    if isinstance(node,(list,tuple)) and len(node)>=2 and isinstance(node[0],(int,float)) and isinstance(node[1],(int,float)):
        easting,northing=float(node[0]),float(node[1])
        if 10.8 <= easting <= 12.5 and 47.5 <= northing <= 49.0:
            # Defensive pass-through if the source service switches to WGS84.
            longitude,latitude=easting,northing
        else:
            if not (600000 <= easting <= 800000 and 5200000 <= northing <= 5500000):
                raise ValueError(f"Unexpected Munich source coordinates {(easting,northing)}; refusing to publish invalid geometry")
            longitude,latitude=TO_WGS84.transform(easting,northing)
        if not (11.1 < longitude < 12.1 and 47.8 < latitude < 48.5):
            raise ValueError(f"Munich vertex outside expected WGS84 bounds: {(longitude,latitude)}")
        return [round(longitude,7),round(latitude,7)]
    if isinstance(node,(list,tuple)):
        return [to_wgs84_coordinates(child) for child in node]
    raise TypeError(f"Invalid Munich coordinate node: {node!r}")

pop=parse_population()
geo=get_json(WFS)

# The WFS can return a district as several polygon records. Collapse those
# parts into one stable Feature per Stadtbezirk so IDs remain unique and the
# browser treats each district as one selectable unit.
parts={n:[] for n in RAW}
for f in geo.get("features",[]):
    props=f.get("properties") or {}
    n=district_no(props)
    if n is None or n not in RAW:continue
    geom=f.get("geometry") or {}
    if geom.get("type")=="Polygon":
        parts[n].append(geom.get("coordinates") or [])
    elif geom.get("type")=="MultiPolygon":
        parts[n].extend(geom.get("coordinates") or [])

features=[]
seen=set()
for n in sorted(RAW):
    polygons=[p for p in parts.get(n,[]) if p]
    if not polygons:continue
    name,vals=RAW[n]
    total,life,sexual,violent_broad,theft_simple,theft_aggravated,fraud,adjusted=vals
    population=pop.get(n)
    if not population:continue

    def metric(cases):
        return {"cases":int(cases),"rate":round(cases/population*100000,1)}

    p={
        "city":"München","state":"Bayern","district_no":n,"name":name,"population":population,
        "crime_total":metric(total),
        "violence_proxy":metric(violent_broad),
        "sexual":metric(sexual),
        "life":metric(life),
        "property_total":metric(theft_simple+theft_aggravated),
        "simple_theft":metric(theft_simple),
        "aggravated_theft":metric(theft_aggravated),
        "fraud":metric(fraud),
        "adjusted_total":metric(adjusted),
    }
    # All district polygons must be longitude/latitude for Leaflet.
    transformed=to_wgs84_coordinates(polygons)
    geometry={"type":"Polygon","coordinates":transformed[0]} if len(transformed)==1 else {"type":"MultiPolygon","coordinates":transformed}
    features.append({"type":"Feature","id":f"munich-{n:02d}","properties":p,"geometry":geometry})
    seen.add(n)

missing=sorted(set(RAW)-seen)
if missing or len(features)!=25:
    raise RuntimeError(f"expected 25 Munich district features; features={len(features)} missing={missing}")

out={
  "type":"FeatureCollection",
  "meta":{
    "schema_version":1,
        "year":2025,"scope":"München Stadtbezirke","feature_count":len(features),"district_count":len(seen),
    "crime_source":"Statistisches Amt München / Polizeipräsidium München: Straftaten in den Stadtbezirken 2025",
    "crime_source_url":CRIME_SOURCE,
    "population_source":"Open Data Portal München: Bevölkerung in den Stadtbezirken (31.12.2024)",
    "population_source_url":POP_API,
    "geometry_source":"GeodatenService München: Stadtbezirke WFS",
    "geometry_source_crs":"EPSG:25832",
    "published_geometry_crs":"EPSG:4326",
    "geometry_source_url":WFS,
    "note":"Violence local layer uses 'Rohheitsdelikte und Straftaten gegen die persönliche Freiheit' as a clearly labelled local proxy; it is not identical to BKA Gewaltkriminalität."
  },
  "features":features
}
write_geojson(OUT,out)
print(json.dumps({"features":len(features),"districts":len(seen),"pop":len(pop),"names":[x["properties"]["name"] for x in features[:4]]},ensure_ascii=False,indent=2))
