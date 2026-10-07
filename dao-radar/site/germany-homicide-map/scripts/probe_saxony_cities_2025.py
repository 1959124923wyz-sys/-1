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
