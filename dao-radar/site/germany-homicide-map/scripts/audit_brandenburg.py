#!/usr/bin/env python3
from __future__ import annotations
import json, time
from collections import Counter

import update_brandenburg as bb

def audit(events):
    s=bb.session()
    cache={}
    last=0.0
    rows=[]
    for e in events:
        query=e["geocode_address"]
        hit,last=bb.geocode(s,query,cache,last)
        used=query
        fallback=False
        if hit is None and e.get("precision")=="street":
            used=f"{e['city']}, Brandenburg, Germany"
            hit,last=bb.geocode(s,used,cache,last)
            fallback=hit is not None
        row={
            "event_id":e["event_id"],"date":e["event_date"],"category":e["category"],
            "offense":e["offense"],"city":e["city"],"district":e.get("district"),
            "source_precision":e.get("precision"),"fallback_to_city":fallback,
            "title":e["summary"].split("：",1)[-1],
        }
        if hit:
            addr=hit.get("address",{})
            state=(addr.get("state") or "").strip()
            lat,lon=hit["lat"],hit["lon"]
            in_bbox=11.20<=lon<=14.85 and 51.30<=lat<=53.65
            state_ok=(not state) or ("brandenburg" in state.lower())
            row.update({
                "lat":lat,"lon":lon,"resolved_state":state,
                "resolved_county":addr.get("county") or addr.get("state_district") or "",
                "resolved_place":addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality") or "",
                "ok":bool(in_bbox and state_ok),
                "reason":"ok" if in_bbox and state_ok else ("state-mismatch" if not state_ok else "outside-brandenburg-bbox"),
            })
        else:
            row.update({"lat":None,"lon":None,"resolved_state":"","resolved_county":"","resolved_place":"","ok":False,"reason":"no-result"})
        rows.append(row)
    good=sum(1 for x in rows if x["ok"])
    return {
        "checked":len(rows),
        "passed":good,
        "pass_rate":round(good/len(rows),4) if rows else 0,
        "precision_counts":dict(Counter(x["source_precision"] for x in rows)),
        "city_fallbacks":sum(1 for x in rows if x["fallback_to_city"]),
        "failed":[x for x in rows if not x["ok"]],
        "rows":rows,
    }

def main():
    result=bb.scan(14,40)
    events=result["events"]
    report={
        "source":"Polizei Brandenburg direct archive",
        "lookback_days":14,
        "pages_scanned":result["pages_scanned"],
        "prefiltered_articles":result["prefiltered"],
        "selected_events":len(events),
        "by_category":dict(Counter(e["category"] for e in events)),
        "geocode_audit":audit(events),
    }
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
