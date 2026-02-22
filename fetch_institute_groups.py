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
SUMMARY_PATH = os.environ.get("LPNU_GROUPS_FETCH_SUMMARY_PATH", "").strip()


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
    results = []
    for inst in INSTITUTES:
        try:
            groups = fetch_groups(inst)
            cache_groups(inst, groups)
            print(f"✅ {inst}: {len(groups)} груп")
            results.append({
                "institute": inst,
                "status": "ok",
                "groups_count": len(groups),
                "used_cache": False,
            })
        except Exception as exc:
            cached = load_cached(inst)
            if cached:
                print(f"⚠️ {inst}: помилка {exc}, використовую кеш ({len(cached)})")
                results.append({
                    "institute": inst,
                    "status": "cache_fallback",
                    "groups_count": len(cached),
                    "used_cache": True,
                    "error": str(exc),
                })
            else:
                print(f"❌ {inst}: {exc}")
                results.append({
                    "institute": inst,
                    "status": "failed",
                    "groups_count": 0,
                    "used_cache": False,
                    "error": str(exc),
                })

    if SUMMARY_PATH:
        payload = {
            "processed_institutes_count": len(results),
            "institutes": results,
            "failed_institutes": [r["institute"] for r in results if r["status"] == "failed"],
        }
        with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
