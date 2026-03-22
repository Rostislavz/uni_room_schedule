"""Fetch group lists per institute via timetable proxy and cache to disk."""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import List

import requests

from institutes import INSTITUTES

PROXY_BASE = "https://timetable-proxy-production.up.railway.app/institutes"
CACHE_DIR = Path("groups_cache")
CACHE_DIR.mkdir(exist_ok=True)
SUMMARY_PATH = os.environ.get("LPNU_GROUPS_FETCH_SUMMARY_PATH", "").strip()
CACHE_MAX_AGE_DAYS = 7

logger = logging.getLogger(__name__)


def fetch_groups(institute: str) -> List[str]:
    url = f"{PROXY_BASE}/{institute}/groups"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    try:
        data = resp.json()
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON from proxy for {institute!r}: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError(f"Unexpected response type for {institute!r}: {type(data).__name__}")
    return data


def cache_groups(institute: str, groups: List[str]) -> Path:
    path = CACHE_DIR / f"{institute}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(groups, f, ensure_ascii=False, indent=2)
    return path


def load_cached(institute: str) -> List[str]:
    path = CACHE_DIR / f"{institute}.json"
    if not path.exists():
        return []
    age_days = (time.time() - path.stat().st_mtime) / 86400
    if age_days > CACHE_MAX_AGE_DAYS:
        logger.warning(
            "Cache for %r is %.0f days old (limit: %d) — will attempt live fetch",
            institute,
            age_days,
            CACHE_MAX_AGE_DAYS,
        )
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read cache for %r: %s", institute, exc)
        return []


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    results = []
    for inst in INSTITUTES:
        try:
            groups = fetch_groups(inst)
            cache_groups(inst, groups)
            logger.info("%s: %d groups fetched", inst, len(groups))
            results.append({
                "institute": inst,
                "status": "ok",
                "groups_count": len(groups),
                "used_cache": False,
            })
        except Exception as exc:
            cached = load_cached(inst)
            if cached:
                logger.warning("%s: fetch failed (%s), using cache (%d groups)", inst, exc, len(cached))
                results.append({
                    "institute": inst,
                    "status": "cache_fallback",
                    "groups_count": len(cached),
                    "used_cache": True,
                    "error": str(exc),
                })
            else:
                logger.error("%s: fetch failed and no cache available — %s", inst, exc)
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
