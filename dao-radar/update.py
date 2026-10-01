from __future__ import annotations
import hashlib, json, re, time
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import requests
from ddgs import DDGS

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "site" / "data.json"
TZ = timezone(timedelta(hours=8))
NOW = datetime.now(TZ)
TODAY = NOW.strftime("%Y-%m-%d")
TODAY_DATE = NOW.date()

QUERIES = [
    '道教 国际 交流 论坛 会议 研讨会 报名',
    '道教 文化 交流 征稿 讲座 活动',
    '道家 国际 会议 交流 论坛 征稿',
    'Daoism conference symposium forum call for papers',
    'Daoist cultural exchange conference workshop registration',
    'Taoism international forum conference exchange upcoming',
    'Daoist studies conference call for proposals registration',
    'Tao Te Ching international forum cultural exchange',
    '道教 国際 会議 シンポジウム 交流 募集',
    '도교 국제 학술대회 문화 교류 모집'
]

DIRECT = ['daoism','daoist','taoism','taoist','道教','道家','道德经','道德經','老子','全真','正一','도교']
OPPORTUNITY = ['conference','symposium','forum','workshop','seminar','call for','proposal','registration','meeting','exchange','lecture','festival','会议','會議','论坛','論壇','研讨会','研討會','交流','征稿','徵稿','讲座','講座','活动','活動','报名','報名','国際会議','シンポジウム','학술대회','교류']
FUTURE_WORDS = ['upcoming','registration','register','call for','deadline','apply','applications','open for','save the date','schedule','报名','報名','征稿','徵稿','截止','招募','即将','即將','开放','開放','現正','募集','申込','모집','등록']
DENY_DOMAINS = ['wikipedia.org','amazon.','facebook.com','instagram.com','pinterest.','quora.com','reddit.com','youtube.com','tiktok.com','eventbrite.','happeningnext.','allevents.','frederickhotelnyc.com']
TRUST_HINTS = ['.edu','.ac.','.gov','university','association','foundation','institute','center','centre','museum','daoist','taoist','religion','cuhk.edu.hk','aarweb.org','ea-cp.eu','daoglobe.com']
TRACKING_KEYS = {'utm_source','utm_medium','utm_campaign','utm_term','utm_content','gclid','fbclid','ref'}

COUNTRY_HINTS = [
    ('中国大陆', ['china','beijing','shanghai','中国大陆','北京','上海','杭州','南京','成都','广州','西安','武汉']),
    ('香港', ['hong kong','香港']), ('台湾', ['taiwan','taipei','臺灣','台湾','台北','臺北']),
    ('日本', ['japan','tokyo','kyoto','日本','东京','東京','京都']), ('韩国', ['korea','seoul','韩国','韓國','首尔','서울']),
    ('新加坡', ['singapore','新加坡']), ('美国', ['united states','usa','u.s.','america','denver','new york','美国','美國']),
    ('加拿大', ['canada','vancouver','toronto','加拿大','温哥华','溫哥華']), ('英国', ['united kingdom','uk','london','britain','英国','英國']),
    ('法国', ['france','paris','法国','法國']), ('德国', ['germany','berlin','德国','德國']), ('波兰', ['poland','poznan','poznań','波兰','波蘭']),
    ('澳大利亚', ['australia','sydney','melbourne','澳大利亚','澳洲'])
]
MONTHS = {m.lower():i for i,m in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'],1)}
MONTHS.update({m[:3].lower():i for m,i in MONTHS.copy().items()})

def canonical(url: str) -> str:
    try:
        p = urlparse(url)
        q = [(k,v) for k,v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in TRACKING_KEYS]
        return urlunparse((p.scheme or 'https', p.netloc.lower(), p.path.rstrip('/') or '/', '', urlencode(q), ''))
    except Exception:
        return url

def contains_any(text, words):
    t = text.lower()
    return any(w.lower() in t for w in words)

def domain_denied(url: str) -> bool:
    d = urlparse(url).netloc.lower()
    return any(x in d for x in DENY_DOMAINS)

def score_item(title: str, body: str, url: str) -> int:
    text = f"{title} {body}".lower()
    domain = urlparse(url).netloc.lower()
    if domain_denied(url): return -99
    direct_title = sum(1 for x in DIRECT if x.lower() in title.lower())
    direct_all = sum(1 for x in DIRECT if x.lower() in text)
    opp_title = sum(1 for x in OPPORTUNITY if x.lower() in title.lower())
    opp_all = sum(1 for x in OPPORTUNITY if x.lower() in text)
    if not direct_all or not opp_all: return -10
    s = direct_title*4 + min(direct_all,3)*2 + opp_title*3 + min(opp_all,3)
    if any(x in domain for x in TRUST_HINTS): s += 3
    if url.startswith('https://'): s += 1
    return s

def extract_dates(text: str):
    out=[]
    for y,m,d in re.findall(r'(?<!\d)(20\d{2})[年\-/\.](\d{1,2})[月\-/\.](\d{1,2})日?', text):
        try: out.append(date(int(y),int(m),int(d)))
        except ValueError: pass
    pat=r'\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(20\d{2})\b'
    for mon,day,year in re.findall(pat,text,re.I):
        try: out.append(date(int(year),MONTHS[mon.lower()],int(day)))
        except (ValueError,KeyError): pass
    return out

def looks_current_or_future(title: str, body: str, url: str) -> bool:
    text=f'{title} {body}'
    dates=extract_dates(text)
    if dates:
        if any(d >= TODAY_DATE - timedelta(days=2) for d in dates): return True
        if max(dates) < TODAY_DATE - timedelta(days=7): return False
    if re.search(r'\b202[7-9]\b', text): return True
    if contains_any(text,FUTURE_WORDS): return True
    path=urlparse(url).path.lower()
    if any(x in path for x in ['/events','/event/','/schedule','/conference','/conferences','/cfp','call-for','registration']): return True
    return False

def is_mostly_chinese(text: str) -> bool:
    if not text: return True
    han=len(re.findall(r'[\u4e00-\u9fff]',text))
    letters=len(re.findall(r'[A-Za-z\u4e00-\u9fff]',text))
    return letters==0 or han/letters>0.45

def translate(text: str, limit=220) -> str:
    text=re.sub(r'\s+',' ',(text or '')).strip()[:limit]
    if not text or is_mostly_chinese(text): return text
    try:
        r=requests.get('https://translate.googleapis.com/translate_a/single',
            params={'client':'gtx','sl':'auto','tl':'zh-CN','dt':'t','q':text},
            timeout=12,headers={'User-Agent':'Mozilla/5.0'})
        r.raise_for_status()
        data=r.json()
        return ''.join(part[0] for part in data[0] if part and part[0]) or text
    except Exception:
        return text

def trim_summary(text: str, n=105) -> str:
    text=re.sub(r'\s+',' ',text).strip()
    if len(text)<=n: return text
    cut=text[:n]
    for mark in ['。','；',';','.']:
        pos=cut.rfind(mark)
        if pos>n*0.55: return cut[:pos+1]
    return cut.rstrip('，,；;。.')+'…'

def infer_country(text: str, url: str) -> str:
    t=text.lower(); domain=urlparse(url).netloc.lower()
    for country,hints in COUNTRY_HINTS:
        if any(h.lower() in t for h in hints): return country
    if domain.endswith('.cn'): return '中国大陆'
    if domain.endswith('.hk'): return '香港'
    if domain.endswith('.tw'): return '台湾'
    if domain.endswith('.jp'): return '日本'
    if domain.endswith('.kr'): return '韩国'
    return '国际'

def category(country: str, text: str) -> str:
    if country=='中国大陆': return '国内交流'
    if country=='国际': return '线上/国际'
    return '海外/港澳台'

def source_name(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix('www.') or '原网站'

def stable_id(url: str) -> str:
    return hashlib.sha1(canonical(url).encode('utf-8')).hexdigest()[:14]

def collect():
    out=[]
    with DDGS() as ddgs:
        for q in QUERIES:
            try:
                rows=ddgs.text(q,region='wt-wt',safesearch='moderate',timelimit='m',max_results=8) or []
                for r in rows:
                    title=(r.get('title') or '').strip()
                    body=(r.get('body') or '').strip()
                    url=canonical((r.get('href') or '').strip())
                    if not title or not url or domain_denied(url): continue
                    if not looks_current_or_future(title,body,url): continue
                    sc=score_item(title,body,url)
                    if sc<12: continue
                    out.append((sc,title,body,url))
                time.sleep(1.0)
            except Exception as e:
                print(f'[warn] search failed: {q}: {e}')
    return out

def main():
    db=json.loads(DATA.read_text(encoding='utf-8'))
    items=db.get('items',[])
    known={canonical(x.get('source_url','')) for x in items}
    candidates={}
    for sc,title,body,url in collect():
        if url in known: continue
        prev=candidates.get(url)
        if not prev or sc>prev[0]: candidates[url]=(sc,title,body,url)

    added=0
    for sc,title,body,url in sorted(candidates.values(),reverse=True)[:5]:
        combined=f'{title} {body}'
        country=infer_country(combined,url)
        items.append({
            'id':stable_id(url),'title':title,'title_zh':translate(title,170),'country':country,'city':'',
            'category':category(country,combined),'format':'交流信息',
            'relevance':'道教直接相关' if contains_any(title,DIRECT) else '相关文化交流',
            'event_date':'','deadline':'','summary_zh':trim_summary(translate(body,280)),
            'source_name':source_name(url),'source_url':url,'discovered_at':TODAY,'manual':False,'score':sc
        })
        known.add(url); added+=1

    manual=[x for x in items if x.get('manual')]
    auto=[x for x in items if not x.get('manual') and looks_current_or_future(x.get('title',''),x.get('summary_zh',''),x.get('source_url',''))]
    auto.sort(key=lambda x:(x.get('discovered_at',''),x.get('score',0)),reverse=True)
    merged=manual+auto[:40]
    merged.sort(key=lambda x:(x.get('discovered_at',''),x.get('score',0)),reverse=True)
    DATA.write_text(json.dumps({'updated_at':TODAY,'items':merged},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'updated {TODAY}; added {added}; total {len(merged)}')

if __name__=='__main__':
    main()
