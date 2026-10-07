#!/usr/bin/env python3
import json,sqlite3,tempfile,requests,os
HEAD={"User-Agent":"Mozilla/5.0 GermanyCrimeMonitor/1.0"}
base="https://stadtritter.de/wp-content/plugins/stadtritter-krimstatistik/data/"
for name in ("pks-historie-manifest.json","pks-historie.db","laenderflaechen-2025.geojson"):
    u=base+name
    r=requests.get(u,headers=HEAD,timeout=90)
    print("FETCH",name,r.status_code,len(r.content),r.headers.get("content-type"))
    r.raise_for_status()
    if name.endswith("manifest.json"):
        obj=r.json(); print("MANIFEST",json.dumps(obj,ensure_ascii=False)[:12000])
    elif name.endswith(".db"):
        fd,path=tempfile.mkstemp(suffix=".db");os.close(fd)
        open(path,"wb").write(r.content)
        con=sqlite3.connect(path)
        print("TABLES",con.execute("select name,sql from sqlite_master where type='table' order by name").fetchall())
        for table in [x[0] for x in con.execute("select name from sqlite_master where type='table'").fetchall()]:
            print("T",table,"COUNT",con.execute(f"select count(*) from {table}").fetchone())
            cols=con.execute(f"pragma table_info({table})").fetchall(); print("COLS",table,cols)
            rows=con.execute(f"select * from {table} limit 5").fetchall(); print("ROWS",table,rows)
            # try searches
            try:
                print("VIOL",table,con.execute(f"select * from {table} where delikt_key='892000' and jahr=2025 limit 30").fetchall())
            except Exception as e: print("NO_VIOL_QUERY",table,repr(e))
        con.close();os.remove(path)
    else:
        obj=r.json(); print("GEO_FEATURES",len(obj.get("features",[]))); print("GEO_PROPS",obj["features"][0].get("properties"))
