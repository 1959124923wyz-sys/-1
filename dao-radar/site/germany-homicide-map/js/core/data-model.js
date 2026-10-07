(() => {
  const { pointInGeometry, quantileBreaks } = window.CrimeMapUtils;

  function caseMatchesMetric(mode, key, item, violenceMetrics) {
    if (mode === 'violence') {
      return new Set(violenceMetrics?.[key]?.news || []).has(item.category);
    }
    if (item.category !== 'property') return false;
    if (key === 'property_total') return true;

    const text = (
      String(item.subcategory || '') + ' ' +
      String(item.offense || '') + ' ' +
      String(item.summary || '')
    ).toLowerCase();

    if (key === 'burglary') return /wohnungseinbruch/.test(text);
    if (key === 'bicycle_theft') return /fahrrad|pedelec|e-bike|ebike/.test(text);
    if (key === 'vehicle_theft') {
      return /autodiebstahl|fahrzeug-\/autodiebstahl|fahrzeugdiebstahl|kraftwagen.*diebstahl/.test(text);
    }
    if (key === 'theft_from_vehicle') {
      return /diebstahl.*(?:aus|an).*fahrzeug|fahrzeugaufbruch|kfz.*aufbruch/.test(text);
    }
    return false;
  }

  function caseInFeature(item, feature) {
    const name = feature?.properties?.name || '';
    if (item.state && item.state === name) return true;
    return (
      Number.isFinite(item.lon) &&
      Number.isFinite(item.lat) &&
      pointInGeometry(item.lon, item.lat, feature?.geometry)
    );
  }

  function populationForAgs(pksData, ags) {
    const violent = pksData?.records?.[ags]?.violence;
    return violent && Number(violent.rate) > 0
      ? (Number(violent.cases) / Number(violent.rate)) * 100000
      : 0;
  }

  function stateBaseStats({ feature, mode, key, propertyData, pksData }) {
    const name = feature?.properties?.name || '';
    const data = mode === 'property' ? propertyData : pksData;
    const rows = Object.values(data?.records || {}).filter(
      (row) =>
        row.state === name &&
        row?.[key] &&
        Number.isFinite(Number(row[key].rate))
    );
    const cases = rows.reduce((sum, row) => sum + Number(row[key].cases || 0), 0);
    const population = rows.reduce(
      (sum, row) => sum + populationForAgs(pksData, row.ags),
      0
    );
    return {
      name,
      key,
      rows,
      cases,
      pop: population,
      rate: population > 0 ? (cases / population) * 100000 : 0,
    };
  }

  function allStateStats({ stateGeo, mode, key, propertyData, pksData }) {
    return (stateGeo?.features || [])
      .map((feature) => ({
        feature,
        ...stateBaseStats({ feature, mode, key, propertyData, pksData }),
      }))
      .filter((row) => row.rows.length)
      .sort((a, b) => b.rate - a.rate);
  }

  function stateStats({
    feature,
    stateGeo,
    mode,
    key,
    propertyData,
    pksData,
    caseData,
    violenceMetrics,
  }) {
    const base = stateBaseStats({ feature, mode, key, propertyData, pksData });
    const all = allStateStats({ stateGeo, mode, key, propertyData, pksData });
    const rank = Math.max(1, all.findIndex((row) => row.name === base.name) + 1);
    const news = (caseData?.cases || [])
      .filter(
        (item) =>
          caseMatchesMetric(mode, key, item, violenceMetrics) &&
          caseInFeature(item, feature)
      )
      .sort((a, b) => String(b.event_date).localeCompare(String(a.event_date)));

    return {
      ...base,
      rank,
      news,
      topCounties: base.rows
        .slice()
        .sort((a, b) => Number(b[base.key].rate) - Number(a[base.key].rate))
        .slice(0, 5),
    };
  }

  function nationalSummary({
    mode,
    key,
    propertyData,
    pksData,
    propertyMetrics,
    violenceMetrics,
  }) {
    const isProperty = mode === 'property';
    const metadata = isProperty ? propertyMetrics[key] : violenceMetrics[key];
    const data = isProperty ? propertyData : pksData;
    const rows = Object.values(data?.records || {}).filter(
      (row) => row?.[key] && Number.isFinite(Number(row[key].rate))
    );
    const sorted = rows
      .slice()
      .sort((a, b) => Number(b[key].rate) - Number(a[key].rate));
    const rates = rows.map((row) => Number(row[key].rate)).sort((a, b) => a - b);
    const median = rates.length ? rates[Math.floor((rates.length - 1) / 2)] : 0;
    const totalCases = rows.reduce(
      (sum, row) => sum + Number(row?.[key]?.cases || 0),
      0
    );
    return {
      key,
      label: metadata?.label || key,
      de: metadata?.de || key,
      rows,
      sorted,
      rates,
      breaks: quantileBreaks(rates),
      median,
      totalCases,
      top: sorted[0] || null,
    };
  }

  window.CrimeDataModel = Object.freeze({
    caseMatchesMetric,
    caseInFeature,
    populationForAgs,
    stateBaseStats,
    allStateStats,
    stateStats,
    nationalSummary,
  });
})();
