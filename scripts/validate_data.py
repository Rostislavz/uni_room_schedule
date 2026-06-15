#!/usr/bin/env python3
"""Pre-publish data validation.

Validates the generated data/ directory before it is pushed to gh_pages.
Exits with code 1 if any check fails, so the CI pipeline aborts the publish step.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "data" / "index.json"
FLOORS_DIR = ROOT / "data" / "floors"

MIN_ROOMS = 100
MIN_BUILDINGS = 3

logger = logging.getLogger(__name__)


def load_index() -> dict:
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"index.json not found at {INDEX_PATH}")
    with INDEX_PATH.open(encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"index.json is not valid JSON: {exc}") from exc


def validate(index: dict) -> list[str]:
    errors: list[str] = []

    # Schema version present
    if "version" not in index:
        errors.append("index.json missing 'version' field")

    # Buildings present
    buildings = index.get("buildings", [])
    if not isinstance(buildings, list) or len(buildings) < MIN_BUILDINGS:
        errors.append(
            f"Expected at least {MIN_BUILDINGS} buildings, got {len(buildings)}"
        )

    # Room count
    totals = index.get("totals", {})
    room_count = totals.get("rooms", 0)
    if room_count < MIN_ROOMS:
        errors.append(
            f"Expected at least {MIN_ROOMS} rooms in totals, got {room_count}"
        )

    # Floor JSON files exist for every declared floor
    for building in buildings:
        b_id = building.get("id", "?")
        for floor in building.get("floors", []):
            f_id = floor.get("id", "?")
            floor_path = FLOORS_DIR / b_id / f"{f_id}.json"
            if not floor_path.exists():
                errors.append(f"Missing floor file: {floor_path.relative_to(ROOT)}")
            else:
                try:
                    with floor_path.open(encoding="utf-8") as fh:
                        json.load(fh)
                except json.JSONDecodeError as exc:
                    errors.append(
                        f"Corrupt floor file {floor_path.relative_to(ROOT)}: {exc}"
                    )

    return errors


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        index = load_index()
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Validation failed: %s", exc)
        return 1

    errors = validate(index)
    if errors:
        logger.error("Data validation failed with %d error(s):", len(errors))
        for err in errors:
            logger.error("  - %s", err)
        return 1

    totals = index.get("totals", {})
    logger.info(
        "Validation passed — buildings: %d, floors: %d, rooms: %d",
        totals.get("buildings", 0),
        totals.get("floors", 0),
        totals.get("rooms", 0),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
