#!/usr/bin/env python3
import io, json, requests, openpyxl

URL="https://www.bka.de/SharedDocs/Downloads/DE/Publikationen/PolizeilicheKriminalstatistik/2025/Kreis/Faelle/KR-F-01-T01-Kreise-Faelle-HZ_xls.xlsx?__blob=publicationFile&v=2"
r=requests.get(URL,timeout=90,headers={"User-Agent":"Mozilla/5.0 GermanyCrimeMap/1.0"})
print("HTTP",r.status_code,"len",len(r.content),"type",r.headers.get("content-type"))
r.raise_for_status()
wb=openpyxl.load_workbook(io.BytesIO(r.content),read_only=True,data_only=True)
print("SHEETS",wb.sheetnames)
for ws in wb.worksheets[:4]:
    print("SHEET",ws.title,"size",ws.max_row,ws.max_column)
    for row in ws.iter_rows(min_row=1,max_row=min(20,ws.max_row),values_only=True):
        print("ROW",json.dumps([None if v is None else str(v)[:120] for v in row[:20]],ensure_ascii=False))
        if any(v and "Gewaltkriminal" in str(v) for v in row):
            print("FOUND VIOLENCE ROW")
