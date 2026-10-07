(()=>{"use strict";
const WARM=['#fff4e6','#fee2c2','#fbc48d','#f59e5b','#ea7449','#d94b3d','#ad2e32'];
const COOL=['#eff6ff','#d9eafb','#b9d8f3','#8bbce3','#5a9bd2','#3678b8','#1f4f8f'];
let api=null,manifest=null,active=null,layer=null,selected=null,cache=new Map();

const $=id=>document.getElementById(id);
const fmt=n=>Number(n||0).toLocaleString('zh-CN');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function metricKey(){return api?.getMode?.()==='property'?$('propertyMetric')?.value:$('violenceMetric')?.value}
function quantile(values){
  const a=values.map(Number).filter(Number.isFinite).sort((x,y)=>x-y);
  if(!a.length)return[0,0,0,0,0,0];
  return [1/7,2/7,3/7,4/7,5/7,6/7].map(p=>{const x=(a.length-1)*p,l=Math.floor(x),h=Math.min(l+1,a.length-1),f=x-l;return a[l]*(1-f)+a[h]*f})
}
function color(v,b,p){for(let i=0;i<b.length;i++)if(v<=b[i])return p[i];return p[p.length-1]}
function percentile(v,values){
  const a=values.slice().sort((x,y)=>x-y),n=Number(v);if(!a.length||!Number.isFinite(n))return 50;
  let below=0,equal=0;for(const x of a){if(x<n)below++;else if(x===n)equal++}
  return Math.max(1,Math.min(99,Math.round(100*(below+equal*.5)/a.length)))
}
function risk(p){return p<=14?['极低','low']:p<=29?['较低','low']:p<=43?['偏低','low']:p<=57?['中等','mid']:p<=71?['偏高','high']:p<=86?['较高','high']:['极高','high']}
function ringHit(lon,lat,ring){let inside=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const xi=+ring[i][0],yi=+ring[i][1],xj=+ring[j][0],yj=+ring[j][1];if(((yi>lat)!==(yj>lat))&&(lon<(xj-xi)*(lat-yi)/((yj-yi)||1e-12)+xi))inside=!inside}return inside}
function geomHit(lon,lat,g){if(!g)return false;const p=rings=>rings?.length&&ringHit(lon,lat,rings[0])&&!rings.slice(1).some(r=>ringHit(lon,lat,r));return g.type==='Polygon'?p(g.coordinates):g.type==='MultiPolygon'?g.coordinates.some(p):false}
function caseMatches(c,key){
  if(api.getMode()==='violence'){
    const m={violence:['homicide','violence','robbery','sexual'],serious_injury:['violence'],robbery:['robbery'],sexual:['sexual'],homicide:['homicide']};
    return (m[key]||[]).includes(c.category)
  }
  if(c.category!=='property')return false;
  const t=((c.subcategory||'')+' '+(c.offense||'')+' '+(c.summary||'')).toLowerCase();
  if(key==='property_total')return true;
  if(key==='burglary')return /wohnungseinbruch/.test(t);
  if(key==='bicycle_theft')return /fahrrad|pedelec|e-bike|ebike/.test(t);
  if(key==='vehicle_theft')return /autodiebstahl|fahrzeug-\/autodiebstahl|fahrzeugdiebstahl|kraftwagen.*diebstahl/.test(t);
  if(key==='theft_from_vehicle')return /diebstahl.*(?:aus|an).*fahrzeug|fahrzeugaufbruch|kfz.*aufbruch/.test(t);
  return false
}
function cityBounds(c){return L.latLngBounds(c.bounds)}
function matchingCity(){
  if(!manifest||!api)return null;
  const k=metricKey();
  return manifest.cities.find(c=>c.metrics?.[k]&&api.map.getZoom()>=(c.min_zoom||8)&&api.map.getBounds().intersects(cityBounds(c)))||null
}
async function cityData(c){
  if(cache.has(c.id))return cache.get(c.id);
  const p=fetch(c.file,{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error(c.id+' '+r.status);return r.json()});
  cache.set(c.id,p);return p
}
function values(data,field){return (data?.features||[]).map(f=>Number(f?.properties?.[field]?.rate)).filter(Number.isFinite)}
function recordForFeature(feature,data){
  const id=String(feature?.id??feature?.properties?.AGS??'').padStart(5,'0'),alias=data?.meta?.geometry_aliases?.[id];
  return data?.records?.[id]||data?.records?.[alias]
}
function baseLayerFor(c){
  const cl=api.getCountyLayer?.(),d=api.getMode()==='property'?api.getPropertyData():api.getPksData();if(!cl)return null;
  return cl.getLayers().find(l=>recordForFeature(l.feature,d)?.name===c.name)||null
}
function restoreBase(c){const cl=api.getCountyLayer?.(),l=baseLayerFor(c);if(cl&&l)cl.resetStyle(l)}
function hideBase(c){const l=baseLayerFor(c);if(l)l.setStyle({color:'transparent',weight:0,opacity:0,fillOpacity:0})}
function areaFor(c,data,f){
  const key=metricKey(),cfg=c.metrics[key],p=f.properties||{},m=p?.[cfg.field]||{},rate=Number(m.rate),cases=Number(m.cases||0),vals=values(data,cfg.field),pc=percentile(rate,vals);
  const recent=(api.getCaseData()?.cases||[]).filter(x=>caseMatches(x,key)&&Number.isFinite(x.lon)&&Number.isFinite(x.lat)&&geomHit(x.lon,x.lat,f.geometry)).length;
  return {kind:'city-local-generic',name:p.name||c.name,state:c.state,metric:c.source_label+' · '+cfg.label,rate,cases,recent,pct:pc,feature:f,change:m.change||'—',city:c}
}
function showPanel(a,pin=false){
  api.showArea(a,{pin});
  const [rt,rc]=risk(a.pct),c=a.city;
  const cp=$('coveragePill'),ct=$('coverageText'),rb=$('riskBadge'),ar=$('areaRate'),arl=$('areaRateLabel'),aq=$('areaQuarter'),aql=$('areaQuarterLabel'),an=$('areaRecent'),anl=$('areaRecentLabel'),note=$('areaNote');
  if(cp){cp.textContent='细分数据';cp.className='coverage-pill high'} if(ct)ct.textContent=c.source_label;
  if(rb){rb.textContent=rt+' · '+(c.name_zh||c.name)+'P'+a.pct;rb.className='risk-badge '+rc}
  if(ar)ar.textContent=Number.isFinite(a.rate)?fmt(Math.round(a.rate)):'—';if(arl)arl.textContent='每10万人·年';
  if(aq)aq.textContent=fmt(a.cases);if(aql)aql.textContent='2025登记案件';
  if(an)an.textContent=a.change;if(anl)anl.textContent='较2024变化';
  if(note)note.textContent=c.source_label+' 官方城市细分数据。'+(a.recent?' 近90天匹配公开通报 '+fmt(a.recent)+' 起。':'')
}
function addLegend(c,data){
  const root=$('legend');if(!root||root.querySelector('.generic-city-legend'))return;
  const cfg=c.metrics[metricKey()],b=quantile(values(data,cfg.field)),pal=api.getMode()==='property'?COOL:WARM;
  const labs=[...b.map(x=>'≤'+fmt(Math.round(x))), '>'+fmt(Math.round(b[5]||0))];
  root.insertAdjacentHTML('beforeend','<div class="legend-block generic-city-legend"><div class="legend-title">'+esc(c.name_zh||c.name)+' · 官方城市细分层</div><div>'+esc(cfg.label)+' · 每10万人/年</div><div class="scale">'+pal.map(x=>'<span style="background:'+x+'"></span>').join('')+'</div><div class="legend-labels">'+labs.map(x=>'<span>'+x+'</span>').join('')+'</div></div>')
}
async function rebuild(){
  const next=matchingCity();
  if(layer){api.map.removeLayer(layer);layer=null;selected=null}
  if(active)restoreBase(active);
  active=next;
  if(!active)return;
  try{
    const data=await cityData(active),cfg=active.metrics[metricKey()],vals=values(data,cfg.field),br=quantile(vals),pal=api.getMode()==='property'?COOL:WARM;
    hideBase(active);
    layer=L.geoJSON(data,{pane:'berlinPane',filter:f=>Number.isFinite(Number(f?.properties?.[cfg.field]?.rate)),style:f=>({pane:'berlinPane',color:api.getMode()==='property'?'#486783':'#8a563b',weight:.34,opacity:.62,fillColor:color(Number(f.properties[cfg.field].rate),br,pal),fillOpacity:.84}),onEachFeature:(f,l)=>{
      l.bindTooltip(()=>{const a=areaFor(active,data,f);return '<b>'+esc(a.name)+'</b><br>'+esc(cfg.label)+' '+fmt(Math.round(a.rate))+'/10万人 · '+risk(a.pct)[0]},{sticky:true});
      l.on('mouseover',()=>{if(l!==selected)l.setStyle({color:'#fff',weight:1.35,opacity:1,fillOpacity:.89});showPanel(areaFor(active,data,f))});
      l.on('mouseout',()=>{if(l!==selected)layer?.resetStyle(l);api.showArea(api.getPinnedArea?.())});
      l.on('click',()=>{if(selected&&selected!==l)layer?.resetStyle(selected);selected=l;layer?.resetStyle(l);l.setStyle({color:'#fff',weight:2.1,opacity:1,fillOpacity:.91});showPanel(areaFor(active,data,f),true)})
    }}).addTo(api.map);
    setTimeout(()=>addLegend(active,data),0)
  }catch(e){console.warn('city detail skipped',active?.id,e)}
}
function addButtons(){
  const anchor=$('focusMunich')||$('focusBerlin');if(!anchor)return;
  for(const c of manifest.cities){
    const id='focusCity_'+c.id;if($(id))continue;
    const b=document.createElement('button');b.id=id;b.type='button';b.textContent=c.name_zh||c.name;b.onclick=()=>api.map.fitBounds(cityBounds(c),{padding:[25,25],maxZoom:10});anchor.before(b)
  }
}
async function boot(){
  for(let i=0;i<100&&!window.__CRIME_MAP__;i++)await new Promise(r=>setTimeout(r,80));
  api=window.__CRIME_MAP__;if(!api)return;
  manifest=await fetch('data/city_layers.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('city registry '+r.status);return r.json()});
  addButtons();
  api.map.on('zoomend',()=>setTimeout(rebuild,0));api.map.on('moveend',()=>setTimeout(rebuild,0));
  for(const id of ['modeViolence','modeProperty','violenceMetric','propertyMetric'])$(id)?.addEventListener('change',()=>setTimeout(rebuild,0));
  $('modeViolence')?.addEventListener('click',()=>setTimeout(rebuild,0));$('modeProperty')?.addEventListener('click',()=>setTimeout(rebuild,0));
  rebuild()
}
boot().catch(e=>console.error('city-local',e));
})();
