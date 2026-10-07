#!/usr/bin/env python3
import io,re,requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pypdf import PdfReader

PAGE="https://www.polizei.sachsen.de/de/polizeiliche-kriminalstatistik-2025-41049.html"
H={"User-Agent":"GermanyCrimeMonitor/1.0 (+https://github.com/1959124923wyz-sys/-1)"}
html=requests.get(PAGE,headers=H,timeout=90);html.raise_for_status()
s=BeautifulSoup(html.text,"html.parser")
links=[]
for a in s.find_all("a",href=True):
    t=" ".join(a.get_text(" ",strip=True).split())
    if "Großstädte" in t or "Grossstädte" in t or "Grossstaedte" in t:
        links.append((t,urljoin(PAGE,a["href"])))
if not links:
    for a in s.find_all("a",href=True):
        href=a["href"]
        if "gross" in href.lower() or "gro" in href.lower():
            links.append((a.get_text(" ",strip=True),urljoin(PAGE,href)))
print("links",links)
if not links: raise SystemExit("No Grossstädte PDF link found")
url=links[-1][1]
r=requests.get(url,headers=H,timeout=120);r.raise_for_status()
print("pdf",url,"bytes",len(r.content),r.headers.get("content-type"))
pdf=PdfReader(io.BytesIO(r.content))
print("pages",len(pdf.pages))
for i,p in enumerate(pdf.pages):
    txt=re.sub(r"[ \t]+"," ",(p.extract_text() or "").replace("\x00",""))
    print(f"\n===== PAGE {i+1} =====\n{txt[:18000]}")


print("\n===== OFFICIAL CITY GEOMETRY DISCOVERY =====")
# Leipzig CKAN
try:
    u="https://opendata.leipzig.de/api/3/action/package_show?id=geodaten-ortsteile-leipzig"
    j=requests.get(u,headers=H,timeout=60).json()
    for x in (j.get("result") or {}).get("resources",[]):
        print("LEIPZIG",x.get("format"),x.get("name"),x.get("url"))
except Exception as e:
    print("LEIPZIG_ERR",repr(e))

# Chemnitz metadata / GovData resource discovery.
for label,u in [
    ("CHEMNITZ","https://www.govdata.de/suche/daten/stadtteile74048"),
    ("CHEMNITZ_META","https://www-11.stadt-chemnitz.de/wss/service/MetaDoku/guest/Internet/HTML/Stadtteile.html"),
    ("DRESDEN_META","https://kommisdd.dresden.de/net3/public/ogc.ashx?NODEID=188&RenderHint=TargetHtml&Service=Ikx"),
]:
    try:
        rr=requests.get(u,headers=H,timeout=60);rr.raise_for_status()
        ss=BeautifulSoup(rr.text,"html.parser")
        print(label,"STATUS",rr.status_code,"LEN",len(rr.text))
        for a in ss.find_all("a",href=True):
            href=urljoin(u,a["href"]);txt=" ".join(a.get_text(" ",strip=True).split())
            low=(href+" "+txt).lower()
            if any(k in low for k in ["geojson","featureserver","mapserver","wfs","download","shapefile","arcgis","json"]):
                print(label,"LINK",txt[:120],href)
    except Exception as e:
        print(label+"_ERR",repr(e))


print("\n===== GEOMETRY SAMPLE PROPERTIES =====")
for label,u in [
 ("LEIPZIG_GEO","https://static.leipzig.de/fileadmin/mediendatenbank/leipzig-de/Stadt/02.1_Dez1_Allgemeine_Verwaltung/12_Statistik_und_Wahlen/Geodaten/Ortsteile_Leipzig_UTM33N.json"),
 ("CHEMNITZ_GEO","https://portal-chemnitz.opendata.arcgis.com/api/download/v1/items/42a13d7737f649409e981db3f0ba1455/geojson?layers=0"),
]:
    try:
        rr=requests.get(u,headers=H,timeout=90);rr.raise_for_status();jj=rr.json()
        print(label,"features",len(jj.get("features",[])),"crs",jj.get("crs"))
        print(label,"sample",(jj.get("features") or [{}])[0].get("properties"))
    except Exception as e: print(label+"_ERR",repr(e))

dresden_candidates=[
 "https://kommisdd.dresden.de/net3/public/ogc.ashx?NODEID=188&SERVICE=WFS&REQUEST=GetCapabilities",
 "https://kommisdd.dresden.de/net3/public/ogc.ashx?NODEID=188&Service=WFS&Request=GetCapabilities",
 "https://kommisdd.dresden.de/net3/public/ogc.ashx?NODEID=188&service=WFS&request=GetCapabilities",
 "https://kommisdd.dresden.de/net3/public/ogc.ashx?NODEID=188&Service=GeoJSON",
]
for u in dresden_candidates:
    try:
        rr=requests.get(u,headers=H,timeout=60)
        print("DRESDEN_PROBE",rr.status_code,rr.headers.get("content-type"),len(rr.content),rr.url)
        print(rr.text[:1200].replace("\n"," "))
    except Exception as e: print("DRESDEN_PROBE_ERR",repr(e),u)


print("\n===== DIRECT GEOMETRY QUERY =====")
try:
    u="https://services6.arcgis.com/jiszdsDupTUO3fSM/arcgis/rest/services/Stadtteile_FL_1/FeatureServer/0/query"
    rr=requests.get(u,headers=H,params={"where":"1=1","outFields":"*","f":"geojson","outSR":"4326"},timeout=90)
    print("CHEMNITZ_QUERY",rr.status_code,rr.headers.get("content-type"),len(rr.content))
    jj=rr.json(); print("CHEMNITZ_QUERY features",len(jj.get("features",[])),"sample",(jj.get("features") or [{}])[0].get("properties"))
except Exception as e: print("CHEMNITZ_QUERY_ERR",repr(e))

try:
    import xml.etree.ElementTree as ET
    cap=requests.get("https://kommisdd.dresden.de/net3/public/ogc.ashx",headers=H,params={"NODEID":"188","SERVICE":"WFS","REQUEST":"GetCapabilities"},timeout=90)
    root=ET.fromstring(cap.content)
    ns={"wfs":"http://www.opengis.net/wfs/2.0"}
    names=[]
    for ft in root.findall(".//wfs:FeatureType",ns):
        n=ft.findtext("wfs:Name",default="",namespaces=ns);t=ft.findtext("wfs:Title",default="",namespaces=ns)
        if n: names.append((n,t))
    print("DRESDEN_TYPES",names)
    if names:
        for n,t in names[:4]:
            rr=requests.get("https://kommisdd.dresden.de/net3/public/ogc.ashx",headers=H,params={
                "NODEID":"188","SERVICE":"WFS","VERSION":"2.0.0","REQUEST":"GetFeature",
                "TYPENAMES":n,"COUNT":"3","SRSNAME":"EPSG:4326","OUTPUTFORMAT":"application/json"
            },timeout=90)
            print("DRESDEN_GET",n,rr.status_code,rr.headers.get("content-type"),len(rr.content),rr.text[:600].replace("\n"," "))
            if "json" in (rr.headers.get("content-type") or "").lower():
                jj=rr.json();print("DRESDEN_SAMPLE",n,(jj.get("features") or [{}])[0].get("properties"))
except Exception as e: print("DRESDEN_DIRECT_ERR",repr(e))


print("\n===== DRESDEN DEFAULT GML SAMPLE =====")
try:
    rr=requests.get("https://kommisdd.dresden.de/net3/public/ogc.ashx",headers=H,params={
      "NODEID":"188","SERVICE":"WFS","VERSION":"2.0.0","REQUEST":"GetFeature",
      "TYPENAMES":"cls:L137","COUNT":"2","SRSNAME":"EPSG:4326"
    },timeout=90)
    print("DRESDEN_GML",rr.status_code,rr.headers.get("content-type"),len(rr.content))
    print(rr.text[:7000].replace("\n"," "))
except Exception as e: print("DRESDEN_GML_ERR",repr(e))
