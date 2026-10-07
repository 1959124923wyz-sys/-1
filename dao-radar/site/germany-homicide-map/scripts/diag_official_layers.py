#!/usr/bin/env python3
import io,requests,openpyxl
HEAD={"User-Agent":"Mozilla/5.0 GermanyCrimeMonitor/1.0"}
guesses=[
 "https://www.bka.de/SharedDocs/Downloads/DE/Publikationen/PolizeilicheKriminalstatistik/2025/Land/Faelle/LA-F-02-T01-Laender-Faelle-HZ_xls.xlsx?__blob=publicationFile&v=2",
 "https://www.bka.de/SharedDocs/Downloads/DE/Publikationen/PolizeilicheKriminalstatistik/2025/Land/Faelle/LA-F-02-T01-Laender-Faelle-HZ_xls.xlsx?__blob=publicationFile&v=1",
]
for u in guesses:
    try:
        r=requests.get(u,headers=HEAD,timeout=60)
        print("BKA_GUESS",r.status_code,r.url,len(r.content),r.headers.get("content-type"),r.content[:4])
        if r.ok and r.content[:2]==b"PK":
            wb=openpyxl.load_workbook(io.BytesIO(r.content),read_only=True,data_only=True)
            print("BKA_SHEETS",wb.sheetnames)
            for ws in wb.worksheets[:5]:
                print("BKA_SHEET",ws.title,ws.max_row,ws.max_column)
                for row in ws.iter_rows(min_row=1,max_row=min(ws.max_row,12),values_only=True):
                    print("BKA_ROW",repr(row[:18]))
            break
    except Exception as e: print("BKA_ERROR",repr(e))

atlas="https://www.berlin.de/polizei/_assets/dienststellen/lka/fallzahlen_hz-2016-2025.xlsx?ts=1790656142"
r=requests.get(atlas,headers=HEAD,timeout=60); print("BERLIN",r.status_code,len(r.content))
wb=openpyxl.load_workbook(io.BytesIO(r.content),read_only=True,data_only=True)
for sheet in ("Fallzahlen_2025","HZ_2025"):
    ws=wb[sheet]
    print("BERLIN_SHEET",sheet,ws.max_row,ws.max_column)
    for row in ws.iter_rows(min_row=1,max_row=min(ws.max_row,18),values_only=True):
        print("BERLIN_ROW",sheet,repr(row[:20]))
