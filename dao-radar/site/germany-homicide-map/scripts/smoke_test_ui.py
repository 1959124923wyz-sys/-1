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

    # Reproduce the user's earlier failure mode: all OSM raster tiles unavailable.
    page.route("**/tile.openstreetmap.org/**", lambda route: route.abort())

    response=page.goto(URL,wait_until="domcontentloaded",timeout=60000)
    assert response and response.ok, f"page HTTP failure: {response.status if response else 'no response'}"

    page.wait_for_function("window.__MAP_SMOKE__ && window.__MAP_SMOKE__.getStateLayer()",timeout=30000)
    page.wait_for_function("window.__MAP_SMOKE__.getCaseData()",timeout=30000)
    page.wait_for_timeout(4500)

    report=page.evaluate("""() => {
      const data=window.__MAP_SMOKE__.getCaseData();
      const counts={};
      for(const c of data.cases) counts[c.category]=(counts[c.category]||0)+1;
      return {
        mode: window.__MAP_SMOKE__.getBasemapMode(),
        states: window.__MAP_SMOKE__.getStateLayer().getLayers().length,
        cases: data.cases.length,
        geocoded: data.cases.filter(c => Number.isFinite(c.lat) && Number.isFinite(c.lon)).length,
        cards: document.querySelectorAll('.card').length,
        selectedDays: document.getElementById('days').value,
        mapHeight: document.getElementById('map').getBoundingClientRect().height,
        mapWidth: document.getElementById('map').getBoundingClientRect().width,
        status: document.getElementById('basemapStatus').textContent,
        title: document.querySelector('h1').textContent,
        categoryChecks: document.querySelectorAll('.cat-check').length,
        enabledCategoryChecks: [...document.querySelectorAll('.cat-check')].filter(x=>!x.disabled).length,
        selectedCategories: window.__MAP_SMOKE__.getSelectedCategories(),
        categoryCounts: counts,
        robberyDisabled: document.querySelector('.cat-check[data-category="robbery"]').disabled,
        sexualDisabled: document.querySelector('.cat-check[data-category="sexual"]').disabled,
        propertyDisabled: document.querySelector('.cat-check[data-category="property"]').disabled
      };
    }""")

    assert report["mode"]=="fallback", report
    assert report["states"]>=16, report
    assert report["cases"]>=40, report
    assert report["cards"]==report["cases"], report
    assert report["geocoded"]==report["cases"], report
    assert report["selectedDays"]=="90", report
    assert "犯罪事件" in report["title"], report
    assert report["categoryChecks"]==5, report
    assert report["enabledCategoryChecks"]>=2, report
    assert "homicide" in report["selectedCategories"], report
    assert "violence" in report["selectedCategories"], report
    assert report["categoryCounts"].get("homicide",0)>=1, report
    assert report["categoryCounts"].get("violence",0)>=1, report
    assert report["robberyDisabled"] and report["sexualDisabled"] and report["propertyDisabled"], report
    assert report["mapHeight"]>=400 and report["mapWidth"]>=700, report
    assert "本地德国州界底图" in report["status"], report
    assert not page_errors, page_errors

    # Verify category filtering is functional rather than decorative.
    page.locator('.cat-check[data-category="homicide"]').uncheck()
    page.wait_for_timeout(200)
    filtered=page.evaluate("""() => ({
      visible: window.__MAP_SMOKE__.getVisibleCases().length,
      cards: document.querySelectorAll('.card').length,
      selected: window.__MAP_SMOKE__.getSelectedCategories()
    })""")
    assert "homicide" not in filtered["selected"], filtered
    assert filtered["visible"]==report["categoryCounts"]["violence"], (report,filtered)
    assert filtered["cards"]==filtered["visible"], filtered

    # Restore the default state before the visual artifact is captured.
    page.locator('.cat-check[data-category="homicide"]').check()
    page.wait_for_timeout(200)

    SHOT.parent.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(SHOT),full_page=True)
    print(json.dumps({"initial":report,"filtered":filtered},ensure_ascii=False))
    browser.close()
