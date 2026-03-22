"""Download schedules for all groups discovered from LPNU site."""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import json
import logging
import os
from typing import Any, Iterable, NamedTuple

from lpnu_data import (
    get_groups,
    get_partial_groups,
    get_timetable,
    get_partial_timetable,
    TemporaryFetchError,
)
from fetch_institute_groups import load_cached
from institutes import INSTITUTES

logger = logging.getLogger(__name__)

OUTPUT_ROOT = "schedules"
DEFAULT_SEMESTER = "2"
WORKERS = max(1, int(os.environ.get("LPNU_WORKERS", "6")))
MAX_TEMP_ERRORS_TOTAL = int(os.environ.get("LPNU_MAX_TEMP_ERRORS_TOTAL", "40"))
PARTIAL_FALLBACK_TO_ALL = os.environ.get("LPNU_PARTIAL_FALLBACK_TO_ALL", "0") == "1"
FORCE_REDOWNLOAD = os.environ.get("LPNU_FORCE_REDOWNLOAD", "0") == "1"
SUMMARY_PATH = os.environ.get("LPNU_BATCH_SUMMARY_PATH", "").strip()


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


def discover_groups(
    institute: str = "All", semester: str = DEFAULT_SEMESTER
) -> list[str]:
    # First try live site (may be empty), then cached proxy list
    live = get_groups(institute=institute, semester=semester)
    if live:
        return live

    # Use cached lists from proxy
    if institute in INSTITUTES:
        cached = load_cached(institute)
        if cached:
            return cached

    if institute == "All":
        all_cached = []
        for inst in INSTITUTES:
            all_cached.extend(load_cached(inst))
        if all_cached:
            return sorted(set(all_cached))

    return []


def discover_partial_groups(
    semester_half: int, institute: str = "All", semester: str = DEFAULT_SEMESTER
) -> list[str]:
    try:
        return get_partial_groups(
            semester_half=semester_half, institute=institute, semester=semester
        )
    except TemporaryFetchError as exc:
        logger.warning(
            "Could not fetch group list for semester half %d (%s): %s",
            semester_half,
            institute,
            exc,
        )
        return []


def _download_group_task(
    group: str, semester: str = DEFAULT_SEMESTER
) -> DownloadResult:
    path = os.path.join(OUTPUT_ROOT, semester, group, f"{group}_schedule.json")
    if os.path.exists(path) and not FORCE_REDOWNLOAD:
        return DownloadResult(group, "skip", f"↩️ {group}: вже існує, пропускаю")

    try:
        schedule = get_timetable(group, semester=semester)
        save_json(path, schedule)
        return DownloadResult(group, "ok", f"✅ {group} → {path}")
    except TemporaryFetchError as exc:
        return DownloadResult(
            group,
            "warn",
            f"⚠️ {group}: тимчасова помилка, пропускаю (можна запустити повторно): {exc}",
            True,
        )
    except Exception as exc:
        return DownloadResult(group, "err", f"❌ {group}: {exc}")


def _download_partial_group_task(
    group: str, semester_half: int, semester: str = DEFAULT_SEMESTER
) -> DownloadResult:
    label = f"{group} (half {semester_half})"
    path = os.path.join(
        OUTPUT_ROOT, f"semester_half_{semester_half}", group, f"{group}_schedule.json"
    )
    if os.path.exists(path) and not FORCE_REDOWNLOAD:
        return DownloadResult(
            label, "skip", f"↩️ {group} (half {semester_half}): вже існує, пропускаю"
        )

    try:
        schedule = get_partial_timetable(
            group, semester_half=semester_half, semester=semester
        )
        save_json(path, schedule)
        return DownloadResult(
            label, "ok", f"✅ {group} (half {semester_half}) → {path}"
        )
    except TemporaryFetchError as exc:
        return DownloadResult(
            label,
            "warn",
            f"⚠️ {group} (half {semester_half}): тимчасова помилка, пропускаю (можна повторити): {exc}",
            True,
        )
    except Exception as exc:
        return DownloadResult(label, "err", f"❌ {group} (half {semester_half}): {exc}")


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


def _run_parallel(groups: Iterable[str], worker_fn):
    group_list = list(groups)
    stats = _empty_stats(processed_groups=len(group_list))
    if not group_list:
        return stats

    workers = min(WORKERS, len(group_list))
    if workers <= 1:
        temp_errors = 0
        for group in group_list:
            result = worker_fn(group)
            _accumulate(stats, result)
            logger.info(result.message)
            if result.is_temp_error:
                temp_errors += 1
                if temp_errors >= MAX_TEMP_ERRORS_TOTAL:
                    logger.warning(
                        "Stopping: accumulated %d temporary errors (likely LPNU throttling).",
                        temp_errors,
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
            pending.add(pool.submit(worker_fn, group))

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
                            "Stopping: accumulated %d temporary errors (likely LPNU throttling).",
                            temp_errors,
                        )
                else:
                    temp_errors = 0

                if not stop_submitting:
                    try:
                        group = next(iterator)
                    except StopIteration:
                        continue
                    pending.add(pool.submit(worker_fn, group))
    return stats


def download_groups(groups: Iterable[str], semester: str = DEFAULT_SEMESTER):
    return _run_parallel(
        groups, lambda group: _download_group_task(group, semester=semester)
    )


def download_partial_groups(
    groups: Iterable[str], semester_half: int, semester: str = DEFAULT_SEMESTER
):
    return _run_parallel(
        groups,
        lambda group: _download_partial_group_task(
            group, semester_half=semester_half, semester=semester
        ),
    )


def _compute_total_stats(
    primary_stats: dict[str, Any], partial_stats: dict[str, Any]
) -> dict[str, Any]:
    stats = _empty_stats()
    stats["processed_groups"] = primary_stats["processed_groups"]
    for item in partial_stats.values():
        stats["processed_groups"] += item["processed_groups"]
    for level in ("ok", "skip", "warn", "err"):
        stats[level] = primary_stats[level] + sum(
            item[level] for item in partial_stats.values()
        )
    stats["success"] = stats["ok"] + stats["skip"]
    stats["failed"] = stats["warn"] + stats["err"]
    stats["failed_fetch_groups"] = primary_stats["failed_fetch_groups"] + [
        g for item in partial_stats.values() for g in item["failed_fetch_groups"]
    ]
    stats["failed_update_groups"] = primary_stats["failed_update_groups"] + [
        g for item in partial_stats.values() for g in item["failed_update_groups"]
    ]
    return stats


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    institute = os.environ.get("LPNU_INSTITUTE", "All")
    semester = os.environ.get("LPNU_SEMESTER", DEFAULT_SEMESTER)
    env_groups = os.environ.get("GROUPS", "")
    file_groups: list[str] = []
    if os.path.exists("groups.txt"):
        with open("groups.txt", encoding="utf-8") as f:
            file_groups = [line.strip() for line in f if line.strip()]

    groups = discover_groups(institute=institute, semester=semester)

    # Fallback: site no longer exposes group select; allow manual list
    if not groups:
        if env_groups:
            groups = [g.strip() for g in env_groups.split(",") if g.strip()]
            logger.warning(
                "Auto-discovery unavailable, using GROUPS env (%d groups)", len(groups)
            )
        elif file_groups:
            groups = file_groups
            logger.warning(
                "Auto-discovery unavailable, using groups.txt (%d groups)", len(groups)
            )
        else:
            logger.error(
                "No groups found. Add them to groups.txt or set GROUPS=oi-31,oi-32"
            )
            if SUMMARY_PATH:
                with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "institute": institute,
                            "semester": semester,
                            "groups_discovery_failed": True,
                            "primary": _empty_stats(),
                            "partial": {"1": _empty_stats(), "2": _empty_stats()},
                            "totals": _empty_stats(),
                        },
                        f,
                        ensure_ascii=False,
                        indent=2,
                    )
            return
    else:
        logger.info("Groups found: %d", len(groups))

    primary_stats = download_groups(groups, semester=semester)
    partial_stats: dict[str, dict[str, Any]] = {
        "1": _empty_stats(),
        "2": _empty_stats(),
    }

    # partial schedules for numerator/denominator halves
    for half in (1, 2):
        partial_groups = discover_partial_groups(
            half, institute=institute, semester=semester
        )
        if partial_groups:
            partial_stats[str(half)] = download_partial_groups(
                partial_groups, semester_half=half, semester=semester
            )
            continue

        if PARTIAL_FALLBACK_TO_ALL and groups:
            logger.warning(
                "No separate group list for half %d — falling back to main list (%d groups).",
                half,
                len(groups),
            )
            partial_stats[str(half)] = download_partial_groups(
                groups, semester_half=half, semester=semester
            )
            continue

        logger.warning(
            "Could not fetch group list for half %d — skipping. "
            "Set LPNU_PARTIAL_FALLBACK_TO_ALL=1 to force using the main list.",
            half,
        )

    if SUMMARY_PATH:
        payload = {
            "institute": institute,
            "semester": semester,
            "groups_discovery_failed": False,
            "primary": primary_stats,
            "partial": partial_stats,
            "totals": _compute_total_stats(primary_stats, partial_stats),
        }
        with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
