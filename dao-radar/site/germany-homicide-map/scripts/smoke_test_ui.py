#!/usr/bin/env python3
import json, os
from pathlib import Path
from playwright.sync_api import sync_playwright

URL=os.getenv("SMOKE_URL","http://127.0.0.1:8765/")
SHOT=Path(os.getenv("SMOKE_SCREENSHOT","/tmp/germany-homicide-map-smoke.png"))

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={"width":1600,"height":900},device_scale_factor=1)
    page_errors=[]
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))

    # Reproduce the user's failure mode: all OSM raster tiles are unavailable.
    page.route("**/tile.openstreetmap.org/**", lambda route: route.abort())

    response=page.goto(URL,wait_until="domcontentloaded",timeout=60000)
    assert response and response.ok, f"page HTTP failure: {response.status if response else 'no response'}"

    page.wait_for_function("window.__MAP_SMOKE__ && window.__MAP_SMOKE__.getStateLayer()",timeout=30000)
    page.wait_for_function("window.__MAP_SMOKE__.getCaseData()",timeout=30000)
    page.wait_for_timeout(4500)

    report=page.evaluate("""() => ({
      mode: window.__MAP_SMOKE__.getBasemapMode(),
      states: window.__MAP_SMOKE__.getStateLayer().getLayers().length,
      cases: window.__MAP_SMOKE__.getCaseData().cases.length,
      cards: document.querySelectorAll('.card').length,
      mapHeight: document.getElementById('map').getBoundingClientRect().height,
      mapWidth: document.getElementById('map').getBoundingClientRect().width,
      status: document.getElementById('basemapStatus').textContent,
      title: document.querySelector('h1').textContent
    })""")

    assert report["mode"]=="fallback", report
    assert report["states"]>=16, report
    assert report["cases"]>=1, report
    assert report["cards"]>=1, report
    assert report["mapHeight"]>=400 and report["mapWidth"]>=700, report
    assert "本地德国州界底图" in report["status"], report
    assert not page_errors, page_errors

    SHOT.parent.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(SHOT),full_page=True)
    print(json.dumps(report,ensure_ascii=False))
    browser.close()
