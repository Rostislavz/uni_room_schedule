"""HTTP client for LPNU timetable endpoints."""
from __future__ import annotations

import atexit
import logging
import os
import random
import threading
import time
from typing import Optional
import requests

logger = logging.getLogger(__name__)

from lpnu_parser import (
    parse_groups,
    parse_institutes,
    parse_partial_groups,
    parse_timetable,
)

BASE_STUDENTS = "https://student.lpnu.ua/"
BASE_STAFF = "https://staff.lpnu.ua/"

TIMETABLE_SUFFIX = "students_schedule"
SELECTIVE_SUFFIX = "schedule_selective"
LECTURER_SUFFIX = "lecturer_schedule"
PART_TIME_SUFFIX = "parttime_schedule"
TIMETABLE_EXAMS_SUFFIX = "students_exam"
LECTURER_EXAMS_SUFFIX = "lecturer_exam"

REQUEST_TIMEOUT = int(os.environ.get("LPNU_REQUEST_TIMEOUT", "20"))
RETRY_ATTEMPTS = int(os.environ.get("LPNU_RETRY_ATTEMPTS", "3"))
DEFAULT_SEM_DURATION = os.environ.get("LPNU_DEFAULT_SEM_DURATION", "1").strip()
HALF1_SEM_DURATION = os.environ.get("LPNU_HALF1_SEM_DURATION", "2").strip() or "2"
HALF2_SEM_DURATION = os.environ.get("LPNU_HALF2_SEM_DURATION", "3").strip() or "3"
SEM_DURATION_FALLBACKS = [
    s.strip()
    for s in os.environ.get("LPNU_SEM_DURATION_FALLBACKS", "1,2,3").split(",")
    if s.strip()
]
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Safari/605.1.15"


class TemporaryFetchError(RuntimeError):
    """Raised when LPNU returns an empty/invalid page (likely rate limiting)."""


_THREAD_LOCAL = threading.local()
_ALL_SESSIONS: list[requests.Session] = []
_SESSIONS_LOCK = threading.Lock()


def _get_session() -> requests.Session:
    session = getattr(_THREAD_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        _THREAD_LOCAL.session = session
        with _SESSIONS_LOCK:
            _ALL_SESSIONS.append(session)
    return session


def _close_all_sessions() -> None:
    with _SESSIONS_LOCK:
        for session in _ALL_SESSIONS:
            try:
                session.close()
            except Exception:
                pass
        _ALL_SESSIONS.clear()


atexit.register(_close_all_sessions)

# Helpers

def _looks_invalid_lpnu_page(text: str) -> bool:
    # LPNU may return an HTML shell without timetable/select controls when throttled.
    if len(text) < 800:
        return True

    has_timetable = "view-content" in text
    has_group_select = (
        "edit-studygroup-abbrname-selective" in text
        or "edit-studygroup-abbrname" in text
    )
    return not (has_timetable or has_group_select)


def _fetch_html(url: str, params: Optional[dict[str, str]] = None) -> str:
    attempts = max(1, RETRY_ATTEMPTS)
    last_err: Exception | None = None
    session = _get_session()
    for i in range(attempts):
        try:
            resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            text = resp.text
            if _looks_invalid_lpnu_page(text):
                raise TemporaryFetchError("LPNU returned empty/invalid timetable page")
            return text
        except Exception as exc:  # noqa: PERF203 (intentional retry)
            last_err = exc
            wait = 0.5 * (2 ** i) + random.random() * 0.3
            logger.warning("Fetch attempt %d/%d failed: %s — retrying in %.1fs", i + 1, attempts, exc, wait)
            time.sleep(wait)
    raise last_err  # type: ignore[misc]


# Public API


def _half_to_sem_duration(semester_half: int) -> str:
    return HALF1_SEM_DURATION if semester_half == 1 else HALF2_SEM_DURATION


def _duration_candidates(explicit: Optional[str]) -> list[Optional[str]]:
    if explicit:
        return [explicit]

    candidates: list[Optional[str]] = []
    if DEFAULT_SEM_DURATION:
        candidates.append(DEFAULT_SEM_DURATION)
    candidates.append(None)
    for dur in SEM_DURATION_FALLBACKS:
        if dur not in candidates:
            candidates.append(dur)
    return candidates

def get_groups(institute: str = "All", semester: str = "2"):
    params = {
        "departmentparent_abbrname_selective": institute,
        "semestr": semester,
    }
    try:
        html = _fetch_html(BASE_STUDENTS + TIMETABLE_SUFFIX, params)
        return parse_groups(html)
    except TemporaryFetchError:
        return []


def get_partial_groups(semester_half: int, institute: str = "All", semester: str = "2"):
    durations = [_half_to_sem_duration(semester_half)]
    if "1" not in durations:
        durations.append("1")

    last_err: Exception | None = None
    for sem_duration in durations:
        params = {
            "departmentparent_abbrname_selective": institute,
            "semestr": semester,
            "semestrduration": sem_duration,
        }
        try:
            html = _fetch_html(BASE_STUDENTS + TIMETABLE_SUFFIX, params)
            groups = parse_partial_groups(html)
            if groups:
                return groups
        except TemporaryFetchError as exc:
            last_err = exc

    if last_err:
        raise last_err
    return []


def get_institutes():
    html = _fetch_html(BASE_STUDENTS + TIMETABLE_SUFFIX)
    return parse_institutes(html)


def get_timetable(group: str, semester: str = "2", sem_duration: Optional[str] = None):
    last_err: Exception | None = None
    saw_no_timetable = False
    for duration in _duration_candidates(sem_duration):
        params = {
            "studygroup_abbrname": group.lower(),
            "semestr": semester,
        }
        if duration:
            params["semestrduration"] = duration
        try:
            html = _fetch_html(BASE_STUDENTS + TIMETABLE_SUFFIX, params)
            return parse_timetable(html)
        except (TemporaryFetchError, ValueError) as exc:
            last_err = exc
            if isinstance(exc, ValueError):
                saw_no_timetable = True

    if saw_no_timetable:
        raise ValueError(f"No timetable content found for group {group}")
    if last_err:
        raise last_err
    raise RuntimeError("Failed to fetch timetable")


def get_partial_timetable(group: str, semester_half: int, semester: str = "2"):
    sem_duration = _half_to_sem_duration(semester_half)
    durations = [sem_duration]
    if "1" not in durations:
        durations.append("1")

    last_err: Exception | None = None
    saw_no_timetable = False
    for duration in durations:
        try:
            return get_timetable(group, semester=semester, sem_duration=duration)
        except (TemporaryFetchError, ValueError) as exc:
            last_err = exc
            if isinstance(exc, ValueError):
                saw_no_timetable = True

    if saw_no_timetable:
        raise ValueError(f"No partial timetable content found for group {group} (half {semester_half})")
    if last_err:
        raise last_err
    raise RuntimeError("Failed to fetch partial timetable")


__all__ = [
    "get_groups",
    "get_partial_groups",
    "get_institutes",
    "get_timetable",
    "get_partial_timetable",
]
