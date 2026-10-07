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
  const {NATIONAL_VIOLENCE_2025,categories:cats,palettes,propertyMetrics,violenceMetrics}=window.CrimeMapConfig;
  const {national:nationalPalette,berlin:berlinPalette,property:propertyPalette,berlinProperty:berlinPropertyPalette}=palettes;
  let mode='violence',caseData=null,pksData=null,propertyData=null,countyGeo=null,berlinViolence=null,heatData=null,stateGeo=null;
  let countyLayer=null,berlinLayer=null,heatLayer=null,stateLayer=null,selectedCountyLayer=null;
  let pinnedArea=null,hoverArea=null,showViolenceNews=false,showPropertyNews=false,statePanel=null,eventLayer=null;
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
  function propertyHeatField(metric=currentPropertyMetric()){
    if(metric==='property_total')return 'total';
    if(metric==='bicycle_theft')return 'bike';
    if(metric==='theft_from_vehicle')return 'vehicle';
    return null;
  }
  function berlinLocalActive(){
    if(map.getZoom()<7.5)return false;
    if(mode==='violence')return currentViolenceMetric()==='violence'&&!!berlinViolence;
    return !!propertyHeatField()&&!!heatData&&!!berlinViolence;
  }
  function stateFeatureByName(name){
    return stateGeo?.features?.find(f=>f.properties?.name===name)||null;
  }
  function caseMatchesCurrentMetric(c){
    const key=mode==='property'?currentPropertyMetric():currentViolenceMetric();
    return window.CrimeDataModel.caseMatchesMetric(mode,key,c,violenceMetrics);
  }
  function caseInState(c,feature){return window.CrimeDataModel.caseInFeature(c,feature);}
  function stateRecentCases(feature){
    if(!caseData||!feature)return[];
    return caseData.cases.filter(c=>caseMatchesCurrentMetric(c)&&caseInState(c,feature)).sort((a,b)=>String(b.event_date).localeCompare(String(a.event_date)));
  }
  function stateStats(feature){
    const key=mode==='property'?currentPropertyMetric():currentViolenceMetric();
    return window.CrimeDataModel.stateStats({feature,stateGeo,mode,key,propertyData,pksData,caseData,violenceMetrics});
  }
  function stateTooltipHtml(feature){
    const s=stateStats(feature);
    const label=mode==='property'?(propertyMetrics[s.key]?.label||s.key):(violenceMetrics[s.key]?.label||s.key);
    return '<b>'+esc(s.name)+'</b><br>'+esc(label)+' · '+fmt(Math.round(s.rate))+'/10万人<br>'+fmt(s.cases)+' 起 · 16州第 '+s.rank;
  }
  function berlinRates(){
    const seen=new Map();
    for(const f of berlinViolence?.features||[]){
      const p=f.properties||{};if(!seen.has(p.bZR))seen.set(p.bZR,Number(p.combined_rate));
    }
    return [...seen.values()].filter(Number.isFinite);
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
  function berlinBzrRecentCount(bzr){
    if(!caseData||!berlinViolence||!bzr)return 0;
    const geoms=(berlinViolence.features||[]).filter(f=>f.properties?.bZR===bzr).map(f=>f.geometry).filter(Boolean);
    const catsOk=new Set(['homicide','violence','robbery','sexual']);
    return caseData.cases.filter(c=>catsOk.has(c.category)&&Number.isFinite(c.lon)&&Number.isFinite(c.lat)&&geoms.some(g=>pointInGeometry(c.lon,c.lat,g))).length;
  }
  function berlinArea(feature,p){
    const rate=Number(p?.combined_rate||0),cases=Number(p?.combined_cases||0),pct=percentile(rate,berlinRates());
    return {kind:'berlin',name:p?.name||'Berlin Bezirksregion',state:'Berlin',metric:'Polizei Berlin PKS 2025 · 抢劫 + 危险/严重身体伤害',rate,cases,
      recent:berlinBzrRecentCount(p?.bZR),pct,feature,
      note:'柏林细分层为两类严重暴力指标的合计，用于观察城市内部空间差异；与全国完整“Gewaltkriminalität”口径不同。'};
  }
  function normPlr(v){
    const d=String(v||'').replace(/\D/g,'');
    return d?d.padStart(8,'0').slice(-8):'';
  }
  function propertyPointMap(){
    const pts=heatData?.windows?.['90']?.points||[];
    return new Map(pts.map(p=>[normPlr(p.lor),p]));
  }
  function propertyLocalValues(field=propertyHeatField()){
    if(!field)return[];
    return [...propertyPointMap().values()].map(p=>Number(p[field]||0)).filter(Number.isFinite);
  }
  function propertyLocalArea(feature,geomProps,point){
    if(!point)return null;
    const field=propertyHeatField()||'total',v=Number(point[field]||0),pct=percentile(v,propertyLocalValues(field));
    const label=field==='bike'?'自行车盗窃':field==='vehicle'?'车内/车上盗窃':'自行车 + 车辆相关盗窃';
    return {kind:'property-local',name:point.name||geomProps?.name||point.lor||'Berlin Planungsraum',state:'Berlin',
      metric:'Polizei Berlin Open Data · 近90天 · '+label,
      rate:null,cases:v,recent:v,pct,feature,
      bike:Number(point.bike||0),vehicle:Number(point.vehicle||0),total:Number(point.total||0),
      note:'柏林 Planungsraum 级官方开放数据；显示最近90天记录数，不按人口标准化，也不代表全部财产犯罪。'};
  }
  function renderCoverage(a){
    if(a?.kind==='property-local'||a?.kind==='berlin'){
      el.coveragePill.textContent='细分数据';el.coveragePill.className='coverage-pill high';
      el.coverageText.textContent=a.kind==='property-local'?'Polizei Berlin Open Data · Planungsraum · 90天':'Polizei Berlin Kriminalitätsatlas';
      return;
    }
    const count=mode==='property'?(propertyData?.meta?.county_count||0):(pksData?.meta?.county_count||0);
    el.coveragePill.textContent='官方年度';el.coveragePill.className='coverage-pill standard';
    el.coverageText.textContent=fmt(count)+'/400 县/市';
  }

  function currentNationalSummary(){
    const key=mode==='property'?currentPropertyMetric():currentViolenceMetric();
    return window.CrimeDataModel.nationalSummary({mode,key,propertyData,pksData,propertyMetrics,violenceMetrics});
  }

  function renderRankList(){
    const s=currentNationalSummary();
    el.rankList.innerHTML='';
    for(const [i,r] of s.sorted.slice(0,8).entries()){
      const b=document.createElement('button');b.className='rank-row';b.type='button';
      b.innerHTML='<span class="rank-no">'+(i+1)+'</span><span class="rank-place">'+esc(r.name)+'</span><span class="rank-value">'+fmt(Math.round(r[s.key].rate))+'</span>';
      b.onclick=()=>{
        const layer=countyLayer?.getLayers().find(x=>{
          const rec=mode==='property'?propertyRecord(x.feature):pksRecord(x.feature);
          return rec?.ags===r.ags;
        });
        if(layer){
          const a=mode==='property'?propertyCountyArea(layer.feature,r):countyArea(layer.feature,r);
          selectCountyLayer(layer);showArea(a,{pin:true});
          if(layer.getBounds)map.fitBounds(layer.getBounds(),{padding:[30,30],maxZoom:8});
        }
      };
      el.rankList.appendChild(b);
    }
  }

  function renderNationalOverview(){
    const s=currentNationalSummary(),top=s.top;
    el.areaName.textContent='德国全国 · '+s.label;
    el.riskBadge.textContent=fmt(s.rows.length)+' 县/市';el.riskBadge.className='risk-badge mid';
    el.areaMetric.textContent='BKA PKS 2025 · '+s.label;
    renderCoverage(null);
    el.areaRate.textContent=fmt(Math.round(s.median));el.areaRateLabel.textContent='县/市中位数 · /10万人';
    el.areaQuarter.textContent=fmt(Math.round(s.totalCases));el.areaQuarterLabel.textContent='2025全国县/市汇总案件';
    el.areaRecent.textContent=top?fmt(Math.round(top[s.key].rate)):'—';el.areaRecentLabel.textContent=top?'最高值 · '+top.name:'最高值';
    el.areaNote.textContent='2025登记 '+fmt(Math.round(s.totalCases))+' 起；地图按全国7分位着色。统计为案件数。';
    renderAreaOverlay(null);
  }

  function showArea(area,{pin=false}={}){
    if(pin)pinnedArea=area;
    hoverArea=pin?null:area;
    const a=area||pinnedArea;
    if(!a){
      renderNationalOverview();
      return;
    }
    el.areaName.textContent=a.name;el.areaMetric.textContent=a.metric;renderCoverage(a);
    if(a.kind==='property-local'){
      const risk=riskLabel(a.pct);
      el.riskBadge.textContent=risk.text+' · 柏林P'+a.pct;el.riskBadge.className='risk-badge '+risk.cls;
      el.areaRate.textContent=fmt(a.cases);el.areaRateLabel.textContent='近90天当前指标';
      el.areaQuarter.textContent=fmt(a.bike);el.areaQuarterLabel.textContent='自行车盗窃';
      el.areaRecent.textContent=fmt(a.vehicle);el.areaRecentLabel.textContent='车内/车上盗窃';
      el.areaNote.textContent=a.note;
    }else if(a.kind==='property-county'||a.kind==='violence-county'){
      const risk=riskLabel(a.pct),isProperty=a.kind==='property-county';
      el.riskBadge.textContent=risk.text+' · P'+a.pct;el.riskBadge.className='risk-badge '+risk.cls;
      el.areaRate.textContent=fmt(Math.round(a.rate));el.areaRateLabel.textContent='每10万人·年';
      el.areaQuarter.textContent=fmt(a.cases);el.areaQuarterLabel.textContent='2025登记案件';
      el.areaRecent.textContent=a.change;el.areaRecentLabel.textContent='较2024变化';
      el.areaNote.textContent=a.note;
        }else{
      const risk=riskLabel(a.pct);
      el.riskBadge.textContent=risk.text+' · P'+a.pct;el.riskBadge.className='risk-badge '+risk.cls;
      el.areaRate.textContent=fmt(Math.round(a.rate));el.areaRateLabel.textContent='每10万人·年';
      el.areaQuarter.textContent=fmt(Math.round(a.cases));el.areaQuarterLabel.textContent='2025登记案件';
      el.areaRecent.textContent=fmt(a.recent);el.areaRecentLabel.textContent='90天公开通报';
      el.areaNote.textContent=a.note;
    }
    renderAreaOverlay(a);
  }
  function renderAreaOverlay(a){
    if(!a){el.layerInfo.innerHTML='';return;}
    if(a.kind==='property-local'){
      el.layerInfo.innerHTML='<b>'+esc(a.name)+'</b><div class="mini-grid"><span><b>'+fmt(a.cases)+'</b><small>90天盗窃</small></span><span><b>'+fmt(a.bike)+'</b><small>自行车</small></span><span><b>'+fmt(a.vehicle)+'</b><small>车辆相关</small></span></div><small>最近统计区近似</small>';
    }else{
      el.layerInfo.innerHTML='<b>'+esc(a.name)+'</b><div class="mini-grid"><span><b>'+fmt(Math.round(a.rate))+'</b><small>/10万人·年</small></span><span><b>'+fmt(Math.round(a.cases||0))+'</b><small>2025案件</small></span><span><b>'+fmt(a.recent||0)+'</b><small>90天通报</small></span></div><small>'+esc(riskLabel(a.pct).text)+' · '+(a.kind==='berlin'?'柏林同级':'德国县/市')+'约P'+a.pct+'</small>';
    }
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
  function nationalStyle(feature){
    if(mode==='property'){
      const key=currentPropertyMetric(),rec=propertyRecord(feature),breaks=quantileBreaks(propertyRates(key));
      const val=rec?.[key]?.rate;
      if(rec?.name==='Berlin'&&berlinLocalActive())return {pane:'countyPane',color:'transparent',weight:0,opacity:0,fillColor:'transparent',fillOpacity:0};
      return {pane:'countyPane',color:'#718390',weight:.28,opacity:.58,fillColor:rec?scaleColor(val,breaks,propertyPalette):'#cbd4d9',fillOpacity:(rec&&val!=null)?0.68:0.07};
    }
    const key=currentViolenceMetric(),rec=pksRecord(feature),breaks=quantileBreaks(nationalRates(key)),val=rec?.[key]?.rate;
    if(rec?.name==='Berlin'&&berlinLocalActive())return {pane:'countyPane',color:'transparent',weight:0,opacity:0,fillColor:'transparent',fillOpacity:0};
    return {pane:'countyPane',color:'#7c7f82',weight:.28,opacity:.56,fillColor:rec?scaleColor(val,breaks,nationalPalette):'#cbd4d9',fillOpacity:(rec&&val!=null)?0.68:0.07};
  }
  function berlinStyle(feature){
    const v=Number(feature?.properties?.combined_rate||0),breaks=quantileBreaks(berlinRates());
    return {pane:'berlinPane',color:'#76558a',weight:.34,opacity:.58,fillColor:scaleColor(v,breaks,berlinPalette),fillOpacity:.84};
  }
  function selectCountyLayer(layer){
    if(!countyLayer||!layer)return;
    if(selectedCountyLayer&&selectedCountyLayer!==layer)countyLayer.resetStyle(selectedCountyLayer);
    selectedCountyLayer=layer;
    countyLayer.resetStyle(layer);
    layer.setStyle({color:'#ffffff',weight:2.65,opacity:1,fillOpacity:.78});
    if(layer.bringToFront)layer.bringToFront();
  }
  function hoverCountyLayer(layer){
    if(!layer||layer===selectedCountyLayer)return;
    layer.setStyle({color:'#d8f2ff',weight:1.45,opacity:1,fillOpacity:.74});
    if(layer.bringToFront)layer.bringToFront();
  }
  function unhoverCountyLayer(layer){
    if(!countyLayer||!layer||layer===selectedCountyLayer)return;
    countyLayer.resetStyle(layer);
  }

  function buildCountyLayer(){
    if(countyLayer){map.removeLayer(countyLayer);countyLayer=null;}
    selectedCountyLayer=null;
    if(!countyGeo)return;
    if(mode==='violence'&&!pksData)return;
    if(mode==='property'&&!propertyData)return;
    countyLayer=L.geoJSON(countyGeo,{
      pane:'countyPane',style:nationalStyle,
      onEachFeature:(feature,layer)=>{
        const r=mode==='property'?propertyRecord(feature):pksRecord(feature);if(!r)return;
        const area=()=>mode==='property'?propertyCountyArea(feature,r):countyArea(feature,r);
        layer.bindTooltip(()=>{
          const a=area(),rk=riskLabel(a.pct);
          return '<b>'+esc(r.name)+'</b><br>'+esc(a.metric.replace('BKA PKS 2025 · ',''))+'<br>'+fmt(Math.round(a.rate))+' /10万人·年 · '+rk.text;
        },{sticky:true});
        layer.on('mouseover',()=>{hoverCountyLayer(layer);showArea(area());});
        layer.on('mouseout',()=>{unhoverCountyLayer(layer);hoverArea=null;showArea(pinnedArea);});
        layer.on('click',()=>{selectCountyLayer(layer);showArea(area(),{pin:true});});
      }
    }).addTo(map);
  }
  function stateStyle(feature){
    const selected=feature?.properties?.name===statePanel?.selectedName;
    return {pane:'statePane',color:selected?'#ffffff':'#20384b',weight:selected?3.1:2.0,opacity:selected?1:.98,fillColor:'#dce7ee',fillOpacity:selected?.045:.006};
  }
  function buildStateLayer(){
    if(stateLayer){map.removeLayer(stateLayer);stateLayer=null;}
    if(!stateGeo)return;
    if(map.getZoom()>=7.5)return;
    const interactive=map.getZoom()<=7.15;
    stateLayer=L.geoJSON(stateGeo,{
      pane:'statePane',style:stateStyle,interactive,
      onEachFeature:(feature,layer)=>{
        if(!interactive)return;
        layer.bindTooltip(()=>stateTooltipHtml(feature),{sticky:true,direction:'top',className:'state-tip'});
        layer.on('mouseover',()=>{if(feature.properties?.name!==statePanel?.selectedName)layer.setStyle({color:'#f4fbff',weight:2.65,fillOpacity:.055});});
        layer.on('mouseout',()=>stateLayer&&stateLayer.resetStyle(layer));
        layer.on('click',()=>{
          statePanel.select(feature);
          stateLayer.eachLayer(l=>stateLayer.resetStyle(l));
          layer.setStyle(stateStyle(feature));
          if(layer.getBounds)map.fitBounds(layer.getBounds(),{padding:[32,32],maxZoom:7.05});
        });
      }
    }).addTo(map);
  }
  function buildBerlinLayer(){
    if(berlinLayer){map.removeLayer(berlinLayer);berlinLayer=null;}
    if(mode!=='violence'||currentViolenceMetric()!=='violence'||!berlinViolence||map.getZoom()<7.5)return;
    berlinLayer=L.geoJSON(berlinViolence,{
      pane:'berlinPane',style:berlinStyle,
      onEachFeature:(feature,layer)=>{
        const p=feature.properties||{},area=()=>berlinArea(feature,p);
        layer.bindTooltip(()=>{const a=area(),rk=riskLabel(a.pct);return '<b>'+esc(p.name)+'</b><br>严重暴力细分 '+fmt(Math.round(a.rate))+' /10万人·年 · '+rk.text+'<br>2025登记 '+fmt(Math.round(a.cases))+' 起';},{sticky:true});
        layer.on('mouseover',()=>showArea(area()));
        layer.on('mouseout',()=>{hoverArea=null;showArea(pinnedArea);});
        layer.on('click',()=>showArea(area(),{pin:true}));
      }
    }).addTo(map);
  }

  function buildHeat(){
    if(heatLayer){map.removeLayer(heatLayer);heatLayer=null;}
    if(mode!=='property'||!heatData||!berlinViolence||map.getZoom()<7.5)return;
    const field=propertyHeatField();if(!field)return;
    const byPlr=propertyPointMap(),breaks=quantileBreaks(propertyLocalValues(field));
    heatLayer=L.geoJSON(berlinViolence,{
      pane:'berlinPane',
      filter:feature=>byPlr.has(normPlr(feature?.properties?.plr)),
      style:feature=>{
        const point=byPlr.get(normPlr(feature?.properties?.plr)),v=Number(point?.[field]||0);
        return {pane:'berlinPane',color:'#486783',weight:.34,opacity:.58,fillColor:scaleColor(v,breaks,berlinPropertyPalette),fillOpacity:.84};
      },
      onEachFeature:(feature,layer)=>{
        const point=byPlr.get(normPlr(feature?.properties?.plr));if(!point)return;
        const area=()=>propertyLocalArea(feature,feature.properties||{},point);
        layer.bindTooltip(()=>{
          const a=area(),rk=riskLabel(a.pct);
          return '<b>'+esc(a.name)+'</b><br>'+esc(a.metric.replace('Polizei Berlin Open Data · 近90天 · ',''))+' '+fmt(a.cases)+' 起 · '+rk.text;
        },{sticky:true});
        layer.on('mouseover',()=>{layer.setStyle({color:'#ffffff',weight:1.25,opacity:1,fillOpacity:.84});showArea(area());});
        layer.on('mouseout',()=>{heatLayer&&heatLayer.resetStyle(layer);hoverArea=null;showArea(pinnedArea);});
        layer.on('click',()=>{heatLayer&&heatLayer.resetStyle(layer);layer.setStyle({color:'#ffffff',weight:2.1,opacity:1,fillOpacity:.86});showArea(area(),{pin:true});});
      }
    }).addTo(map);
  }

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
    if(hoverArea||pinnedArea){renderAreaOverlay(hoverArea||pinnedArea);return;}
    if(mode==='violence'){
      renderAreaOverlay(null);
    }else{
      renderAreaOverlay(null);
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
    buildCountyLayer();buildStateLayer();buildBerlinLayer();buildHeat();
    const cs=renderNews();renderLegend();renderLayerInfo(cs);renderSummary(cs);renderRankList();
    const stateFilter=statePanel?.filterName;if(stateFilter){const f=stateFeatureByName(stateFilter);if(f)statePanel.render(f);}
  }

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
  el.viewGermany.onclick=()=>{pinnedArea=null;hoverArea=null;selectedCountyLayer=null;statePanel.reset();render();showArea(null);map.fitBounds(germanyBounds,{padding:[14,14]});};
  el.focusBerlin.onclick=()=>{pinnedArea=null;hoverArea=null;selectedCountyLayer=null;statePanel.reset();showArea(null);map.fitBounds(berlinBounds,{padding:[25,25],maxZoom:10});};
  map.on('zoomend',()=>{buildStateLayer();if(mode==='violence')buildBerlinLayer();if(mode==='property')buildHeat();renderLegend();});
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
    getCountyLayer:()=>countyLayer,getBerlinLayer:()=>berlinLayer,getHeatLayer:()=>heatLayer,getVisibleCases:()=>visibleCases(),
    getPinnedArea:()=>pinnedArea,getHoverArea:()=>hoverArea,
    clearSelection:()=>{pinnedArea=null;hoverArea=null;selectedCountyLayer=null;statePanel.reset();showArea(null);},
    showArea
  };
})();
