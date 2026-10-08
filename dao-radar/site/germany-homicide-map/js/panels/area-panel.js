(() => {
  'use strict';
  const { riskLabel } = window.CrimeMapUtils;

  function create({
    elements: el, getMode, getPksData, getPropertyData,
    getNationalSummary, onRankSelect, formatNumber: fmt, escapeHtml: esc,
  }) {
    function renderCoverage(a) {
      if (a?.kind === 'property-local' || a?.kind === 'berlin') {
        el.coveragePill.textContent='细分数据';
        el.coveragePill.className='coverage-pill high';
        el.coverageText.textContent=a.kind==='property-local'
          ? 'Polizei Berlin Open Data · Planungsraum · 90天'
          : 'Polizei Berlin Kriminalitätsatlas';
        return;
      }
      const count=getMode()==='property'
        ? (getPropertyData()?.meta?.county_count||0)
        : (getPksData()?.meta?.county_count||0);
      el.coveragePill.textContent='官方年度';
      el.coveragePill.className='coverage-pill standard';
      el.coverageText.textContent=fmt(count)+'/400 县/市';
    }

    function renderRankList() {
      const s=getNationalSummary();
      el.rankList.innerHTML='';
      for (const [i,r] of s.sorted.slice(0,8).entries()) {
        const b=document.createElement('button');
        b.className='rank-row';b.type='button';
        b.innerHTML='<span class="rank-no">'+(i+1)+'</span><span class="rank-place">'+
          esc(r.name)+'</span><span class="rank-value">'+fmt(Math.round(r[s.key].rate))+'</span>';
        b.onclick=()=>onRankSelect(r);
        el.rankList.appendChild(b);
      }
    }

    function renderAreaOverlay(a) {
      if (!a) { el.layerInfo.innerHTML=''; return; }
      if (a.kind==='property-local') {
        el.layerInfo.innerHTML='<b>'+esc(a.name)+'</b><div class="mini-grid"><span><b>'+
          fmt(a.cases)+'</b><small>90天盗窃</small></span><span><b>'+fmt(a.bike)+
          '</b><small>自行车</small></span><span><b>'+fmt(a.vehicle)+
          '</b><small>车辆相关</small></span></div><small>最近统计区近似</small>';
      } else {
        el.layerInfo.innerHTML='<b>'+esc(a.name)+'</b><div class="mini-grid"><span><b>'+
          fmt(Math.round(a.rate))+'</b><small>/10万人·年</small></span><span><b>'+
          fmt(Math.round(a.cases||0))+'</b><small>2025案件</small></span><span><b>'+
          fmt(a.recent||0)+'</b><small>90天通报</small></span></div><small>'+
          esc(riskLabel(a.pct).text)+' · '+(a.kind==='berlin'?'柏林同级':'德国县/市')+'约P'+a.pct+'</small>';
      }
    }

    function renderNationalOverview() {
      const s=getNationalSummary(),top=s.top;
      el.areaName.textContent='德国全国 · '+s.label;
      el.riskBadge.textContent=fmt(s.rows.length)+' 县/市';
      el.riskBadge.className='risk-badge mid';
      el.areaMetric.textContent='BKA PKS 2025 · '+s.label;
      renderCoverage(null);
      el.areaRate.textContent=fmt(Math.round(s.median));
      el.areaRateLabel.textContent='县/市中位数 · /10万人';
      el.areaQuarter.textContent=fmt(Math.round(s.totalCases));
      el.areaQuarterLabel.textContent='2025全国县/市汇总案件';
      el.areaRecent.textContent=top?fmt(Math.round(top[s.key].rate)):'—';
      el.areaRecentLabel.textContent=top?'最高值 · '+top.name:'最高值';
      el.areaNote.textContent='2025登记 '+fmt(Math.round(s.totalCases))+' 起；地图按全国7分位着色。统计为案件数。';
      renderAreaOverlay(null);
    }

    function show(a) {
      if (!a) { renderNationalOverview(); return; }
      el.areaName.textContent=a.name;
      el.areaMetric.textContent=a.metric;
      renderCoverage(a);
      if (a.kind==='property-local') {
        const risk=riskLabel(a.pct);
        el.riskBadge.textContent=risk.text+' · 柏林P'+a.pct;
        el.riskBadge.className='risk-badge '+risk.cls;
        el.areaRate.textContent=fmt(a.cases);
        el.areaRateLabel.textContent='近90天当前指标';
        el.areaQuarter.textContent=fmt(a.bike);
        el.areaQuarterLabel.textContent='自行车盗窃';
        el.areaRecent.textContent=fmt(a.vehicle);
        el.areaRecentLabel.textContent='车内/车上盗窃';
        el.areaNote.textContent=a.note;
      } else if(a.kind==='property-county'||a.kind==='violence-county') {
        const risk=riskLabel(a.pct);
        el.riskBadge.textContent=risk.text+' · P'+a.pct;
        el.riskBadge.className='risk-badge '+risk.cls;
        el.areaRate.textContent=fmt(Math.round(a.rate));
        el.areaRateLabel.textContent='每10万人·年';
        el.areaQuarter.textContent=fmt(a.cases);
        el.areaQuarterLabel.textContent='2025登记案件';
        el.areaRecent.textContent=a.change;
        el.areaRecentLabel.textContent='较2024变化';
        el.areaNote.textContent=a.note;
      } else {
        const risk=riskLabel(a.pct);
        el.riskBadge.textContent=risk.text+' · P'+a.pct;
        el.riskBadge.className='risk-badge '+risk.cls;
        el.areaRate.textContent=fmt(Math.round(a.rate));
        el.areaRateLabel.textContent='每10万人·年';
        el.areaQuarter.textContent=fmt(Math.round(a.cases));
        el.areaQuarterLabel.textContent='2025登记案件';
        el.areaRecent.textContent=fmt(a.recent);
        el.areaRecentLabel.textContent='90天公开通报';
        el.areaNote.textContent=a.note;
      }
      renderAreaOverlay(a);
    }

    return Object.freeze({show,renderRankList,renderCoverage,renderNationalOverview,renderAreaOverlay});
  }

  window.CrimeAreaPanel=Object.freeze({create});
})();
