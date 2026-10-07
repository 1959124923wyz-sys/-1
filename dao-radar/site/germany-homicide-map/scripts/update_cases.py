#!/usr/bin/env python3
from __future__ import annotations
import email.utils, hashlib, html, json, os, re, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import feedparser, requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
CASES=ROOT/"data/cases.json"; CACHE=ROOT/"data/geocode_cache.json"; SEEN=ROOT/"data/seen_urls.json"
WINDOW=90
RSS=[
 ("Presseportal Polizei","https://www.presseportal.de/rss/polizei.rss2"),
 ("Polizei Hessen","https://polizei.hessen.de/presse-feed/all"),
 ("Polizei Berlin","https://www.berlin.de/polizei/polizeimeldungen/index.php/rss"),
]
CONTACT=os.getenv("APP_CONTACT","https://github.com/")
HEAD={"User-Agent":f"GermanyHomicideMonitor/1.2 ({CONTACT})","Accept-Language":"de,en;q=0.8"}
CAND=re.compile(r"Tötungsdelikt|Totschlag|Mordkommission|\bMord\b|Tötung|erschossen|erstochen|tödlich\s+verletzt|Leichnam",re.I)
DEATH=re.compile(r"verstarb|verstorben|\bstarb\b|\bgetötet\b|tödlich\w*\s+verletzt|tot\s+aufgefunden|\bLeichnam\b|erschossen|erstochen",re.I)
HOM=re.compile(r"Tötungsdelikt|Totschlag|Mordkommission|\bMord(?:es|verdacht|vorwurf)?\b|\bTötung\b|\bgetötet\b",re.I)
ATT=re.compile(r"versucht\w*\s+(?:Mord|Totschlag|Tötungsdelikt)",re.I)
DONE=re.compile(r"vollendet\w*|verstarb|verstorben|\bstarb\b|tödlich\w*\s+verletzt|\bgetötet\b|\bLeichnam\b",re.I)
OLD=re.compile(r"Cold\s*Case|Aktenzeichen\s+XY|vor\s+\w+\s+Jahr",re.I)
STREET=re.compile(r"\b([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-.' ]{1,55}?(?:straße|strasse|allee|weg|platz|gasse|damm|ring|ufer|chaussee|markt))\b",re.I)
NUMDATE=re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(20\d{2})(?!\d)")
TEXTDATE=re.compile(r"(?<!\d)(\d{1,2})\.\s*(Januar|Februar|März|Maerz|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)(?:\s+(20\d{2}))?",re.I)
MONTHS={"januar":1,"februar":2,"märz":3,"maerz":3,"april":4,"mai":5,"juni":6,"juli":7,"august":8,"september":9,"oktober":10,"november":11,"dezember":12}

def load(p,default):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return default
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=False)+"\n",encoding="utf-8")
def txt(s):
    return re.sub(r"\s+"," ",BeautifulSoup(html.unescape(s or ""),"html.parser").get_text(" ",strip=True)).strip()
def article(session,url):
    r=session.get(url,headers=HEAD,timeout=30); r.raise_for_status()
    soup=BeautifulSoup(r.text,"html.parser")
    for t in soup(["script","style","nav","footer","form","svg","noscript"]): t.decompose()
    main=soup.find("article") or soup.find("main") or soup.body or soup
    return re.sub(r"\s+"," ",main.get_text(" ",strip=True)).strip()
def pubdate(entry):
    raw=entry.get("published") or entry.get("updated") or ""
    try:
        d=email.utils.parsedate_to_datetime(raw)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        st=entry.get("published_parsed") or entry.get("updated_parsed")
        if st:return datetime(*st[:6],tzinfo=timezone.utc)
        return datetime.now(timezone.utc)

def event_date(text,published,today):
    m=re.search(r"Tatzeit:\s*(?:\w+,\s*)?(\d{1,2})\.\s*([A-Za-zÄÖÜäöü]+)\s+(20\d{2})",text,re.I)
    if m:
        mm=MONTHS.get(m.group(2).lower()) or MONTHS.get(m.group(2).lower().replace("ä","ae"))
        if mm:
            try:return date(int(m.group(3)),mm,int(m.group(1))),"high"
            except ValueError:pass
    candidates=[]
    def score_date(x,start,end):
        if not (0 <= (published.date()-x).days <= 45):return
        before=text[max(0,start-120):start]
        after=text[end:min(len(text),end+180)]
        around=before+" "+after
        score=0
        if re.search(r"Tatzeit|Tatort",around,re.I):score+=8
        if re.search(r"getötet|tödlich|verstarb|verstorben|\bstarb\b|erschossen|erstochen",after,re.I):score+=12
        elif re.search(r"Tötungsdelikt|Totschlag|\bMord\b|\bTötung\b",around,re.I):score+=4
        if re.search(r"festgenommen|Festnahme|Haft|Haftrichter|Untersuchungshaft|Folgemeldung|Nachtrag",after,re.I):score-=9
        candidates.append((score,x))
    for m in NUMDATE.finditer(text):
        try:x=date(int(m.group(3)),int(m.group(2)),int(m.group(1)))
        except ValueError:continue
        score_date(x,m.start(),m.end())
    for m in TEXTDATE.finditer(text):
        mm=MONTHS.get(m.group(2).lower()) or MONTHS.get(m.group(2).lower().replace("ä","ae"))
        if not mm:continue
        try:x=date(int(m.group(3) or published.year),mm,int(m.group(1)))
        except ValueError:continue
        score_date(x,m.start(),m.end())
    if candidates:
        score,x=max(candidates,key=lambda z:(z[0],-z[1].toordinal()))
        return x,("high" if score>=8 else "medium")
    return published.date(),"publication_date"

def city_for(title,desc,body,url):
    if "berlin.de" in url:return "Berlin"
    for s in (desc,body[:700]):
        m=re.search(r"(?:^|\s)([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-./ ]{1,60})\s*\(ots\)",s)
        if m:return m.group(1).strip(" -/,.").split("/")[0].strip()
    m=re.search(r"POL-[A-ZÄÖÜ0-9]+:\s*(?:\d+[- ]+)?([^:/\-]{2,55})",title)
    if m:return m.group(1).strip()
    m=re.search(r"(?:Tötungsdelikt|Totschlag|Mord|Tötung)[^\n]{0,50}?\bin\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\- ]{2,45}?)(?:\s*[-–:]|$)",title,re.I)
    return m.group(1).strip() if m else ""

def location_for(body,city):
    core=re.split(r"Rückfragen|Pressekontakt|Pressestelle|Original-Content|Kontakt:",body,maxsplit=1,flags=re.I)[0]
    m=re.search(r"Tatort:\s*([^\n\r<]{3,120})",core,re.I)
    if m:
        v=re.split(r"(?:Gestern|Heute|Am\s|Zeit:)",m.group(1))[0].strip(" .,-")
        if 2<len(v)<100:return v,f"{v}, {city}, Germany","reported-place"
    m=STREET.search(core)
    if m:
        v=m.group(1).strip()
        return v,f"{v}, {city}, Germany","street"
    return city,f"{city}, Germany","city"

def classify(title,desc,body):
    t=" ".join((title,desc,body))
    if OLD.search(" ".join((title,desc))) or not CAND.search(t):return False,""
    if not (DEATH.search(t) and HOM.search(t)):return False,""
    if ATT.search(t) and not DONE.search(t):return False,""
    return True,("suspected" if re.search(r"Verdacht|mutmaßlich|dringend\s+tatverdächtig|Hinweise?\s+auf",t,re.I) else "confirmed")

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
        print("WARN geocode",q,e); hit=None
    cache[q]=hit; save(CACHE,cache)
    return hit,last

today=datetime.now(timezone.utc).date()
payload=load(CASES,{"meta":{},"cases":[]})
cases=payload.get("cases",[])
before_cases=json.dumps(cases,ensure_ascii=False,sort_keys=True)
previous_generated=payload.get("meta",{}).get("generated_at")
cache=load(CACHE,{})
seen=load(SEEN,{})
session=requests.Session()
existing_urls={c.get("source_url") for c in cases}
existing_day_city={(c.get("event_date"),c.get("city","").lower()) for c in cases}
added=0

for source,url in RSS:
    try:
        r=session.get(url,headers=HEAD,timeout=30); r.raise_for_status(); feed=feedparser.parse(r.content)
    except Exception as e:
        print("WARN feed",source,e); continue
    for e in feed.entries:
        title=txt(e.get("title","")); desc=txt(e.get("summary") or e.get("description") or ""); link=e.get("link","").strip()
        if not link or not CAND.search(title+" "+desc) or link in existing_urls:continue
        if link in seen and seen[link].get("final"):continue
        try:body=article(session,link)
        except Exception as ex:
            print("WARN article",link,ex); continue
        ok,status=classify(title,desc,body)
        seen[link]={"seen_at":datetime.now(timezone.utc).isoformat(),"final":True,"included":ok}
        if not ok:continue
        published=pubdate(e); dt,confidence=event_date(body,published,today)
        if not(today-timedelta(days=WINDOW)<=dt<=today):continue
        city=city_for(title,desc,body,link)
        if not city or (dt.isoformat(),city.lower()) in existing_day_city:continue
        loc,q,prec=location_for(body,city)
        offense="Tötungsdelikt"
        if re.search(r"\bTotschlag\b",body,re.I):offense="Totschlag"
        elif re.search(r"(?<!versuchter\s)\bMord\b",body,re.I):offense="Mord"
        c={"id":f"{dt.isoformat()}-{hashlib.sha1(link.encode()).hexdigest()[:10]}","event_date":dt.isoformat(),"publication_date":published.date().isoformat(),"city":city,"state":"","location":loc,"geocode_address":q,"precision":prec,"location_type":"Tatort/Reported location","status":status,"offense":offense,"category":"homicide","category_label":"凶杀","severity":5,"summary":("Public police release reports a fatal "+("suspected " if status=="suspected" else "")+"homicide: "+re.sub(r"^POL-[A-ZÄÖÜ0-9]+:\s*","",title))[:260],"source_agency":source,"source_url":link,"lat":None,"lon":None,"date_confidence":confidence}
        cases.append(c); existing_urls.add(link); existing_day_city.add((dt.isoformat(),city.lower())); added+=1

cut=today-timedelta(days=WINDOW)
cases[:]=[c for c in cases if cut<=date.fromisoformat(c["event_date"])<=today]
last=0.0
for c in cases:
    if c.get("lat") is not None and c.get("lon") is not None:continue
    queries=[c.get("geocode_address") or f"{c['city']}, Germany",f"{c['city']}, Germany"]
    hit=None; used=None
    for q in dict.fromkeys(queries):
        hit,last=geocode(session,q,cache,last)
        if hit:used=q;break
    if hit:
        c["lat"],c["lon"]=hit["lat"],hit["lon"]
        c["geocode_precision"]="city-fallback" if used==f"{c['city']}, Germany" and c.get("precision")!="city" else c.get("precision","unknown")
        a=hit.get("address",{}); c["state"]=a.get("state") or c.get("state","")

cases.sort(key=lambda c:(c["event_date"],c.get("city","")),reverse=True)
cases_changed=json.dumps(cases,ensure_ascii=False,sort_keys=True)!=before_cases
generated=(datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z") if cases_changed or not previous_generated else previous_generated)
category_counts={k:sum(1 for c in cases if c.get("category")==k) for k in ("homicide","violence","robbery","sexual","property")}
payload["meta"]={"generated_at":generated,"window_days":WINDOW,"scope":"Germany","case_count":len(cases),"geocoded_count":sum(c.get("lat") is not None for c in cases),"category_counts":category_counts,"schema_version":2,"coverage_note":"Current dataset includes homicide/suspected homicide and fatal serious violence. Other category controls are reserved for future source coverage; zero does not mean zero crime.","method":"Verified 90-day seed/backfill set plus automated monitoring of public police RSS sources; strict death+homicide filter with follow-up-date and contact-address guards.","disclaimer":"Public-source monitor, not an official or exhaustive crime register. Locations reflect the most precise place publicly reported; Fundort means body-discovery location and may not be the crime scene."}
payload["cases"]=cases
save(CASES,payload); save(CACHE,cache); save(SEEN,seen)
print(f"cases={len(cases)} added={added} geocoded={payload['meta']['geocoded_count']} changed={cases_changed}")
