#!/usr/bin/env python3
import json, os
from pathlib import Path
from playwright.sync_api import sync_playwright

URL=os.getenv("SMOKE_URL","http://127.0.0.1:8765/")
SHOT=Path(os.getenv("SMOKE_SCREENSHOT","/tmp/germany-crime-map-smoke.png"))

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={"width":1600,"height":900},device_scale_factor=1)
    page_errors=[]
    page.on("pageerror",lambda exc: page_errors.append(str(exc)))
    page.route("**/tile.openstreetmap.org/**",lambda route: route.abort())

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
        mode:window.__MAP_SMOKE__.getBasemapMode(),
        states:window.__MAP_SMOKE__.getStateLayer().getLayers().length,
        cases:data.cases.length,
        geocoded:data.cases.filter(c=>Number.isFinite(c.lat)&&Number.isFinite(c.lon)).length,
        cards:document.querySelectorAll('.card').length,
        selectedDays:document.getElementById('days').value,
        mapHeight:document.getElementById('map').getBoundingClientRect().height,
        mapWidth:document.getElementById('map').getBoundingClientRect().width,
        status:document.getElementById('basemapStatus').textContent,
        title:document.querySelector('h1').textContent,
        categoryChecks:document.querySelectorAll('.cat-check').length,
        enabledCategoryChecks:[...document.querySelectorAll('.cat-check')].filter(x=>!x.disabled).length,
        selectedCategories:window.__MAP_SMOKE__.getSelectedCategories(),
        categoryCounts:counts,
        allChecked:document.getElementById('allCategories').checked,
        allIndeterminate:document.getElementById('allCategories').indeterminate
      };
    }""")

    counts=report["categoryCounts"]
    assert report["mode"]=="fallback",report
    assert report["states"]>=16,report
    assert report["cases"]>=80,report
    assert report["geocoded"]/report["cases"]>=0.90,report
    assert report["selectedDays"]=="90",report
    assert "犯罪事件" in report["title"],report
    assert report["categoryChecks"]==5,report
    assert report["enabledCategoryChecks"]==5,report
    assert counts.get("homicide",0)>=40,report
    assert counts.get("violence",0)>=3,report
    assert counts.get("robbery",0)>=10,report
    assert counts.get("sexual",0)>=2,report
    assert counts.get("property",0)>=30,report
    assert set(report["selectedCategories"])=={"homicide","violence","robbery","sexual"},report
    expected_initial=counts["homicide"]+counts["violence"]+counts["robbery"]+counts["sexual"]
    assert report["cards"]==expected_initial,(report,expected_initial)
    assert report["allChecked"] is False and report["allIndeterminate"] is True,report
    assert report["mapHeight"]>=400 and report["mapWidth"]>=700,report
    assert "本地德国州界底图" in report["status"],report
    assert not page_errors,page_errors

    page.locator('.cat-check[data-category="homicide"]').uncheck()
    page.wait_for_timeout(200)
    no_homicide=page.evaluate("""() => ({
      visible:window.__MAP_SMOKE__.getVisibleCases().length,
      cards:document.querySelectorAll('.card').length,
      selected:window.__MAP_SMOKE__.getSelectedCategories()
    })""")
    expected_no_h=counts["violence"]+counts["robbery"]+counts["sexual"]
    assert no_homicide["visible"]==expected_no_h,(report,no_homicide)
    assert no_homicide["cards"]==expected_no_h,no_homicide

    page.locator('.cat-check[data-category="property"]').check()
    page.wait_for_timeout(200)
    with_property=page.evaluate("""() => ({
      visible:window.__MAP_SMOKE__.getVisibleCases().length,
      cards:document.querySelectorAll('.card').length,
      selected:window.__MAP_SMOKE__.getSelectedCategories()
    })""")
    assert with_property["visible"]==expected_no_h+counts["property"],(report,with_property)
    assert with_property["cards"]==with_property["visible"],with_property

    page.locator('.cat-check[data-category="homicide"]').check()
    page.wait_for_timeout(100)
    SHOT.parent.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(SHOT),full_page=True)
    print(json.dumps({"initial":report,"no_homicide":no_homicide,"with_property":with_property},ensure_ascii=False))
    browser.close()
