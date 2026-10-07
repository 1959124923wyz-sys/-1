#!/usr/bin/env python3
from __future__ import annotations
import hashlib, html, json, os, re, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urljoin
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
CASES=ROOT/"data/cases.json"
CACHE=ROOT/"data/geocode_cache.json"
WINDOW=90
LOOKBACK=max(1,min(int(os.getenv("CRIME_LOOKBACK_DAYS","90")),90))
TODAY=datetime.now(timezone.utc).date()
START=TODAY-timedelta(days=LOOKBACK)
KEEP_CUTOFF=TODAY-timedelta(days=WINDOW)
CONTACT=os.getenv("APP_CONTACT","https://github.com/")
HEAD={"User-Agent":f"GermanyCrimeMonitor/2.0 ({CONTACT})","Accept-Language":"de,en;q=0.8"}

# Targeted tags keep volume manageable and the categories interpretable.
SOURCES=[
    ("robbery","Raubüberfall"),
    ("sexual","Vergewaltigung"),
    ("sexual","Sexuelle Nötigung"),
    ("violence","Messerstiche"),
    ("violence","Messerangriff"),
    ("violence","Messer"),
    ("violence","Schüsse"),
    ("violence","Schwerverletzt"),
    ("property","Wohnungseinbruchdiebstahl"),
    ("property","Wohnungseinbruch"),
    ("property","Fahrraddiebstahl"),
    ("property","Autodiebstahl"),
    ("property","Taschendiebstahl"),
]

MONTHS={"januar":1,"februar":2,"märz":3,"maerz":3,"april":4,"mai":5,"juni":6,"juli":7,"august":8,"september":9,"oktober":10,"november":11,"dezember":12}
NUMDATE=re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(20\d{2})(?!\d)")
TEXTDATE=re.compile(r"(?<!\d)(\d{1,2})\.\s*(Januar|Februar|März|Maerz|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)(?:\s+(20\d{2}))?",re.I)
STREET_COMBINED=re.compile(r"\b((?:[A-ZÄÖÜ][A-Za-zÄÖÜäöüß0-9.'’\-]*\s+){0,2}[A-ZÄÖÜ][A-Za-zÄÖÜäöüß0-9.'’\-]*(?:straße|strasse|allee|weg|platz|gasse|damm|ring|ufer|chaussee|markt|stieg|graben|wall|steig))\b")
STREET_SEPARATE=re.compile(r"\b((?:[A-ZÄÖÜ][A-Za-zÄÖÜäöüß0-9.'’\-]*\s+){1,3}(?:Straße|Strasse|Allee|Weg|Platz|Gasse|Damm|Ring|Ufer|Chaussee|Markt|Stieg|Graben|Wall|Steig))\b")
FOLLOWUP=re.compile(r"Öffentlichkeitsfahndung|Haftbefehl|Tatverdächtig\w+\s+ermittelt|Ermittlungserfolg|Nachtrag|Folgemeldung|Anklage|Urteil",re.I)
NON_EVENT=re.compile(r"Prävention|Präventions|Tipps|Aktionstag|Aktionswoche|sensibilis|Statistik|Bilanz|Sicherheitsbericht|Kontrollaktion|Schwerpunktkontrolle|Warnung vor|Polizei warnt|^Achtung[,! ]|Taschendiebe.*aktiv",re.I)
TRAFFIC=re.compile(r"Verkehrsunfall|Unfall|Zusammenstoß|Sturz|E-Scooter|Motorrad|Pedelec",re.I)
HOMICIDE=re.compile(r"Tötungsdelikt|Totschlag|Mordkommission|\bMord\b|tödlich verletzt|verstarb|verstorben|\bstarb\b",re.I)

def load(p,default):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return default

def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def clean(s):
    return re.sub(r"\s+"," ",BeautifulSoup(html.unescape(s or ""),"html.parser").get_text(" ",strip=True)).strip()

def normalize(s):
    return re.sub(r"[^a-z0-9äöüß]+","",str(s).lower())

def article_url(node):
    ugly=node.get("data-url-ugly","")
    if ugly.startswith("https:@@"):
        return ugly.replace("@","/")
    a=node.find("a",href=re.compile(r"/blaulicht/pm/\d+/\d+"))
    return urljoin("https://www.presseportal.de",a["href"]) if a else ""

def listing_date(text):
    m=NUMDATE.search(text[:60])
    if not m:return None
    try:return date(int(m.group(3)),int(m.group(2)),int(m.group(1)))
    except ValueError:return None

def event_date(text,published):
    # Prefer explicit Tatzeit.
    m=re.search(r"Tatzeit:\s*(?:\w+,\s*)?(\d{1,2})\.\s*([A-Za-zÄÖÜäöü]+)\s+(20\d{2})",text,re.I)
    if m:
        mm=MONTHS.get(m.group(2).lower()) or MONTHS.get(m.group(2).lower().replace("ä","ae"))
        if mm:
            try:return date(int(m.group(3)),mm,int(m.group(1))),"high"
            except ValueError:pass

    candidates=[]
    def add(x,start,end):
        if x>TODAY or x<published-timedelta(days=150):return
        before=text[max(0,start-150):start]
        after=text[end:min(len(text),end+240)]
        around=before+" "+after
        score=0
        if re.search(r"Tatzeit|Tatort",around,re.I):score+=10
        if re.search(r"ereignet|kam es|überfiel|griff|stach|schlug|entwendet|gestohlen|brach|vergewaltig|nötig",after,re.I):score+=8
        if re.search(r"festgenommen|Haft|Fahndung|Nachtrag|Folgemeldung|Urteil|Anklage",after,re.I):score-=8
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

def core_text(text):
    return re.split(r"Rückfragen|Pressekontakt|Pressestelle|Original-Content|Kontakt:",text,maxsplit=1,flags=re.I)[0]

def street_from(text):
    core=core_text(text)
    matches=[]
    for rx in (STREET_COMBINED,STREET_SEPARATE):
        for m in rx.finditer(core):
            v=m.group(1).strip(" ,.-")
            if len(v)>=4:
                matches.append((m.start(),v))
    if not matches:return ""
    matches.sort(key=lambda x:x[0])
    return matches[0][1]

def classify(category,title,text):
    head=(title+" "+text[:1800]).strip()
    if NON_EVENT.search(title) or FOLLOWUP.search(title):return None
    if category=="robbery":
        if not re.search(r"\bRaub(?:überfall|delikt)?\b|\bschwerer Raub\b|\bberaubt\b|\bÜberfall\b",title,re.I):return None
        if re.search(r"angeblich\w*\s+Raubüberfall|erfundene\w*\s+Raubüberfall",head,re.I):return None
        return ("Raub/Überfall","robbery",4)
    if category=="sexual":
        if re.search(r"Vergewaltigung",title,re.I):
            return ("Vergewaltigung","sexual",4)
        if re.search(r"sexuell\w*\s+Nötigung",title,re.I):
            return ("Sexuelle Nötigung","sexual",4)
        return None
    if category=="violence":
        if HOMICIDE.search(head) or TRAFFIC.search(title):return None
        if not re.search(r"Messer|Stich|Schuss|Angriff|Gewalttat|gefährliche Körperverletzung|schwere Körperverletzung",title,re.I):return None
        weapon=bool(re.search(r"Messer|Stichverletz|Schuss|Schusswaffe|gefährliche Körperverletzung|schwere Körperverletzung",head,re.I))
        serious=bool(re.search(r"schwer verletzt|lebensgefährlich|erheblich verletzt|stationär|Notoperation|Stichverletz|Messerstich|Schussverletz",head,re.I))
        if not (weapon and serious):return None
        sub="Messer-/Waffenangriff" if re.search(r"Messer|Stich|Schuss",head,re.I) else "Schwere Körperverletzung"
        return (sub,"violence",4)
    if category=="property":
        if re.search(r"Pressemeldungen|Meldungen der Polizei|Polizeibericht|Wochenend|Kreisgebiet|mehrere (?:Einbrüche|Diebstähle)|und mehr|Sammelmeldung",title,re.I):return None
        if re.search(r"Wohnungseinbruch|Einbruchdiebstahl|\bEinbruch\b|Einbrecher",title,re.I):
            return ("Wohnungseinbruch","property",2)
        if re.search(r"Fahrraddiebstahl|Fahrraddieb|Fahrrad.*(?:gestohlen|entwendet)|Pedelec.*(?:gestohlen|entwendet)|E-Bike.*(?:gestohlen|entwendet)",title,re.I):
            return ("Fahrraddiebstahl","property",2)
        if re.search(r"entpuppt sich|vermeintlich",title,re.I):return None
        if re.search(r"Autodiebstahl|Autodieb|Pkw-Diebstahl|Fahrzeugdiebstahl|(?:Auto|Pkw|Fahrzeug).*gestohlen",title,re.I):
            return ("Autodiebstahl","property",2)
        if re.search(r"Taschendiebstahl|Taschendieb",title,re.I):
            return ("Taschendiebstahl","property",2)
        return None
    return None

def summarize(category,sub,title,text):
    # Avoid reproducing article text; store a short factual synopsis generated from title/location metadata.
    if category=="robbery": return f"警方公开通报的抢劫/暴力夺取财物案件：{re.sub(r'^POL-[A-ZÄÖÜ0-9-]+:\s*','',title)[:170]}"
    if category=="sexual": return f"警方公开通报的严重性犯罪案件：{re.sub(r'^POL-[A-ZÄÖÜ0-9-]+:\s*','',title)[:170]}"
    if category=="violence": return f"警方公开通报的严重暴力案件：{re.sub(r'^POL-[A-ZÄÖÜ0-9-]+:\s*','',title)[:170]}"
    return f"警方公开通报的{sub}案件：{re.sub(r'^POL-[A-ZÄÖÜ0-9-]+:\s*','',title)[:170]}"

def geocode(session,q,cache,last):
    if q in cache:return cache[q],last
    wait=1.15-(time.monotonic()-last)
    if wait>0:time.sleep(wait)
    last=time.monotonic()
    try:
        r=session.get("https://nominatim.openstreetmap.org/search",
            params={"q":q,"format":"jsonv2","limit":1,"countrycodes":"de","addressdetails":1},
            headers=HEAD,timeout=30)
        r.raise_for_status();a=r.json()
        hit=None if not a else {"lat":float(a[0]["lat"]),"lon":float(a[0]["lon"]),"address":a[0].get("address",{})}
    except Exception as e:
        print("WARN geocode",q,e);hit=None
    cache[q]=hit;save(CACHE,cache)
    return hit,last

payload=load(CASES,{"meta":{},"cases":[]})
cases=payload.get("cases",[])
before_cases=json.dumps(cases,ensure_ascii=False,sort_keys=True)
previous_generated=payload.get("meta",{}).get("generated_at")
cache=load(CACHE,{})
existing_urls={c.get("source_url") for c in cases if c.get("source_url")}
existing_keys={(c.get("event_date"),normalize(c.get("city","")),c.get("subcategory") or c.get("offense",""),normalize(c.get("location",""))) for c in cases}
session=requests.Session()
added=[]
stats={k:0 for k in ("robbery","sexual","violence","property")}
seen_listing_urls=set()

for category,tag in SOURCES:
    base=f"https://www.presseportal.de/blaulicht/st/{quote(tag,safe='')}"
    page=f"{base}?startDate={START.isoformat()}&endDate={TODAY.isoformat()}"
    pages=0
    while page and pages<45:
        pages+=1
        try:
            r=session.get(page,headers=HEAD,timeout=30);r.raise_for_status()
        except Exception as e:
            print("WARN listing",category,tag,page,e);break
        soup=BeautifulSoup(r.text,"html.parser")
        nodes=soup.select("article.news")
        if not nodes:break
        oldest=None
        for node in nodes:
            listing=clean(node.get_text(" ",strip=True))
            pub=listing_date(listing)
            if pub:
                oldest=pub if oldest is None or pub<oldest else oldest
                if pub<START-timedelta(days=2):continue
            url=article_url(node)
            if not url or url in seen_listing_urls or url in existing_urls:continue
            seen_listing_urls.add(url)
            title_node=node.find(["h2","h3"])
            title=clean(title_node.get_text(" ",strip=True) if title_node else "")
            city_node=node.select_one("a.news-topic")
            city=clean(city_node.get_text(" ",strip=True) if city_node else "")
            teaser_node=node.find("p")
            teaser=clean(teaser_node.get_text(" ",strip=True) if teaser_node else "")
            if not city or len(city)>65:continue
            if not classify(category,title,teaser):continue
            try:
                ar=session.get(url,headers=HEAD,timeout=30);ar.raise_for_status()
                asoup=BeautifulSoup(ar.text,"html.parser")
                main=asoup.find("article") or asoup.find("main") or asoup.body or asoup
                for t in main(["script","style","nav","footer","form","svg","noscript"]):t.decompose()
                body=clean(main.get_text(" ",strip=True))
            except Exception as e:
                print("WARN article",url,e);continue

            info=classify(category,title,body)
            if not info:continue
            sub,cat,severity=info
            published=pub or TODAY
            dt,confidence=event_date(body,published)
            if not (START<=dt<=TODAY):continue

            street=street_from(body)
            privacy=(cat=="sexual")
            if privacy:
                location=f"{city}（为保护受害者隐私，位置降至城市级）"
                query=f"{city}, Germany"
                precision="city-privacy"
                location_type="Approximate / privacy protected"
            else:
                location=street or city
                query=f"{street}, {city}, Germany" if street else f"{city}, Germany"
                precision="street" if street else "city"
                location_type="Tatort / reported location"

            key=(dt.isoformat(),normalize(city),sub,normalize(location))
            if key in existing_keys:continue

            status="suspected" if re.search(r"Verdacht|mutmaßlich|soll\s",title+" "+body[:900],re.I) else "confirmed"
            c={
                "id":f"{dt.isoformat()}-{cat}-{hashlib.sha1(url.encode()).hexdigest()[:10]}",
                "event_date":dt.isoformat(),
                "publication_date":published.isoformat(),
                "city":city,
                "state":"",
                "location":location,
                "geocode_address":query,
                "precision":precision,
                "location_type":location_type,
                "status":status,
                "offense":sub,
                "subcategory":sub,
                "category":cat,
                "category_label":{"robbery":"抢劫","sexual":"性犯罪","violence":"严重暴力","property":"盗窃/财产犯罪"}[cat],
                "severity":severity,
                "summary":summarize(cat,sub,title,body),
                "source_agency":"Presseportal police release",
                "source_url":url,
                "lat":None,"lon":None,
                "date_confidence":confidence,
                "privacy_protected":privacy
            }
            cases.append(c);existing_urls.add(url);existing_keys.add(key);added.append(c);stats[cat]+=1
            print("ADD",cat,sub,c["event_date"],city,location,url)

        nxt=soup.find("link",rel=lambda x:x and "next" in x)
        page=urljoin(page,nxt.get("href")) if nxt and nxt.get("href") else None
        if oldest and oldest<START-timedelta(days=2):break
        time.sleep(.15)
    print("SOURCE",category,tag,"pages",pages,"added_so_far",stats[category])

# Geocode all newly added incidents. Sex-crime points are intentionally city-level only.
last=0.0
for idx,c in enumerate(added,1):
    q=c["geocode_address"]
    hit,last=geocode(session,q,cache,last)
    if not hit and c["precision"]!="city" and c["precision"]!="city-privacy":
        hit,last=geocode(session,f"{c['city']}, Germany",cache,last)
        if hit:c["geocode_precision"]="city-fallback"
    if hit:
        c["lat"],c["lon"]=hit["lat"],hit["lon"]
        c.setdefault("geocode_precision",c["precision"])
        a=hit.get("address",{})
        c["state"]=a.get("state") or ""
    if idx%50==0:print("GEOCODE",idx,"of",len(added))

# Retain rolling 90 days for every category.
cases=[c for c in cases if KEEP_CUTOFF<=date.fromisoformat(c["event_date"])<=TODAY]
cases.sort(key=lambda c:(c["event_date"],c.get("city",""),c.get("category","")),reverse=True)
category_counts={k:sum(1 for c in cases if c.get("category")==k) for k in ("homicide","violence","robbery","sexual","property")}
payload["cases"]=cases
cases_changed=json.dumps(cases,ensure_ascii=False,sort_keys=True)!=before_cases
generated=(datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z") if cases_changed or not previous_generated else previous_generated)
payload["meta"].update({
    "generated_at":generated,
    "window_days":90,
    "case_count":len(cases),
    "geocoded_count":sum(c.get("lat") is not None and c.get("lon") is not None for c in cases),
    "category_counts":category_counts,
    "schema_version":3,
    "coverage_note":"Public-source monitor. Homicide coverage is separately curated; non-homicide categories use targeted police-release tags and are not exhaustive official crime statistics.",
    "method":"Rolling 90-day public police/prosecutor release monitor with targeted category backfill, event-date filtering, deduplication, cached geocoding, and privacy-reduced sexual-crime locations."
})
save(CASES,payload)
print("SUMMARY","lookback",LOOKBACK,"new",len(added),"stats",stats,"total",len(cases),"category_counts",category_counts,"geocoded",payload["meta"]["geocoded_count"],"changed",cases_changed)
