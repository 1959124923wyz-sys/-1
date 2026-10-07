#!/usr/bin/env python3
import json, os
from pathlib import Path
from playwright.sync_api import sync_playwright

URL=os.getenv("SMOKE_URL","http://127.0.0.1:8765/")
SHOT=Path(os.getenv("SMOKE_SCREENSHOT","/tmp/germany-crime-map-national.png"))
BERLIN_SHOT=SHOT.with_name("germany-crime-map-berlin.png")
PROPERTY_SHOT=SHOT.with_name("germany-crime-map-property.png")

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={"width":1600,"height":900},device_scale_factor=1)
    page_errors=[]
    page.on("pageerror",lambda exc: page_errors.append(str(exc)))
    page.route("**/tile.openstreetmap.org/**",lambda route: route.abort())

    response=page.goto(URL,wait_until="domcontentloaded",timeout=60000)
    assert response and response.ok, f"page HTTP failure: {response.status if response else 'no response'}"
    page.wait_for_function("window.__CRIME_MAP__ && window.__CRIME_MAP__.getCaseData()",timeout=30000)
    page.wait_for_function("window.__CRIME_MAP__.getPksData()",timeout=30000)
    page.wait_for_function("window.__CRIME_MAP__.getBerlinViolence()",timeout=30000)
    page.wait_for_function("window.__CRIME_MAP__.getHeatData()",timeout=30000)
    page.wait_for_timeout(4500)

    report=page.evaluate("""() => {
      const api=window.__CRIME_MAP__;
      const cases=api.getCaseData().cases;
      const counts={};
      for(const c of cases) counts[c.category]=(counts[c.category]||0)+1;
      return {
        mode:api.getMode(),
        cases:cases.length,
        counts,
        pksCount:api.getPksData().meta.county_count,
        pksMatched:api.getPksData().meta.matched_geometry,
        pksBreaks:api.getPksData().meta.quantile_breaks,
        countyLayers:api.getCountyLayer()?.getLayers().length||0,
        berlinFeatures:api.getBerlinViolence().meta.feature_count,
        visible:api.getVisibleCases().length,
        heat90:api.getHeatData().windows["90"],
        mapStatus:document.getElementById("mapStatus").textContent,
        mapHeight:document.getElementById("map").getBoundingClientRect().height,
        hasDaysSelector:!!document.getElementById("days"),
        title:document.title,
        heading:document.querySelector(".title")?.textContent,
        violenceControlsHidden:document.getElementById("violenceLayers").hidden,
        propertyControlsHidden:document.getElementById("propertyLayers").hidden
      };
    }""")

    assert report["mode"]=="violence",report
    assert report["cases"]>=500,report
    assert report["pksCount"]>=390,report
    assert report["pksMatched"]>=402,report
    assert report["countyLayers"]>=400,report
    assert report["berlinFeatures"]>=135,report
    assert report["visible"]==sum(report["counts"].get(k,0) for k in ("homicide","violence","robbery","sexual")),report
    assert report["counts"].get("homicide",0)>=40,report
    assert report["counts"].get("robbery",0)>=20,report
    assert report["hasDaysSelector"] is False,report
    assert report["mapHeight"]>=500,report
    assert "本地统计底图" in report["mapStatus"],report
    assert "犯罪态势" in report["heading"],report
    assert report["violenceControlsHidden"] is False,report
    assert report["propertyControlsHidden"] is True,report
    assert report["heat90"]["total"]>=10000,report["heat90"]
    assert not page_errors,page_errors

    SHOT.parent.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(SHOT),full_page=True)

    # Zoom to Berlin: the official high-coverage 2025 Bezirksregion layer should appear.
    page.click("#focusBerlin")
    page.wait_for_timeout(1300)
    berlin=page.evaluate("""() => ({
      zoom:window.__CRIME_MAP__.map.getZoom(),
      layerCount:window.__CRIME_MAP__.getBerlinLayer()?.getLayers().length||0,
      countyLayer:!!window.__CRIME_MAP__.getCountyLayer(),
      info:document.getElementById("layerInfo").textContent,
      violenceControlsHidden:document.getElementById("violenceLayers").hidden,
      propertyControlsHidden:document.getElementById("propertyLayers").hidden
    })""")
    assert berlin["zoom"]>=8,berlin
    assert berlin["layerCount"]>=135,berlin
    assert berlin["countyLayer"] is True,berlin
    page.screenshot(path=str(BERLIN_SHOT),full_page=True)

    # Property mode must keep the same fixed 90-day window and switch to official Berlin heat + news points.
    page.click("#modeProperty")
    page.wait_for_timeout(1000)
    prop=page.evaluate("""() => ({
      mode:window.__CRIME_MAP__.getMode(),
      heat:!!window.__CRIME_MAP__.getHeatLayer(),
      visible:window.__CRIME_MAP__.getVisibleCases().length,
      propertyCount:window.__CRIME_MAP__.getCaseData().cases.filter(c=>c.category==="property").length,
      info:document.getElementById("layerInfo").textContent,
      violenceControlsHidden:document.getElementById("violenceLayers").hidden,
      propertyControlsHidden:document.getElementById("propertyLayers").hidden
    })""")
    assert prop["mode"]=="property",prop
    assert prop["heat"] is True,prop
    assert prop["visible"]==prop["propertyCount"],prop
    assert prop["propertyCount"]>=300,prop
    assert prop["violenceControlsHidden"] is True,prop
    assert prop["propertyControlsHidden"] is False,prop
    assert "90天" in prop["info"],prop
    page.screenshot(path=str(PROPERTY_SHOT),full_page=True)

    print(json.dumps({"national":report,"berlin":berlin,"property":prop},ensure_ascii=False))
    browser.close()
