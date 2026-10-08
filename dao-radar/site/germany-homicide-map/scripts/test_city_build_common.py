#!/usr/bin/env python3
"""Local, network-free contract test for deterministic city GeoJSON publishing."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from city_build_common import write_geojson


def main() -> None:
    with TemporaryDirectory() as tmp:
        target = Path(tmp) / "city.geojson"
        first = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "id": "test-001",
                "properties": {"name": "München", "crime_total": {"cases": 2, "rate": 10.5}},
                "geometry": {"type": "Polygon", "coordinates": []}
            }]
        }
        assert write_geojson(target, first) is True
        original = target.read_bytes()
        original_mtime = target.stat().st_mtime_ns
        assert write_geojson(target, first) is False, "identical data should not be republished"
        assert target.read_bytes() == original
        assert target.stat().st_mtime_ns == original_mtime
        assert json.loads(original)["features"][0]["properties"]["name"] == "München"

        changed = {**first, "features": [{**first["features"][0], "id": "test-002"}]}
        assert write_geojson(target, changed) is True
        assert json.loads(target.read_text(encoding="utf-8"))["features"][0]["id"] == "test-002"
    print("[city-build-common] PASS: UTF-8, deterministic no-op, atomic content replacement")


if __name__ == "__main__":
    main()
