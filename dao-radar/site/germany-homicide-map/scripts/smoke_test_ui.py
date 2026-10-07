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
        countyLayers:api.getCountyLayer()?.getLayers().length||0,
        berlinFeatures:api.getBerlinViolence().meta.feature_count,
        visible:api.getVisibleCases().length,
        heat90:api.getHeatData().windows["90"],
        mapStatus:document.getElementById("mapStatus").textContent,
        mapHeight:document.getElementById("map").getBoundingClientRect().height,
        hasDaysSelector:!!document.getElementById("days"),
        heading:document.querySelector(".title")?.textContent,
        legend:document.getElementById("legend").textContent,
        areaName:document.getElementById("areaName").textContent,
        areaQuarterLabel:document.getElementById("areaQuarterLabel").textContent,
        incidentOpen:document.querySelector(".incident-drawer").open,
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
    assert report["hasDaysSelector"] is False,report
    assert report["mapHeight"]>=500,report
    assert "本地统计底图" in report["mapStatus"],report
    assert "犯罪态势" in report["heading"],report
    assert "柏林试点" in report["legend"] and "紫色细分层" in report["legend"],report
    assert report["areaName"]=="在地图上选择地区",report
    assert report["incidentOpen"] is False,report
    assert report["violenceControlsHidden"] is False,report
    assert report["propertyControlsHidden"] is True,report
    assert report["heat90"]["total"]>=10000,report["heat90"]
    assert not page_errors,page_errors

    # Hover a county: tourist panel must immediately expose official frequency,
    # annual/4 quarterly scale, relative percentile and 90-day public reports.
    county=page.evaluate("""() => {
      const layer=window.__CRIME_MAP__.getCountyLayer().getLayers().find(x=>x.feature);
      layer.fire('mouseover');
      return true;
    }""")
    assert county is True
    page.wait_for_timeout(150)
    county_card=page.evaluate("""() => ({
      name:document.getElementById("areaName").textContent,
      rate:document.getElementById("areaRate").textContent,
      rateLabel:document.getElementById("areaRateLabel").textContent,
      quarter:document.getElementById("areaQuarter").textContent,
      quarterLabel:document.getElementById("areaQuarterLabel").textContent,
      recent:document.getElementById("areaRecent").textContent,
      rank:document.getElementById("riskRankText").textContent,
      overlay:document.getElementById("layerInfo").textContent
    })""")
    assert county_card["name"]!="在地图上选择地区",county_card
    assert "10万人" in county_card["rateLabel"],county_card
    assert "全年÷4" in county_card["quarterLabel"],county_card
    assert county_card["quarter"].startswith("≈"),county_card
    assert county_card["rank"].startswith("约 P"),county_card
    assert "季度量级" in county_card["overlay"],county_card
    page.screenshot(path=str(SHOT),full_page=True)

    # Zoom to Berlin and verify the local purple scale + BZR tourist card.
    page.click("#focusBerlin")
    page.wait_for_timeout(1300)
    page.evaluate("""() => {
      const layer=window.__CRIME_MAP__.getBerlinLayer().getLayers().find(x=>x.feature);
      layer.fire('mouseover');
    }""")
    page.wait_for_timeout(150)
    berlin=page.evaluate("""() => ({
      zoom:window.__CRIME_MAP__.map.getZoom(),
      layerCount:window.__CRIME_MAP__.getBerlinLayer()?.getLayers().length||0,
      countyLayer:!!window.__CRIME_MAP__.getCountyLayer(),
      legend:document.getElementById("legend").textContent,
      areaName:document.getElementById("areaName").textContent,
      metric:document.getElementById("areaMetric").textContent,
      quarter:document.getElementById("areaQuarter").textContent,
      quarterLabel:document.getElementById("areaQuarterLabel").textContent,
      recentLabel:document.getElementById("areaRecentLabel").textContent,
      rankLabel:document.getElementById("riskRankLabel").textContent
    })""")
    assert berlin["zoom"]>=8,berlin
    assert berlin["layerCount"]>=135,berlin
    assert berlin["countyLayer"] is True,berlin
    assert "柏林试点" in berlin["legend"] and "每10万人/年" in berlin["legend"],berlin
    assert "抢劫 + 危险/严重身体伤害" in berlin["metric"],berlin
    assert berlin["quarter"].startswith("≈"),berlin
    assert "全年÷4" in berlin["quarterLabel"],berlin
    assert "90天" in berlin["recentLabel"],berlin
    assert "柏林同级" in berlin["rankLabel"],berlin
    page.screenshot(path=str(BERLIN_SHOT),full_page=True)

    # Property mode: the same side panel becomes a local 90-day theft card.
    page.click("#modeProperty")
    page.wait_for_timeout(1000)
    page.evaluate("""() => { window.__CRIME_MAP__.map.fire('click',{latlng:L.latLng(52.52,13.405)}); return true; }""")
    page.wait_for_timeout(150)
    prop=page.evaluate("""() => ({
      mode:window.__CRIME_MAP__.getMode(),
      heat:!!window.__CRIME_MAP__.getHeatLayer(),
      visible:window.__CRIME_MAP__.getVisibleCases().length,
      propertyCount:window.__CRIME_MAP__.getCaseData().cases.filter(c=>c.category==="property").length,
      pinned:window.__CRIME_MAP__.getPinnedArea(),
      areaName:document.getElementById("areaName").textContent,
      rateLabel:document.getElementById("areaRateLabel").textContent,
      quarterLabel:document.getElementById("areaQuarterLabel").textContent,
      recentLabel:document.getElementById("areaRecentLabel").textContent,
      info:document.getElementById("layerInfo").textContent,
      violenceControlsHidden:document.getElementById("violenceLayers").hidden,
      propertyControlsHidden:document.getElementById("propertyLayers").hidden
    })""")
    assert prop["mode"]=="property",prop
    assert prop["heat"] is True,prop
    assert prop["visible"]==prop["propertyCount"],prop
    assert prop["propertyCount"]>=300,prop
    assert prop["pinned"]["kind"]=="property",prop
    assert "最近90天" in prop["rateLabel"],prop
    assert "自行车" in prop["quarterLabel"],prop
    assert "车辆" in prop["recentLabel"],prop
    assert "90天盗窃" in prop["info"],prop
    assert prop["violenceControlsHidden"] is True,prop
    assert prop["propertyControlsHidden"] is False,prop
    page.screenshot(path=str(PROPERTY_SHOT),full_page=True)

    assert not page_errors,page_errors
    print(json.dumps({"national":report,"county_card":county_card,"berlin":berlin,"property":prop},ensure_ascii=False))
    browser.close()
