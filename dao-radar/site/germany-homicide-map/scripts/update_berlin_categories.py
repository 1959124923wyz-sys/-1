#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, re, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
CASES=ROOT/"data/cases.json"
CACHE=ROOT/"data/geocode_cache.json"
LOOKBACK=max(1,min(int(os.getenv("BERLIN_LOOKBACK_DAYS","7")),90))
TODAY=datetime.now(timezone.utc).date()
CUTOFF=TODAY-timedelta(days=LOOKBACK)
KEEP_CUTOFF=TODAY-timedelta(days=90)
ARCHIVE="https://www.berlin.de/polizei/polizeimeldungen/archiv/2026/"
HEAD={"User-Agent":"GermanyCrimeMonitorBerlin/1.0 (+https://github.com/1959124923wyz-sys/-1)","Accept-Language":"de,en;q=0.8"}
ARTICLE_RE=re.compile(r"/polizei/polizeimeldungen/2026/pressemitteilung\.\d+\.php")
DATE_RE=re.compile(r"(\d{2})\.(\d{2})\.(20\d{2})")
STREET_RE=re.compile(r"\b([A-ZÄÖÜ][A-Za-zÄÖÜäöüß0-9.'’\- ]{1,65}?(?:straße|strasse|allee|weg|platz|gasse|damm|ring|ufer|chaussee|markt|stieg|graben|wall|steig))\b",re.I)
DISTRICTS=["Mitte","Friedrichshain-Kreuzberg","Pankow","Charlottenburg-Wilmersdorf","Spandau","Steglitz-Zehlendorf","Tempelhof-Schöneberg","Neukölln","Treptow-Köpenick","Marzahn-Hellersdorf","Lichtenberg","Reinickendorf"]

ROB=re.compile(r"\bRaub\w*|ausgeraubt|überfallen|Überfall|räuberisch",re.I)
SEX=re.compile(r"Vergewaltig|sexuell\w*\s+(?:Nötigung|Übergriff|Belästigung)|sexueller\s+Übergriff",re.I)
PROP=re.compile(r"Einbruch|Einbrecher|Diebstahl|gestohlen|entwendet|aufgebrochen|Fahrrad.*(?:weg|gestohlen)|Auto.*(?:aufgebrochen|gestohlen)",re.I)
VIOL=re.compile(r"Messer|Stich|Schuss|Schüsse|Schusswaffe|lebensgefährlich\s+verletzt|schwer\w*\s+verletzt|Körperverletzung|angegriffen|Angriff",re.I)
TRAFFIC=re.compile(r"Verkehrsunfall|Unfall|Radfahrer|Fußgänger|E-Scooter|Motorrad",re.I)
NON_EVENT=re.compile(r"Zeugen gesucht|wer erkennt|Öffentlichkeitsfahndung|Fahndung|Prävention|Statistik|Bilanz|Polizei bittet um Mithilfe",re.I)
FATAL=re.compile(r"Tötungsdelikt|Totschlag|Mordkommission|\bMord\b|verstarb|verstorben|tödlich verletzt|tot aufgefunden",re.I)

def load(p,default):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return default

def save(p,x):
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def clean(s):
    return re.sub(r"\s+"," ",s or "").strip()

def classify_title(title):
    if TRAFFIC.search(title):return None
    if ROB.search(title):return ("robbery","Raub/Überfall",4)
    if SEX.search(title):return ("sexual","Sexualdelikt",4)
    if PROP.search(title):return ("property","Diebstahl/Einbruch",2)
    if VIOL.search(title):return ("violence","Schwere Gewalttat",4)
    return None

def refine(category,title,text):
    joined=title+" "+text[:2600]
    if TRAFFIC.search(title):return None
    if category=="robbery":
        return ("robbery","Raub/Überfall",4) if ROB.search(joined) else None
    if category=="sexual":
        if re.search(r"Vergewaltig",joined,re.I):return ("sexual","Vergewaltigung",4)
        if re.search(r"sexuell\w*\s+Nötigung",joined,re.I):return ("sexual","Sexuelle Nötigung",4)
        return ("sexual","Sexualdelikt",4)
    if category=="property":
        if re.search(r"Wohnungseinbruch|Einbruch in (?:Wohnung|Haus)|Einbrecher",joined,re.I):sub="Wohnungseinbruch"
        elif re.search(r"Fahrrad|Pedelec|E-Bike",joined,re.I):sub="Fahrraddiebstahl"
        elif re.search(r"Auto|Pkw|Fahrzeug",joined,re.I):sub="Fahrzeug-/Autodiebstahl"
        else:sub="Diebstahl/Einbruch"
        return ("property",sub,2)
    if category=="violence":
        # completed homicides are handled by the homicide pipeline; non-fatal attempts stay as violence
        if FATAL.search(joined) and re.search(r"verstarb|verstorben|tödlich verletzt|tot aufgefunden",joined,re.I):
            return None
        if not VIOL.search(joined):return None
        if re.search(r"Messer|Stich",joined,re.I):sub="Messer-/Stichangriff"
        elif re.search(r"Schuss|Schusswaffe",joined,re.I):sub="Schusswaffengewalt"
        elif re.search(r"versuchter Totschlag|versuchtes Tötungsdelikt",joined,re.I):sub="Versuchtes Tötungsdelikt"
        else:sub="Schwere Körperverletzung"
        return ("violence",sub,4)
    return None

def article_date(text):
    m=re.search(r"Polizeimeldung vom\s+(\d{2})\.(\d{2})\.(20\d{2})",text,re.I)
    if not m:return None
    try:return date(int(m.group(3)),int(m.group(2)),int(m.group(1)))
    except ValueError:return None

def district_from(text):
    head=text[:1200]
    for d in DISTRICTS:
        if d in head:return d
    return "Berlin"

def street_from(text):
    core=re.split(r"Weitere Informationen|Kontakt|Direkt zur Kontaktinformation",text,maxsplit=1,flags=re.I)[0]
    hits=[]
    for m in STREET_RE.finditer(core):
        v=clean(m.group(1)).strip(" ,.-")
        if len(v)>=4 and not re.search(r"Platz der Luftbrücke",v,re.I):
            hits.append((m.start(),v))
    return hits[0][1] if hits else ""

def geocode(session,q,cache,last):
    if q in cache:return cache[q],last
    wait=1.15-(time.monotonic()-last)
    if wait>0:time.sleep(wait)
    last=time.monotonic()
    try:
        r=session.get("https://nominatim.openstreetmap.org/search",params={"q":q,"format":"jsonv2","limit":1,"countrycodes":"de","addressdetails":1},headers=HEAD,timeout=30)
        r.raise_for_status();a=r.json()
        hit=None if not a else {"lat":float(a[0]["lat"]),"lon":float(a[0]["lon"]),"address":a[0].get("address",{})}
    except Exception as e:
        print("WARN geocode",q,e);hit=None
    cache[q]=hit;save(CACHE,cache)
    return hit,last

payload=load(CASES,{"meta":{},"cases":[]})
cases=payload.get("cases",[])
cache=load(CACHE,{})
existing_urls={c.get("source_url") for c in cases if c.get("source_url")}
session=requests.Session()
candidates=[]
seen=set()

# Archive has ~20 items/page. Scan until listing dates are older than the requested lookback.
for page_no in range(1,36):
    url=f"{ARCHIVE}?page_at_1_0={page_no}"
    r=session.get(url,headers=HEAD,timeout=30);r.raise_for_status()
    soup=BeautifulSoup(r.text,"html.parser")
    anchors=soup.find_all("a",href=ARTICLE_RE)
    if not anchors:break
    page_dates=[]
    for a in anchors:
        href=urljoin(url,a.get("href"))
        title=clean(a.get_text(" ",strip=True))
        if not title or href in seen or href in existing_urls:continue
        seen.add(href)
        parent=a.parent
        context=clean(parent.get_text(" ",strip=True) if parent else title)
        dm=DATE_RE.search(context)
        pub=None
        if dm:
            try:pub=date(int(dm.group(3)),int(dm.group(2)),int(dm.group(1)));page_dates.append(pub)
            except ValueError:pass
        seed=classify_title(title)
        if seed:
            candidates.append((href,title,pub,seed))
    if page_dates and min(page_dates)<CUTOFF-timedelta(days=3):
        break
    time.sleep(.08)

added=[]
last=0.0
for href,title,pub,seed in candidates:
    try:
        r=session.get(href,headers=HEAD,timeout=30);r.raise_for_status()
        soup=BeautifulSoup(r.text,"html.parser")
        main=soup.find("article") or soup.find("main") or soup.body or soup
        for t in main(["script","style","nav","footer","form","svg","noscript"]):t.decompose()
        text=clean(main.get_text(" ",strip=True))
    except Exception as e:
        print("WARN article",href,e);continue
    d=article_date(text) or pub or TODAY
    if d<CUTOFF or d>TODAY:continue
    info=refine(seed[0],title,text)
    if not info:continue
    category,sub,severity=info
    district=district_from(text)
    privacy=(category=="sexual")
    street=street_from(text)
    if privacy:
        location=f"{district}（隐私保护：仅显示城区级）"
        query=f"{district}, Berlin, Germany"
        precision="district-privacy"
        location_type="Approximate / privacy protected"
    else:
        location=street or district
        query=f"{street}, Berlin, Germany" if street else f"{district}, Berlin, Germany"
        precision="street" if street else "district"
        location_type="Tatort / reported location"
    status="suspected" if re.search(r"Verdacht|mutmaßlich|soll\w*",text[:2500],re.I) else "confirmed"
    summary_prefix={"robbery":"柏林警方公开通报的抢劫案件","sexual":"柏林警方公开通报的性犯罪案件","violence":"柏林警方公开通报的严重暴力案件","property":"柏林警方公开通报的盗窃/财产犯罪案件"}[category]
    c={
      "id":f"{d.isoformat()}-{category}-berlin-{hashlib.sha1(href.encode()).hexdigest()[:10]}",
      "event_date":d.isoformat(),"publication_date":d.isoformat(),"city":"Berlin","state":"Berlin",
      "location":location,"geocode_address":query,"precision":precision,"location_type":location_type,
      "status":status,"offense":sub,"subcategory":sub,"category":category,
      "category_label":{"robbery":"抢劫","sexual":"性犯罪","violence":"严重暴力","property":"盗窃/财产犯罪"}[category],
      "severity":severity,"summary":f"{summary_prefix}：{title[:180]}",
      "source_agency":"Polizei Berlin","source_url":href,"lat":None,"lon":None,
      "date_confidence":"publication_date","privacy_protected":privacy
    }
    hit,last=geocode(session,query,cache,last)
    if not hit and not privacy:
        hit,last=geocode(session,f"{district}, Berlin, Germany",cache,last)
        if hit:c["geocode_precision"]="district-fallback"
    if hit:
        c["lat"],c["lon"]=hit["lat"],hit["lon"]
        c.setdefault("geocode_precision",precision)
    cases.append(c);existing_urls.add(href);added.append(c)
    print("ADD",category,d.isoformat(),district,location,title)

cases=[c for c in cases if KEEP_CUTOFF<=date.fromisoformat(c["event_date"])<=TODAY]
cases.sort(key=lambda c:(c["event_date"],c.get("city",""),c.get("category","")),reverse=True)
counts={k:sum(1 for c in cases if c.get("category")==k) for k in ("homicide","violence","robbery","sexual","property")}
payload["cases"]=cases
payload["meta"].update({
  "generated_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
  "case_count":len(cases),
  "geocoded_count":sum(c.get("lat") is not None and c.get("lon") is not None for c in cases),
  "category_counts":counts,
  "schema_version":4,
  "coverage_note":"Public-source monitor. Includes targeted Presseportal police releases plus direct Polizei Berlin archive coverage. Sexual-crime locations are privacy-reduced.",
  "method":"Rolling 90-day monitor using multiple public police/prosecutor sources, targeted category parsing, deduplication, cached geocoding and privacy-reduced sexual-crime locations."
})
save(CASES,payload)
print("SUMMARY","lookback",LOOKBACK,"candidates",len(candidates),"added",len(added),"berlin_added", {k:sum(1 for c in added if c["category"]==k) for k in ("violence","robbery","sexual","property")},"total",len(cases),"geocoded",payload["meta"]["geocoded_count"])

# backfill trigger
