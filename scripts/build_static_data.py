#!/usr/bin/env python3
"""Build static data assets for hosting.

Inputs:
- ./аудиторії/<building>/<floor>/<room>.json

Outputs:
- ./data/index.json
- ./data/floors/<building>/<floor>.json
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ROOM_SOURCE_DIR = ROOT / "аудиторії"
DATA_DIR = ROOT / "data"
FLOORS_DIR = DATA_DIR / "floors"
INDEX_PATH = DATA_DIR / "index.json"


def natural_sort_key(value: str):
    parts = []
    current = ""
    for ch in value:
        if ch.isdigit():
            current += ch
        else:
            if current:
                parts.append(int(current))
                current = ""
            parts.append(ch)
    if current:
        parts.append(int(current))
    return parts


def sorted_dirs(path: Path):
    return sorted((item for item in path.iterdir() if item.is_dir()), key=lambda p: natural_sort_key(p.name))


def sorted_room_files(path: Path):
    files = [item for item in path.iterdir() if item.is_file() and item.suffix == ".json"]
    return sorted(files, key=lambda p: natural_sort_key(p.stem))


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))


def build() -> None:
    if not ROOM_SOURCE_DIR.exists():
        raise FileNotFoundError(f"Missing source directory: {ROOM_SOURCE_DIR}")

    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    FLOORS_DIR.mkdir(parents=True, exist_ok=True)

    buildings_payload = []
    total_floors = 0
    total_rooms = 0

    for building_dir in sorted_dirs(ROOM_SOURCE_DIR):
        floors_payload = []
        building_room_count = 0

        for floor_dir in sorted_dirs(building_dir):
            room_files = sorted_room_files(floor_dir)
            if not room_files:
                continue

            rooms_payload = []
            rooms_map = {}

            for room_file in room_files:
                room_id = room_file.stem
                rooms_payload.append(room_id)
                rooms_map[room_id] = load_json(room_file)

            floor_payload = {
                "building": building_dir.name,
                "floor": floor_dir.name,
                "rooms": rooms_map,
            }
            write_json(FLOORS_DIR / building_dir.name / f"{floor_dir.name}.json", floor_payload)

            floors_payload.append(
                {
                    "id": floor_dir.name,
                    "rooms": rooms_payload,
                }
            )
            building_room_count += len(rooms_payload)
            total_rooms += len(rooms_payload)
            total_floors += 1

        if floors_payload:
            buildings_payload.append(
                {
                    "id": building_dir.name,
                    "floors": floors_payload,
                    "roomCount": building_room_count,
                }
            )

    index_payload = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "buildings": buildings_payload,
        "totals": {
            "buildings": len(buildings_payload),
            "floors": total_floors,
            "rooms": total_rooms,
        },
    }
    write_json(INDEX_PATH, index_payload)

    print(f"Built {INDEX_PATH.relative_to(ROOT)}")
    print(f"Buildings: {index_payload['totals']['buildings']}")
    print(f"Floors: {index_payload['totals']['floors']}")
    print(f"Rooms: {index_payload['totals']['rooms']}")


if __name__ == "__main__":
    build()
