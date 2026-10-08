#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "city_layers.json"


def fail(msg: str) -> None:
    raise SystemExit(f"[city-layers] {msg}")


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def iter_vertices(node):
    """Yield [longitude, latitude] vertices from Polygon/MultiPolygon trees."""
    if isinstance(node, list) and len(node) >= 2 and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in node[:2]
    ):
        yield float(node[0]), float(node[1])
    elif isinstance(node, list):
        for child in node:
            yield from iter_vertices(child)


def validate_city_coordinates(cid: str, features: list, bounds: list) -> tuple:
    # Configured bounds cover the town; a small buffer allows official coastal
    # islands/outlying geometry but rejects projected metre-based CRS entirely.
    (south, west), (north, east) = bounds
    buffer_degrees = 0.5
    extent = [float("inf"), float("inf"), float("-inf"), float("-inf")]
    count = 0
    for feature in features:
        geometry = feature.get("geometry") or {}
        for lon, lat in iter_vertices(geometry.get("coordinates")):
            if not (math.isfinite(lon) and math.isfinite(lat)):
                fail(f"{cid}: non-finite coordinate in {feature.get('id')}")
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                fail(
                    f"{cid}: coordinate {lon}, {lat} is not EPSG:4326 longitude/latitude; "
                    "source CRS must be reprojected before publishing"
                )
            if not (
                west - buffer_degrees <= lon <= east + buffer_degrees
                and south - buffer_degrees <= lat <= north + buffer_degrees
            ):
                fail(
                    f"{cid}: feature {feature.get('id')} coordinate {lon}, {lat} "
                    f"is outside city region {bounds}; check CRS and geometry join"
                )
            extent[0] = min(extent[0], lon)
            extent[1] = min(extent[1], lat)
            extent[2] = max(extent[2], lon)
            extent[3] = max(extent[3], lat)
            count += 1

    if count < len(features) * 4:
        fail(f"{cid}: insufficient polygon coordinate vertices ({count})")
    if extent[2] < west or extent[0] > east or extent[3] < south or extent[1] > north:
        fail(f"{cid}: geographic layer does not overlap its registered bounds")
    return tuple(round(value, 5) for value in extent)


def main() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if registry.get("schema_version") != 1:
        fail(f"unsupported schema_version={registry.get('schema_version')!r}")

    cities = registry.get("cities")
    if not isinstance(cities, list) or not cities:
        fail("registry must contain a non-empty cities array")

    seen_ids: set[str] = set()
    seen_names: set[str] = set()

    for city in cities:
        cid = city.get("id")
        name = city.get("name")
        if not cid or cid in seen_ids:
            fail(f"invalid/duplicate city id: {cid!r}")
        if not name or name in seen_names:
            fail(f"invalid/duplicate city name: {name!r}")
        seen_ids.add(cid)
        seen_names.add(name)

        bounds = city.get("bounds")
        if (
            not isinstance(bounds, list)
            or len(bounds) != 2
            or any(not isinstance(p, list) or len(p) != 2 for p in bounds)
        ):
            fail(f"{cid}: bounds must be [[south,west],[north,east]]")

        data_path = ROOT / str(city.get("file", ""))
        if not data_path.is_file():
            fail(f"{cid}: missing data file {data_path.relative_to(ROOT)}")

        builder = city.get("builder")
        if builder:
            builder_path = ROOT / str(builder)
            if not builder_path.is_file():
                fail(f"{cid}: missing builder {builder}")

        metrics = city.get("metrics")
        if not isinstance(metrics, dict) or not metrics:
            fail(f"{cid}: no metrics configured")

        geo = json.loads(data_path.read_text(encoding="utf-8"))
        if geo.get("type") != "FeatureCollection":
            fail(f"{cid}: {data_path.name} is not a FeatureCollection")
        features = geo.get("features")
        if not isinstance(features, list) or not features:
            fail(f"{cid}: {data_path.name} has no features")

        ids: set[str] = set()
        for feature in features:
            fid = str(feature.get("id", ""))
            if fid:
                if fid in ids:
                    fail(f"{cid}: duplicate feature id {fid}")
                ids.add(fid)
            geometry = feature.get("geometry") or {}
            if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
                fail(f"{cid}: unsupported geometry type {geometry.get('type')!r}")

        extent = validate_city_coordinates(cid, features, bounds)

        for public_key, cfg in metrics.items():
            field = (cfg or {}).get("field")
            if not field:
                fail(f"{cid}:{public_key}: missing field")
            present = 0
            valid_rates = 0
            for feature in features:
                value = (feature.get("properties") or {}).get(field)
                if isinstance(value, dict):
                    present += 1
                    if is_number(value.get("rate")):
                        valid_rates += 1
            if present == 0:
                fail(f"{cid}:{public_key}: field {field!r} absent from all features")
            if valid_rates == 0:
                fail(f"{cid}:{public_key}: field {field!r} has no numeric rates")

        print(
            f"[city-layers] {cid}: {len(features)} polygons, "
            f"{len(metrics)} exposed metrics, extent={extent}, source={city.get('source_label', 'n/a')}"
        )

    print(f"[city-layers] OK: {len(cities)} registered city layers")


if __name__ == "__main__":
    main()
