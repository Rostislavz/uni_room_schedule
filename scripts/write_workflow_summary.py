#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_json(path: str) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def list_as_lines(values: list[str]) -> str:
    if not values:
        return "None"
    return "<br>".join(escape_cell(v) for v in values)


def main():
    groups_fetch_summary = load_json(os.environ.get("GROUPS_FETCH_SUMMARY_PATH", ""))
    batch_summary = load_json(os.environ.get("BATCH_SUMMARY_PATH", ""))
    index_summary = load_json(os.environ.get("INDEX_SUMMARY_PATH", ""))

    institutes = groups_fetch_summary.get("institutes", [])
    institute_names = [item.get("institute", "") for item in institutes if item.get("institute")]
    failed_institutes = groups_fetch_summary.get("failed_institutes", [])

    totals = batch_summary.get("totals", {})
    processed_groups = int(totals.get("processed_groups", 0))
    success_groups = int(totals.get("success", int(totals.get("ok", 0)) + int(totals.get("skip", 0))))
    failed_groups = int(totals.get("failed", int(totals.get("warn", 0)) + int(totals.get("err", 0))))
    failed_fetch_groups = totals.get("failed_fetch_groups", [])
    failed_update_groups = totals.get("failed_update_groups", [])

    rooms_count = (
        index_summary.get("totals", {}).get("rooms")
        if index_summary
        else None
    )
    rooms_text = str(rooms_count) if rooms_count is not None else "Unknown"

    rows = [
        ("Processed institutes", f"{len(institute_names)}"),
        ("Institutes list", ", ".join(institute_names) if institute_names else "Unknown"),
        ("Processed groups (total)", str(processed_groups)),
        ("Groups success / failed", f"{success_groups} / {failed_groups}"),
        ("Processed rooms", rooms_text),
        ("Failed to fetch groups", list_as_lines(failed_fetch_groups)),
        ("Failed to update groups", list_as_lines(failed_update_groups)),
        ("Failed institute updates", list_as_lines(failed_institutes)),
    ]

    summary_lines = [
        "## Data Refresh Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    for metric, value in rows:
        summary_lines.append(f"| {escape_cell(metric)} | {escape_cell(value)} |")
    summary_lines.append("")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(summary_lines))
            fh.write("\n")
    else:
        print("\n".join(summary_lines))


if __name__ == "__main__":
    main()
