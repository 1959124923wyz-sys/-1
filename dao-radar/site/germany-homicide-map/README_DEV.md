# Germany Crime Map – Developer Guide

This directory powers the public Germany crime map. The current goal is to keep the map visually simple while the implementation remains modular enough to add or replace official data sources without editing unrelated code.

## Runtime architecture

```text
index.html                      thin page shell
css/map.css                     all map UI styling
js/app.js                       startup, orchestration and UI event wiring
js/core/config.js               metric labels, categories and palettes
js/core/geo-stats.js            shared geometry / quantile helpers
js/core/data-model.js           aggregation and case-matching logic
js/panels/state-panel.js        state drawer rendering / selection state
js/panels/area-panel.js         area data and national summary cards
js/panels/drawer-drag.js        reusable draggable panel behavior
js/layers/berlin-detail.js      Berlin-specific annual + rolling local layers
js/layers/county-layer.js       national county boundaries and choropleth
js/layers/state-layer.js        federal state borders and selection
js/layers/city-detail.js        generic registry-driven city detail loader
js/layers/recent-events.js      recent police-publication markers
js/layers/recent-events.js      rolling report markers and list rendering
data/city_layers.json           city layer + builder registry
data/*.geojson / *.json         generated runtime datasets
scripts/build_city_layers.py    registry-driven annual city build orchestrator
scripts/city_build_common.py    shared HTTP download and atomic deterministic GeoJSON I/O
scripts/*.py                    source adapters, updaters and validators
```

The public page should not contain large inline CSS or JavaScript blocks. New city detail layers should normally be added through `data/city_layers.json` and a generated GeoJSON file, not by adding city-specific branches to `index.html`.

## Data-layer hierarchy

The map deliberately separates spatial/data levels:

1. **National** – BKA PKS 2025, Kreis / kreisfreie Stadt.
2. **State** – state outline and aggregate view; used for hover/click navigation.
3. **City detail** – official Stadtteil / Stadtbezirk / Planungsraum data where a current compatible source exists.
4. **Recent reports** – rolling public police/news reports; supplemental only and never treated as total crime.

When a city detail layer is active, the underlying national polygon for that city should visually retreat so boundaries and fills never compete.

## Metric rules

Public metric keys are stable UI concepts:

```text
violence
serious_injury
robbery
sexual
homicide

property_total
burglary
bicycle_theft
vehicle_theft
theft_from_vehicle
```

A city may expose only the subset supported by its official source. If a local source uses a proxy rather than the same BKA definition, put the explanation in that metric's `note` field. Never silently present a proxy as an identical definition.

## Adding a city detail layer

1. Create a deterministic builder such as `scripts/build_<city>_local_2025.py`. Annual builders must not embed the current wall-clock time in output; identical source data should produce identical files. Use `city_build_common.py` for official downloads and atomic output writing; do not duplicate HTTP and JSON publishing boilerplate.
2. Generate a GeoJSON FeatureCollection into `data/<city>_local_2025.geojson`.
3. Each feature should have a stable `id`, Polygon/MultiPolygon geometry, `properties.name`, and metric objects such as:
   ```json
   "property_total": {
     "cases": 1234,
     "rate": 2456.7
   }
   ```
4. Register the layer in `data/city_layers.json` with:
   - `builder`
   - bounds
   - minimum zoom
   - source label
   - public metric → GeoJSON field mapping
5. Run:
   ```bash
   python scripts/build_city_layers.py --city <city-id>
   python scripts/validate_city_layers.py
   node --check js/app.js
   node --check js/layers/city-detail.js
   ```

The generic city loader will create the jump button, detect the city by map extent, render the choropleth, show tooltips, and populate the existing side panel.

## Files that should remain stable

- `index.html`: HTML structure only.
- `js/app.js`: orchestration only; map layers and area UI should stay in their own modules.
- `js/layers/county-layer.js`: nationwide geography and click/hover selection.
- `js/layers/state-layer.js`: federal state boundaries and selection.
- `js/panels/area-panel.js`: current-area and national-aggregate card.
- `js/layers/berlin-detail.js`: Berlin-only behavior.
- `js/layers/city-detail.js`: generic city detail behavior.
- `data/city_layers.json`: declarative city/data-builder registry.

Avoid putting source-specific scraping/parsing logic in browser JavaScript.

## Build and update responsibilities

- `build_*.py`: annual or reproducible official baseline datasets.
- `update_*.py`: rolling/recent datasets.
- `validate_*.py`: invariants and schema/data checks.
- one-off probes should not have permanent push-triggered workflows once the production builder exists.

The main workflow runs one registry-driven city build step, validates JavaScript and registry/data consistency, runs rolling-data validators/updaters, commits only changed generated data, and deploys Pages. Static annual builders are deterministic so a no-change rebuild does not create a new commit. A Playwright smoke workflow also tests national hover/click, state close/reopen, Berlin mode switching and Hamburg lazy detail loading.

## Data integrity principles

- Do not mix annual PKS data with rolling 90-day reports as if they have one denominator.
- `0` public reports does not mean `0` crimes.
- Crime counts are cases unless a source explicitly supplies victims.
- Prefer rates per 100,000 for national/city structural comparisons.
- Use official local geometry for city detail layers; do not approximate a district boundary from point density.
- If a source fails, preserve the last known good generated file rather than replacing it with empty data.

## Current city-detail sources

The registry is authoritative for Hamburg, Munich and the supported Saxony cities. Berlin remains the only dedicated city path because it combines two different local datasets: an annual violence layer and a rolling 90-day property layer with its own Planungsraum mapping.
