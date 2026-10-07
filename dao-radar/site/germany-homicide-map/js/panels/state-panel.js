(() => {
  function create({
    elements,
    map,
    getMode,
    getStats,
    getMetricLabel,
    onCountySelect,
    onNewsSelect,
    onStateChanged,
    formatNumber,
    formatDate,
    escapeHtml,
  }) {
    let selectedName = null;
    let filterName = null;
    let returnView = null;

    function render(feature) {
      if (!feature) return;
      const s = getStats(feature);
      const label = getMetricLabel(s.key);

      elements.stateName.textContent = s.name;
      elements.stateMetric.textContent = 'BKA PKS 2025 · ' + label;
      elements.stateRate.textContent = formatNumber(Math.round(s.rate));
      elements.stateCases.textContent = formatNumber(s.cases);
      elements.stateRank.textContent = '#' + s.rank;
      elements.stateRecent.textContent = formatNumber(s.news.length);

      elements.stateTopCounties.innerHTML = '';
      for (const row of s.topCounties) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'state-county-row';
        button.innerHTML =
          '<span>' + escapeHtml(row.name) + '</span><b>' +
          formatNumber(Math.round(row[s.key].rate)) +
          '</b>';
        button.onclick = () => onCountySelect(row, s.key);
        elements.stateTopCounties.appendChild(button);
      }

      elements.stateNewsCount.textContent = s.news.length
        ? formatNumber(s.news.length) + ' 起'
        : '';
      elements.stateNews.innerHTML = '';

      if (!s.news.length) {
        elements.stateNews.innerHTML =
          '<div class="state-empty">当前公开抓取暂无匹配通报；不代表没有案件。</div>';
      } else {
        for (const item of s.news.slice(0, 6)) {
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'state-news-row';
          button.innerHTML =
            '<span>' +
            escapeHtml(item.city || s.name) +
            ' · ' +
            escapeHtml(item.offense || item.category_label || '事件') +
            '</span><small>' +
            formatDate(item.event_date) +
            '</small>';
          button.onclick = () => onNewsSelect(item);
          elements.stateNews.appendChild(button);
        }
      }

      elements.stateDrawer.classList.add('open');
    }

    function select(feature) {
      if (!elements.stateDrawer.classList.contains('open')) {
        returnView = { center: map.getCenter(), zoom: map.getZoom() };
      }
      selectedName = feature?.properties?.name || null;
      filterName = selectedName;
      render(feature);
      onStateChanged?.();
    }

    function close({ restore = true } = {}) {
      selectedName = null;
      filterName = null;
      elements.stateDrawer.classList.remove('open');

      const view = returnView;
      returnView = null;
      onStateChanged?.();

      if (restore && view) {
        map.setView(view.center, view.zoom, { animate: true });
      }
    }

    function reset() {
      selectedName = null;
      filterName = null;
      returnView = null;
      elements.stateDrawer.classList.remove('open');
      onStateChanged?.();
    }

    return Object.freeze({
      render,
      select,
      close,
      reset,
      get selectedName() { return selectedName; },
      get filterName() { return filterName; },
      get isOpen() { return elements.stateDrawer.classList.contains('open'); },
    });
  }

  window.CrimeStatePanel = Object.freeze({ create });
})();
