#!/usr/bin/env python3
"""Best-effort refresh for Shenzhen Save-Years Map.

No API key is required. The script:
1) refreshes known community detail pages;
2) optionally walks a small number of Fang community-list pages;
3) matches current community names to a public, older geocoded Lianjia snapshot
   used ONLY as a coordinate cache;
4) never deletes valid cached data when a source is blocked or changes markup.

It deliberately does not bypass CAPTCHAs, login walls, or 403/429 responses.
"""
from __future__ import annotations
import argparse, csv, io, json, math, re, statistics, sys, time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "communities.json"
SEED = ROOT / "data" / "seed.json"
JS = ROOT / "data" / "communities.js"
COORD_CACHE = ROOT / "data" / "coords_cache.json"
COORD_BOOTSTRAP_URL = "https://raw.githubusercontent.com/Qixuan5/data_analysis/main/%E5%B0%8F%E5%BE%90_%E6%88%BF%E4%BB%B7%E5%88%86%E6%9E%90/data_clear/%E6%B7%B1%E5%9C%B3_geo.csv"
FANG_INDEX = "https://sz.esf.fang.com/housing/"
UA = "ShenzhenSaveYearsMap/1.0 (public-data visualizer; scheduled GitHub Action)"
TZ = timezone(timedelta(hours=8))
PRICE_RE = re.compile(r"(?<!\d)([1-9]\d{3,5})\s*元\s*/\s*(?:㎡|m²|平米)", re.I)
CAPTCHA_WORDS = ("验证码", "访问过于频繁", "安全验证", "人机验证", "captcha")
DISTRICT_MAP = {"龙华区":"龙华","坪山区":"坪山","光明区":"光明","大鹏新区":"大鹏"}

@dataclass
class FetchResult:
    url: str
    text: str | None
    error: str | None
    status: int | None

def now_iso() -> str:
    return datetime.now(TZ).replace(microsecond=0).isoformat()

def clean_name(s: str) -> str:
    return re.sub(r"[\s·•・\-—_（）()\[\]【】]", "", (s or "")).replace("一期","1期").replace("二期","2期").replace("三期","3期")

def normalize_district(s: str) -> str:
    s=(s or "").strip().replace("深圳市","").replace("区", "区")
    return DISTRICT_MAP.get(s, s.removesuffix("区"))

def fetch(session: requests.Session, url: str, timeout=18) -> FetchResult:
    try:
        r=session.get(url, timeout=timeout, allow_redirects=True)
        if r.status_code in (403, 429): return FetchResult(url,None,f"HTTP {r.status_code}; stopped (no bypass attempted)",r.status_code)
        r.raise_for_status()
        t=r.text
        low=t.lower()
        if any(w.lower() in low for w in CAPTCHA_WORDS): return FetchResult(url,None,"challenge/captcha detected; stopped",r.status_code)
        return FetchResult(r.url,t,None,r.status_code)
    except Exception as e:
        return FetchResult(url,None,f"{type(e).__name__}: {e}",None)

def extract_price(text: str, source_url: str="") -> tuple[int|None,str|None]:
    plain=BeautifulSoup(text,"html.parser").get_text(" ",strip=True)
    patterns = [
        r"(20\d{2})年\s*(\d{1,2})月[^。]{0,50}?(?:二手房价格)?均价\s*([1-9]\d{3,5})\s*元/(?:平米|㎡|m²)",
        r"([1-9]\d{3,5})\s*元/(?:㎡|m²)\s*[（(](\d{1,2})月参考价[)）]",
        r"([1-9]\d{3,5})\s*元/(?:㎡|m²)\s*(?:本周挂牌均价|小区参考价)",
    ]
    m=re.search(patterns[0],plain,re.I)
    if m: return int(m.group(3)),f"{m.group(1)}-{int(m.group(2)):02d}"
    m=re.search(patterns[1],plain,re.I)
    if m:
        month=int(m.group(2)); now=datetime.now(TZ); year=now.year
        if month > now.month + 1: year -= 1
        return int(m.group(1)),f"{year}-{month:02d}"
    m=re.search(patterns[2],plain,re.I)
    if m: return int(m.group(1)),"current-page"
    # Conservative fallback: only when price is near explicit price wording.
    m=re.search(r"(?:参考均价|参考价|挂牌均价|二手房价格均价)[^\d]{0,18}([1-9]\d{3,5})\s*元/(?:㎡|m²|平米)",plain,re.I)
    if m: return int(m.group(1)),"current-page"
    return None,None

def plausible_price(new:int, old:int|None) -> bool:
    if not 3000 <= new <= 500000: return False
    if old and not (old*0.55 <= new <= old*1.65): return False
    return True


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0*x + 3.0*y + 0.2*y*y + 0.1*x*y + 0.2*math.sqrt(abs(x))
    ret += (20.0*math.sin(6.0*x*math.pi) + 20.0*math.sin(2.0*x*math.pi)) * 2.0/3.0
    ret += (20.0*math.sin(y*math.pi) + 40.0*math.sin(y/3.0*math.pi)) * 2.0/3.0
    ret += (160.0*math.sin(y/12.0*math.pi) + 320.0*math.sin(y*math.pi/30.0)) * 2.0/3.0
    return ret

def _transform_lng(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0*y + 0.1*x*x + 0.1*x*y + 0.1*math.sqrt(abs(x))
    ret += (20.0*math.sin(6.0*x*math.pi) + 20.0*math.sin(2.0*x*math.pi)) * 2.0/3.0
    ret += (20.0*math.sin(x*math.pi) + 40.0*math.sin(x/3.0*math.pi)) * 2.0/3.0
    ret += (150.0*math.sin(x/12.0*math.pi) + 300.0*math.sin(x/30.0*math.pi)) * 2.0/3.0
    return ret

def gcj02_to_wgs84(lat: float, lng: float) -> tuple[float, float]:
    """Approximate inverse transform for Amap GCJ-02 -> WGS84 (for OSM display)."""
    if not (73.66 < lng < 135.05 and 3.86 < lat < 53.55):
        return lat, lng
    a=6378245.0; ee=0.00669342162296594323
    dlat=_transform_lat(lng-105.0, lat-35.0); dlng=_transform_lng(lng-105.0, lat-35.0)
    radlat=lat/180.0*math.pi; magic=math.sin(radlat); magic=1-ee*magic*magic; sqrtmagic=math.sqrt(magic)
    dlat=(dlat*180.0)/((a*(1-ee))/(magic*sqrtmagic)*math.pi)
    dlng=(dlng*180.0)/(a/sqrtmagic*math.cos(radlat)*math.pi)
    return 2*lat-(lat+dlat), 2*lng-(lng+dlng)

def load_coords(session: requests.Session) -> dict[str,dict]:
    if COORD_CACHE.exists():
        try: return json.loads(COORD_CACHE.read_text(encoding="utf-8"))
        except Exception: pass
    r=fetch(session,COORD_BOOTSTRAP_URL,timeout=25)
    if not r.text:
        print("coordinate bootstrap unavailable:",r.error,file=sys.stderr); return {}
    groups={}
    for row in csv.DictReader(io.StringIO(r.text)):
        try: lat=float(row.get("lat") or 0); lng=float(row.get("lon") or 0)
        except ValueError: continue
        if not (22.35<lat<22.9 and 113.7<lng<114.65): continue
        lat,lng=gcj02_to_wgs84(lat,lng)
        name=(row.get("小区名称") or "").strip();
        if not name: continue
        key=clean_name(name); g=groups.setdefault(key,{"name":name,"lats":[],"lngs":[],"district":normalize_district(row.get("区") or ""),"subdistrict":row.get("街道") or "","address":row.get("地址") or ""})
        g["lats"].append(lat); g["lngs"].append(lng)
    out={k:{"name":g["name"],"lat":statistics.median(g["lats"]),"lng":statistics.median(g["lngs"]),"district":g["district"],"subdistrict":g["subdistrict"],"address":g["address"]} for k,g in groups.items()}
    COORD_CACHE.write_text(json.dumps(out,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print("built coord cache:",len(out))
    return out

def find_card_container(node):
    cur=node.parent
    for _ in range(7):
        if not cur: break
        txt=" ".join(cur.stripped_strings)
        if len(txt)<1200 and PRICE_RE.search(txt) and len(cur.find_all("a"))>=1: return cur
        cur=cur.parent
    return node.parent

def parse_fang_index(html: str, base_url: str) -> tuple[list[dict], str|None]:
    soup=BeautifulSoup(html,"html.parser"); seen=set(); rows=[]
    price_nodes=soup.find_all(string=PRICE_RE)
    for node in price_nodes:
        card=find_card_container(node); txt=" ".join(card.stripped_strings)
        pm=PRICE_RE.search(txt)
        if not pm: continue
        price=int(pm.group(1)); links=[]
        for a in card.find_all("a",href=True):
            label=" ".join(a.stripped_strings).strip()
            if label and not label.isdigit(): links.append((label,urljoin(base_url,a.get("href"))))
        if not links: continue
        # Fang cards usually put community name first; filter navigation labels.
        bad={"住宅","商业","收藏","在售","在租","查看详情"}
        name,url=next(((x,u) for x,u in links if x not in bad and len(x)<=40),links[0])
        key=clean_name(name)
        if not key or key in seen: continue
        seen.add(key)
        district=sub=""; address=""
        # Explicit district anchors are more stable than guessing from address.
        for label,_ in links[1:5]:
            n=normalize_district(label)
            if n in {"南山","福田","罗湖","宝安","龙岗","龙华","坪山","光明","盐田","大鹏"} and not district: district=n
            elif district and not sub and 1<len(label)<=12: sub=label
        rows.append({"name":name,"unit_price":price,"district":district,"subdistrict":sub,"address":address,"source_url":url})
    nxt=None
    a=soup.find("a",string=lambda s:s and "下一页" in s)
    if a and a.get("href"): nxt=urljoin(base_url,a["href"])
    return rows,nxt

def merge_discovered(db:dict, rows:list[dict], coords:dict, timestamp:str) -> tuple[int,int]:
    by_name={clean_name(x.get("name","")):x for x in db["communities"]}; added=updated=0
    for r in rows:
        key=clean_name(r["name"]); pos=coords.get(key); existing=by_name.get(key)
        if existing:
            if plausible_price(r["unit_price"],existing.get("unit_price")):
                existing.update(unit_price=r["unit_price"],price_period="current-index",price_source="房天下小区列表",last_success_at=timestamp)
                if r.get("source_url"): existing["source_url"]=r["source_url"]
                updated+=1
            continue
        if not pos: continue
        db["communities"].append({"id":"fang-index-"+re.sub(r"\W+","",key)[:48],"name":r["name"],"district":r.get("district") or pos.get("district", ""),"subdistrict":r.get("subdistrict") or pos.get("subdistrict", ""),"address":r.get("address") or pos.get("address", ""),"lat":pos["lat"],"lng":pos["lng"],"unit_price":r["unit_price"],"price_period":"current-index","price_source":"房天下小区列表","source_url":r.get("source_url") or FANG_INDEX,"coord_source":"public historical Lianjia geocoded snapshot; coordinate cache only","coord_quality":"historical-cache","last_success_at":timestamp})
        by_name[key]=db["communities"][-1]; added+=1
    return added,updated

def write_outputs(db:dict):
    db["communities"].sort(key=lambda x:(x.get("district","") , x.get("name","")))
    DATA.write_text(json.dumps(db,ensure_ascii=False,indent=2),encoding="utf-8")
    JS.write_text("window.HOUSING_DATA = "+json.dumps(db,ensure_ascii=False,separators=(",",":"))+";\n",encoding="utf-8")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--discover-pages",type=int,default=8,help="how many Fang index pages to walk; 0 disables discovery")
    ap.add_argument("--delay",type=float,default=1.6); args=ap.parse_args()
    db=json.loads((DATA if DATA.exists() else SEED).read_text(encoding="utf-8")); timestamp=now_iso(); failures=[]; successes=0
    s=requests.Session(); s.headers.update({"User-Agent":UA,"Accept":"text/html,application/xhtml+xml;q=0.9,*/*;q=0.7","Accept-Language":"zh-CN,zh;q=0.8,en;q=0.4"})
    # Refresh known detail URLs. Stop per-host on explicit anti-bot response.
    blocked_hosts=set()
    for c in db.get("communities",[]):
        urls=[u for u in (c.get("source_url"),c.get("fallback_url")) if u]
        for url in urls:
            host=urlparse(url).netloc
            if host in blocked_hosts: continue
            r=fetch(s,url)
            if not r.text:
                failures.append({"name":c.get("name"),"url":url,"error":r.error});
                if r.status in (403,429) or (r.error and "captcha" in r.error): blocked_hosts.add(host)
                time.sleep(args.delay)
                continue
            p,period=extract_price(r.text,url)
            if p and plausible_price(p,c.get("unit_price")):
                c["unit_price"]=p; c["price_period"]=period or c.get("price_period"); c["last_success_at"]=timestamp; c["price_source"]="58同城" if "58.com" in r.url else "房天下"; successes+=1
                time.sleep(args.delay)
                break
            failures.append({"name":c.get("name"),"url":url,"error":"price pattern not found or implausible jump"})
            time.sleep(args.delay)
    # Discovery: current list + old public coordinates. No mass geocoding service involved.
    discovered_added=discovered_updated=0
    if args.discover_pages>0:
        coords=load_coords(s)
        url=db.get("meta",{}).get("next_discovery_url") or FANG_INDEX
        last_next=None
        for i in range(args.discover_pages):
            if not url or urlparse(url).netloc in blocked_hosts: break
            r=fetch(s,url)
            if not r.text:
                failures.append({"name":"Fang index","url":url,"error":r.error}); break
            rows,nxt=parse_fang_index(r.text,r.url)
            if len(rows)<3:
                failures.append({"name":"Fang index","url":url,"error":f"parser got only {len(rows)} rows; stopped to avoid bad data"}); break
            a,u=merge_discovered(db,rows,coords,timestamp); discovered_added+=a; discovered_updated+=u
            last_next=nxt
            if not nxt or nxt==url: break
            url=nxt; time.sleep(args.delay)
        # Continue from the next unseen page tomorrow; wrap to page 1 at the end.
        db.setdefault("meta",{})["next_discovery_url"] = last_next or FANG_INDEX
    db.setdefault("meta",{}).update(generated_at=timestamp,last_run_successes=successes,discovery_added=discovered_added,discovery_updated=discovered_updated,last_run_failures=len(failures),last_run_notes=failures[:25])
    write_outputs(db)
    print(json.dumps({"points":len(db["communities"]),"detail_refreshes":successes,"discovery_added":discovered_added,"discovery_updated":discovered_updated,"failures":len(failures)},ensure_ascii=False))

if __name__=="__main__": main()
