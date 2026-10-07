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
    page.wait_for_function("window.__MAP_SMOKE__.getHeatData()",timeout=60000)
    page.wait_for_function("window.__MAP_SMOKE__.getOfficialNationalData()",timeout=60000)
    page.wait_for_function("window.__MAP_SMOKE__.getBerlinViolenceData()",timeout=60000)
    page.wait_for_timeout(4500)

    report=page.evaluate("""() => {
      const s=window.__MAP_SMOKE__;
      const data=s.getCaseData();
      const counts={};
      for(const c of data.cases) counts[c.category]=(counts[c.category]||0)+1;
      return {
        mode:s.getBasemapMode(),
        viewMode:s.getCurrentMode(),
        states:s.getStateLayer().getLayers().length,
        cases:data.cases.length,
        geocoded:data.cases.filter(c=>Number.isFinite(c.lat)&&Number.isFinite(c.lon)).length,
        cards:document.querySelectorAll('.card').length,
        mapHeight:document.getElementById('map').getBoundingClientRect().height,
        mapWidth:document.getElementById('map').getBoundingClientRect().width,
        status:document.getElementById('basemapStatus').textContent,
        title:document.querySelector('h1').textContent,
        daysSelector:!!document.getElementById('days'),
        categoryCounts:counts,
        selectedCategories:s.getSelectedCategories(),
        nationalStates:Object.keys(s.getOfficialNationalData().states||{}).length,
        officialEnabled:s.getOfficialEnabled(),
        officialInfoHidden:document.getElementById('officialInfo').hidden,
        berlinRegions:s.getBerlinViolenceData().features.length,
        berlinLayerOnMap:!!s.getBerlinViolenceLayer() && s.map.hasLayer(s.getBerlinViolenceLayer()),
        heat90:s.getHeatData().windows["90"],
        heatLayerOnMap:!!s.getHeatLayer(),
        heatInfoHidden:document.getElementById('heatInfo').hidden
      };
    }""")

    counts=report["categoryCounts"]
    assert report["mode"]=="fallback",report
    assert report["viewMode"]=="violence",report
    assert report["states"]==16,report
    assert report["nationalStates"]==16,report
    assert report["berlinRegions"]>=120,report
    assert report["officialEnabled"] is True,report
    assert report["officialInfoHidden"] is False,report
    assert report["berlinLayerOnMap"] is True,report
    assert report["heatLayerOnMap"] is False,report
    assert report["heatInfoHidden"] is True,report
    assert report["daysSelector"] is False,report
    assert report["cases"]>=80,report
    assert report["geocoded"]/report["cases"]>=0.90,report
    assert report["mapHeight"]>=400 and report["mapWidth"]>=700,report
    assert "本地德国州界底图" in report["status"],report
    assert set(report["selectedCategories"])=={"homicide","violence","robbery","sexual"},report
    expected_violence=counts["homicide"]+counts["violence"]+counts["robbery"]+counts["sexual"]
    assert report["cards"]==expected_violence,(report,expected_violence)
    assert set(s for s in window_keys(report["heat90"])) if False else True
    assert report["heat90"]["total"]>=1500,report["heat90"]
    assert not page_errors,page_errors

    # Toggle the federal annual background independently.
    page.locator('#officialNationalEnabled').uncheck()
    page.wait_for_timeout(150)
    official_off=page.evaluate("""() => ({
      enabled:window.__MAP_SMOKE__.getOfficialEnabled(),
      hidden:document.getElementById('officialInfo').hidden
    })""")
    assert official_off["enabled"] is False,official_off
    assert official_off["hidden"] is True,official_off
    page.locator('#officialNationalEnabled').check()

    # Switch to property mode: only property press points + Berlin official 90-day theft heat.
    page.locator('#modeProperty').click()
    page.wait_for_timeout(350)
    prop=page.evaluate("""() => {
      const s=window.__MAP_SMOKE__;
      return {
        mode:s.getCurrentMode(),
        selected:s.getSelectedCategories(),
        visible:s.getVisibleCases().length,
        cards:document.querySelectorAll('.card').length,
        heatLayer:!!s.getHeatLayer(),
        heatInfo:document.getElementById('heatNumbers').textContent,
        officialHidden:document.getElementById('officialInfo').hidden,
        berlinViolenceOn:!!s.getBerlinViolenceLayer() && s.map.hasLayer(s.getBerlinViolenceLayer())
      };
    }""")
    assert prop["mode"]=="property",prop
    assert prop["selected"]==["property"],prop
    assert prop["visible"]==counts["property"],(counts,prop)
    assert prop["cards"]==counts["property"],prop
    assert prop["heatLayer"] is True,prop
    assert "90天" in prop["heatInfo"],prop
    assert prop["officialHidden"] is True,prop
    assert prop["berlinViolenceOn"] is False,prop

    # Switch back to violence mode and focus Berlin; both annual Berlin regions and 90-day points remain.
    page.locator('#modeViolence').click()
    page.locator('#focusBerlin').click()
    page.wait_for_timeout(350)
    back=page.evaluate("""() => ({
      mode:window.__MAP_SMOKE__.getCurrentMode(),
      berlinViolenceOn:window.__MAP_SMOKE__.map.hasLayer(window.__MAP_SMOKE__.getBerlinViolenceLayer()),
      heatLayer:!!window.__MAP_SMOKE__.getHeatLayer(),
      zoom:window.__MAP_SMOKE__.map.getZoom(),
      legend:document.getElementById('legendContent').textContent
    })""")
    assert back["mode"]=="violence",back
    assert back["berlinViolenceOn"] is True,back
    assert back["heatLayer"] is False,back
    assert back["zoom"]>=8,back
    assert "BKA PKS 2025" in back["legend"],back

    SHOT.parent.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(SHOT),full_page=True)
    print(json.dumps({"initial":report,"official_off":official_off,"property":prop,"back":back},ensure_ascii=False))
    browser.close()
