"""Generate per-room occupation files from normalized schedules."""
from __future__ import annotations

import argparse
import json
import os
import re
from typing import Iterable

SCHEDULE_ROOT = "schedules"
OUTPUT_ROOT = "аудиторії"


def roman_to_int(s: str) -> int:
    roman = {
        "I": 1,
        "V": 5,
        "X": 10,
        "L": 50,
        "C": 100,
        "D": 500,
        "M": 1000,
    }
    prev = 0
    total = 0
    for char in reversed(s.upper()):
        value = roman.get(char, 0)
        if value < prev:
            total -= value
        else:
            total += value
            prev = value
    return total


def parse_room_info(room_str):
    """Extract building, floor, room from strings like '804а V н.к.'"""
    match = re.match(r"(?P<room>\d{3}[а-яa-z]?)\s+(?P<building>[IVXLСНІМК]+)\sн\.к\.\s*", room_str.strip(), re.IGNORECASE)
    if not match:
        return None
    room = match.group("room")
    building_roman = match.group("building").upper()
    building = roman_to_int(building_roman)
    floor = room[0]
    return str(building), str(floor), room


def iter_schedule_files(root: str = SCHEDULE_ROOT):
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if not name.endswith("_schedule.json"):
                continue
            yield os.path.join(dirpath, name)


def load_schedule(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def append_record(path: str, record: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = []
    data.append(record)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clear_generated_rooms(root: str = OUTPUT_ROOT):
    removed = 0
    if not os.path.exists(root):
        return removed
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if not name.endswith(".json"):
                continue
            os.remove(os.path.join(dirpath, name))
            removed += 1
    return removed


def process_schedule(path: str):
    group_code = os.path.basename(path).replace("_schedule.json", "")
    schedule = load_schedule(path)
    for entry in schedule:
        room_str = entry.get("Аудиторія", "")
        parsed = parse_room_info(room_str)
        if not parsed:
            continue
        building, floor, room = parsed
        record = {
            "День": entry.get("День"),
            "Пара": entry.get("Пара"),
            "Група": group_code,
            "Предмет": entry.get("Предмет"),
            "Викладач": entry.get("Викладач"),
            "Тип заняття": entry.get("Тип заняття"),
            "Тип тижня": entry.get("Тип тижня", "постійно"),
        }
        append_record(os.path.join(OUTPUT_ROOT, building, floor, f"{room}.json"), record)


def main():
    parser = argparse.ArgumentParser(description="Generate room occupancy files from schedules.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete existing room JSON files in output directory before regeneration.",
    )
    args = parser.parse_args()

    if args.force:
        removed = clear_generated_rooms(OUTPUT_ROOT)
        print(f"🧹 removed {removed} existing room files")

    for schedule_path in iter_schedule_files():
        process_schedule(schedule_path)
        print(f"✅ processed {schedule_path}")


if __name__ == "__main__":
    main()
