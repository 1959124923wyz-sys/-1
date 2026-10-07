#!/usr/bin/env python3
import re,requests
from bs4 import BeautifulSoup
u="https://stadtritter.de/kriminalstatistik-deutschland/"
r=requests.get(u,headers={"User-Agent":"Mozilla/5.0 GermanyCrimeMonitor/1.0"},timeout=45)
print("PAGE",r.status_code,r.url,len(r.content),r.headers.get("content-type"))
r.raise_for_status()
s=BeautifulSoup(r.text,"html.parser")
links=[]
for a in s.find_all("a",href=True):
    href=requests.compat.urljoin(r.url,a["href"])
    txt=" ".join(a.get_text(" ",strip=True).split())
    if re.search(r"json|csv|sqlite|manifest|geojson|download|daten",txt+" "+href,re.I):
        links.append((txt,href))
print("LINKS",len(links))
for x in links[:200]:print("L",repr(x[0]),x[1])
for pat in (r'https?://[^"\']+\.json[^"\']*',r'["\']([^"\']*\.json[^"\']*)["\']',r'892000',r'Gewaltkriminal'):
    ms=list(re.finditer(pat,r.text,re.I))
    print("PAT",pat,"N",len(ms))
    for m in ms[:30]:
        a=max(0,m.start()-180);b=min(len(r.text),m.end()+260)
        print("RAW",re.sub(r"\s+"," ",r.text[a:b])[:800])
