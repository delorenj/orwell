from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from clock_state import (  # noqa: E402
    derive_clock_status,
    find_active_and_last_completed_rows,
    state_supports_action,
    today_row_label,
)


def row(group=None, start="", end="", total="", has_delete=False, is_footer=False):
    return {
        "group": group or today_row_label(),
        "isFooter": is_footer,
        "hasDelete": has_delete,
        "start_time": start,
        "end_time": end,
        "total": total,
    }


class ClockStateRowValidationTest(unittest.TestCase):
    def test_end_without_start_is_a_failure(self):
        active, completed, failures = find_active_and_last_completed_rows(
            [
                row("FRI Jun 26", start="08:01 am", end="10:06 am", total="2.08 hrs"),
                row("FRI Jun 26", end="01:56 am", total="17.67 hrs"),
            ]
        )

        self.assertIsNone(active)
        self.assertIsNotNone(completed)
        self.assertEqual(derive_clock_status(active, completed, failures), "error")
        self.assertIn("blank From", failures[0])

    def test_stale_open_row_is_clocked_in(self):
        active, completed, failures = find_active_and_last_completed_rows(
            [
                row("SAT Jun 27", start="01:54 pm", has_delete=True),
                row(today_row_label()),
            ]
        )

        self.assertIsNotNone(active)
        self.assertIsNone(completed)
        self.assertEqual(failures, [])
        self.assertEqual(derive_clock_status(active, completed, failures), "clocked_in")

    def test_today_open_row_is_clocked_in(self):
        active, completed, failures = find_active_and_last_completed_rows(
            [row(start="09:03 am", has_delete=True)]
        )

        self.assertIsNotNone(active)
        self.assertIsNone(completed)
        self.assertEqual(failures, [])
        self.assertEqual(derive_clock_status(active, completed, failures), "clocked_in")

    def test_empty_template_row_does_not_hide_completed_state(self):
        active, completed, failures = find_active_and_last_completed_rows(
            [
                row("MON Jun 22", start="09:00 am", end="05:00 pm", total="8.00 hrs"),
                row(has_delete=True),
            ]
        )

        self.assertIsNone(active)
        self.assertIsNotNone(completed)
        self.assertEqual(failures, [])
        self.assertEqual(derive_clock_status(active, completed, failures), "clocked_out")

    def test_empty_current_row_by_itself_is_unknown(self):
        active, completed, failures = find_active_and_last_completed_rows([row(has_delete=True)])

        self.assertIsNone(active)
        self.assertIsNone(completed)
        self.assertEqual(failures, [])
        self.assertEqual(derive_clock_status(active, completed, failures), "unknown")

    def test_stale_blank_placeholder_row_is_clocked_in(self):
        active, completed, failures = find_active_and_last_completed_rows([row("SAT Jun 27", has_delete=True)])

        self.assertIsNotNone(active)
        self.assertIsNone(completed)
        self.assertEqual(failures, [])
        self.assertEqual(derive_clock_status(active, completed, failures), "clocked_in")

    def test_unknown_state_is_not_actionable(self):
        self.assertFalse(state_supports_action("unknown", "in"))
        self.assertFalse(state_supports_action("unknown", "out"))


if __name__ == "__main__":
    unittest.main()
