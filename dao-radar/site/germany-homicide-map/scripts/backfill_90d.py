#!/usr/bin/env python3
from __future__ import annotations
import hashlib, html, json, os, re, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
CASES=ROOT/"data/cases.json"
CACHE=ROOT/"data/geocode_cache.json"
WINDOW=90
TODAY=datetime.now(timezone.utc).date()
CUTOFF=TODAY-timedelta(days=WINDOW)
CONTACT=os.getenv("APP_CONTACT","https://github.com/")
HEAD={"User-Agent":f"GermanyHomicideMonitorBackfill/1.0 ({CONTACT})","Accept-Language":"de,en;q=0.8"}
SEEDS=[
 "https://www.presseportal.de/blaulicht/st/T%C3%B6tungsdelikt",
 "https://www.presseportal.de/blaulicht/st/Mordkommission",
 "https://www.presseportal.de/blaulicht/st/Totschlag",
]
CAND=re.compile(r"Tötungsdelikt|Totschlag|Mordkommission|\bMord\b|Tötung|erschossen|erstochen|tödlich\w*\s+verletzt|Leichnam|Körperverletzung\s+mit\s+Todesfolge|tödliche\s+Auseinandersetzung",re.I)
DEATH=re.compile(r"verstarb|verstorben|\bstarb\b|\bgetötet\b|tödlich\w*\s+verletzt|tot\s+aufgefunden|\bLeichnam\b|erschossen|erstochen|Tod\s+des|tödliche\s+Auseinandersetzung",re.I)
HOM=re.compile(r"Tötungsdelikt|Totschlag|Mordkommission|\bMord(?:es|verdacht|vorwurf)?\b|\bTötung\b|\bgetötet\b|Körperverletzung\s+mit\s+Todesfolge|tödliche\s+Auseinandersetzung",re.I)
ATT=re.compile(r"versucht\w*\s+(?:Mord|Totschlag|Tötungsdelikt)",re.I)
DONE=re.compile(r"vollendet\w*|verstarb|verstorben|\bstarb\b|tödlich\w*\s+verletzt|\bgetötet\b|\bLeichnam\b|Tod\s+des|Körperverletzung\s+mit\s+Todesfolge",re.I)
OLD=re.compile(r"Cold\s*Case|Aktenzeichen\s+XY|vor\s+\w+\s+Jahr|aus\s+dem\s+Jahr\s+20(?:0\d|1\d|2[0-5])",re.I)
STREET=re.compile(r"\b([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-.' ]{1,55}?(?:straße|strasse|allee|weg|platz|gasse|damm|ring|ufer|chaussee|markt))\b",re.I)
NUMDATE=re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(20\d{2})(?!\d)")
TEXTDATE=re.compile(r"(?<!\d)(\d{1,2})\.\s*(Januar|Februar|März|Maerz|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)(?:\s+(20\d{2}))?",re.I)
MONTHS={"januar":1,"februar":2,"märz":3,"maerz":3,"april":4,"mai":5,"juni":6,"juli":7,"august":8,"september":9,"oktober":10,"november":11,"dezember":12}

def load(p,default):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return default
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def clean(s):
    return re.sub(r"\s+"," ",BeautifulSoup(html.unescape(s or ""),"html.parser").get_text(" ",strip=True)).strip()
def parse_pub(soup,text):
    vals=[]
    for tag in soup.find_all(["meta","time"]):
        v=tag.get("content") or tag.get("datetime") or ""
        if v: vals.append(v)
    for v in vals:
        try:
            z=v.replace("Z","+00:00")
            d=datetime.fromisoformat(z)
            if 2020<=d.year<=TODAY.year:return d.date()
        except Exception:pass
    m=NUMDATE.search(text[:1800])
    if m:
        try:return date(int(m.group(3)),int(m.group(2)),int(m.group(1)))
        except ValueError:pass
    return TODAY
def event_date(text,published):
    m=re.search(r"Tatzeit:\s*(?:\w+,\s*)?(\d{1,2})\.\s*([A-Za-zÄÖÜäöü]+)\s+(20\d{2})",text,re.I)
    if m:
        mm=MONTHS.get(m.group(2).lower()) or MONTHS.get(m.group(2).lower().replace("ä","ae"))
        if mm:
            try:return date(int(m.group(3)),mm,int(m.group(1))),"high"
            except ValueError:pass
    candidates=[]
    def add(x,start,end):
        if x>TODAY or x<published-timedelta(days=120):return
        around=text[max(0,start-220):min(len(text),end+300)]
        after=text[end:min(len(text),end+220)]
        score=0
        if re.search(r"Tatzeit|Tatort",around,re.I):score+=10
        if re.search(r"getötet|tödlich|verstarb|verstorben|\bstarb\b|erschossen|erstochen",after,re.I):score+=12
        if re.search(r"Tötungsdelikt|Totschlag|\bMord\b|Mordkommission|Körperverletzung\s+mit\s+Todesfolge",around,re.I):score+=5
        if re.search(r"festgenommen|Festnahme|Haft|Haftrichter|Untersuchungshaft|Folgemeldung|Nachtrag|Durchsuchung",after,re.I):score-=6
        candidates.append((score,x))
    for m in NUMDATE.finditer(text):
        try:x=date(int(m.group(3)),int(m.group(2)),int(m.group(1)))
        except ValueError:continue
        add(x,m.start(),m.end())
    for m in TEXTDATE.finditer(text):
        mm=MONTHS.get(m.group(2).lower()) or MONTHS.get(m.group(2).lower().replace("ä","ae"))
        if not mm:continue
        try:x=date(int(m.group(3) or published.year),mm,int(m.group(1)))
        except ValueError:continue
        add(x,m.start(),m.end())
    if candidates:
        score,x=max(candidates,key=lambda z:(z[0],-z[1].toordinal()))
        return x,("high" if score>=8 else "medium")
    return published,"publication_date"
def city_for(title,text,url):
    if "berlin.de" in url:return "Berlin"
    m=re.search(r"(?:^|\s)([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-./ ]{1,60})\s*\(ots\)",text[:1000])
    if m:return m.group(1).strip(" -/,.").split("/")[0].strip()
    m=re.search(r"POL-[A-ZÄÖÜ0-9]+:\s*(?:\d+[- ]+)?([^:/\-]{2,55})",title)
    if m:return m.group(1).strip()
    return ""
def location_for(text,city):
    core=re.split(r"Rückfragen|Pressekontakt|Pressestelle|Original-Content|Kontakt:",text,maxsplit=1,flags=re.I)[0]
    m=re.search(r"Tatort:\s*([^\n\r<]{3,120})",core,re.I)
    if m:
        v=re.split(r"(?:Gestern|Heute|Am\s|Zeit:)",m.group(1))[0].strip(" .,-")
        if 2<len(v)<100:return v,f"{v}, {city}, Germany","reported-place"
    m=STREET.search(core)
    if m:
        v=m.group(1).strip()
        return v,f"{v}, {city}, Germany","street"
    return city,f"{city}, Germany","city"
def classify(title,text):
    alltext=title+" "+text
    if OLD.search(title) and not re.search(r"2026",title):return False,""
    if not CAND.search(alltext):return False,""
    if not (DEATH.search(alltext) and HOM.search(alltext)):return False,""
    if ATT.search(alltext) and not DONE.search(alltext):return False,""
    status="suspected" if re.search(r"Verdacht|mutmaßlich|dringend\s+tatverdächtig|Hinweise?\s+auf",alltext,re.I) else "confirmed"
    return True,status
def geocode(session,q,cache,last):
    if q in cache:return cache[q],last
    wait=15.5-(time.monotonic()-last)
    if wait>0:time.sleep(wait)
    last=time.monotonic()
    try:
        r=session.get("https://nominatim.openstreetmap.org/search",params={"q":q,"format":"jsonv2","limit":1,"countrycodes":"de","addressdetails":1},headers=HEAD,timeout=30)
        r.raise_for_status(); a=r.json()
        hit=None if not a else {"lat":float(a[0]["lat"]),"lon":float(a[0]["lon"]),"address":a[0].get("address",{})}
    except Exception as e:
        print("WARN geocode",q,e);hit=None
    cache[q]=hit;save(CACHE,cache);return hit,last

session=requests.Session()
# Discover Presseportal pagination and collect article URLs.
articles=set()
for seed in SEEDS:
    root_path=urlparse(seed).path
    queue=[seed];visited=set()
    while queue and len(visited)<12:
        page=queue.pop(0)
        if page in visited:continue
        visited.add(page)
        try:
            r=session.get(page,headers=HEAD,timeout=30);r.raise_for_status()
        except Exception as e:
            print("WARN listing",page,e);continue
        soup=BeautifulSoup(r.text,"html.parser")
        for a in soup.find_all("a",href=True):
            href=urljoin(page,a["href"])
            p=urlparse(href)
            if re.search(r"/blaulicht/pm/\d+/\d+",p.path):
                articles.add(href.split("?")[0])
            label=clean(a.get_text(" ",strip=True))
            if p.path==root_path and ("?" in href) and (label.isdigit() or "Nächste" in label or "Weiter" in label):
                if href not in visited and href not in queue:queue.append(href)
        print("LIST",seed,"page",len(visited),"articles",len(articles),"queue",len(queue))

payload=load(CASES,{"meta":{},"cases":[]});cases=payload.get("cases",[])
cache=load(CACHE,{})
existing_urls={c.get("source_url") for c in cases}
existing_day_city={(c.get("event_date"),str(c.get("city","")).lower()) for c in cases}
added=[]
for i,url in enumerate(sorted(articles),1):
    if url in existing_urls:continue
    try:
        r=session.get(url,headers=HEAD,timeout=30);r.raise_for_status()
        soup=BeautifulSoup(r.text,"html.parser")
    except Exception as e:
        print("WARN article",url,e);continue
    title=clean((soup.find("h1") or soup.title).get_text(" ",strip=True) if (soup.find("h1") or soup.title) else "")
    main=soup.find("article") or soup.find("main") or soup.body or soup
    for t in main(["script","style","nav","footer","form","svg","noscript"]):t.decompose()
    text=clean(main.get_text(" ",strip=True))
    published=parse_pub(soup,text)
    if published<CUTOFF-timedelta(days=20):continue
    ok,status=classify(title,text)
    if not ok:continue
    dt,confidence=event_date(text,published)
    if not(CUTOFF<=dt<=TODAY):continue
    city=city_for(title,text,url)
    if not city:continue
    key=(dt.isoformat(),city.lower())
    if key in existing_day_city:
        continue
    loc,q,prec=location_for(text,city)
    offense="Tötungsdelikt"
    if re.search(r"Körperverletzung\s+mit\s+Todesfolge",text,re.I):offense="Körperverletzung mit Todesfolge"
    elif re.search(r"\bTotschlag\b",text,re.I):offense="Totschlag"
    elif re.search(r"(?<!versuchter\s)\bMord\b",text,re.I):offense="Mord"
    summary=re.sub(r"^POL-[A-ZÄÖÜ0-9]+:\s*","",title)
    c={"id":f"{dt.isoformat()}-{hashlib.sha1(url.encode()).hexdigest()[:10]}","event_date":dt.isoformat(),"publication_date":published.isoformat(),"city":city,"state":"","location":loc,"geocode_address":q,"precision":prec,"location_type":"Tatort/Reported location","status":status,"offense":offense,"summary":("Public police release reports a fatal "+("suspected " if status=="suspected" else "")+"homicide: "+summary)[:280],"source_agency":"Presseportal police release","source_url":url,"lat":None,"lon":None,"date_confidence":confidence}
    cases.append(c);existing_urls.add(url);existing_day_city.add(key);added.append(c)
    print("ADD",c["event_date"],c["city"],c["location"],url)

# Geocode only newly added historical cases.
last=0.0
for c in added:
    queries=[c.get("geocode_address") or f"{c['city']}, Germany",f"{c['city']}, Germany"]
    hit=None;used=None
    for q in dict.fromkeys(queries):
        hit,last=geocode(session,q,cache,last)
        if hit:used=q;break
    if hit:
        c["lat"],c["lon"]=hit["lat"],hit["lon"]
        c["geocode_precision"]="city-fallback" if used==f"{c['city']}, Germany" and c.get("precision")!="city" else c.get("precision","unknown")
        a=hit.get("address",{});c["state"]=a.get("state") or c.get("state","")

cases[:]=[c for c in cases if CUTOFF<=date.fromisoformat(c["event_date"])<=TODAY]
cases.sort(key=lambda c:(c["event_date"],c.get("city","")),reverse=True)
payload["cases"]=cases
payload["meta"]={"generated_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),"window_days":WINDOW,"scope":"Germany","case_count":len(cases),"geocoded_count":sum(c.get("lat") is not None for c in cases),"method":"Verified seed set plus 90-day Presseportal historical backfill and daily public police source monitoring; strict death+homicide filter.","disclaimer":"Public-source monitor, not an official or exhaustive crime register. Locations reflect the most precise place publicly reported; Fundort means body-discovery location and may not be the crime scene."}
save(CASES,payload)
print("SUMMARY articles",len(articles),"added",len(added),"total",len(cases),"geocoded",payload["meta"]["geocoded_count"])
