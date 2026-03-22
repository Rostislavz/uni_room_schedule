"""
HTML parsing utilities for LPNU timetable pages.
Ported from the React implementation in ../timetable/src/utils/data/Parser.ts
with adaptations for Python + BeautifulSoup.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup, NavigableString, Tag

DAY_ORDER = ["пн", "вт", "ср", "чт", "пт", "сб", "нд"]
DAY_ABBR = {
    1: "Пн",
    2: "Вт",
    3: "Ср",
    4: "Чт",
    5: "Пт",
    6: "Сб",
    7: "Нд",
}

logger = logging.getLogger(__name__)


@dataclass
class Lesson:
    day: str
    number: int
    subject: str
    lecturer: str
    location: str
    lesson_type: str
    subgroup: str
    week_type: str
    urls: list[str]
    date: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "День": self.day,
            "Пара": self.number,
            "Предмет": self.subject,
            "Викладач": self.lecturer,
            "Аудиторія": self.location,
            "Тип заняття": self.lesson_type,
            "Підгрупа": self.subgroup,
            "Тип тижня": self.week_type,
            "Посилання": self.urls,
            # Always emit "Дата" for a consistent schema; null when not a date-based schedule
            "Дата": self.date,
        }


class TimetableParser:
    INSTITUTES_SELECTOR = "#edit-departmentparent-abbrname-selective"
    GROUPS_SELECTORS = [
        "#edit-studygroup-abbrname-selective",
        "#edit-studygroup-abbrname",
    ]
    SELECTIVE_GROUPS_SELECTORS = [
        "#edit-studygroup-abbrname-selective",
        "#edit-studygroup-abbrname",
    ]
    LECTURERS_SELECTOR = "#edit-teachername-selective"
    DEPARTMENTS_SELECTOR = "#edit-department-name-selective"
    TIMETABLE_SELECTOR = ".view-content"

    def _parse_select(self, html: str, selector: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        select = soup.select_one(selector)
        if not select:
            logger.warning(
                "Selector not found: %r (page length: %d chars) — LPNU HTML may have changed",
                selector,
                len(html),
            )
            return []
        options = [opt.get("value", "") for opt in select.find_all("option")]
        result = sorted([o for o in options if o and o != "All"], key=str.lower)
        if not result:
            logger.warning("Selector %r matched but returned no options", selector)
        return result

    def _parse_select_many(self, html: str, selectors: list[str]) -> list[str]:
        for selector in selectors:
            values = self._parse_select(html, selector)
            if values:
                return values
        return []

    # ===== Meta lists =====
    def parse_institutes(self, html: str) -> list[str]:
        return self._parse_select(html, self.INSTITUTES_SELECTOR)

    def parse_groups(self, html: str) -> list[str]:
        return self._parse_select_many(html, self.GROUPS_SELECTORS)

    def parse_partial_groups(self, html: str) -> list[str]:
        return self._parse_select_many(html, self.GROUPS_SELECTORS)

    def parse_selective_groups(self, html: str) -> list[str]:
        return self._parse_select_many(html, self.SELECTIVE_GROUPS_SELECTORS)

    def parse_lecturers(self, html: str) -> list[str]:
        return self._parse_select(html, self.LECTURERS_SELECTOR)

    def parse_lecturer_departments(self, html: str) -> list[str]:
        return self._parse_select(html, self.DEPARTMENTS_SELECTOR)

    # ===== Timetable =====
    def parse_timetable(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        content = soup.select_one(self.TIMETABLE_SELECTOR)
        if not content:
            raise ValueError("No timetable content found")

        lessons: list[Lesson] = []
        current_day_abbr: Optional[str] = None
        current_date: Optional[str] = None
        current_pair = None

        for child in content.children:
            if isinstance(child, NavigableString):
                continue
            if not isinstance(child, Tag):
                continue

            if child.name == "span" and "view-grouping-header" in child.get(
                "class", []
            ):
                current_day_abbr, current_date = self._parse_day_or_date(
                    child.get_text(strip=True)
                )
            elif child.name == "h3":
                try:
                    current_pair = int(child.get_text(strip=True))
                except ValueError:
                    current_pair = None
            elif child.get("class") and "stud_schedule" in child.get("class", []):
                if current_pair is None or not current_day_abbr:
                    raise ValueError("Encountered schedule block without day/pair")
                lessons.extend(
                    self._parse_pair(
                        child, current_day_abbr, current_pair, current_date
                    )
                )
            else:
                # tolerate unknown nodes instead of failing hard
                continue

        return [lesson.as_dict() for lesson in lessons]

    # ===== internals =====
    def _parse_day_or_date(self, text: str):
        lower = text.strip().lower()
        if lower in DAY_ORDER:
            idx = DAY_ORDER.index(lower) + 1
            return DAY_ABBR[idx], None
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            try:
                dt = datetime.strptime(text, "%d.%m.%Y")
            except ValueError:
                return text, None
        # Python weekday: Monday=0
        idx = dt.weekday() + 1
        return DAY_ABBR.get(idx, text), dt.date().isoformat()

    def _parse_pair(
        self, pair_block: Tag, day_abbr: str, pair_num: int, date_str: Optional[str]
    ) -> list[Lesson]:
        lessons: list[Lesson] = []
        for group_content in pair_block.select(".group_content"):
            parent = group_content.parent
            meta = self._parse_lesson_id(parent.get("id", "")) if parent else {}
            data = self._parse_lesson_data(group_content)

            lesson_type = self._guess_type(group_content.get_text(" ", strip=True))
            lesson = Lesson(
                day=day_abbr,
                number=pair_num,
                subject=data["subject"],
                lecturer=data["lecturer"],
                location=data["location"],
                lesson_type=lesson_type,
                subgroup=meta.get("subgroup_label", "вся група"),
                week_type=meta.get("week_label", "постійно"),
                urls=data["urls"],
                date=date_str,
            )
            lessons.append(lesson)
        return lessons

    def _parse_lesson_id(self, ident: str):
        parts = ident.split("_")
        subgroup = "вся група"
        week_label = "постійно"

        if "sub" in ident:
            try:
                idx = parts.index("sub")
                subgroup_num = int(parts[idx + 1])
                subgroup = "перша" if subgroup_num == 1 else "друга"
            except (ValueError, IndexError):
                subgroup = "вся група"

        tail = parts[-1] if parts else "full"
        if tail == "chys":
            week_label = "чисельник"
        elif tail == "znam":
            week_label = "знаменник"
        else:
            week_label = "постійно"

        return {"subgroup_label": subgroup, "week_label": week_label}

    def _parse_lesson_data(self, element: Tag):
        texts: list[str] = []
        urls: list[str] = []
        for node in element.contents:
            if isinstance(node, NavigableString):
                content = node.strip()
                if content:
                    texts.append(content)
            elif isinstance(node, Tag):
                if node.name == "br":
                    continue
                if node.name == "span":
                    link = node.find("a")
                    href = link.get("href") if link else None
                    if href:
                        urls.append(
                            href if href.startswith("http") else f"https://{href}"
                        )
                else:
                    text = node.get_text(strip=True)
                    if text:
                        texts.append(text)

        subject = texts[0] if texts else ""
        lecturer = ""
        location = ""

        if len(texts) > 1:
            second = texts[1]
            parts = [p.strip() for p in second.split(",")]
            if parts:
                lecturer = parts[0]
            if len(parts) > 1:
                location = parts[1]

        # Handle case when lecturer/location missing but present later
        if len(texts) > 2 and not location:
            location = texts[2]

        return {
            "subject": subject,
            "lecturer": lecturer,
            "location": location,
            "urls": urls,
        }

    def _guess_type(self, text: str):
        lower = text.lower()
        if "лаб" in lower:
            return "Лабораторна"
        if "прак" in lower:
            return "Практична"
        if "конс" in lower:
            return "Консультація"
        return "Лекція"


def parse_timetable(html: str) -> list[dict]:
    return TimetableParser().parse_timetable(html)


def parse_groups(html: str) -> list[str]:
    return TimetableParser().parse_groups(html)


def parse_partial_groups(html: str) -> list[str]:
    return TimetableParser().parse_partial_groups(html)


def parse_institutes(html: str) -> list[str]:
    return TimetableParser().parse_institutes(html)


def parse_selective_groups(html: str) -> list[str]:
    return TimetableParser().parse_selective_groups(html)


def parse_lecturers(html: str) -> list[str]:
    return TimetableParser().parse_lecturers(html)


def parse_lecturer_departments(html: str) -> list[str]:
    return TimetableParser().parse_lecturer_departments(html)
