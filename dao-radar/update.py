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

# 原则：广覆盖，只排除明显过期、明显无关和低质量聚合页。
QUERIES = [
    # 中国大陆：协会、宫观、学院、论坛、法会、讲经、培训、文化活动
    '道教 活动 预告 报名 法会 讲经 培训 论坛',
    '道观 活动 预告 法会 文化节 讲座',
    '道教 论坛 研讨会 征稿 2026 2027',
    '道教 培训 课程 研修班 招生 2026 2027',
    '玄门讲经 活动 预告 2026 2027',
    '道教 音乐 非遗 展览 展演 文化节 2026 2027',
    '武当 太极 道教 交流 活动 2026 2027',
    '道教 海峡两岸 交流 活动 2026 2027',
    '道教 国际交流 活动 2026 2027',
    'site:taoist.org.cn 道教 预告 活动 报名 征集',
    'site:dao.china.com.cn 道教 活动 预告 2026 2027',
    'site:daoisms.com.cn 道教 活动 报名 预告 2026 2027',
    'site:wdsdjxh.com 道教 活动 交流 2026 2027',
    'site:xiancyg.cn 预告 法会 道教 2026 2027',
    'site:sdsdjxh.com 道教 活动 讲经 2026 2027',

    # 港澳台
    '香港 道教 活动 报名 课程 论坛 2026 2027',
    '台湾 道教 活动 报名 宫庙 论坛 2026 2027',
    '澳門 澳门 道教 文化节 论坛 活动 2026 2027',

    # 海外及国际学术/文化交流
    'Daoism upcoming events conference workshop course 2026 2027',
    'Daoist cultural exchange conference workshop registration 2026 2027',
    'Daoist studies conference call for papers 2026 2027',
    'Taoism festival lecture seminar retreat 2026 2027',
    'Tao Te Ching international forum cultural exchange 2026 2027',
    'Wudang Taiji Taoist cultural event 2026 2027',
    '道教 国際 会議 シンポジウム 交流 募集 2026 2027',
    '도교 국제 학술대회 문화 교류 모집 2026 2027'
]

DIRECT = [
    'daoism','daoist','taoism','taoist','tao te ching','道教','道家','道德经','道德經',
    '玄门','玄門','全真','正一','道经','道經','宫观','宮觀','黄大仙','黃大仙','도교'
]
ASSOCIATED = [
    '武当','武當','wudang','太极','太極','taiji','qigong','气功','氣功','老子','laozi',
    '玄天上帝','太乙救苦天尊','斗姆','斗母','九皇','道法','科仪','科儀'
]
ACTIVITY = [
    'conference','symposium','forum','workshop','seminar','course','class','training','retreat',
    'call for','proposal','registration','meeting','exchange','lecture','festival','exhibition',
    'event','open day','pilgrimage','conference','会议','會議','论坛','論壇','研讨会','研討會',
    '交流','征稿','徵稿','讲座','講座','活动','活動','报名','報名','课程','課程','培训','培訓',
    '研修','法会','法會','醮','科仪','科儀','祈福','讲经','講經','展览','展覽','展演','文化节',
    '文化節','庙会','廟會','招生','参访','參訪','巡礼','巡禮','国際会議','シンポジウム','募集',
    '학술대회','교류','강좌'
]
FUTURE_WORDS = [
    'upcoming','registration','register','call for','deadline','apply','applications','open for',
    'save the date','schedule','报名','報名','征稿','徵稿','截止','招募','招生','即将','即將',
    '预告','預告','开放','開放','现正','現正','筹备','籌備','接受报名','接受報名','募集','申込',
    '모집','등록'
]
PAST_NEWS = [
    '圆满结束','圓滿結束','圆满举行','圓滿舉行','成功举办','成功舉辦','顺利举办','順利舉辦',
    '活动回顾','活動回顧','会议召开','會議召開','已举办','已舉辦','闭幕','閉幕','开班式','開班式'
]
DENY_DOMAINS = [
    'wikipedia.org','amazon.','facebook.com','instagram.com','pinterest.','quora.com','reddit.com',
    'youtube.com','tiktok.com','happeningnext.','allevents.','frederickhotelnyc.com',
    'bookretreats.com','cectv.net'
]
TRUST_DOMAINS = [
    'taoist.org.cn','dao.china.com.cn','daoisms.com.cn','wdsdjxh.com','xiancyg.cn','sdsdjxh.com',
    'sxdaojiao.com','bixiaci.org','dao.crs.cuhk.edu.hk','daoist.org','siksikyuen.org.hk',
    'macaotaoist.org.mo','daoglobe.com','aarweb.org','ea-cp.eu','daoistfoundation.org',
    'edu.cn','edu.hk','edu.tw','.gov.cn','.gov.tw','.ac.cn','.ac.hk','.ac.tw'
]
GENERIC_TITLES = [
    '中国道教协会 - taoist.org.cn','中国道教协会','events — daoist foundation',
    'events - daoist foundation','upcoming events, workshops, and seminars',
    'the 10 best taoist retreats','活动 — daoist foundation','schedule - taoist studies institute'
]
REVIEWED_EXPIRED_URLS = {
    'https://www.daoisms.com.cn/2026/22/20/126469',
    'https://www.daoisms.com.cn/2026/19/15/125869'
}
TRACKING_KEYS = {'utm_source','utm_medium','utm_campaign','utm_term','utm_content','gclid','fbclid','ref'}

COUNTRY_HINTS = [
    ('中国大陆', ['china','beijing','shanghai','中国大陆','北京','上海','杭州','南京','成都','广州','西安','武汉','浙江','山东','四川','陕西','湖北','江苏','广东','福建','河南','河北','山西']),
    ('香港', ['hong kong','香港']),
    ('澳门', ['macao','macau','澳门','澳門']),
    ('台湾', ['taiwan','taipei','臺灣','台湾','台北','臺北']),
    ('日本', ['japan','tokyo','kyoto','日本','东京','東京','京都']),
    ('韩国', ['korea','seoul','韩国','韓國','首尔','서울']),
    ('新加坡', ['singapore','新加坡']),
    ('马来西亚', ['malaysia','kuala lumpur','马来西亚','馬來西亞']),
    ('美国', ['united states','usa','u.s.','america','denver','new york','chicago','美国','美國']),
    ('加拿大', ['canada','vancouver','toronto','加拿大','温哥华','溫哥華']),
    ('英国', ['united kingdom','uk','london','britain','英国','英國']),
    ('法国', ['france','paris','法国','法國']),
    ('德国', ['germany','berlin','德国','德國']),
    ('波兰', ['poland','poznan','poznań','波兰','波蘭']),
    ('澳大利亚', ['australia','sydney','melbourne','澳大利亚','澳洲'])
]

MONTHS = {m.lower():i for i,m in enumerate(
    ['January','February','March','April','May','June','July','August','September','October','November','December'], 1
)}
MONTHS.update({m[:3].lower():i for m,i in list(MONTHS.items())})

def canonical(url: str) -> str:
    try:
        p = urlparse(url)
        q = [(k,v) for k,v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in TRACKING_KEYS]
        return urlunparse((p.scheme or 'https', p.netloc.lower(), p.path.rstrip('/') or '/', '', urlencode(q), ''))
    except Exception:
        return url

def contains_any(text, words):
    t = (text or '').lower()
    return any(w.lower() in t for w in words)

def trusted(url: str) -> bool:
    d = urlparse(url).netloc.lower()
    return any(x in d for x in TRUST_DOMAINS)

def domain_denied(url: str) -> bool:
    d = urlparse(url).netloc.lower()
    if canonical(url).rstrip('/') in {x.rstrip('/') for x in REVIEWED_EXPIRED_URLS}:
        return True
    return any(x in d for x in DENY_DOMAINS)

def generic_page(title: str, url: str) -> bool:
    t = (title or '').strip().lower()
    if any(x.lower() in t for x in GENERIC_TITLES):
        return True
    path = urlparse(url).path.rstrip('/').lower()
    if t in {'events','event','schedule','活动','活動','通知公告'}:
        return True
    if t.startswith('upcoming events') or path.endswith('/upcoming-events'):
        return True
    if path in {'', '/events', '/event', '/schedule'} and len(t) < 45:
        return True
    return False

def title_key(title: str) -> str:
    s = re.sub(r'20\d{2}|第[一二三四五六七八九十百0-9]+届|\s+', '', title or '')
    s = re.sub(r'[^\w\u4e00-\u9fff]', '', s.lower())
    return s[:90]

def extract_dates(text: str):
    out = []
    text = text or ''
    # 2026年10月17日 / 2026-10-17 / 2026.10.17
    for y,m,d in re.findall(r'(?<!\d)(20\d{2})[年\-/\.](\d{1,2})[月\-/\.](\d{1,2})日?', text):
        try: out.append(date(int(y), int(m), int(d)))
        except ValueError: pass

    # English dates
    pat = r'\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(20\d{2})\b'
    for mon,day,year in re.findall(pat, text, re.I):
        try: out.append(date(int(year), MONTHS[mon.lower()], int(day)))
        except (ValueError, KeyError): pass
    return sorted(set(out))

def explicit_future_dates(text: str):
    return [d for d in extract_dates(text) if d >= TODAY_DATE]

def looks_current_or_future(title: str, body: str, url: str) -> bool:
    text = f'{title} {body}'
    dates = extract_dates(text)
    future = [d for d in dates if d >= TODAY_DATE]

    if future:
        return True
    if dates and max(dates) < TODAY_DATE:
        return False

    if contains_any(text, PAST_NEWS) and not contains_any(text, FUTURE_WORDS):
        return False
    if re.search(r'\b202[7-9]\b', text):
        return True

    # Search snippets often write ranges such as "31 July - 16 August" while
    # putting the year only once in the title. Infer the current-year month
    # so an already-finished summer event is not kept in October.
    if str(TODAY_DATE.year) in text:
        eng_months = [MONTHS[m.lower()] for m in re.findall(
            r'\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b',
            text, re.I
        ) if m.lower() in MONTHS]
        cn_months = [int(m) for m in re.findall(r'(?<!\d)(\d{1,2})月', text)]
        all_months = eng_months + [m for m in cn_months if 1 <= m <= 12]
        if all_months:
            if max(all_months) < TODAY_DATE.month:
                return False
            if max(all_months) >= TODAY_DATE.month:
                return True

    if contains_any(text, FUTURE_WORDS):
        return True
    return False

def score_item(title: str, body: str, url: str) -> int:
    text = f'{title} {body}'
    if domain_denied(url):
        return -99
    if not contains_any(text, ACTIVITY):
        return -20

    direct = sum(1 for x in DIRECT if x.lower() in text.lower())
    assoc = sum(1 for x in ASSOCIATED if x.lower() in text.lower())
    if direct == 0 and assoc == 0:
        return -20

    score = direct * 4 + min(assoc, 3) * 2
    if contains_any(title, ACTIVITY): score += 3
    if contains_any(text, FUTURE_WORDS): score += 2
    if trusted(url): score += 4
    if url.startswith('https://'): score += 1
    return score

def is_mostly_chinese(text: str) -> bool:
    if not text: return True
    han = len(re.findall(r'[\u4e00-\u9fff]', text))
    letters = len(re.findall(r'[A-Za-z\u4e00-\u9fff]', text))
    return letters == 0 or han / letters > 0.45

def translate(text: str, limit=240) -> str:
    text = re.sub(r'\s+', ' ', (text or '')).strip()[:limit]
    if not text or is_mostly_chinese(text):
        return text
    try:
        r = requests.get(
            'https://translate.googleapis.com/translate_a/single',
            params={'client':'gtx','sl':'auto','tl':'zh-CN','dt':'t','q':text},
            timeout=12,
            headers={'User-Agent':'Mozilla/5.0'}
        )
        r.raise_for_status()
        data = r.json()
        return ''.join(part[0] for part in data[0] if part and part[0]) or text
    except Exception:
        return text

def trim_summary(text: str, n=110) -> str:
    text = re.sub(r'\s+', ' ', text or '').strip()
    if len(text) <= n:
        return text
    cut = text[:n]
    for mark in ['。','；',';','.']:
        pos = cut.rfind(mark)
        if pos > n * 0.55:
            return cut[:pos+1]
    return cut.rstrip('，,；;。.') + '…'

def infer_country(text: str, url: str) -> str:
    t = (text or '').lower()
    domain = urlparse(url).netloc.lower()
    for country,hints in COUNTRY_HINTS:
        if any(h.lower() in t for h in hints):
            return country
    if domain.endswith('.hk'): return '香港'
    if domain.endswith('.tw'): return '台湾'
    if domain.endswith('.mo'): return '澳门'
    if domain.endswith('.cn'): return '中国大陆'
    if domain.endswith('.jp'): return '日本'
    if domain.endswith('.kr'): return '韩国'
    return '国际'

def region(country: str, text: str) -> str:
    if contains_any(text, ['online','zoom','线上','線上','网络','網絡','webinar']):
        return '线上'
    if country == '中国大陆':
        return '国内'
    if country in {'香港','澳门','台湾'}:
        return '港澳台'
    return '海外'

def event_type(text: str) -> str:
    rules = [
        ('法会科仪', ['法会','法會','科仪','科儀','醮','祈福','圣诞','聖誕','礼斗','禮斗','拜忏','拜懺']),
        ('培训课程', ['培训','培訓','课程','課程','研修','招生','training','course','class','seminary']),
        ('论坛会议', ['论坛','論壇','会议','會議','研讨会','研討會','conference','symposium','forum']),
        ('讲座讲经', ['讲座','講座','讲经','講經','lecture']),
        ('文化展演', ['展览','展覽','展演','文化节','文化節','festival','exhibition']),
        ('武术养生', ['太极','太極','武术','武術','气功','氣功','养生','養生','taiji','qigong','martial']),
        ('交流参访', ['交流','参访','參訪','巡礼','巡禮','exchange','pilgrimage']),
        ('征稿征集', ['征稿','徵稿','征集','call for','proposal'])
    ]
    for name, words in rules:
        if contains_any(text, words):
            return name
    return '道教活动'

def source_name(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix('www.') or '原网站'

def stable_id(url: str) -> str:
    return hashlib.sha1(canonical(url).encode('utf-8')).hexdigest()[:14]

def collect():
    found = []
    with DDGS() as ddgs:
        for q in QUERIES:
            try:
                rows = ddgs.text(q, region='wt-wt', safesearch='moderate', timelimit='y', max_results=8) or []
                for r in rows:
                    title = (r.get('title') or '').strip()
                    body = (r.get('body') or '').strip()
                    url = canonical((r.get('href') or '').strip())
                    if not title or not url or domain_denied(url) or generic_page(title, url):
                        continue
                    if not looks_current_or_future(title, body, url):
                        continue
                    # Prefer concrete event pages over category/index pages.
                    if not contains_any(title, ACTIVITY) and not explicit_future_dates(f'{title} {body}') and not re.search(r'\b202[7-9]\b', title):
                        continue
                    score = score_item(title, body, url)
                    if score < 7:
                        continue
                    found.append((score, title, body, url))
                time.sleep(0.7)
            except Exception as e:
                print(f'[warn] search failed: {q}: {e}')
    return found

def parse_iso(s: str):
    try:
        return date.fromisoformat(s)
    except Exception:
        return None

def not_expired(item: dict) -> bool:
    exp = parse_iso(item.get('expires_on',''))
    if exp:
        return exp >= TODAY_DATE
    # 自动条目没有明确到期日：若最近 60 天仍被搜索发现则保留
    last = parse_iso(item.get('last_seen','') or item.get('discovered_at',''))
    return bool(last and last >= TODAY_DATE - timedelta(days=60))

def main():
    db = json.loads(DATA.read_text(encoding='utf-8'))
    items = db.get('items', [])

    by_url = {canonical(x.get('source_url','')): x for x in items if x.get('source_url')}
    by_title = {title_key(x.get('title_zh') or x.get('title','')): x for x in items if title_key(x.get('title_zh') or x.get('title',''))}

    candidates = {}
    for score,title,body,url in collect():
        key = title_key(title)
        prev = candidates.get(key)
        if not prev or score > prev[0]:
            candidates[key] = (score,title,body,url)

    added = 0
    refreshed = 0

    for score,title,body,url in sorted(candidates.values(), reverse=True):
        key = title_key(title)
        existing = by_url.get(url) or by_title.get(key)
        dates = explicit_future_dates(f'{title} {body}')
        expires_on = max(dates).isoformat() if dates else ''

        if existing:
            existing['last_seen'] = TODAY
            if expires_on:
                old = parse_iso(existing.get('expires_on',''))
                new = date.fromisoformat(expires_on)
                if not old or new > old:
                    existing['expires_on'] = expires_on
            refreshed += 1
            continue

        combined = f'{title} {body}'
        country = infer_country(combined, url)
        item = {
            'id': stable_id(url),
            'title': title,
            'title_zh': translate(title, 180),
            'country': country,
            'city': '',
            'region': region(country, combined),
            'type': event_type(combined),
            'event_date': '',
            'deadline': '',
            'summary_zh': trim_summary(translate(body, 300)),
            'source_name': source_name(url),
            'source_url': url,
            'discovered_at': TODAY,
            'last_seen': TODAY,
            'expires_on': expires_on,
            'manual': False,
            'score': score
        }
        items.append(item)
        by_url[url] = item
        by_title[title_key(item['title_zh'] or item['title'])] = item
        added += 1
        if added >= 15:
            break

    # 过期删除；手工种子也按照 expires_on 自动退出
    items = [x for x in items if not_expired(x)]

    # 再次按标题去重，优先手工核实来源，其次分数高的来源
    dedup = {}
    for x in items:
        key = title_key(x.get('title_zh') or x.get('title','')) or x.get('id')
        old = dedup.get(key)
        quality = (1 if x.get('manual') else 0, x.get('score',0))
        old_quality = (1 if old and old.get('manual') else 0, old.get('score',0) if old else -1)
        if not old or quality > old_quality:
            dedup[key] = x

    items = list(dedup.values())
    items.sort(key=lambda x: (
        x.get('discovered_at',''),
        x.get('expires_on','9999-12-31'),
        x.get('score',0)
    ), reverse=True)

    # 宽覆盖，但避免网页无限膨胀
    items = items[:140]
    DATA.write_text(json.dumps({'updated_at':TODAY,'items':items}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'updated {TODAY}; added {added}; refreshed {refreshed}; total {len(items)}')

if __name__ == '__main__':
    main()
