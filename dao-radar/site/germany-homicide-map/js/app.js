(() => {
  const $=id=>document.getElementById(id);
  const el={
    updated:$('updated'),
    modeViolence:$('modeViolence'),modeProperty:$('modeProperty'),
    toggleViolenceNews:$('toggleViolenceNews'),violenceMetric:$('violenceMetric'),
    togglePropertyNews:$('togglePropertyNews'),propertyMetric:$('propertyMetric'),
    violenceLayers:$('violenceLayers'),propertyLayers:$('propertyLayers'),
    viewGermany:$('viewGermany'),focusBerlin:$('focusBerlin'),mapStatus:$('mapStatus'),
    legend:$('legend'),layerInfo:$('layerInfo'),
    stateDrawer:$('stateDrawer'),stateDragHandle:$('stateDragHandle'),stateName:$('stateName'),stateClose:$('stateClose'),stateMetric:$('stateMetric'),
    stateRate:$('stateRate'),stateCases:$('stateCases'),stateRank:$('stateRank'),stateRecent:$('stateRecent'),
    stateTopCounties:$('stateTopCounties'),stateNews:$('stateNews'),stateNewsCount:$('stateNewsCount'),
    safetyPanel:$('safetyPanel'),areaName:$('areaName'),riskBadge:$('riskBadge'),areaMetric:$('areaMetric'),
    coveragePill:$('coveragePill'),coverageText:$('coverageText'),
    areaRate:$('areaRate'),areaRateLabel:$('areaRateLabel'),areaQuarter:$('areaQuarter'),areaQuarterLabel:$('areaQuarterLabel'),
    areaRecent:$('areaRecent'),areaRecentLabel:$('areaRecentLabel'),
    areaNote:$('areaNote'),rankList:$('rankList'),
    listTitle:$('listTitle'),list:$('list')
  };
  const {categories:cats,palettes,propertyMetrics,violenceMetrics}=window.CrimeMapConfig;
  const {national:nationalPalette,berlin:berlinPalette,property:propertyPalette,berlinProperty:berlinPropertyPalette}=palettes;
  let mode='violence',caseData=null,pksData=null,propertyData=null,countyGeo=null,berlinViolence=null,heatData=null,stateGeo=null;
  let countyLayer=null,stateLayer=null,countyController=null,stateController=null;
  let pinnedArea=null,hoverArea=null,showViolenceNews=false,showPropertyNews=false,statePanel=null,eventLayer=null,berlinDetail=null,areaPanel=null;
  const stateDrawerDrag=window.CrimeDrawerDrag.create({drawer:el.stateDrawer,handle:el.stateDragHandle});

  const map=L.map('map',{minZoom:5,maxZoom:17,zoomControl:true,preferCanvas:true,worldCopyJump:false});
  const germanyBounds=L.latLngBounds([[47.05,5.45],[55.15,15.65]]);
  const berlinBounds=L.latLngBounds([[52.33,13.08],[52.69,13.77]]);
  map.fitBounds(germanyBounds,{padding:[14,14]});map.setMaxBounds([[45.3,3.2],[57.1,18.0]]);
  map.createPane('countyPane');map.getPane('countyPane').style.zIndex=230;
  map.createPane('statePane');map.getPane('statePane').style.zIndex=245;
  map.createPane('berlinPane');map.getPane('berlinPane').style.zIndex=260;
  map.createPane('newsPane');map.getPane('newsPane').style.zIndex=460;
  map.getPane('tilePane').style.filter='saturate(.45) contrast(.86) brightness(1.06)';

  let tileOk=false,tileErrors=0;
  const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,opacity:.52,attribution:'© OpenStreetMap contributors',crossOrigin:true,updateWhenIdle:true});
  tiles.on('tileload',()=>{if(!tileOk){tileOk=true;el.mapStatus.className='mapstatus ok';el.mapStatus.textContent='OSM街道底图 + 本地统计图层';}});
  tiles.on('tileerror',()=>{tileErrors++;if(tileErrors>=6&&!tileOk){if(map.hasLayer(tiles))map.removeLayer(tiles);el.mapStatus.className='mapstatus fallback';el.mapStatus.textContent='本地统计底图（OSM当前不可用）';}});
  tiles.addTo(map);
  setTimeout(()=>{if(!tileOk){if(map.hasLayer(tiles))map.removeLayer(tiles);el.mapStatus.className='mapstatus fallback';el.mapStatus.textContent='本地统计底图（OSM当前不可用）';}},4000);

  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=n=>Number(n||0).toLocaleString('zh-CN');
  const pd=s=>{const [y,m,d]=String(s||'').split('-');return y&&m&&d?d+'.'+m+'.'+y:String(s||'')};
  const safe=u=>/^https:\/\//i.test(String(u||''))?u:'#';
  const {scaleColor,pointInGeometry,percentile,riskLabel,quantileBreaks}=window.CrimeMapUtils;

  function violentRecentCount(feature,metric=currentViolenceMetric()){
    if(!caseData||!feature?.geometry)return 0;
    const catsOk=new Set(violenceMetrics[metric]?.news||[]);
    return caseData.cases.filter(c=>catsOk.has(c.category)&&Number.isFinite(c.lon)&&Number.isFinite(c.lat)&&pointInGeometry(c.lon,c.lat,feature.geometry)).length;
  }
  function currentViolenceMetric(){return el.violenceMetric?.value||'violence';}
  function nationalRates(metric=currentViolenceMetric()){
    return Object.values(pksData?.records||{}).map(r=>Number(r?.[metric]?.rate)).filter(Number.isFinite);
  }
  function currentPropertyMetric(){return el.propertyMetric?.value||'property_total';}
  function propertyRates(metric=currentPropertyMetric()){
    return Object.values(propertyData?.records||{}).map(r=>Number(r?.[metric]?.rate)).filter(Number.isFinite);
  }
  function propertyHeatField(){return berlinDetail?.propertyField()||null;}
  function berlinLocalActive(){return berlinDetail?.isActive()||false;}
  function stateFeatureByName(name){
    return stateGeo?.features?.find(f=>f.properties?.name===name)||null;
  }
  function caseMatchesCurrentMetric(c){
    const key=mode==='property'?currentPropertyMetric():currentViolenceMetric();
    return window.CrimeDataModel.caseMatchesMetric(mode,key,c,violenceMetrics);
  }
  function caseInState(c,feature){return window.CrimeDataModel.caseInFeature(c,feature);}
  function stateStats(feature){
    const key=mode==='property'?currentPropertyMetric():currentViolenceMetric();
    return window.CrimeDataModel.stateStats({feature,stateGeo,mode,key,propertyData,pksData,caseData,violenceMetrics});
  }
  function stateTooltipHtml(feature){
    const s=stateStats(feature);
    const label=mode==='property'?(propertyMetrics[s.key]?.label||s.key):(violenceMetrics[s.key]?.label||s.key);
    return '<b>'+esc(s.name)+'</b><br>'+esc(label)+' · '+fmt(Math.round(s.rate))+'/10万人<br>'+fmt(s.cases)+' 起 · 16州第 '+s.rank;
  }
  function countyArea(feature,rec){
    const key=currentViolenceMetric(),m=rec?.[key]||{},rate=Number(m.rate||0),cases=Number(m.cases||0),pct=percentile(rate,nationalRates(key));
    return {kind:'violence-county',ags:rec?.ags||'',name:rec?.name||'未知县/市',state:rec?.state||'',metric:'BKA PKS 2025 · '+(violenceMetrics[key]?.label||key),
      rate,cases,change:m.change||'—',recent:violentRecentCount(feature,key),pct,feature,metricKey:key,
      note:'2025年警方记录的县/市级年度数据。颜色按德国县/市同一指标的相对分位着色；未报案事件不在PKS中。'};
  }
  function propertyCountyArea(feature,rec){
    const key=currentPropertyMetric(),m=rec?.[key]||{},rate=Number(m.rate||0),cases=Number(m.cases||0),pct=percentile(rate,propertyRates(key));
    const recent=caseData?.cases?.filter(c=>c.category==='property'&&Number.isFinite(c.lon)&&Number.isFinite(c.lat)&&pointInGeometry(c.lon,c.lat,feature.geometry)).length||0;
    return {kind:'property-county',ags:rec?.ags||'',name:rec?.name||'未知县/市',state:rec?.state||'',metric:'BKA PKS 2025 · '+(propertyMetrics[key]?.label||key),
      rate,cases,change:m.change||'—',recent,pct,feature,metricKey:key,
      note:'2025年警方记录的县/市级年度数据。颜色按德国县/市同一指标的相对分位着色；未报案事件不在PKS中。'};
  }

  function berlinRates(){return berlinDetail?.violenceRates()||[];}
  function propertyLocalValues(field=propertyHeatField()){return berlinDetail?.propertyValues(field)||[];}

  function currentNationalSummary(){
    const key=mode==='property'?currentPropertyMetric():currentViolenceMetric();
    return window.CrimeDataModel.nationalSummary({mode,key,propertyData,pksData,propertyMetrics,violenceMetrics});
  }
  function renderRankList(){areaPanel.renderRankList();}
  function showArea(area,{pin=false}={}){
    if(pin)pinnedArea=area;
    hoverArea=pin?null:area;
    areaPanel.show(area||pinnedArea);
  }

  function pksRecord(feature){
    const id=String(feature?.id??feature?.properties?.AGS??'').padStart(5,'0');
    const alias=pksData?.meta?.geometry_aliases?.[id];
    return pksData?.records?.[id]||pksData?.records?.[alias]||null;
  }
  function propertyRecord(feature){
    const id=String(feature?.id??feature?.properties?.AGS??'').padStart(5,'0');
    const alias=propertyData?.meta?.geometry_aliases?.[id];
    return propertyData?.records?.[id]||propertyData?.records?.[alias]||null;
  }
  function selectCountyLayer(layer){countyController.select(layer);}
  function buildCountyLayer(){countyLayer=countyController.render();}
  function buildStateLayer(){stateLayer=stateController.render();}

  function visibleCases(){
    if(!caseData)return[];
    let rows=caseData.cases.filter(caseMatchesCurrentMetric);
    const stateFilter=statePanel?.filterName;
    if(stateFilter){
      const f=stateFeatureByName(stateFilter);
      if(f)rows=rows.filter(c=>caseInState(c,f));
      return rows;
    }
    if(mode==='property')return showPropertyNews?rows:[];
    return showViolenceNews?rows:[];
  }
  function renderNews(){
    return eventLayer.render(visibleCases(),{titlePrefix:statePanel?.filterName||''});
  }

  function scaleHtml(palette,breaks){
    const labs=[
      '≤'+fmt(Math.round(breaks[0]||0)),
      '≤'+fmt(Math.round(breaks[1]||0)),
      '≤'+fmt(Math.round(breaks[2]||0)),
      '≤'+fmt(Math.round(breaks[3]||0)),
      '≤'+fmt(Math.round(breaks[4]||0)),
      '≤'+fmt(Math.round(breaks[5]||0)),
      '>'+fmt(Math.round(breaks[5]||0))
    ];
    return '<div class="scale">'+palette.map(c=>'<span style="background:'+c+'"></span>').join('')+'</div>'+
      '<div class="legend-labels">'+labs.map(x=>'<span>'+x+'</span>').join('')+'</div>';
  }
  function renderLegend(){
    if(mode==='violence'){
      const key=currentViolenceMetric(),meta=violenceMetrics[key]||{},n=quantileBreaks(nationalRates(key));
      const b=quantileBreaks(berlinRates());
      el.legend.innerHTML=
        '<div class="legend-block"><div class="legend-title">德国县/市 · BKA PKS 2025</div><div>'+esc(meta.label||key)+' · 每10万人/年</div>'+scaleHtml(nationalPalette,n)+'</div>'+
        (key==='violence'&&map.getZoom()>=7.5&&map.getBounds().intersects(berlinBounds)?'<div class="legend-block"><div class="legend-title">柏林 · 官方细分层</div><div>抢劫 + 危险/严重伤害 · 每10万人/年</div>'+scaleHtml(berlinPalette,b)+'</div>':'')+
        '<div class="legend-row">全国层按县/市分位；城市细分层仅在官方口径可对应时自动显示。</div>';
    }else{
      const key=currentPropertyMetric(),meta=propertyMetrics[key]||{},n=quantileBreaks(propertyRates(key));
      const localField=propertyHeatField(),localBreaks=localField?quantileBreaks(propertyLocalValues(localField)):[];
      el.legend.innerHTML=
        '<div class="legend-block"><div class="legend-title">德国县/市 · BKA PKS 2025</div><div>'+esc(meta.label||key)+' · 每10万人/年</div>'+scaleHtml(propertyPalette,n)+'</div>'+
        (localField&&map.getZoom()>=7.5&&map.getBounds().intersects(berlinBounds)?'<div class="legend-block"><div class="legend-title">柏林 · 官方90天分区</div><div>'+(localField==='bike'?'自行车盗窃':localField==='vehicle'?'车内/车上盗窃':'自行车 + 车辆相关')+' · 记录数</div>'+scaleHtml(berlinPropertyPalette,localBreaks)+'</div>':'')+
        '<div class="legend-row">全国层按县/市犯罪率分位；城市细分层仅在官方可比数据存在时显示。</div>';
    }
  }
  function renderLayerInfo(cs){
    if(hoverArea||pinnedArea){areaPanel.renderAreaOverlay(hoverArea||pinnedArea);return;}
    if(mode==='violence'){
      areaPanel.renderAreaOverlay(null);
    }else{
      areaPanel.renderAreaOverlay(null);
    }
  }
  function renderSummary(){
    if(mode==='violence'){
      if(!pinnedArea||pinnedArea.kind==='berlin')showArea(null);
    }else{
      if(!pinnedArea||pinnedArea.kind==='property-local')showArea(null);
    }
  }
  function render(){
    el.modeViolence.classList.toggle('active',mode==='violence');el.modeProperty.classList.toggle('active',mode==='property');
    el.violenceLayers.hidden=mode!=='violence';el.propertyLayers.hidden=mode!=='property';
    el.toggleViolenceNews.classList.toggle('active',showViolenceNews);el.toggleViolenceNews.setAttribute('aria-pressed',String(showViolenceNews));
    el.togglePropertyNews.classList.toggle('active',showPropertyNews);el.togglePropertyNews.setAttribute('aria-pressed',String(showPropertyNews));
    buildCountyLayer();buildStateLayer();berlinDetail.render();
    const cs=renderNews();renderLegend();renderLayerInfo(cs);renderSummary(cs);renderRankList();
    const stateFilter=statePanel?.filterName;if(stateFilter){const f=stateFeatureByName(stateFilter);if(f)statePanel.render(f);}
  }

  areaPanel=window.CrimeAreaPanel.create({
    elements:el,
    getMode:()=>mode,getPksData:()=>pksData,getPropertyData:()=>propertyData,
    getNationalSummary:currentNationalSummary,
    formatNumber:fmt,escapeHtml:esc,
    onRankSelect:r=>{
      const layer=countyLayer?.getLayers().find(x=>{
        const rec=mode==='property'?propertyRecord(x.feature):pksRecord(x.feature);
        return rec?.ags===r.ags;
      });
      if(layer){
        const a=mode==='property'?propertyCountyArea(layer.feature,r):countyArea(layer.feature,r);
        selectCountyLayer(layer);showArea(a,{pin:true});
        if(layer.getBounds)map.fitBounds(layer.getBounds(),{padding:[30,30],maxZoom:8});
      }
    }
  });

  countyController=window.CrimeCountyLayer.create({
    map,getCountyGeo:()=>countyGeo,getMode:()=>mode,
    getPksData:()=>pksData,getPropertyData:()=>propertyData,
    getMetric:kind=>kind==='property'?currentPropertyMetric():currentViolenceMetric(),
    getRates:(key,kind)=>kind==='property'?propertyRates(key):nationalRates(key),
    getRecord:(feature,kind)=>kind==='property'?propertyRecord(feature):pksRecord(feature),
    getArea:(feature,record,kind)=>kind==='property'?propertyCountyArea(feature,record):countyArea(feature,record),
    isBerlinDetailActive:berlinLocalActive,
    showArea,getPinnedArea:()=>pinnedArea,onLeave:()=>{hoverArea=null;},
    formatNumber:fmt,escapeHtml:esc,nationalPalette,propertyPalette
  });
  stateController=window.CrimeStateLayer.create({
    map,getStateGeo:()=>stateGeo,getStatePanel:()=>statePanel,
    tooltipHtml:stateTooltipHtml
  });

  berlinDetail=window.CrimeBerlinDetail.create({
    map,
    getMode:()=>mode,
    getViolenceMetric:currentViolenceMetric,
    getPropertyMetric:currentPropertyMetric,
    getCaseData:()=>caseData,
    getViolenceData:()=>berlinViolence,
    getPropertyData:()=>heatData,
    showArea,
    getPinnedArea:()=>pinnedArea,
    formatNumber:fmt,
    escapeHtml:esc,
    violencePalette:berlinPalette,
    propertyPalette:berlinPropertyPalette
  });

  eventLayer=window.CrimeRecentEvents.create({
    map,
    listElement:el.list,
    titleElement:el.listTitle,
    categories:cats,
    formatNumber:fmt,
    formatDate:pd,
    escapeHtml:esc,
    safeUrl:safe
  });

  statePanel=window.CrimeStatePanel.create({
    elements:{
      stateDrawer:el.stateDrawer,stateName:el.stateName,stateMetric:el.stateMetric,
      stateRate:el.stateRate,stateCases:el.stateCases,stateRank:el.stateRank,stateRecent:el.stateRecent,
      stateTopCounties:el.stateTopCounties,stateNews:el.stateNews,stateNewsCount:el.stateNewsCount
    },
    map,
    getMode:()=>mode,
    getStats:stateStats,
    getMetricLabel:key=>mode==='property'?(propertyMetrics[key]?.label||key):(violenceMetrics[key]?.label||key),
    onCountySelect:(row,key)=>{
      const layer=countyLayer?.getLayers().find(x=>{
        const rec=mode==='property'?propertyRecord(x.feature):pksRecord(x.feature);
        return rec?.ags===row.ags;
      });
      if(layer){
        const area=mode==='property'?propertyCountyArea(layer.feature,row):countyArea(layer.feature,row);
        selectCountyLayer(layer);showArea(area,{pin:true});
        if(layer.getBounds)map.fitBounds(layer.getBounds(),{padding:[30,30],maxZoom:9});
      }
    },
    onNewsSelect:item=>eventLayer.open(item,{minZoom:10,duration:.45}),
    onStateChanged:()=>renderNews(),
    formatNumber:fmt,formatDate:pd,escapeHtml:esc
  });

  el.modeViolence.onclick=()=>{mode='violence';pinnedArea=null;hoverArea=null;statePanel.reset();render();showArea(null);};
  el.modeProperty.onclick=()=>{mode='property';pinnedArea=null;hoverArea=null;statePanel.reset();render();showArea(null);};
  el.stateClose.onclick=e=>{e.stopPropagation();statePanel.close({restore:true});buildStateLayer();};
  el.stateClose.onpointerdown=e=>e.stopPropagation();
  el.stateDragHandle.addEventListener('pointerdown',stateDrawerDrag.begin);
  el.stateDragHandle.addEventListener('pointermove',stateDrawerDrag.move);
  el.stateDragHandle.addEventListener('pointerup',stateDrawerDrag.end);
  el.stateDragHandle.addEventListener('pointercancel',stateDrawerDrag.end);
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&statePanel.isOpen){statePanel.close({restore:true});buildStateLayer();}});
  el.toggleViolenceNews.onclick=()=>{showViolenceNews=!showViolenceNews;render();};
  el.togglePropertyNews.onclick=()=>{showPropertyNews=!showPropertyNews;render();};
  el.violenceMetric.addEventListener('change',()=>{pinnedArea=null;hoverArea=null;render();showArea(null);});
  el.propertyMetric.addEventListener('change',()=>{pinnedArea=null;hoverArea=null;render();showArea(null);});
  el.viewGermany.onclick=()=>{pinnedArea=null;hoverArea=null;countyController.clearSelection();statePanel.reset();render();showArea(null);map.fitBounds(germanyBounds,{padding:[14,14]});};
  el.focusBerlin.onclick=()=>{pinnedArea=null;hoverArea=null;countyController.clearSelection();statePanel.reset();showArea(null);map.fitBounds(berlinBounds,{padding:[25,25],maxZoom:10});};
  map.on('zoomend',()=>{buildStateLayer();berlinDetail.render();renderLegend();});
  map.on('moveend',()=>{if(!stateLayer)buildStateLayer();if(el.stateDrawer.classList.contains('open'))stateDrawerDrag.keepInside();});

  window.addEventListener('resize',()=>{if(el.stateDrawer.classList.contains('open'))stateDrawerDrag.keepInside();});
  Promise.all([
    fetch('data/cases.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('cases '+r.status);return r.json()}),
    fetch('data/germany-counties.geojson',{cache:'force-cache'}).then(r=>{if(!r.ok)throw new Error('counties '+r.status);return r.json()}),
    fetch('data/germany-states.geojson',{cache:'force-cache'}).then(r=>{if(!r.ok)throw new Error('states '+r.status);return r.json()}),
    fetch('data/pks_violent_2025.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('pks '+r.status);return r.json()}),
    fetch('data/pks_property_2025.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('property pks '+r.status);return r.json()}),
    fetch('data/berlin_violent_2025.geojson',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('berlin violence '+r.status);return r.json()}),
    fetch('data/berlin_heatmap.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('heat '+r.status);return r.json()})
  ]).then(([cases,counties,states,pks,propertyPks,berlinV,heat])=>{
    caseData=cases;countyGeo=counties;stateGeo=states;pksData=pks;propertyData=propertyPks;berlinViolence=berlinV;heatData=heat;
    const t=caseData.meta?.generated_at?new Date(caseData.meta.generated_at):null;
    el.updated.textContent=t&&!Number.isNaN(+t)?'通报更新 '+t.toLocaleString():'通报更新时间未知';
    render();showArea(null);
  }).catch(err=>{
    console.error(err);el.mapStatus.className='mapstatus fallback';el.mapStatus.textContent='数据加载失败：'+err.message;el.updated.textContent='数据加载失败';
  });

  window.__CRIME_MAP__={
    map,getMode:()=>mode,getCaseData:()=>caseData,getPksData:()=>pksData,getPropertyData:()=>propertyData,getBerlinViolence:()=>berlinViolence,getHeatData:()=>heatData,
    getCountyLayer:()=>countyLayer,getBerlinLayer:()=>berlinDetail?.violenceLayer||null,getHeatLayer:()=>berlinDetail?.propertyLayer||null,getVisibleCases:()=>visibleCases(),
    getPinnedArea:()=>pinnedArea,getHoverArea:()=>hoverArea,
    clearSelection:()=>{pinnedArea=null;hoverArea=null;countyController.clearSelection();statePanel.reset();showArea(null);},
    showArea
  };
})();
