#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "city_layers.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build registered Germany city detail layers.")
    parser.add_argument(
        "--city",
        action="append",
        default=[],
        help="Build only the given city id. May be passed multiple times.",
    )
    args = parser.parse_args()

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    wanted = set(args.city)
    selected = []
    seen_builders: set[str] = set()

    for city in registry.get("cities", []):
        cid = city.get("id")
        builder = city.get("builder")
        if wanted and cid not in wanted:
            continue
        if not builder:
            print(f"[city-build] {cid}: no builder declared; preserve existing data")
            continue
        if builder in seen_builders:
            continue

        path = ROOT / builder
        if not path.is_file():
            raise SystemExit(f"[city-build] {cid}: builder missing: {builder}")

        seen_builders.add(builder)
        selected.append((cid, path))

    if wanted:
        known = {city.get("id") for city in registry.get("cities", [])}
        missing = sorted(wanted - known)
        if missing:
            raise SystemExit(f"[city-build] unknown city id(s): {', '.join(missing)}")

    if not selected:
        print("[city-build] nothing to build")
        return

    for cid, path in selected:
        rel = path.relative_to(ROOT)
        print(f"[city-build] {cid}: {rel}", flush=True)
        subprocess.run([sys.executable, str(path)], cwd=ROOT, check=True)

    print(f"[city-build] OK: {len(selected)} builder(s)")


if __name__ == "__main__":
    main()
