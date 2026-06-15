"""Generate per-room exam occupation files from downloaded exam schedules."""

from __future__ import annotations

import argparse
import json
import logging
import os
from typing import Iterable

from generate_room_status import parse_room_info

SCHEDULE_ROOT = "schedules_exam"
OUTPUT_ROOT = "аудиторії_exam"

logger = logging.getLogger(__name__)


def _clear_exam_rooms() -> int:
    removed = 0
    if not os.path.exists(OUTPUT_ROOT):
        return removed
    for dirpath, _dirnames, filenames in os.walk(OUTPUT_ROOT):
        for name in filenames:
            if not name.endswith(".json"):
                continue
            try:
                os.remove(os.path.join(dirpath, name))
                removed += 1
            except OSError as exc:
                logger.error("Failed to remove %s: %s", name, exc)
    return removed


def iter_exam_files(root: str = SCHEDULE_ROOT) -> Iterable[str]:
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if not name.endswith("_exam.json"):
                continue
            yield os.path.join(dirpath, name)


def load_schedule(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Corrupted exam schedule file {path!r}: {exc}") from exc


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


def process_exam_schedule(path: str) -> tuple[int, int]:
    group_code = os.path.basename(path).replace("_exam.json", "")
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
            "Дата": entry.get("Дата"),
            "День": entry.get("День"),
            "Пара": entry.get("Пара"),
            "Група": group_code,
            "Предмет": entry.get("Предмет"),
            "Викладач": entry.get("Викладач"),
            "Тип заняття": entry.get("Тип заняття", "Екзамен"),
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
        description="Generate room exam occupancy files from exam schedules."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete existing exam room JSON files before regeneration.",
    )
    args = parser.parse_args()

    if args.force:
        removed = _clear_exam_rooms()
        logger.info("Removed %d existing exam room files", removed)

    total_processed = 0
    total_skipped = 0

    for exam_path in iter_exam_files():
        processed, skipped = process_exam_schedule(exam_path)
        total_processed += processed
        total_skipped += skipped
        if processed:
            logger.info(
                "Processed %s (%d entries, %d skipped)", exam_path, processed, skipped
            )

    logger.info(
        "Done — entries written: %d, skipped (unparseable room): %d",
        total_processed,
        total_skipped,
    )


if __name__ == "__main__":
    main()
