#!/usr/bin/env python3
import io, requests
from pypdf import PdfReader

URL="https://daten.transparenz.hamburg.de/Dataport.HmbTG.ZS.Webservice.GetRessource100/GetRessource100.svc/8c90d027-c52d-45f4-8bdc-d3e2dde784e6/Upload__Stadtteilatlas-pks-2025_do.PDF"
r=requests.get(URL,timeout=90,headers={"User-Agent":"GermanyCrimeMonitor/1.0"})
r.raise_for_status()
pdf=PdfReader(io.BytesIO(r.content))
print("pages",len(pdf.pages),"bytes",len(r.content))
for i,p in enumerate(pdf.pages[:12]):
    txt=(p.extract_text() or "").replace("\x00","")
    print(f"\n===== PAGE {i+1} =====\n")
    print(txt[:14000])
