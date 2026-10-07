#!/usr/bin/env python3
"""Polizei Brandenburg direct-source adapter.

This is deliberately state-scoped.  It reads the official Brandenburg police
archive, extracts a conservative subset of violent/property incidents, and can
either print a diagnostic report (default) or append validated events to the
shared 90-day cases.json (--write).

The adapter is incremental by design: use a 7-day overlapping window for daily
runs and a separate 90-day backfill when first enabling the state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data/cases.json"
CACHE = ROOT / "data/geocode_cache.json"
BASE = "https://polizei.brandenburg.de"
LISTING = BASE + "/pressemeldungen/{page}"
HEAD = {
    "User-Agent": "GermanyCrimeMonitor/3.0 (+https://github.com/1959124923wyz-sys/-1)",
    "Accept-Language": "de,en;q=0.8",
}

DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(20\d{2})(?!\d)")
ARTICLE_RE = re.compile(r"/pressemeldung/[^/]+/\d+(?:$|[?#])", re.I)
LOCATION_RE = re.compile(r"\((.+?)\s+-\s+([^)]+)\)")
STREET_RE = re.compile(
    r"\b([A-ZÄÖÜ][A-Za-zÄÖÜäöüß0-9.'’\-/ ]{1,70}?"
    r"(?:straße|strasse|allee|weg|platz|gasse|damm|ring|ufer|chaussee|markt|stieg|graben|wall))\b",
    re.I,
)

TRAFFIC = re.compile(
    r"Verkehrsunfall|Unfall|kollidiert|Zusammenstoß|Vorfahrt|Fahrerflucht|"
    r"Radfahrer\w* verletzt|Motorradfahrer\w* verstorben|Sturz",
    re.I,
)
FOLLOWUP = re.compile(
    r"Öffentlichkeitsfahndung|Tatverdächtig\w+ gesucht|Zeugen gesucht|"
    r"wer erkennt|Nachtrag|Folgemeldung|Verurteilung|Urteil|Haftrichter|"
    r"Ermittlungserfolg|Durchsuchung|Durchsuchungsbeschluss|Fahndungserfolg",
    re.I,
)
NON_EVENT = re.compile(
    r"Prävention|Tipps|Statistik|Bilanz|Kontrollaktion|Geschwindigkeitskontrolle|"
    r"Verkehrskontrolle|Aktionstag|Versammlung|Stellenausschreibung",
    re.I,
)
PREFILTER = re.compile(
    r"Mord|Totschlag|Tötungsdelikt|Leiche|tot aufgefunden|tödlich|"
    r"Raub|beraubt|Überfall|räuber|"
    r"Vergewalt|sexuell|"
    r"Messer|Stich|Schuss|Körperverletzung|Angriff|Auseinandersetzung|Streit eskaliert|"
    r"Einbruch|Einbrecher|aufgebrochen|Fahrrad.*(?:entwendet|gestohlen)|"
    r"Pedelec.*(?:entwendet|gestohlen)|E-Bike.*(?:entwendet|gestohlen)|"
    r"(?:PKW|Pkw|Auto|Fahrzeug).*?(?:entwendet|gestohlen|aufgebrochen)|"
    r"Taschendieb|Taschendiebstahl",
    re.I,
)
HOMICIDE = re.compile(r"Tötungsdelikt|Totschlag|\bMord\b|Mordkommission", re.I)
DEATH = re.compile(r"getötet|verstarb|verstorben|\bstarb\b|tot aufgefunden|tödlich verletzt", re.I)
SEXUAL = re.compile(r"Vergewaltig|sexuell\w*\s+(?:Nötigung|Übergriff)|sexueller Übergriff", re.I)
ROBBERY = re.compile(r"\bRaub\w*|beraubt|räuberisch|Raubüberfall|\bÜberfall\b", re.I)
WEAPON = re.compile(r"Messer|Stich|Schuss|Schusswaffe", re.I)
SERIOUS = re.compile(
    r"schwer\w* verletzt|lebensgefährlich|lebensbedrohlich|erheblich\w* verletzt|"
    r"stationär|Notoperation|gefährliche Körperverletzung|schwere Körperverletzung",
    re.I,
)
ASSAULT = re.compile(r"angegriffen|attackiert|verletzt|zugestochen|geschlagen|bedroht|Auseinandersetzung|Streit", re.I)
TRAFFIC_ACTOR = re.compile(r"Radfahrer(?:in)?|Fahrradfahrer(?:in)?|E-Scooter|Motorradfahrer(?:in)?", re.I)
TRAFFIC_EVENT = re.compile(r"Unfall|kollid|Sturz|gestürzt|Verkehr|angefahren|überfahren|verletzt|verstarb|tödlich", re.I)
PROPERTY_RULES = [
    ("Wohnungseinbruch", re.compile(r"Wohnungseinbruch|Einbruch.{0,55}(?:Wohnung|Wohnhaus|Einfamilienhaus|Wohngebäude)", re.I)),
    ("Diebstahl aus Fahrzeug", re.compile(
        r"(?:Lenkrad|Navigationsgerät|Airbag|Werkzeug|Wertsachen).{0,50}(?:aus|von).{0,35}(?:PKW|Pkw|Auto|Fahrzeug)|"
        r"(?:aus|in)\s+(?:einem|dem|einen)?\s*(?:PKW|Pkw|Auto|Fahrzeug).{0,70}(?:entwendet|gestohlen|Diebstahl|aufgebrochen)",
        re.I,
    )),
    ("Fahrzeugdiebstahl", re.compile(
        r"(?:PKW|Pkw|Auto|Fahrzeug).{0,45}(?:komplett\s+)?(?:entwendet|gestohlen)|"
        r"(?:entwendet|gestohlen).{0,35}(?:PKW|Pkw|Auto|Fahrzeug)",
        re.I,
    )),
    ("Fahrraddiebstahl", re.compile(
        r"(?:Fahrrad|Pedelec|E-Bike).{0,70}(?:entwendet|gestohlen|Diebstahl)|"
        r"(?:entwendet|gestohlen|Diebstahl).{0,55}(?:Fahrrad|Pedelec|E-Bike)",
        re.I,
    )),
    ("Taschendiebstahl", re.compile(r"Taschendieb|Taschendiebstahl", re.I)),
]
WEEKDAYS = {
    "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
    "freitag": 4, "samstag": 5, "sonnabend": 5, "sonntag": 6,
}


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3, connect=3, read=3, status=3, backoff_factor=.6,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update(HEAD)
    return s


def official_get(s: requests.Session, url: str, *, timeout: int = 35):
    """Fetch only the official Brandenburg police host.

    The site currently serves an incomplete certificate chain to GitHub-hosted
    runners. Browsers recover the chain, while Python/OpenSSL on Actions does
    not. TLS verification is therefore disabled *only* for this fixed public
    government host; redirects to any other host are rejected.
    """
    if not url.startswith(BASE + "/"):
        raise ValueError(f"refusing non-Brandenburg URL: {url}")
    r = s.get(url, timeout=timeout, verify=False)
    if not r.url.startswith(BASE + "/"):
        raise RuntimeError(f"unexpected redirect outside official host: {r.url}")
    return r


def parse_date(text: str) -> date | None:
    m = DATE_RE.search(text or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def listing_context(anchor) -> str:
    """Walk upward until the card text includes both date and locality.

    The Brandenburg CMS nests the clickable title several divs below the
    publication date/location, so using only the immediate parent loses those
    fields.
    """
    node = anchor
    fallback = clean(anchor.get_text(" ", strip=True))
    for _ in range(8):
        node = getattr(node, "parent", None)
        if node is None:
            break
        text = clean(node.get_text(" ", strip=True))
        if text:
            fallback = text
        if parse_date(text) and LOCATION_RE.search(text):
            return text
    return fallback


def listing_location(context: str) -> tuple[str, str]:
    m = LOCATION_RE.search(context or "")
    if not m:
        return "", ""
    left, district = clean(m.group(1)), clean(m.group(2))
    # Location before the first comma is normally the municipality/locality.
    city = clean(left.split(",")[0])
    return city, district


def event_date_from_text(text: str, published: date) -> tuple[date, str]:
    # Explicit calendar dates closest to event language win.
    candidates = []
    for m in DATE_RE.finditer(text[:5000]):
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        delta = (published - d).days
        if 0 <= delta <= 14:
            around = text[max(0, m.start()-100):m.end()+150]
            score = 2
            if re.search(r"Tatzeit|ereignet|geschah|kam es|gegen\s+\d", around, re.I):
                score += 6
            candidates.append((score, -delta, d))
    if candidates:
        return max(candidates)[2], "high"

    # Brandenburg articles frequently say "am Montag gegen 16:30 Uhr".
    m = re.search(
        r"(?:am|bereits am|in der Nacht zum)\s+"
        r"(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonnabend|Sonntag)\b",
        text[:4000], re.I,
    )
    if m:
        target = WEEKDAYS[m.group(1).lower()]
        delta = (published.weekday() - target) % 7
        # If a release on Monday says "am Montag", same-day is plausible.
        return published - timedelta(days=delta), "medium"

    return published, "publication_date"


def classify(title: str, body: str):
    joined = clean(title + " " + body[:4500])
    early = clean(title + " " + body[:1400])
    if (
        TRAFFIC.search(title)
        or (TRAFFIC_ACTOR.search(title) and TRAFFIC_EVENT.search(early))
        or NON_EVENT.search(title)
        or FOLLOWUP.search(title)
    ):
        return None

    labels = []
    if HOMICIDE.search(joined) and DEATH.search(joined):
        labels.append(("homicide", "Tötungsdelikt", 5))
    if SEXUAL.search(joined):
        labels.append(("sexual", "Sexualdelikt", 4))
    if ROBBERY.search(joined):
        labels.append(("robbery", "Raub/Überfall", 4))
    if (
        (WEAPON.search(early) and (SERIOUS.search(early) or ASSAULT.search(early)))
        or re.search(
            r"gefährliche Körperverletzung|schwere Körperverletzung|versuchter Totschlag|versuchtes Tötungsdelikt",
            early, re.I
        )
    ):
        labels.append(("violence", "Schwere Gewalttat", 4))

    # The point layer intentionally keeps only travel-relevant property events.
    # Broad property-crime volume comes from the official statistical surface,
    # not from counting every police press release.
    property_text = clean(title + " " + body[:1800])
    for sub, rx in PROPERTY_RULES:
        if rx.search(property_text):
            labels.append(("property", sub, 2))
            break

    if not labels:
        return None

    priority = {"homicide": 0, "sexual": 1, "robbery": 2, "violence": 3, "property": 4}
    labels.sort(key=lambda x: priority[x[0]])
    primary = labels[0]
    categories = list(dict.fromkeys(x[0] for x in labels))
    return primary[0], primary[1], max(x[2] for x in labels), categories


def article_text(s: requests.Session, url: str) -> str:
    r = official_get(s, url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    main = soup.find("main") or soup.find("article") or soup.body or soup
    for tag in main(["script", "style", "nav", "footer", "form", "svg", "noscript"]):
        tag.decompose()
    return clean(main.get_text(" ", strip=True))


def street_from(text: str) -> str:
    core = re.split(r"Verantwortlich:|Zum Impressum|Kontakt", text, maxsplit=1, flags=re.I)[0]
    hits = []
    for m in STREET_RE.finditer(core):
        value = clean(m.group(1)).strip(" ,.-")
        if 4 <= len(value) <= 90:
            hits.append((m.start(), value))
    return hits[0][1] if hits else ""


def geocode(s: requests.Session, query: str, cache: dict, last_call: float):
    cached = cache.get(query, "__missing__")
    if cached != "__missing__" and cached is not None:
        return cached, last_call
    wait = 1.15 - (time.monotonic() - last_call)
    if wait > 0:
        time.sleep(wait)
    last_call = time.monotonic()
    try:
        r = s.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "de", "addressdetails": 1},
            timeout=30,
        )
        r.raise_for_status()
        rows = r.json()
        hit = None if not rows else {
            "lat": float(rows[0]["lat"]), "lon": float(rows[0]["lon"]),
            "address": rows[0].get("address", {}),
        }
    except Exception as exc:
        print("WARN geocode", query, exc)
        return None, last_call
    # Do not cache failures: transient failures must be retried on the next run.
    if hit is not None:
        cache[query] = hit
        save(CACHE, cache)
    return hit, last_call


def scan(lookback: int, max_pages: int):
    today = datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=lookback)
    s = session()
    seen = set()
    listing_rows = []
    raw_anchor_sample = []
    pages_scanned = 0

    for page_no in range(1, max_pages + 1):
        url = LISTING.format(page=page_no)
        r = official_get(s, url, timeout=35)
        if r.status_code == 404:
            break
        r.raise_for_status()
        pages_scanned += 1
        soup = BeautifulSoup(r.text, "html.parser")
        # The first link in each card is an image with no text; use the h4
        # headline link so title extraction and deduplication are stable.
        anchors = [a for a in soup.select("h4 a[href]") if ARTICLE_RE.search(urljoin(url, a["href"]))]
        if not anchors:
            break

        page_dates = []
        for a in anchors:
            href = urljoin(url, a["href"]).split("#")[0]
            if href in seen:
                continue
            seen.add(href)
            title = clean(a.get_text(" ", strip=True))
            context = listing_context(a)
            if len(raw_anchor_sample) < 5:
                raw_anchor_sample.append({
                    "title": title[:180],
                    "href": href,
                    "context": context[:600],
                    "parent_html": str(a.parent)[:1200],
                })
            published = parse_date(context)
            if not published:
                # Heading itself normally starts with the publication date.
                published = parse_date(title)
            if published:
                page_dates.append(published)
            if not published or published < cutoff - timedelta(days=2) or published > today:
                continue
            title = DATE_RE.sub("", title, count=1).strip(" ,–-")
            if not title or not PREFILTER.search(title):
                continue
            city, district = listing_location(context)
            listing_rows.append({
                "url": href, "title": title, "published": published,
                "city": city, "district": district,
            })

        if page_dates and min(page_dates) < cutoff - timedelta(days=2):
            break
        time.sleep(.05)

    events = []
    for idx, row in enumerate(listing_rows, 1):
        try:
            body = article_text(s, row["url"])
        except Exception as exc:
            print("WARN article", row["url"], exc)
            continue
        info = classify(row["title"], body)
        if not info:
            continue
        category, subcategory, severity, categories = info
        published = row["published"]
        event_date, date_confidence = event_date_from_text(body, published)
        if not cutoff <= event_date <= today:
            continue

        city = row["city"] or row["district"] or "Brandenburg"
        district = row["district"]
        privacy = category == "sexual"
        street = "" if privacy else street_from(body)
        if privacy:
            location = f"{district or city}（隐私保护：降低定位精度）"
            query = f"{district or city}, Brandenburg, Germany"
            precision = "district-privacy"
        elif street:
            location = street
            query = f"{street}, {city}, Brandenburg, Germany"
            precision = "street"
        else:
            location = city
            query = f"{city}, Brandenburg, Germany"
            precision = "city"

        events.append({
            "id": f"{event_date.isoformat()}-bb-{hashlib.sha1(row['url'].encode()).hexdigest()[:12]}",
            "event_id": f"bb-{hashlib.sha1(row['url'].encode()).hexdigest()[:16]}",
            "event_date": event_date.isoformat(),
            "publication_date": published.isoformat(),
            "city": city,
            "district": district,
            "state": "Brandenburg",
            "location": location,
            "geocode_address": query,
            "precision": precision,
            "location_type": "Tatort / reported location",
            "status": "reported",
            "offense": subcategory,
            "subcategory": subcategory,
            "category": category,
            "categories": categories,
            "category_label": {
                "homicide": "凶杀", "violence": "严重暴力", "robbery": "抢劫",
                "sexual": "性犯罪", "property": "盗窃/财产犯罪",
            }[category],
            "severity": severity,
            "summary": f"Brandenburg警方公开通报：{row['title'][:180]}",
            "source_agency": "Polizei Brandenburg",
            "source_type": "state_police_direct",
            "source_url": row["url"],
            "lat": None,
            "lon": None,
            "date_confidence": date_confidence,
            "privacy_protected": privacy,
        })
        if idx % 50 == 0:
            print("detail progress", idx, "/", len(listing_rows))

    # URL is the stable primary dedup key for this source.
    unique = {e["source_url"]: e for e in events}
    events = sorted(unique.values(), key=lambda e: (e["event_date"], e["city"]), reverse=True)
    return {
        "today": today, "cutoff": cutoff, "pages_scanned": pages_scanned,
        "prefiltered": len(listing_rows), "events": events,
        "raw_anchor_sample": raw_anchor_sample,
    }


def write_events(events):
    today = datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=90)
    payload = load(CASES, {"meta": {}, "cases": []})
    cases = payload.get("cases", [])
    existing_urls = {c.get("source_url") for c in cases if c.get("source_url")}
    cache = load(CACHE, {})
    s = session()
    last = 0.0
    added = []

    for event in events:
        if event["source_url"] in existing_urls:
            continue
        hit, last = geocode(s, event["geocode_address"], cache, last)
        if hit is None and event["precision"] == "street":
            fallback = f"{event['city']}, Brandenburg, Germany"
            hit, last = geocode(s, fallback, cache, last)
            if hit:
                event["geocode_precision"] = "city-fallback"
        if hit:
            event["lat"], event["lon"] = hit["lat"], hit["lon"]
            event.setdefault("geocode_precision", event["precision"])
            # Reject geocodes that clearly resolve outside Brandenburg.
            addr = hit.get("address", {})
            state = (addr.get("state") or "").lower()
            if state and "brandenburg" not in state:
                event["lat"] = event["lon"] = None
                event["geocode_rejected"] = "state-mismatch"
        cases.append(event)
        existing_urls.add(event["source_url"])
        added.append(event)

    cases = [
        c for c in cases
        if c.get("event_date") and cutoff <= date.fromisoformat(c["event_date"]) <= today
    ]
    cases.sort(key=lambda c: (c["event_date"], c.get("city", ""), c.get("category", "")), reverse=True)
    meta = payload.setdefault("meta", {})
    meta["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    meta["case_count"] = len(cases)
    meta["geocoded_count"] = sum(c.get("lat") is not None and c.get("lon") is not None for c in cases)
    meta["category_counts"] = {
        k: sum(1 for c in cases if c.get("category") == k)
        for k in ("homicide", "violence", "robbery", "sexual", "property")
    }
    meta["schema_version"] = max(int(meta.get("schema_version") or 0), 5)
    meta["coverage_note"] = (
        "Public-source monitor. Direct state-police adapters are being added progressively; "
        "absence of a point never means absence of crime."
    )
    payload["cases"] = cases
    save(CASES, payload)
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback", type=int, default=7)
    ap.add_argument("--max-pages", type=int, default=80)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    lookback = max(1, min(args.lookback, 90))
    result = scan(lookback, max(1, args.max_pages))
    counts = Counter(e["category"] for e in result["events"])
    districts = Counter(e.get("district") or "(unknown)" for e in result["events"])
    report = {
        "source": "Polizei Brandenburg direct archive",
        "lookback_days": lookback,
        "pages_scanned": result["pages_scanned"],
        "prefiltered_articles": result["prefiltered"],
        "selected_events": len(result["events"]),
        "by_category": dict(counts),
        "top_districts": districts.most_common(10),
        "raw_anchor_sample": result.get("raw_anchor_sample", []),
        "sample": [
            {
                "date": e["event_date"], "category": e["category"],
                "city": e["city"], "district": e.get("district"),
                "offense": e["offense"], "title": e["summary"].split("：", 1)[-1],
            }
            for e in result["events"][:20]
        ],
    }
    if args.write:
        added = write_events(result["events"])
        report["write_mode"] = True
        report["added"] = len(added)
    else:
        report["write_mode"] = False
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
