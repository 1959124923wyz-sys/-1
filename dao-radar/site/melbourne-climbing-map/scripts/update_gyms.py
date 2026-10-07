#!/usr/bin/env python3
"""
Regenerate the Melbourne climbing map data without paid APIs.

Primary facts (hours/prices/status/notes) live in data/seed.json and are curated
from venue/public sources. Automation deliberately does NOT scrape arbitrary
search results into published facts.

Automation does three conservative jobs:
1) Geocode missing exact venue addresses with Nominatim and cache the result.
2) Check source URLs for basic reachability (a health signal, not verification).
3) Ask Overpass for sport=climbing objects in the broad region and save unmatched
   objects as discovery candidates. Candidates never auto-publish.

Any network failure preserves previously cached coordinates/candidates.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SEED = DATA / "seed.json"
CACHE = DATA / "geocode_cache.json"
CANDIDATES = DATA / "osm_candidates.json"
OUT_JSON = DATA / "gyms.json"
OUT_JS = DATA / "gyms.js"

UA = "melbourne-climbing-map/1.0 (public GitHub Pages data maintainer)"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"
BBOX = (-38.35, 144.10, -37.40, 145.60)  # S,W,N,E; includes Melbourne + Geelong fringe
CBD = (-37.8136, 144.9631)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def request_json(url: str, *, data: bytes | None = None, timeout: int = 25):
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": UA, "Accept": "application/json"},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def geocode(address: str):
    qs = urllib.parse.urlencode({
        "q": address,
        "format": "jsonv2",
        "limit": 1,
        "countrycodes": "au",
        "addressdetails": 0,
    })
    rows = request_json(f"{NOMINATIM}?{qs}", timeout=25)
    if not rows:
        return None
    return {"lat": float(rows[0]["lat"]), "lng": float(rows[0]["lon"]), "display_name": rows[0].get("display_name", "")}


def url_health(url: str):
    if not url:
        return {"ok": False, "status": None, "error": "no-url"}
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.8", "Range": "bytes=0-1024"},
        )
        with urllib.request.urlopen(req, timeout=18) as resp:
            return {"ok": 200 <= int(resp.status) < 400, "status": int(resp.status), "final_url": resp.geturl()}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": int(e.code), "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "status": None, "error": str(e)[:160]}


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)), 1)


def canonical(s: str):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def discover_osm(existing_names: set[str]):
    s, w, n, e = BBOX
    query = f"""[out:json][timeout:25];
(
  nwr["sport"="climbing"]({s},{w},{n},{e});
  nwr["climbing:boulder"="yes"]({s},{w},{n},{e});
);
out center tags;"""
    payload = urllib.parse.urlencode({"data": query}).encode()
    raw = request_json(OVERPASS, data=payload, timeout=40)
    out = []
    for el in raw.get("elements", []):
        tags = el.get("tags") or {}
        name = tags.get("name") or ""
        if not name:
            continue
        if canonical(name) in existing_names:
            continue
        lat = el.get("lat")
        lng = el.get("lon")
        if lat is None or lng is None:
            c = el.get("center") or {}
            lat, lng = c.get("lat"), c.get("lon")
        if lat is None or lng is None:
            continue
        out.append({
            "osm_type": el.get("type"),
            "osm_id": el.get("id"),
            "name": name,
            "lat": lat,
            "lng": lng,
            "tags": {k: v for k, v in tags.items() if k in {
                "sport", "leisure", "climbing:boulder", "climbing:indoor",
                "website", "contact:website", "addr:street", "addr:housenumber",
                "addr:suburb", "opening_hours"
            }},
        })
    out.sort(key=lambda x: x["name"].lower())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-health", action="store_true")
    ap.add_argument("--skip-discovery", action="store_true")
    args = ap.parse_args()

    seed = load_json(SEED, {})
    venues = seed.get("venues", [])
    if not venues:
        raise SystemExit("seed.json contains no venues")

    cache = load_json(CACHE, {})
    old_candidates = load_json(CANDIDATES, {"generated_at": None, "candidates": []})

    geocode_attempted = geocode_new = 0
    for v in venues:
        if v.get("map") is False:
            continue
        lat, lng = v.get("lat"), v.get("lng")
        if lat is None or lng is None:
            cached = cache.get(v["id"])
            if cached and cached.get("lat") is not None:
                v["lat"], v["lng"] = cached["lat"], cached["lng"]
                v["geocode_source"] = "cache:nominatim"
            else:
                geocode_attempted += 1
                try:
                    found = geocode(v["address"])
                    if found:
                        cache[v["id"]] = {
                            **found,
                            "address": v["address"],
                            "cached_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                        }
                        v["lat"], v["lng"] = found["lat"], found["lng"]
                        v["geocode_source"] = "nominatim"
                        geocode_new += 1
                except Exception as e:
                    v["geocode_error"] = str(e)[:160]
                time.sleep(1.1)
        else:
            v["geocode_source"] = "curated"

        if v.get("lat") is not None and v.get("lng") is not None:
            v["distance_cbd_km"] = haversine_km(CBD[0], CBD[1], float(v["lat"]), float(v["lng"]))

    save_json(CACHE, cache)

    now = dt.datetime.now(dt.timezone.utc)
    today = now.date()
    for v in venues:
        closing = v.get("closing_date")
        if closing:
            try:
                if today > dt.date.fromisoformat(closing):
                    v["effective_status"] = "closed"
                else:
                    v["effective_status"] = v.get("status", "active")
            except ValueError:
                v["effective_status"] = v.get("status", "active")
        else:
            v["effective_status"] = v.get("status", "active")

    health = {}
    if not args.skip_health:
        for url in sorted({v.get("website") for v in venues if v.get("website")}):
            health[url] = url_health(url)
            time.sleep(0.15)
    else:
        health = (load_json(OUT_JSON, {}).get("meta", {}) or {}).get("source_health", {})

    existing_names = {canonical(v.get("name", "")) for v in venues}
    candidates = old_candidates
    if not args.skip_discovery:
        try:
            found = discover_osm(existing_names)
            candidates = {"generated_at": now.isoformat(), "candidates": found}
            save_json(CANDIDATES, candidates)
        except Exception as e:
            candidates = dict(old_candidates)
            candidates["last_error"] = str(e)[:220]
            candidates["last_error_at"] = now.isoformat()
            save_json(CANDIDATES, candidates)

    mapped = sum(1 for v in venues if v.get("lat") is not None and v.get("lng") is not None and v.get("map") is not False)
    active = sum(1 for v in venues if v.get("effective_status") in {"active", "attention"})
    core = sum(1 for v in venues if v.get("kind") == "gym" and v.get("effective_status") in {"active", "attention"})
    output = {
        "meta": {
            **(seed.get("meta") or {}),
            "generated_at": now.isoformat(),
            "venue_count": len(venues),
            "mapped_count": mapped,
            "active_count": active,
            "core_gym_count": core,
            "geocode_attempted": geocode_attempted,
            "geocode_new": geocode_new,
            "candidate_count": len((candidates or {}).get("candidates", [])),
            "source_health": health,
            "automation_note": "Automated checks do not imply semantic re-verification of prices/hours; curated facts keep their verified_at date.",
        },
        "venues": venues,
    }
    save_json(OUT_JSON, output)
    OUT_JS.write_text(
        "window.CLIMBING_DATA = " + json.dumps(output, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "venue_count": len(venues),
        "mapped_count": mapped,
        "active_count": active,
        "core_gym_count": core,
        "geocode_attempted": geocode_attempted,
        "geocode_new": geocode_new,
        "candidate_count": len((candidates or {}).get("candidates", [])),
        "health_ok": sum(1 for x in health.values() if x.get("ok")),
        "health_total": len(health),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
