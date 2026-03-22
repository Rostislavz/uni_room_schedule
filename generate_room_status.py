"""Generate per-room occupation files from normalized schedules."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
from typing import Iterable

SCHEDULE_ROOT = "schedules"
OUTPUT_ROOT = "аудиторії"
HASHES_PATH = os.path.join(OUTPUT_ROOT, ".schedule_hashes.json")

logger = logging.getLogger(__name__)


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
    s_upper = s.upper()
    if not s_upper:
        raise ValueError("Empty Roman numeral string")
    invalid = set(s_upper) - set(roman)
    if invalid:
        raise ValueError(f"Invalid Roman numeral characters {invalid!r} in {s!r}")
    prev = 0
    total = 0
    for char in reversed(s_upper):
        value = roman[char]
        if value < prev:
            total -= value
        else:
            total += value
            prev = value
    if total <= 0:
        raise ValueError(f"Roman numeral resolved to non-positive value: {s!r}")
    return total


def parse_room_info(room_str: str):
    """Extract (building, floor, room) from strings like '804а V н.к.'"""
    if not room_str or not room_str.strip():
        return None
    match = re.match(
        r"(?P<room>\d{3}[а-яa-z]?)\s+(?P<building>[IVXLСНІМК]+)\sн\.к\.\s*",
        room_str.strip(),
        re.IGNORECASE,
    )
    if not match:
        logger.debug("Room pattern mismatch: %r", room_str)
        return None
    room = match.group("room")
    building_roman = match.group("building").upper()
    try:
        building = roman_to_int(building_roman)
    except ValueError as exc:
        logger.warning(
            "Cannot parse building numeral %r in %r: %s", building_roman, room_str, exc
        )
        return None
    floor = room[0]
    return str(building), str(floor), room


def _file_hash(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_hashes(path: str = HASHES_PATH) -> dict[str, str]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_hashes(hashes: dict[str, str], path: str = HASHES_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(hashes, f, ensure_ascii=False)


def iter_schedule_files(root: str = SCHEDULE_ROOT) -> Iterable[str]:
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if not name.endswith("_schedule.json"):
                continue
            yield os.path.join(dirpath, name)


def load_schedule(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Corrupted schedule file {path!r}: {exc}") from exc


def append_record(path: str, record: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = []
    except json.JSONDecodeError:
        logger.warning("Corrupted %r — resetting to empty list", path)
        data = []
    data.append(record)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def clear_generated_rooms(root: str = OUTPUT_ROOT) -> int:
    abs_root = os.path.abspath(root)
    abs_expected = os.path.abspath(OUTPUT_ROOT)
    if abs_root == "/" or not abs_root.startswith(abs_expected):
        raise ValueError(
            f"Refusing to clear {abs_root!r} — must be inside {abs_expected!r}"
        )
    removed = 0
    if not os.path.exists(root):
        return removed
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if not name.endswith(".json"):
                continue
            try:
                os.remove(os.path.join(dirpath, name))
                removed += 1
            except OSError as exc:
                logger.error("Failed to remove %s: %s", name, exc)
    return removed


def process_schedule(path: str) -> tuple[int, int]:
    """Process one schedule file. Returns (processed, skipped) counts."""
    group_code = os.path.basename(path).replace("_schedule.json", "")
    try:
        schedule = load_schedule(path)
    except ValueError as exc:
        logger.error("%s", exc)
        return 0, 0

    processed = 0
    skipped = 0
    for entry in schedule:
        room_str = entry.get("Аудиторія", "")
        parsed = parse_room_info(room_str)
        if not parsed:
            if room_str:
                skipped += 1
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
        append_record(
            os.path.join(OUTPUT_ROOT, building, floor, f"{room}.json"), record
        )
        processed += 1
    return processed, skipped


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(
        description="Generate room occupancy files from schedules."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete existing room JSON files in output directory before regeneration.",
    )
    args = parser.parse_args()

    if args.force:
        removed = clear_generated_rooms(OUTPUT_ROOT)
        logger.info("Removed %d existing room files", removed)
        known_hashes: dict[str, str] = {}
    else:
        known_hashes = load_hashes()

    total_processed = 0
    total_skipped = 0
    total_unchanged = 0
    updated_hashes = dict(known_hashes)

    for schedule_path in iter_schedule_files():
        current_hash = _file_hash(schedule_path)
        if not args.force and known_hashes.get(schedule_path) == current_hash:
            total_unchanged += 1
            continue
        processed, skipped = process_schedule(schedule_path)
        total_processed += processed
        total_skipped += skipped
        updated_hashes[schedule_path] = current_hash
        logger.info(
            "Processed %s (%d entries, %d skipped)", schedule_path, processed, skipped
        )

    save_hashes(updated_hashes)
    logger.info(
        "Done — entries written: %d, skipped (unparseable room): %d, unchanged (skipped): %d",
        total_processed,
        total_skipped,
        total_unchanged,
    )


if __name__ == "__main__":
    main()
