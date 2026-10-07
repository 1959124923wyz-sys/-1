#!/usr/bin/env python3
"""Refresh and expand the Shenzhen Save-Years Map without API keys.

Data policy:
- Current asking/reference prices come from public Fang community list/detail pages
  (plus any explicitly seeded fallback sources).
- Coordinates come from a public historical Shenzhen Lianjia geocoded snapshot and
  are used ONLY as a coordinate cache, never as the current-price source.
- No CAPTCHA bypass, login bypass, proxy rotation, or private API is used.
- Valid cached data is retained whenever a source is blocked or changes markup.
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
FANG_PAGE = "https://sz.esf.fang.com/housing/__0_{sort}_0_0_{page}_0_0_0/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0 Safari/537.36"
TZ = timezone(timedelta(hours=8))
CAPTCHA_WORDS = ("验证码", "访问过于频繁", "安全验证", "人机验证", "captcha")
DISTRICTS = {"南山","福田","罗湖","宝安","龙岗","龙华","坪山","光明","盐田","大鹏"}
DISTRICT_MAP = {"龙华区":"龙华","坪山区":"坪山","光明区":"光明","大鹏新区":"大鹏"}
PRICE_RE = re.compile(r"(?<!\d)([1-9]\d{3,5})\s*元\s*/\s*(?:㎡|m²|平米)", re.I)

@dataclass
class FetchResult:
    url: str
    text: str | None
    error: str | None
    status: int | None

def now_iso() -> str:
    return datetime.now(TZ).replace(microsecond=0).isoformat()

def clean_name(s: str) -> str:
    s=(s or "").strip()
    s=re.sub(r"[\s·•・\-—_（）()\[\]【】《》“”'\"]", "", s)
    return (s.replace("一期","1期").replace("二期","2期").replace("三期","3期")
             .replace("四期","4期").replace("五期","5期"))

def normalize_district(s: str) -> str:
    s=(s or "").strip().replace("深圳市","")
    return DISTRICT_MAP.get(s, s.removesuffix("区"))

def fetch(session: requests.Session, url: str, timeout=22) -> FetchResult:
    try:
        r=session.get(url, timeout=timeout, allow_redirects=True)
        if r.status_code in (403,429):
            return FetchResult(url,None,f"HTTP {r.status_code}; stopped (no bypass attempted)",r.status_code)
        r.raise_for_status()
        t=r.text
        low=t.lower()
        if any(w.lower() in low for w in CAPTCHA_WORDS):
            return FetchResult(r.url,None,"challenge/captcha detected; stopped",r.status_code)
        return FetchResult(r.url,t,None,r.status_code)
    except Exception as e:
        return FetchResult(url,None,f"{type(e).__name__}: {e}",None)

def extract_price(text: str, source_url: str="") -> tuple[int|None,str|None]:
    plain=BeautifulSoup(text,"html.parser").get_text(" ",strip=True)
    patterns=[
        r"(20\d{2})年\s*(\d{1,2})月[^。]{0,50}?(?:二手房价格)?均价\s*([1-9]\d{3,5})\s*元/(?:平米|㎡|m²)",
        r"([1-9]\d{3,5})\s*元/(?:㎡|m²)\s*[（(](\d{1,2})月参考价[)）]",
        r"([1-9]\d{3,5})\s*元/(?:㎡|m²)\s*(?:本周挂牌均价|小区参考价)",
    ]
    m=re.search(patterns[0],plain,re.I)
    if m: return int(m.group(3)),f"{m.group(1)}-{int(m.group(2)):02d}"
    m=re.search(patterns[1],plain,re.I)
    if m:
        month=int(m.group(2)); now=datetime.now(TZ); year=now.year
        if month>now.month+1: year-=1
        return int(m.group(1)),f"{year}-{month:02d}"
    m=re.search(patterns[2],plain,re.I)
    if m: return int(m.group(1)),"current-page"
    m=re.search(r"(?:参考均价|参考价|挂牌均价|二手房价格均价)[^\d]{0,18}([1-9]\d{3,5})\s*元/(?:㎡|m²|平米)",plain,re.I)
    return (int(m.group(1)),"current-page") if m else (None,None)

def plausible_price(new:int, old:int|None=None) -> bool:
    if not 3000<=new<=500000: return False
    if old and not (old*0.50<=new<=old*1.80): return False
    return True

def _transform_lat(x:float,y:float)->float:
    ret=-100.0+2.0*x+3.0*y+0.2*y*y+0.1*x*y+0.2*math.sqrt(abs(x))
    ret+=(20.0*math.sin(6*x*math.pi)+20.0*math.sin(2*x*math.pi))*2/3
    ret+=(20.0*math.sin(y*math.pi)+40.0*math.sin(y/3*math.pi))*2/3
    ret+=(160.0*math.sin(y/12*math.pi)+320.0*math.sin(y*math.pi/30))*2/3
    return ret

def _transform_lng(x:float,y:float)->float:
    ret=300.0+x+2.0*y+0.1*x*x+0.1*x*y+0.1*math.sqrt(abs(x))
    ret+=(20.0*math.sin(6*x*math.pi)+20.0*math.sin(2*x*math.pi))*2/3
    ret+=(20.0*math.sin(x*math.pi)+40.0*math.sin(x/3*math.pi))*2/3
    ret+=(150.0*math.sin(x/12*math.pi)+300.0*math.sin(x/30*math.pi))*2/3
    return ret

def gcj02_to_wgs84(lat:float,lng:float)->tuple[float,float]:
    if not (73.66<lng<135.05 and 3.86<lat<53.55): return lat,lng
    a=6378245.0; ee=0.00669342162296594323
    dlat=_transform_lat(lng-105,lat-35); dlng=_transform_lng(lng-105,lat-35)
    radlat=lat/180*math.pi; magic=1-ee*math.sin(radlat)**2; sqrtmagic=math.sqrt(magic)
    dlat=dlat*180/((a*(1-ee))/(magic*sqrtmagic)*math.pi)
    dlng=dlng*180/(a/sqrtmagic*math.cos(radlat)*math.pi)
    return 2*lat-(lat+dlat),2*lng-(lng+dlng)

def load_coords(session:requests.Session)->dict[str,dict]:
    if COORD_CACHE.exists():
        try: return json.loads(COORD_CACHE.read_text(encoding="utf-8"))
        except Exception: pass
    r=fetch(session,COORD_BOOTSTRAP_URL,timeout=30)
    if not r.text:
        print("coordinate bootstrap unavailable:",r.error,file=sys.stderr); return {}
    groups={}
    for row in csv.DictReader(io.StringIO(r.text)):
        try: lat=float(row.get("lat") or 0); lng=float(row.get("lon") or 0)
        except ValueError: continue
        if not (22.35<lat<22.9 and 113.7<lng<114.65): continue
        lat,lng=gcj02_to_wgs84(lat,lng)
        name=(row.get("小区名称") or "").strip()
        if not name: continue
        key=clean_name(name)
        g=groups.setdefault(key,{"name":name,"lats":[],"lngs":[],"district":normalize_district(row.get("区") or ""),"subdistrict":row.get("街道") or "","address":row.get("地址") or ""})
        g["lats"].append(lat); g["lngs"].append(lng)
    out={k:{"name":g["name"],"lat":statistics.median(g["lats"]),"lng":statistics.median(g["lngs"]),"district":g["district"],"subdistrict":g["subdistrict"],"address":g["address"]} for k,g in groups.items()}
    COORD_CACHE.write_text(json.dumps(out,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print("built coord cache:",len(out))
    return out

def parse_fang_index(html:str,base_url:str)->tuple[list[dict],str|None]:
    """Parse the current Fang community list using its stable card classes.

    Falls back to a generic parser so tests and minor markup variants remain safe.
    """
    soup=BeautifulSoup(html,"html.parser"); rows=[]; seen=set()
    cards=soup.select(".houseList > .list")
    for card in cards:
        title=card.select_one("a.plotTit")
        price_el=card.select_one(".priceAverage")
        if not title or not price_el: continue
        ptype=(card.select_one(".plotFangType").get_text(" ",strip=True) if card.select_one(".plotFangType") else "")
        if ptype and ptype not in {"住宅","别墅"}: continue
        m=PRICE_RE.search(price_el.get_text(" ",strip=True))
        if not m: continue
        price=int(m.group(1))
        if not plausible_price(price): continue
        name=title.get_text(" ",strip=True)
        key=clean_name(name)
        if not key or key in seen: continue
        seen.add(key)
        district=sub=address=""
        locps=card.select("dl dd > p")
        if len(locps)>=2:
            loc=locps[1]; links=loc.find_all("a")
            if links:
                district=normalize_district(links[0].get_text(" ",strip=True))
                if len(links)>1: sub=links[1].get_text(" ",strip=True)
            full=loc.get_text(" ",strip=True)
            address=full
            for bit in (district,sub,"-"):
                if bit: address=address.replace(bit," ",1)
            address=re.sub(r"\s+"," ",address).strip()
        newcode=""
        raw=card.get("data-bgcomare") or ""
        mm=re.search(r'"newcode"\s*:\s*"?(\d+)',raw)
        if mm: newcode=mm.group(1)
        if not newcode:
            mm=re.search(r"/loupan/(?:office/)?(\d+)\.htm",title.get("href",""))
            if mm: newcode=mm.group(1)
        rows.append({"name":name,"newcode":newcode,"property_type":ptype or "住宅","unit_price":price,"district":district,"subdistrict":sub,"address":address,"source_url":urljoin(base_url,title.get("href",""))})
    # Fallback for synthetic tests / minor legacy variants.
    if not rows:
        for container in soup.select(".houseList dl"):
            txt=container.get_text(" ",strip=True); pm=PRICE_RE.search(txt)
            if not pm: continue
            links=[a for a in container.find_all("a",href=True) if a.get_text(" ",strip=True)]
            if not links: continue
            name=links[0].get_text(" ",strip=True); key=clean_name(name)
            if key in seen: continue
            seen.add(key)
            district=sub=""
            if len(links)>1: district=normalize_district(links[1].get_text(" ",strip=True))
            if len(links)>2: sub=links[2].get_text(" ",strip=True)
            rows.append({"name":name,"newcode":"","property_type":"住宅","unit_price":int(pm.group(1)),"district":district,"subdistrict":sub,"address":"","source_url":urljoin(base_url,links[0].get("href",""))})
    nxt=None
    a=soup.find("a",string=lambda x:x and "下一页" in x)
    if a and a.get("href"): nxt=urljoin(base_url,a["href"])
    return rows,nxt

def match_coord(row:dict,coords:dict[str,dict])->dict|None:
    key=clean_name(row.get("name",""))
    if key in coords: return coords[key]
    district=normalize_district(row.get("district",""))
    # Conservative fuzzy fallback: only a unique near-identical name in the same district.
    candidates=[]
    for ck,pos in coords.items():
        if district and pos.get("district") and normalize_district(pos.get("district"))!=district: continue
        if min(len(key),len(ck))<4: continue
        if (key in ck or ck in key) and abs(len(key)-len(ck))<=2:
            candidates.append(pos)
    return candidates[0] if len(candidates)==1 else None

def merge_discovered(db:dict,rows:list[dict],coords:dict,timestamp:str)->tuple[int,int,int]:
    by_name={clean_name(x.get("name","")):x for x in db["communities"]}
    added=updated=unmatched=0
    for r in rows:
        key=clean_name(r["name"]); existing=by_name.get(key)
        if existing:
            if plausible_price(r["unit_price"],existing.get("unit_price")):
                existing.update(unit_price=r["unit_price"],price_period=timestamp[:10],price_source="房天下小区列表",last_success_at=timestamp)
                for k in ("district","subdistrict","address","property_type","newcode"):
                    if r.get(k): existing[k]=r[k]
                if r.get("source_url"): existing["source_url"]=r["source_url"]
                updated+=1
            continue
        pos=match_coord(r,coords)
        if not pos:
            unmatched+=1; continue
        rec={"id":"fang-"+(r.get("newcode") or re.sub(r"\W+","",key)[:48]),"name":r["name"],"district":r.get("district") or pos.get("district",""),"subdistrict":r.get("subdistrict") or pos.get("subdistrict",""),"address":r.get("address") or pos.get("address",""),"lat":pos["lat"],"lng":pos["lng"],"unit_price":r["unit_price"],"price_period":timestamp[:10],"price_source":"房天下小区列表","source_url":r.get("source_url") or FANG_INDEX,"property_type":r.get("property_type") or "住宅","newcode":r.get("newcode") or "","coord_source":"public historical Lianjia geocoded snapshot; coordinate cache only","coord_quality":"historical-cache","last_success_at":timestamp}
        db["communities"].append(rec); by_name[key]=rec; added+=1
    return added,updated,unmatched

def fang_page_url(page:int, sort_code:int=3)->str:
    if page<=1 and sort_code==3: return FANG_INDEX
    return FANG_PAGE.format(sort=sort_code,page=max(1,page))

def write_outputs(db:dict):
    db["communities"].sort(key=lambda x:(x.get("district",""),x.get("subdistrict",""),x.get("name","")))
    DATA.write_text(json.dumps(db,ensure_ascii=False,indent=2),encoding="utf-8")
    JS.write_text("window.HOUSING_DATA = "+json.dumps(db,ensure_ascii=False,separators=(",",":"))+";\n",encoding="utf-8")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--discover-pages",type=int,default=25,help="number of deterministic Fang list pages to scan")
    ap.add_argument("--start-page",type=int,default=0,help="first Fang list page; 0 uses rotating cursor for default sort")
    ap.add_argument("--sort-code",type=int,choices=(1,2,3),default=3,help="Fang list sort code; 3=second-hand listing volume, 1/2=price-order variants")
    ap.add_argument("--detail-limit",type=int,default=12,help="max known detail pages to refresh; 0 disables")
    ap.add_argument("--delay",type=float,default=.65,help="delay between public page requests")
    args=ap.parse_args()

    db=json.loads((DATA if DATA.exists() else SEED).read_text(encoding="utf-8"))
    meta=db.setdefault("meta",{})
    # New default semantics: annual savings, RMB/year.
    meta["default_annual_savings"]=100000
    meta.pop("default_monthly_savings",None)
    timestamp=now_iso(); failures=[]; detail_successes=0
    s=requests.Session()
    s.headers.update({"User-Agent":UA,"Accept":"text/html,application/xhtml+xml;q=0.9,*/*;q=0.7","Accept-Language":"zh-CN,zh;q=0.9","Referer":"https://sz.esf.fang.com/"})
    blocked_hosts=set()

    # Refresh only a small stale slice of known detail pages. The list scan below does bulk refresh.
    if args.detail_limit>0:
        known=sorted(db.get("communities",[]),key=lambda c:c.get("last_success_at") or "")
        attempted=0
        for c in known:
            if attempted>=args.detail_limit: break
            urls=[u for u in (c.get("source_url"),c.get("fallback_url")) if u and ("/housing/" not in u)]
            if not urls: continue
            attempted+=1
            for url in urls:
                host=urlparse(url).netloc
                if host in blocked_hosts: continue
                r=fetch(s,url)
                if not r.text:
                    failures.append({"name":c.get("name"),"url":url,"error":r.error})
                    if r.status in (403,429) or (r.error and "captcha" in r.error): blocked_hosts.add(host)
                    time.sleep(args.delay); continue
                p,period=extract_price(r.text,url)
                if p and plausible_price(p,c.get("unit_price")):
                    c["unit_price"]=p;c["price_period"]=period or timestamp[:10];c["last_success_at"]=timestamp
                    c["price_source"]="58同城" if "58.com" in r.url else "房天下"
                    detail_successes+=1; time.sleep(args.delay); break
                failures.append({"name":c.get("name"),"url":url,"error":"price pattern not found or implausible jump"})
                time.sleep(args.delay)

    coords=load_coords(s)
    total_coord_cache=len(coords)
    start=args.start_page if args.start_page>0 else (int(meta.get("discovery_cursor_page") or 1) if args.sort_code==3 else 1)
    start=max(1,min(100,start)); pages=max(0,min(100,args.discover_pages))
    discovered_added=discovered_updated=unmatched=rows_seen=pages_ok=0
    stopped_reason=None
    for offset in range(pages):
        page=((start-1+offset)%100)+1
        url=fang_page_url(page,args.sort_code)
        r=fetch(s,url)
        if not r.text:
            failures.append({"name":"Fang index","url":url,"error":r.error})
            stopped_reason=r.error; break
        rows,_=parse_fang_index(r.text,r.url)
        if len(rows)<5:
            msg=f"parser got only {len(rows)} priced residential rows on page {page}; stopped"
            failures.append({"name":"Fang index","url":url,"error":msg});stopped_reason=msg;break
        a,u,n=merge_discovered(db,rows,coords,timestamp)
        rows_seen+=len(rows);discovered_added+=a;discovered_updated+=u;unmatched+=n;pages_ok+=1
        if offset<pages-1: time.sleep(args.delay)

    next_page=((start-1+max(1,pages_ok))%100)+1
    if args.sort_code==3:
        meta["discovery_cursor_page"]=next_page
    meta.update(
        generated_at=timestamp,
        default_annual_savings=100000,
        last_run_successes=detail_successes,
        discovery_start_page=start,
        discovery_pages_ok=pages_ok,
        discovery_rows_seen=rows_seen,
        discovery_added=discovered_added,
        discovery_updated=discovered_updated,
        discovery_unmatched=unmatched,
        coordinate_cache_size=total_coord_cache,
        discovery_sort_code=args.sort_code,
        last_run_failures=len(failures),
        last_run_notes=failures[:25],
        last_run_stopped_reason=stopped_reason,
    )
    write_outputs(db)
    print(json.dumps({
        "points":len(db["communities"]),
        "coordinate_cache":total_coord_cache,
        "detail_refreshes":detail_successes,
        "pages_ok":pages_ok,
        "rows_seen":rows_seen,
        "discovery_added":discovered_added,
        "discovery_updated":discovered_updated,
        "unmatched_no_coordinate":unmatched,
        "failures":len(failures)
    },ensure_ascii=False))

if __name__=="__main__":
    main()
