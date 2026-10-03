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
    # 中国大陆线上：慕课/公开课/读书会/直播/混合课程
    '道教 慕课 在线课程 开课中 2026 2027',
    '道家 哲学 慕课 在线课程 开课中 2026 2027',
    '道德经 在线课程 慕课 2026 2027',
    '道教 线上 公开课 直播 读书会 2026 2027',
    '道教 Zoom 腾讯会议 线上 讲座 读书会 2026 2027',
    'site:chinaooc.com.cn 道教 道家 道德经 开课中 2026 2027',
    'site:cscr.swjtu.edu.cn 道教 Zoom 线上 读书会 2026 2027',

    # 港澳台
    '香港 道教 活动 报名 课程 论坛 2026 2027',
    '台湾 道教 活动 报名 宫庙 论坛 2026 2027',
    '澳門 澳门 道教 文化节 论坛 活动 2026 2027',
    # 台湾线上：同步直播、Google Meet、Zoom、网课、读书会
    '台灣 道教 線上 課程 直播 Google Meet Zoom 2026 2027',
    '台灣 道家 道教 經典 研習 線上 同步 2026 2027',
    '台灣 道教 直播 講座 讀書會 線上 2026 2027',
    'site:lungshan.org.tw 道家 道教 線上 2026 2027',
    'site:edu.tw 道教 線上 直播 講座 2026 2027',

    # 海外及国际学术/文化交流
    'Daoism upcoming events conference workshop course 2026 2027',
    'Daoist cultural exchange conference workshop registration 2026 2027',
    'Daoist studies conference call for papers 2026 2027',
    'Taoism festival lecture seminar retreat 2026 2027',
    'Tao Te Ching international forum cultural exchange 2026 2027',
    'Wudang Taiji Taoist cultural event 2026 2027',
    '道教 国際 会議 シンポジウム 交流 募集 2026 2027',
    '도교 국제 학술대회 문화 교류 모집 2026 2027',

    # 文化交流、宫观互访、教务、非遗与国际组织
    '道教 文化交流 宫观 互访 参访 谒祖 2026 2027',
    '道教 国际交流 人才 培训 研修 2026 2027',
    '道教 传戒 授箓 冠巾 传度 2026 2027',
    '道教 音乐 道乐 非遗 展演 2026 2027',
    '道德经 书法 征文 歌曲 创作 比赛 2026 2027',
    '道教 青年 体验周 夏令营 研学 2026 2027',
    '道教 跨宗教 文明对话 宗教和谐 2026 2027',
    '世界道教联合会 东西道教 合作 交流 2026 2027',
    '世界道教联合会 道经翻译 文化传播 2026 2027',
    '澳门 道教文化节 2026 2027',
    '香港 道教日 罗天大醮 2027',
    'site:macaotaoist.org.mo 道教 文化节 交流 参访 2026 2027',
    'site:fysk.org 道教 活动 班组 讲座 2026 2027',
    'site:cts65.org 道教 课程 招生 2026 2027',
    'site:taoismmalaysia.my 道教 活动 交流 2026 2027',
    'site:taoistfederation.org.sg 道教 活动 交流 2026 2027',
    'site:daoistassociationofeurope.org Daoist cultural exchange collaboration 2026 2027',

    # 出海传播：中医药与中华养生文化
    '中医药 国际传播 海外 交流 会议 报名 2026 2027',
    '中医药 海外 文化交流 讲座 展示 参展 2026 2027',
    '中医 海外 访问 教学 讲座 合作 2026 2027',
    '针灸 中医 海外 国际会议 交流 2026 2027',
    'traditional chinese medicine international cultural exchange conference 2026 2027',
    'TCM overseas lecture workshop cultural exchange speaker 2026 2027',
    'Chinese medicine visiting teacher guest lecture international 2026 2027',
    'Chinese cultural center traditional Chinese medicine lecture 2026 2027',
    'Confucius Institute traditional Chinese medicine lecture 2026 2027',
    'site:wfcms.org 2026 新加坡 埃及 中医药 国际交流',
    'site:singaporetcm.edu.sg 2026 lecture course symposium TCM',
    'site:dcg-health.com TCM Konferenz 2026',

    # 出海机会：招聘、任教、顾问、志愿者、民间团体、访问教师
    '2027 国际中文教育志愿者 1066 27国 招募 海外',
    '孔子学院 招聘 公派教师 2027 海外',
    '孔子学院 武术老师 太极 书法 中华文化 教师 招聘 2026 2027',
    '海外 华文学校 中文教师 中华文化教师 招聘 2026 2027',
    '海外 中国文化中心 教师 讲师 顾问 招聘 2026 2027',
    '海外 道观 招聘 道士 道长 讲师 顾问 2026 2027',
    '海外 道教协会 招聘 顾问 访问教师 客座讲师 2026 2027',
    'Daoist teacher vacancy hiring resident instructor 2026 2027',
    'Taoist priest hiring temple teacher 2026 2027',
    'Daoist consultant cultural association guest lecturer 2026 2027',
    'visiting Daoist teacher apply 2026 2027',
    '中医 海外 招聘 讲师 教师 顾问 2026 2027',
    'traditional Chinese medicine lecturer vacancy 2026 2027',
    'Chinese medicine guest lecturer visiting professor 2026 2027',
    '太极 气功 海外 招聘 instructor 2026 2027',
    'Chinese culture instructor calligraphy tai chi recruitment 2026 2027',
    '海外 华人社团 中华文化 顾问 招募 邀请 讲座 2026 2027',
    'Chinese association cultural advisor guest speaker 2026 2027',
    'festival call for presenters Chinese culture TCM Tai Chi 2026 2027',
    'site:edu.cn 2027 国际中文教育志愿者 1066 27国',
    'site:ci.cn 招募 合作伙伴 孔子学院 2026 2027',
    'site:singaporetcm.edu.sg 工作机会 2026 中医 顾问',
    'site:imu.edu.my careers TCM lecturer',
    'site:careers.singhealth.com.sg acupuncturist TCM'
]

LOW_BARRIER_QUERIES = [
    # 社区/兼职/临时教学：学历要求通常低于高校和大机构
    '"Tai Chi instructor" community center hiring 2026 2027',
    '"Tai Chi instructor" recreation center part time 2026 2027',
    '"Tai Chi instructor" senior center casual 2026 2027',
    '"Qigong instructor" community center part time 2026 2027',
    '"Qigong instructor" senior living hiring 2026 2027',
    '"Chinese culture instructor" community center part time 2026 2027',
    '"Chinese cultural instructor" volunteer community 2026 2027',
    'site:governmentjobs.com "Tai Chi Instructor" 2026',
    'site:jobbank.gc.ca "tai-chi instructor" 2026',
    'site:indeed.com "Tai Chi Instructor" community 2026',
    # 节庆、表演、摊位、工作坊：允许个人/小团体直接报名
    '"2027 Lunar New Year" performer application',
    '"2027 Chinese New Year" performer application',
    '"2027 Lunar New Year" vendor application',
    '"Chinese festival" "call for performers" 2027',
    '"Chinese culture festival" performer application 2027',
    '"call for presenters" tai chi qigong Chinese medicine 2026 2027',
    '"call for workshop facilitators" Chinese culture 2026 2027',
    '"community festival" tai chi qigong performer application',
    # 民间协会/华人社团/中文学校
    '"Chinese association" guest speaker tai chi qigong 2026 2027',
    '"Chinese community center" instructor tai chi calligraphy 2026 2027',
    '"Chinese school" part time culture teacher calligraphy martial arts 2026 2027',
    '"Chinatown" cultural instructor workshop 2026 2027',
    '"Chinese cultural association" volunteer teacher 2026 2027',
    '海外 华人社团 太极 气功 书法 讲师 招募 2026 2027',
    '海外 华文学校 武术 太极 书法 教师 招聘 2026 2027',
    '海外 中国文化节 表演者 工作坊 招募 2027',
    # 道教/养生小机构、静修与民间合作
    '"Daoist center" guest teacher volunteer workshop 2026 2027',
    '"Taoist temple" volunteer resident teacher 2026 2027',
    '"Daoist association" guest lecturer volunteer 2026 2027',
    '"qigong retreat center" guest teacher host retreat 2027',
    '"wellness center" tai chi qigong guest instructor 2026 2027',
    '"traditional Chinese medicine" community workshop speaker 2026 2027',
    # 本地语言扩大覆盖
    '太極拳 講師 募集 海外 2026 2027',
    '気功 講師 募集 中国文化 2026 2027',
    '태극권 강사 모집 중국문화 2026 2027',
    '기공 강사 모집 중국문화 2026 2027',
    '"Tai Chi Kursleiter" gesucht 2026 2027',
    '"Qigong Kursleiter" gesucht 2026 2027',
    '"professeur tai chi" recrutement 2026 2027',
    '"professeur qigong" recrutement 2026 2027',
    '"instructor tai chi" empleo 2026 2027',
    '"profesor qigong" cultura china 2026 2027',
    # 平台型公开招募：作为发现入口
    'site:eventbrite.com "Lunar New Year" performer application 2027',
    'site:eventbrite.com tai chi qigong workshop community 2026 2027',
    'site:meetup.com tai chi qigong Chinese culture organizer 2026 2027',
    'site:volunteermatch.org Chinese culture volunteer tai chi 2026 2027',
    'site:idealist.org Chinese culture volunteer instructor 2026 2027',
    'site:workaway.info tai chi qigong volunteer host',
    '"community instructor" tai chi qigong 2026 2027',
    '"recreation instructor" tai chi 2026 2027',
    '"senior center" tai chi instructor hiring 2026 2027',
    '"library" Chinese culture workshop presenter 2026 2027',
    # 已验证存在有效机会的平台/固定来源
    'site:governmentjobs.com "Volunteer Tai Chi/QiGong Instructor"',
    'site:governmentjobs.com "Tai Chi Instructor" "No education requirement"',
    'site:neonmarketplace.nsw.gov.au "Lunar New Year" performer',
    'site:neonmarketplace.nsw.gov.au "Lunar New Year" stallholder',
    'site:georgesriver.nsw.gov.au Lunar New Year performers stallholders',
    'site:626nightmarket.com performer application',
    'site:asianfestivalaz.com 2027 vendor performer volunteer',
    'site:ccchouston.org 2027 Lunar New Year performer vendor volunteer',
    'site:squarespace.com "2027 Lunar New Year" performer volunteer application',
    # 固定低门槛来源：已人工验证过会持续产出
    'site:cityofsydney.nsw.gov.au/opportunities Lunar Festival community performance',
    'site:chineseparade.com 2027 parade application',
    'site:cccsydney.org volunteer Chinese culture',
    'site:ccccph.org volunteer Chinese culture',
    'site:chinesecultureconnection.org volunteer application tai chi',
    'site:cccvan.com volunteerism Chinese Cultural Centre',
    'site:rcca.ca volunteer Chinese culture tai chi',
    'site:chineseassociationmississauga.com volunteer',
    'site:thchinese.org.uk volunteer Chinese association',
    'site:kungfu-school.de/show Chinese New Year 2027 mitmachen',
    'site:chineseculturecentre.co.za volunteer get involved',
    'site:fetechinoise.ca volunteer 2027 Chinese New Year',
    'site:workaway.info/en/host qigong tai chi "Last activity" 2026'
]

DIRECT = [
    'daoism','daoist','taoism','taoist','tao te ching','道教','道家','道德经','道德經',
    '玄门','玄門','全真','正一','道经','道經','宫观','宮觀','黄大仙','黃大仙','孔子学院','孔子學院','国际中文','國際中文','中华文化','中華文化','华文学校','華文學校','Confucius Institute','Chinese language','Chinese culture','中医','中醫','中医药','中醫藥','traditional chinese medicine','tcm','针灸','針灸','acupuncture','도교'
]
ASSOCIATED = [
    '武当','武當','wudang','太极','太極','taiji','qigong','气功','氣功','老子','laozi',
    '玄天上帝','太乙救苦天尊','斗姆','斗母','九皇','道法','科仪','科儀'
]
ACTIVITY = [
    'conference','symposium','forum','workshop','seminar','course','class','training','retreat',
    'call for','proposal','registration','meeting','exchange','lecture','festival','exhibition',
    'event','open day','pilgrimage','conference','mooc','livestream','live stream','online','webinar','会议','會議','论坛','論壇','研讨会','研討會',
    '交流','征稿','徵稿','讲座','講座','活动','活動','报名','報名','课程','課程','培训','培訓',
    '研修','法会','法會','醮','科仪','科儀','祈福','讲经','講經','展览','展覽','展演','文化节',
    '文化節','庙会','廟會','招生','参访','參訪','巡礼','巡禮','慕课','慕課','网课','網課','公开课','公開課','直播','线上同步','線上同步','读书会','讀書會','共修','国際会議','シンポジウム','募集',
    '학술대회','교류','강좌','招聘','招募','征聘','徵聘','聘请','聘請','岗位','崗位','教师','教師','讲师','講師','顾问','顧問','志愿者','志願者','vacancy','job','hiring','recruitment','instructor','advisor','consultant','volunteer','visiting professor','guest lecturer','resident teacher'
]
LOW_BARRIER_SIGNALS = [
    'no education requirement','all levels welcome','high school','ged','0 years','entry level',
    'part time','part-time','casual','temporary','contract','volunteer','performer','vendor',
    'community center','community centre','recreation center','recreation centre','senior center',
    'guest speaker','guest instructor','workshop facilitator','open call','apply now','anyone can',
    'no formal training','no degree','个人','個人','团体','團體','志愿者','志願者','表演者','摊位',
    '攤位','兼职','兼職','临时','臨時','社区','社區','公开招募','公開招募','公开申请','公開申請'
]
HIGH_BARRIER_SIGNALS = [
    'phd required','doctoral degree required','master degree required','master\'s degree required',
    'medical license required','licensed physician','board certified','faculty appointment',
    'professor required','当地注册','當地註冊','执业证','執業證','博士学位','博士學位'
]
OUTBOUND_SIGNALS = [
    'international','overseas','global','exchange','cultural exchange','conference','forum','exhibition',
    'speaker','lecture','workshop','call for','visiting','collaboration','国际','國際','海外','全球','交流',
    '文化传播','文化傳播','传播','傳播','论坛','論壇','会议','會議','展览','展覽','参展','參展','投稿',
    '讲座','講座','访问','訪問','合作','招聘','招募','征聘','聘请','岗位','教师','讲师','顾问','志愿者','vacancy','job','hiring','recruitment','instructor','advisor','consultant','volunteer','visiting professor','guest lecturer','resident teacher','孔子学院','国际中文','中华文化','新加坡','埃及','欧洲','歐洲','美国','美國','德国','德國'
]
FUTURE_WORDS = [
    'upcoming','registration','register','call for','deadline','apply','applications','open for',
    'save the date','schedule','apply now','career','vacancy','hiring','recruitment','报名','報名','征稿','徵稿','截止','招聘','征聘','聘请','岗位','招募','招生','即将','即將',
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
    'macaotaoist.org.mo','daoglobe.com','aarweb.org','ea-cp.eu','daoistfoundation.org','chinaooc.com.cn','lungshan.org.tw','cscr.swjtu.edu.cn',
    'edu.cn','edu.hk','edu.tw','.gov.cn','.gov.tw','.ac.cn','.ac.hk','.ac.tw','governmentjobs.com','jobbank.gc.ca','volunteermatch.org'
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
REVIEWED_BLOCKED_URLS = {
    'https://www.hkcd.com.hk/hkcdweb/content/2026/08/13/content_8769564.html',
    'https://www.hkcd.com/newsTopic_content.php?id=8769564',
    'https://www.taoism.tw/教育內涵/課程設計',
    'http://www.cts65.org/upload/75b1e278be41ab0033b03c5a25d2125f.pdf'
}
CHINESE_URL_OVERRIDES = {
    'https://wudang.org/events/i-ching-learning/i-ching-beginner-course-singapore':
        'https://wudang.org/zh/events/i-ching-learning/i-ching-beginner-course-singapore',
    'https://wudang.org/events/internal-arts-wellness/baduanjin-workshop-september':
        'https://wudang.org/zh/events/internal-arts-wellness/baduanjin-workshop-september',
    'https://www.daoglobe.com/eng.php/News/190.html':
        'https://www.daoglobe.com/News/190.html',
    'https://www.phil.arts.cuhk.edu.hk/conference/ISCP2027/en':
        'https://www.phil.arts.cuhk.edu.hk/conference/ISCP2027/gb/',
    'https://www.phil.arts.cuhk.edu.hk/conference/ISCP2027/en/':
        'https://www.phil.arts.cuhk.edu.hk/conference/ISCP2027/gb/'
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
    ('澳大利亚', ['australia','sydney','melbourne','澳大利亚','澳洲']),
    ('泰国', ['thailand','bangkok','khon kaen','泰国','泰國']),
    ('印度尼西亚', ['indonesia','jakarta','印尼','印度尼西亚']),
    ('俄罗斯', ['russia','俄罗斯','俄羅斯']),
    ('哈萨克斯坦', ['kazakhstan','哈萨克斯坦','哈薩克斯坦']),
    ('埃及', ['egypt','cairo','埃及']),
    ('斯里兰卡', ['sri lanka','斯里兰卡','斯里蘭卡'])
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

def prefer_chinese_url(url: str) -> str:
    return CHINESE_URL_OVERRIDES.get(url, CHINESE_URL_OVERRIDES.get(url.rstrip('/'), url))

def trusted(url: str) -> bool:
    d = urlparse(url).netloc.lower()
    return any(x in d for x in TRUST_DOMAINS)

def domain_denied(url: str) -> bool:
    d = urlparse(url).netloc.lower()
    cu = canonical(url).rstrip('/')
    if cu in {x.rstrip('/') for x in REVIEWED_EXPIRED_URLS}:
        return True
    if cu in {canonical(x).rstrip('/') for x in REVIEWED_BLOCKED_URLS}:
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
    # 同等质量下优先中文页面，尤其方便长辈直接阅读。
    # 这里只给小幅加分，不允许中文转载压过更权威的外文官方原页。
    if is_mostly_chinese(f'{title} {body}'): score += 3
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
    if contains_any(text, ['online','zoom','线上','線上','网络','網絡','webinar','google meet','腾讯会议','騰訊會議','慕课','慕課','网课','網課','直播','线上同步','線上同步']):
        return '线上'
    if country == '中国大陆':
        return '国内'
    if country in {'香港','澳门','台湾'}:
        return '港澳台'
    return '海外'

def outbound_focus(country: str, text: str) -> bool:
    return contains_any(text, OUTBOUND_SIGNALS) and contains_any(text, DIRECT + ASSOCIATED)

def low_barrier_focus(text: str) -> bool:
    if contains_any(text, HIGH_BARRIER_SIGNALS):
        return False
    return contains_any(text, LOW_BARRIER_SIGNALS) and contains_any(text, DIRECT + ASSOCIATED)

def event_type(text: str) -> str:
    rules = [
        ('海外招聘', ['招聘','征聘','徵聘','聘请','聘請','vacancy','hiring','recruitment','job opening','lecturer position','instructor position']),
        ('法会科仪', ['法会','法會','科仪','科儀','醮','祈福','圣诞','聖誕','礼斗','禮斗','拜忏','拜懺']),
        ('培训课程', ['培训','培訓','课程','課程','研修','招生','training','course','class','seminary']),
        ('论坛会议', ['论坛','論壇','会议','會議','研讨会','研討會','conference','symposium','forum']),
        ('讲座讲经', ['讲座','講座','讲经','講經','lecture']),
        ('文化展演', ['展览','展覽','展演','文化节','文化節','festival','exhibition']),
        ('武术养生', ['太极','太極','武术','武術','气功','氣功','养生','養生','taiji','qigong','martial']),
        ('交流参访', ['交流','参访','參訪','巡礼','巡禮','exchange','pilgrimage']),
        ('征稿征集', ['征稿','徵稿','征集','call for','proposal']),
        ('教务传承', ['传戒','傳戒','授箓','授籙','冠巾','传度','傳度','皈依']),
        ('文化交流', ['文化交流','文明对话','文明對話','宗教和谐','宗教和諧','合作计划','合作計劃','collaboration']),
        ('交流参访', ['互访','互訪','参访','參訪','谒祖','謁祖','参学','參學','研学','研學','pilgrimage']),
        ('文化展演', ['道乐','道樂','非遗','非遺','书法','書法','歌曲创作','歌曲創作'])
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
        query_sets = [
            (QUERIES, 8, 7, 0.7),
            # 低门槛方向多翻几页结果，并允许稍低的初筛分数，之后仍做相关性/日期过滤。
            (LOW_BARRIER_QUERIES, 20, 5, 0.35),
        ]
        for queries, max_results, min_score, pause in query_sets:
          for q in queries:
            try:
                rows = ddgs.text(q, region='wt-wt', safesearch='moderate', timelimit='y', max_results=max_results) or []
                for r in rows:
                    title = (r.get('title') or '').strip()
                    body = (r.get('body') or '').strip()
                    url = prefer_chinese_url(canonical((r.get('href') or '').strip()))
                    if not title or not url or domain_denied(url) or generic_page(title, url):
                        continue
                    if not looks_current_or_future(title, body, url):
                        continue
                    # Prefer concrete event pages over category/index pages.
                    if not contains_any(title, ACTIVITY) and not explicit_future_dates(f'{title} {body}') and not re.search(r'\b202[7-9]\b', title):
                        continue
                    score = score_item(title, body, url)
                    if score < min_score:
                        continue
                    found.append((score, title, body, url))
                time.sleep(pause)
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
            'score': score,
            'outbound': outbound_focus(country, combined),
            'outbound_action': '海外交流机会' if outbound_focus(country, combined) else '',
            'low_barrier': low_barrier_focus(combined),
            'barrier_note': '公开/社区型机会，具体签证和资格要求请看原文' if low_barrier_focus(combined) else ''
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
