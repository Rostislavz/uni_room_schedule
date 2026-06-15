"""Download exam schedules for all groups discovered from LPNU site."""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import json
import logging
import os
from typing import Any, Iterable, NamedTuple

from lpnu_data import get_exam_timetable, TemporaryFetchError
from batch_schedule_downloader import discover_groups

logger = logging.getLogger(__name__)

OUTPUT_ROOT = "schedules_exam"
WORKERS = max(1, int(os.environ.get("LPNU_WORKERS", "6")))
MAX_TEMP_ERRORS_TOTAL = int(os.environ.get("LPNU_MAX_TEMP_ERRORS_TOTAL", "40"))
FORCE_REDOWNLOAD = os.environ.get("LPNU_FORCE_REDOWNLOAD", "0") == "1"
SUMMARY_PATH = os.environ.get("LPNU_EXAM_BATCH_SUMMARY_PATH", "").strip()


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def save_json(path: str, data):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class DownloadResult(NamedTuple):
    group: str
    level: str
    message: str
    is_temp_error: bool = False


def _download_exam_task(group: str) -> DownloadResult:
    path = os.path.join(OUTPUT_ROOT, group, f"{group}_exam.json")
    if os.path.exists(path) and not FORCE_REDOWNLOAD:
        return DownloadResult(group, "skip", f"↩️ {group}: вже існує, пропускаю")

    try:
        schedule = get_exam_timetable(group)
        save_json(path, schedule)
        return DownloadResult(group, "ok", f"✅ {group} → {path}")
    except TemporaryFetchError as exc:
        return DownloadResult(
            group,
            "warn",
            f"⚠️ {group}: тимчасова помилка, пропускаю: {exc}",
            True,
        )
    except ValueError:
        save_json(path, [])
        return DownloadResult(group, "ok", f"✅ {group} → {path} (немає екзаменів)")
    except Exception as exc:
        return DownloadResult(group, "err", f"❌ {group}: {exc}")


def _empty_stats(processed_groups: int = 0) -> dict[str, Any]:
    return {
        "processed_groups": processed_groups,
        "ok": 0,
        "skip": 0,
        "warn": 0,
        "err": 0,
        "failed_fetch_groups": [],
        "failed_update_groups": [],
    }


def _accumulate(stats: dict[str, Any], result: DownloadResult):
    stats[result.level] = stats.get(result.level, 0) + 1
    if result.level == "warn":
        stats["failed_fetch_groups"].append(result.group)
    if result.level == "err":
        stats["failed_update_groups"].append(result.group)


def download_exams(groups: Iterable[str]) -> dict[str, Any]:
    group_list = list(groups)
    stats = _empty_stats(processed_groups=len(group_list))
    if not group_list:
        return stats

    workers = min(WORKERS, len(group_list))
    if workers <= 1:
        temp_errors = 0
        for group in group_list:
            result = _download_exam_task(group)
            _accumulate(stats, result)
            logger.info(result.message)
            if result.is_temp_error:
                temp_errors += 1
                if temp_errors >= MAX_TEMP_ERRORS_TOTAL:
                    logger.warning(
                        "Stopping: accumulated %d temporary errors.", temp_errors
                    )
                    break
            else:
                temp_errors = 0
        return stats

    temp_errors = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending: set[Future[DownloadResult]] = set()
        iterator = iter(group_list)

        for _ in range(workers):
            try:
                group = next(iterator)
            except StopIteration:
                break
            pending.add(pool.submit(_download_exam_task, group))

        stop_submitting = False
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for fut in done:
                result = fut.result()
                _accumulate(stats, result)
                logger.info(result.message)
                if result.is_temp_error:
                    temp_errors += 1
                    if temp_errors >= MAX_TEMP_ERRORS_TOTAL and not stop_submitting:
                        stop_submitting = True
                        logger.warning(
                            "Stopping: accumulated %d temporary errors.", temp_errors
                        )
                else:
                    temp_errors = 0

                if not stop_submitting:
                    try:
                        group = next(iterator)
                    except StopIteration:
                        continue
                    pending.add(pool.submit(_download_exam_task, group))
    return stats


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    institute = os.environ.get("LPNU_INSTITUTE", "All")
    semester = os.environ.get("LPNU_SEMESTER", "2")

    groups = discover_groups(institute=institute, semester=semester)
    if not groups:
        logger.error("No groups found for exam schedule download")
        return

    logger.info("Downloading exam schedules for %d groups", len(groups))
    stats = download_exams(groups)

    logger.info(
        "Done — ok: %d, skip: %d, warn: %d, err: %d",
        stats["ok"],
        stats["skip"],
        stats["warn"],
        stats["err"],
    )

    if SUMMARY_PATH:
        with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
