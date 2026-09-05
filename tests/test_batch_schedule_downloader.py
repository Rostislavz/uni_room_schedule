"""Regression coverage for downloader exit status and failure summaries."""

from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import batch_schedule_downloader as downloader


class DownloadExitStatusTests(unittest.TestCase):
    def run_batch(self, primary="err", partial="err", groups=None, summary=True):
        def stats(level):
            result = downloader._empty_stats(processed_groups=1)
            result[level] = 1
            return result

        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            summary_path = Path(tmp) / "batch_summary.json"
            stack.enter_context(
                patch.dict(downloader.os.environ, {"LPNU_SEMESTER": "1"}, clear=True)
            )
            stack.enter_context(
                patch.object(downloader.os.path, "exists", return_value=False)
            )
            stack.enter_context(
                patch.object(
                    downloader, "SUMMARY_PATH", str(summary_path) if summary else ""
                )
            )
            stack.enter_context(
                patch.object(downloader, "PARTIAL_FALLBACK_TO_ALL", True)
            )
            discover = stack.enter_context(
                patch.object(
                    downloader,
                    "discover_groups",
                    return_value=["ОІ-31"] if groups is None else groups,
                )
            )
            stack.enter_context(
                patch.object(downloader, "discover_partial_groups", return_value=[])
            )
            download = stack.enter_context(
                patch.object(downloader, "download_groups", return_value=stats(primary))
            )
            stack.enter_context(
                patch.object(
                    downloader,
                    "download_partial_groups",
                    side_effect=lambda *a, **kw: stats(partial),
                )
            )
            status = downloader.main()
            discover.assert_called_once_with(institute="All", semester="1")
            if groups != []:
                download.assert_called_once_with(["ОІ-31"], semester="1")
            payload = json.loads(summary_path.read_text()) if summary else None
            return status, payload

    def test_all_failures_exit_nonzero_and_preserve_summary(self):
        status, payload = self.run_batch()
        self.assertEqual(status, 1)
        self.assertEqual(payload["semester"], "1")
        self.assertEqual(payload["totals"]["success"], 0)
        self.assertEqual(payload["totals"]["failed"], 3)

    def test_no_groups_exit_nonzero_and_preserve_summary(self):
        status, payload = self.run_batch(groups=[])
        self.assertEqual(status, 1)
        self.assertTrue(payload["groups_discovery_failed"])

    def test_failure_does_not_require_summary_configuration(self):
        status, _ = self.run_batch(summary=False)
        self.assertEqual(status, 1)

    def test_temporary_failures_exit_nonzero(self):
        status, payload = self.run_batch(primary="warn", partial="warn")
        self.assertEqual(status, 1)
        self.assertEqual(payload["totals"]["failed"], 3)

    def test_available_schedules_allow_downstream_validation(self):
        for primary, partial in (("ok", "err"), ("skip", "err"), ("err", "ok")):
            with self.subTest(primary=primary, partial=partial):
                status, payload = self.run_batch(primary=primary, partial=partial)
                self.assertEqual(status, 0)
                self.assertGreater(payload["totals"]["success"], 0)


if __name__ == "__main__":
    unittest.main()
