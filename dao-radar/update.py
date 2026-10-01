from __future__ import annotations
import hashlib, json, re, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from ddgs import DDGS
from deep_translator import GoogleTranslator

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "site" / "data.json"
TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TZ).strftime("%Y-%m-%d")

QUERIES = [
    '道教 国际 交流 论坛 会议 研讨会',
    '道教 文化 交流 征稿 讲座 活动',
    '道家 国际 会议 交流 论坛',
    'Daoism conference symposium forum call for papers',
    'Daoist cultural exchange conference workshop',
    'Taoism international forum conference exchange',
    'Daoist studies conference call for proposals',
    'Tao Te Ching international forum cultural exchange',
    '道教 国際 会議 シンポジウム 交流',
    '도교 국제 학술대회 문화 교류'
]

DIRECT = ['daoism','daoist','taoism','taoist','道教','道家','道德经','道德經','老子','全真','正一','도교']
OPPORTUNITY = ['conference','symposium','forum','workshop','seminar','call for','proposal','registration','meeting','exchange','lecture','festival','会议','會議','论坛','論壇','研讨会','研討會','交流','征稿','徵稿','讲座','講座','活动','活動','报名','報名','国際会議','シンポジウム','학술대회','교류']
NEGATIVE = ['wikipedia','amazon.','facebook.com','instagram.com','pinterest.','quora.com','reddit.com','youtube.com','tiktok.com']
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

def score_item(title: str, body: str, url: str) -> int:
    text = f"{title} {body}".lower()
    domain = urlparse(url).netloc.lower()
    if any(x in domain for x in NEGATIVE): return -99
    direct_title = sum(1 for x in DIRECT if x.lower() in title.lower())
    direct_all = sum(1 for x in DIRECT if x.lower() in text)
    opp_title = sum(1 for x in OPPORTUNITY if x.lower() in title.lower())
    opp_all = sum(1 for x in OPPORTUNITY if x.lower() in text)
    if not direct_all or not opp_all: return -10
    s = direct_title*4 + min(direct_all,3)*2 + opp_title*3 + min(opp_all,3)
    if any(x in domain for x in TRUST_HINTS): s += 3
    if url.startswith('https://'): s += 1
    return s

def is_mostly_chinese(text: str) -> bool:
    if not text: return True
    han = len(re.findall(r'[\u4e00-\u9fff]', text))
    letters = len(re.findall(r'[A-Za-z\u4e00-\u9fff]', text))
    return letters == 0 or han / letters > 0.45

def translate(text: str, limit=180) -> str:
    text = re.sub(r'\s+', ' ', (text or '')).strip()
    if not text: return ''
    text = text[:limit]
    if is_mostly_chinese(text): return text
    try:
        return GoogleTranslator(source='auto', target='zh-CN').translate(text)
    except Exception:
        return text

def trim_summary(text: str, n=105) -> str:
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) <= n: return text
    cut = text[:n]
    for mark in ['。','；',';','.']:
        pos = cut.rfind(mark)
        if pos > n*0.55: return cut[:pos+1]
    return cut.rstrip('，,；;。.') + '…'

def infer_country(text: str, url: str) -> str:
    t = text.lower(); domain = urlparse(url).netloc.lower()
    for country, hints in COUNTRY_HINTS:
        if any(h.lower() in t for h in hints): return country
    if domain.endswith('.cn'): return '中国大陆'
    if domain.endswith('.hk'): return '香港'
    if domain.endswith('.tw'): return '台湾'
    if domain.endswith('.jp'): return '日本'
    if domain.endswith('.kr'): return '韩国'
    return '国际'

def category(country: str, text: str) -> str:
    if country == '中国大陆': return '国内交流'
    if country == '国际' and contains_any(text, ['online','remote','线上','網上','网络']): return '线上/国际'
    if country == '国际': return '线上/国际'
    return '海外/港澳台'

def source_name(url: str) -> str:
    d = urlparse(url).netloc.lower().removeprefix('www.')
    return d or '原网站'

def stable_id(url: str) -> str:
    return hashlib.sha1(canonical(url).encode('utf-8')).hexdigest()[:14]

def collect():
    out=[]
    with DDGS() as ddgs:
        for q in QUERIES:
            try:
                rows = ddgs.text(q, region='wt-wt', safesearch='moderate', timelimit='m', max_results=8) or []
                for r in rows:
                    title=(r.get('title') or '').strip(); body=(r.get('body') or '').strip(); url=(r.get('href') or '').strip()
                    if not title or not url: continue
                    sc=score_item(title, body, url)
                    if sc < 9: continue
                    out.append((sc,title,body,canonical(url)))
                time.sleep(1.2)
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
    for sc,title,body,url in sorted(candidates.values(), reverse=True)[:12]:
        combined=f'{title} {body}'
        country=infer_country(combined,url)
        title_zh=translate(title,160)
        summary=trim_summary(translate(body,260))
        relevance='道教直接相关' if contains_any(title,DIRECT) else '相关文化交流'
        items.append({
            'id':stable_id(url),'title':title,'title_zh':title_zh,'country':country,'city':'',
            'category':category(country,combined),'format':'交流信息','relevance':relevance,
            'event_date':'','deadline':'','summary_zh':summary,
            'source_name':source_name(url),'source_url':url,'discovered_at':TODAY,'manual':False,'score':sc
        })
        known.add(url); added+=1

    manual=[x for x in items if x.get('manual')]
    auto=[x for x in items if not x.get('manual')]
    auto.sort(key=lambda x:(x.get('discovered_at',''),x.get('score',0)), reverse=True)
    merged=manual+auto[:80]
    merged.sort(key=lambda x:(x.get('discovered_at',''),x.get('score',0)), reverse=True)
    db={'updated_at':TODAY,'items':merged}
    DATA.write_text(json.dumps(db,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'updated {TODAY}; added {added}; total {len(merged)}')

if __name__=='__main__': main()
