#!/usr/bin/env python3
"""Shared, deterministic I/O for annual official city-crime datasets.

Keep parsing, census population joins, and municipality-specific rules in each
builder. This module only normalizes transport and JSON file publication.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import requests

HEADERS = {
    "User-Agent": "GermanyCrimeMonitor/1.0 (+https://github.com/1959124923wyz-sys/-1)"
}


def download_bytes(url: str, params: dict | None = None, timeout: int = 120) -> bytes:
    response = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.content


def download_json(url: str, params: dict | None = None, timeout: int = 120) -> Any:
    return json.loads(download_bytes(url, params=params, timeout=timeout))


def download_text(url: str, params: dict | None = None, timeout: int = 120) -> str:
    content = download_bytes(url, params=params, timeout=timeout)
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def write_geojson(path: str | Path, data: dict) -> bool:
    """Publish atomically; do not rewrite a GeoJSON when bytes are unchanged."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"
    if dest.exists() and dest.read_text(encoding="utf-8") == content:
        return False

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=dest.parent, prefix="." + dest.name + ".",
            suffix=".tmp", delete=False
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(content)
        os.replace(temp_path, dest)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    return True
