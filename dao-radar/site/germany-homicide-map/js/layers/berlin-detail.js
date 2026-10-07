(() => {
  const {
    scaleColor,
    percentile,
    riskLabel,
    quantileBreaks,
    pointInGeometry,
  } = window.CrimeMapUtils;

  function create({
    map,
    getMode,
    getViolenceMetric,
    getPropertyMetric,
    getCaseData,
    getViolenceData,
    getPropertyData,
    showArea,
    getPinnedArea,
    formatNumber,
    escapeHtml,
    violencePalette,
    propertyPalette,
  }) {
    let violenceLayer = null;
    let propertyLayer = null;

    function propertyField(metric) {
      const key = metric || 'property_total';
      if (key === 'property_total') return 'total';
      if (key === 'bicycle_theft') return 'bike';
      if (key === 'theft_from_vehicle') return 'vehicle';
      return null;
    }

    function currentPropertyField() {
      return propertyField(getPropertyMetric?.() || 'property_total');
    }

    function isActive() {
      if (map.getZoom() < 7.5) return false;
      if (getMode() === 'violence') {
        return getViolenceMetric() === 'violence' && !!getViolenceData();
      }
      return !!currentPropertyField() && !!getPropertyData() && !!getViolenceData();
    }

    function violenceRates() {
      const seen = new Map();
      for (const feature of getViolenceData()?.features || []) {
        const p = feature.properties || {};
        if (!seen.has(p.bZR)) seen.set(p.bZR, Number(p.combined_rate));
      }
      return [...seen.values()].filter(Number.isFinite);
    }

    function recentViolenceCount(bzr) {
      const cases = getCaseData()?.cases || [];
      const data = getViolenceData();
      if (!bzr || !data) return 0;

      const geometries = (data.features || [])
        .filter((feature) => feature.properties?.bZR === bzr)
        .map((feature) => feature.geometry)
        .filter(Boolean);
      const categories = new Set(['homicide', 'violence', 'robbery', 'sexual']);

      return cases.filter(
        (item) =>
          categories.has(item.category) &&
          Number.isFinite(item.lon) &&
          Number.isFinite(item.lat) &&
          geometries.some((geometry) => pointInGeometry(item.lon, item.lat, geometry))
      ).length;
    }

    function violenceArea(feature, props) {
      const rate = Number(props?.combined_rate || 0);
      const cases = Number(props?.combined_cases || 0);
      return {
        kind: 'berlin',
        name: props?.name || 'Berlin Bezirksregion',
        state: 'Berlin',
        metric: 'Polizei Berlin PKS 2025 · 抢劫 + 危险/严重身体伤害',
        rate,
        cases,
        recent: recentViolenceCount(props?.bZR),
        pct: percentile(rate, violenceRates()),
        feature,
        note:
          '柏林细分层为两类严重暴力指标的合计，用于观察城市内部空间差异；与全国完整“Gewaltkriminalität”口径不同。',
      };
    }

    function normalizePlr(value) {
      const digits = String(value || '').replace(/\D/g, '');
      return digits ? digits.padStart(8, '0').slice(-8) : '';
    }

    function propertyPointMap() {
      const points = getPropertyData()?.windows?.['90']?.points || [];
      return new Map(points.map((point) => [normalizePlr(point.lor), point]));
    }

    function propertyValues(field = currentPropertyField()) {
      if (!field) return [];
      return [...propertyPointMap().values()]
        .map((point) => Number(point[field] || 0))
        .filter(Number.isFinite);
    }

    function propertyArea(feature, geomProps, point) {
      if (!point) return null;
      const field = currentPropertyField() || 'total';
      const value = Number(point[field] || 0);
      const label =
        field === 'bike'
          ? '自行车盗窃'
          : field === 'vehicle'
            ? '车内/车上盗窃'
            : '自行车 + 车辆相关盗窃';

      return {
        kind: 'property-local',
        name: point.name || geomProps?.name || point.lor || 'Berlin Planungsraum',
        state: 'Berlin',
        metric: 'Polizei Berlin Open Data · 近90天 · ' + label,
        rate: null,
        cases: value,
        recent: value,
        pct: percentile(value, propertyValues(field)),
        feature,
        bike: Number(point.bike || 0),
        vehicle: Number(point.vehicle || 0),
        total: Number(point.total || 0),
        note:
          '柏林 Planungsraum 级官方开放数据；显示最近90天记录数，不按人口标准化，也不代表全部财产犯罪。',
      };
    }

    function clearViolence() {
      if (violenceLayer) {
        map.removeLayer(violenceLayer);
        violenceLayer = null;
      }
    }

    function clearProperty() {
      if (propertyLayer) {
        map.removeLayer(propertyLayer);
        propertyLayer = null;
      }
    }

    function buildViolence() {
      clearViolence();
      if (
        getMode() !== 'violence' ||
        getViolenceMetric() !== 'violence' ||
        !getViolenceData() ||
        map.getZoom() < 7.5
      ) {
        return;
      }

      const breaks = quantileBreaks(violenceRates());
      violenceLayer = L.geoJSON(getViolenceData(), {
        pane: 'berlinPane',
        style: (feature) => {
          const value = Number(feature?.properties?.combined_rate || 0);
          return {
            pane: 'berlinPane',
            color: '#76558a',
            weight: 0.34,
            opacity: 0.58,
            fillColor: scaleColor(value, breaks, violencePalette),
            fillOpacity: 0.84,
          };
        },
        onEachFeature: (feature, layer) => {
          const props = feature.properties || {};
          const area = () => violenceArea(feature, props);

          layer.bindTooltip(
            () => {
              const a = area();
              return (
                '<b>' +
                escapeHtml(props.name) +
                '</b><br>严重暴力细分 ' +
                formatNumber(Math.round(a.rate)) +
                ' /10万人·年 · ' +
                riskLabel(a.pct).text +
                '<br>2025登记 ' +
                formatNumber(Math.round(a.cases)) +
                ' 起'
              );
            },
            { sticky: true }
          );
          layer.on('mouseover', () => showArea(area()));
          layer.on('mouseout', () => showArea(getPinnedArea()));
          layer.on('click', () => showArea(area(), { pin: true }));
        },
      }).addTo(map);
    }

    function buildProperty() {
      clearProperty();
      const data = getViolenceData();
      const points = getPropertyData();
      const field = currentPropertyField();

      if (getMode() !== 'property' || !points || !data || map.getZoom() < 7.5 || !field) {
        return;
      }

      const byPlr = propertyPointMap();
      const breaks = quantileBreaks(propertyValues(field));

      propertyLayer = L.geoJSON(data, {
        pane: 'berlinPane',
        filter: (feature) => byPlr.has(normalizePlr(feature?.properties?.plr)),
        style: (feature) => {
          const point = byPlr.get(normalizePlr(feature?.properties?.plr));
          const value = Number(point?.[field] || 0);
          return {
            pane: 'berlinPane',
            color: '#486783',
            weight: 0.34,
            opacity: 0.58,
            fillColor: scaleColor(value, breaks, propertyPalette),
            fillOpacity: 0.84,
          };
        },
        onEachFeature: (feature, layer) => {
          const point = byPlr.get(normalizePlr(feature?.properties?.plr));
          if (!point) return;
          const area = () => propertyArea(feature, feature.properties || {}, point);

          layer.bindTooltip(
            () => {
              const a = area();
              return (
                '<b>' +
                escapeHtml(a.name) +
                '</b><br>' +
                escapeHtml(a.metric.replace('Polizei Berlin Open Data · 近90天 · ', '')) +
                ' ' +
                formatNumber(a.cases) +
                ' 起 · ' +
                riskLabel(a.pct).text
              );
            },
            { sticky: true }
          );

          layer.on('mouseover', () => {
            layer.setStyle({ color: '#ffffff', weight: 1.25, opacity: 1, fillOpacity: 0.84 });
            showArea(area());
          });
          layer.on('mouseout', () => {
            propertyLayer?.resetStyle(layer);
            showArea(getPinnedArea());
          });
          layer.on('click', () => {
            propertyLayer?.resetStyle(layer);
            layer.setStyle({ color: '#ffffff', weight: 2.1, opacity: 1, fillOpacity: 0.86 });
            showArea(area(), { pin: true });
          });
        },
      }).addTo(map);
    }

    function render() {
      if (getMode() === 'violence') {
        clearProperty();
        buildViolence();
      } else {
        clearViolence();
        buildProperty();
      }
    }

    function clear() {
      clearViolence();
      clearProperty();
    }

    return Object.freeze({
      render,
      clear,
      isActive,
      propertyField: currentPropertyField,
      violenceRates,
      propertyValues,
      get violenceLayer() { return violenceLayer; },
      get propertyLayer() { return propertyLayer; },
    });
  }

  window.CrimeBerlinDetail = Object.freeze({ create });
})();
