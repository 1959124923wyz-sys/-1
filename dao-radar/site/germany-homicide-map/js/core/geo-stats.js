(() => {
  function scaleColor(value, breaks, palette, fallback = '#c8d1d8') {
    if (value == null || !Number.isFinite(Number(value))) return fallback;
    const n = Number(value);
    for (let i = 0; i < breaks.length; i++) {
      if (n <= breaks[i]) return palette[i];
    }
    return palette[palette.length - 1];
  }

  function pointInRing(lon, lat, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = Number(ring[i][0]);
      const yi = Number(ring[i][1]);
      const xj = Number(ring[j][0]);
      const yj = Number(ring[j][1]);
      const hit =
        (yi > lat) !== (yj > lat) &&
        lon < ((xj - xi) * (lat - yi)) / ((yj - yi) || 1e-12) + xi;
      if (hit) inside = !inside;
    }
    return inside;
  }

  function pointInPolygon(lon, lat, polygon) {
    if (!polygon?.length || !pointInRing(lon, lat, polygon[0])) return false;
    for (let i = 1; i < polygon.length; i++) {
      if (pointInRing(lon, lat, polygon[i])) return false;
    }
    return true;
  }

  function pointInGeometry(lon, lat, geometry) {
    if (!geometry) return false;
    if (geometry.type === 'Polygon') {
      return pointInPolygon(lon, lat, geometry.coordinates);
    }
    if (geometry.type === 'MultiPolygon') {
      return geometry.coordinates.some((polygon) => pointInPolygon(lon, lat, polygon));
    }
    return false;
  }

  function percentile(value, values) {
    const clean = values.map(Number).filter(Number.isFinite).sort((a, b) => a - b);
    const n = Number(value);
    if (!clean.length || !Number.isFinite(n)) return 50;
    let below = 0;
    let equal = 0;
    for (const x of clean) {
      if (x < n) below += 1;
      else if (x === n) equal += 1;
    }
    return Math.max(1, Math.min(99, Math.round((100 * (below + equal * 0.5)) / clean.length)));
  }

  function riskLabel(percentileValue) {
    const p = Number(percentileValue);
    if (p <= 14) return { text: '极低', cls: 'low' };
    if (p <= 29) return { text: '较低', cls: 'low' };
    if (p <= 43) return { text: '偏低', cls: 'low' };
    if (p <= 57) return { text: '中等', cls: 'mid' };
    if (p <= 71) return { text: '偏高', cls: 'high' };
    if (p <= 86) return { text: '较高', cls: 'high' };
    return { text: '极高', cls: 'high' };
  }

  function quantileBreaks(values, bins = 7) {
    const clean = values.map(Number).filter(Number.isFinite).sort((a, b) => a - b);
    if (!clean.length) return Array.from({ length: Math.max(1, bins - 1) }, () => 0);
    const breaks = [];
    for (let i = 1; i < bins; i++) {
      const p = i / bins;
      const pos = (clean.length - 1) * p;
      const lo = Math.floor(pos);
      const hi = Math.min(lo + 1, clean.length - 1);
      const f = pos - lo;
      breaks.push(Math.round((clean[lo] * (1 - f) + clean[hi] * f) * 10) / 10);
    }
    return breaks;
  }

  window.CrimeMapUtils = Object.freeze({
    scaleColor,
    pointInRing,
    pointInPolygon,
    pointInGeometry,
    percentile,
    riskLabel,
    quantileBreaks,
  });
})();
