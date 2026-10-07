#!/usr/bin/env python3
import io,re,requests
from bs4 import BeautifulSoup
try:
    import openpyxl
except Exception as e:
    print("NO_OPENPYXL",repr(e)); raise

HEAD={"User-Agent":"Mozilla/5.0 GermanyCrimeMonitor/1.0"}
urls=[
 ("bka2025","https://www.bka.de/DE/AktuelleInformationen/StatistikenLagebilder/PolizeilicheKriminalstatistik/PKS2025/PKSTabellen/LandFalltabellen/landFalltabellen.html"),
 ("berlin_atlas","https://www.berlin.de/polizei/service/kriminalitaetsatlas/")
]
for label,url in urls:
    r=requests.get(url,headers=HEAD,timeout=45)
    print("PAGE",label,r.status_code,r.url,len(r.content),r.headers.get("content-type"))
    print("HEAD",r.text[:200].replace("\n"," "))
    if not r.ok: continue
    s=BeautifulSoup(r.text,"html.parser")
    links=[]
    for a in s.find_all("a",href=True):
        href=requests.compat.urljoin(r.url,a["href"])
        txt=" ".join(a.get_text(" ",strip=True).split())
        if re.search(r"T01|HZ|xlsx|csv|Kriminalitätsatlas|Fallzahlen",txt+" "+href,re.I):
            links.append((txt,href))
    print("LINKS",label,len(links))
    for x in links[:80]: print("L",repr(x[0]),x[1])
    if label=="berlin_atlas":
        xls=[h for t,h in links if ".xlsx" in h.lower() or "download" in h.lower()]
        for h in xls[:3]:
            rr=requests.get(h,headers=HEAD,timeout=60)
            print("XLS",rr.status_code,rr.url,len(rr.content),rr.headers.get("content-type"))
            if rr.ok and len(rr.content)>10000:
                wb=openpyxl.load_workbook(io.BytesIO(rr.content),read_only=True,data_only=True)
                print("SHEETS",wb.sheetnames)
                for ws in wb.worksheets[:8]:
                    print("SHEET",ws.title,ws.max_row,ws.max_column)
                    for row in ws.iter_rows(min_row=1,max_row=min(ws.max_row,15),values_only=True):
                        print("ROW",ws.title,repr(row[:12]))
                    print("END_SHEET")
                break
