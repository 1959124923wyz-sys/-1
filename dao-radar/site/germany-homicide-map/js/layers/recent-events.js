(() => {
  function create({
    map,
    pane = 'newsPane',
    listElement,
    titleElement,
    categories,
    formatNumber,
    formatDate,
    escapeHtml,
    safeUrl,
  }) {
    const layer = L.layerGroup().addTo(map);
    const markers = new Map();

    function markerFor(item) {
      const meta = categories[item.category] || {
        label: item.category,
        color: '#667',
      };
      const foundLocation = String(item.location_type || '').includes('Fundort');
      const suspected = item.status === 'suspected';

      return L.circleMarker([item.lat, item.lon], {
        pane,
        radius: item.category === 'homicide' ? 7.5 : item.category === 'property' ? 4.5 : 6.2,
        weight: foundLocation ? 3 : suspected ? 2.2 : 1.5,
        color: foundLocation ? '#fff' : meta.color,
        dashArray: suspected && !foundLocation ? '3 2' : null,
        fillColor: meta.color,
        fillOpacity: suspected ? 0.55 : 0.92,
      });
    }

    function popupHtml(item) {
      const meta = categories[item.category] || { label: item.category };
      return (
        '<h3>' +
        escapeHtml(item.city) +
        ' · ' +
        formatDate(item.event_date) +
        '</h3><p><b>' +
        escapeHtml(meta.label) +
        '</b> · ' +
        escapeHtml(item.offense || '') +
        ' · ' +
        escapeHtml(item.status || '') +
        '</p><p>' +
        escapeHtml(item.location || '') +
        '</p><p>' +
        escapeHtml(item.summary || '') +
        '</p><p><a target="_blank" rel="noopener noreferrer" href="' +
        escapeHtml(safeUrl(item.source_url)) +
        '">查看原始通报 ↗</a></p>'
      );
    }

    function open(item, { minZoom = 11, duration = 0.55 } = {}) {
      const marker = markers.get(item.id);
      if (marker) {
        map.flyTo(marker.getLatLng(), Math.max(map.getZoom(), minZoom), { duration });
        marker.openPopup();
      } else {
        window.open(safeUrl(item.source_url), '_blank', 'noopener');
      }
    }

    function render(items, { titlePrefix = '' } = {}) {
      layer.clearLayers();
      markers.clear();
      listElement.innerHTML = '';

      const rows = items
        .slice()
        .sort(
          (a, b) =>
            String(b.event_date).localeCompare(String(a.event_date)) ||
            String(a.city).localeCompare(String(b.city))
        );

      for (const item of rows) {
        if (Number.isFinite(item.lat) && Number.isFinite(item.lon)) {
          const marker = markerFor(item)
            .bindPopup(popupHtml(item), { maxWidth: 360 })
            .addTo(layer);
          markers.set(item.id, marker);
        }

        const meta = categories[item.category] || { label: item.category };
        const button = document.createElement('button');
        button.className = 'card';
        button.innerHTML =
          '<div class="cardtop"><b>' +
          escapeHtml(item.city) +
          ' · ' +
          formatDate(item.event_date) +
          '</b><span class="badges"><span class="badge ' +
          escapeHtml(item.category) +
          '">' +
          escapeHtml(meta.label) +
          '</span><span class="badge status">' +
          escapeHtml(item.status || '') +
          '</span></span></div><div class="cardmeta">' +
          escapeHtml(item.location || '') +
          '</div><div class="cardsum">' +
          escapeHtml(item.summary || '') +
          '</div>';
        button.onclick = () => open(item);
        listElement.appendChild(button);
      }

      if (!rows.length) {
        listElement.innerHTML = '<div class="mode-note">当前筛选没有公开通报点。</div>';
      }

      titleElement.textContent =
        (titlePrefix ? titlePrefix + ' · ' : '') +
        '近90天公开通报（' +
        formatNumber(rows.length) +
        '）· 次要参考';

      return rows;
    }

    return Object.freeze({
      render,
      open,
      get layer() { return layer; },
      get markers() { return markers; },
    });
  }

  window.CrimeRecentEvents = Object.freeze({ create });
})();
