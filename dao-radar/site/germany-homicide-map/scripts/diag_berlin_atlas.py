#!/usr/bin/env python3
import io,json,requests,openpyxl
URL="https://www.berlin.de/polizei/_assets/dienststellen/lka/fallzahlen_hz-2016-2025.xlsx?ts=1790656142"
r=requests.get(URL,timeout=60,headers={"User-Agent":"Mozilla/5.0 GermanyCrimeMap/1.0"})
print("HTTP",r.status_code,"len",len(r.content),"type",r.headers.get("content-type"))
r.raise_for_status()
wb=openpyxl.load_workbook(io.BytesIO(r.content),read_only=True,data_only=True)
print("SHEETS",wb.sheetnames)
for ws in wb.worksheets[:8]:
    print("SHEET",ws.title,ws.max_row,ws.max_column)
    for row in ws.iter_rows(min_row=1,max_row=min(14,ws.max_row),values_only=True):
        print("ROW",json.dumps([None if v is None else str(v)[:100] for v in row[:18]],ensure_ascii=False))
