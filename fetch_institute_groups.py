"""Fetch group lists per institute via timetable proxy and cache to disk."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

import requests

from institutes import INSTITUTES

PROXY_BASE = "https://timetable-proxy-production.up.railway.app/institutes"
CACHE_DIR = Path("groups_cache")
CACHE_DIR.mkdir(exist_ok=True)


def fetch_groups(institute: str) -> List[str]:
    url = f"{PROXY_BASE}/{institute}/groups"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError(f"Unexpected response for {institute}: {data}")
    return data


def cache_groups(institute: str, groups: List[str]):
    path = CACHE_DIR / f"{institute}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(groups, f, ensure_ascii=False, indent=2)
    return path


def load_cached(institute: str) -> List[str]:
    path = CACHE_DIR / f"{institute}.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return []


def main():
    for inst in INSTITUTES:
        try:
            groups = fetch_groups(inst)
            cache_groups(inst, groups)
            print(f"✅ {inst}: {len(groups)} груп")
        except Exception as exc:
            cached = load_cached(inst)
            if cached:
                print(f"⚠️ {inst}: помилка {exc}, використовую кеш ({len(cached)})")
            else:
                print(f"❌ {inst}: {exc}")


if __name__ == "__main__":
    main()
