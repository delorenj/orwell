from pathlib import Path
import importlib.util
import sys
import unittest
from unittest.mock import patch

scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(scripts_dir))

spec = importlib.util.spec_from_file_location("clock_action", scripts_dir / "03_clock_action.py")
clock_action = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(clock_action)


class ClockActionModalTest(unittest.TestCase):
    def test_missing_previous_punch_requires_manual_repair(self):
        text = "Warning Missing previous in punch. Please submit a timesheet change request."
        self.assertTrue(clock_action.modal_requires_manual_repair(text))

    def test_plain_confirmation_can_be_confirmed(self):
        self.assertFalse(clock_action.modal_requires_manual_repair("Warning Are you sure you want to punch out?"))

    def test_clock_out_repair_probe_requires_env_and_button(self):
        state = {"button_texts": ["clock out", "clock in"]}
        self.assertFalse(clock_action.allow_clock_out_repair_probe("out", state))
        with patch.dict("os.environ", {"ORWELL_ALLOW_CLOCK_OUT_REPAIR_PROBE": "1"}):
            self.assertTrue(clock_action.allow_clock_out_repair_probe("out", state))
            self.assertFalse(clock_action.allow_clock_out_repair_probe("in", state))


if __name__ == "__main__":
    unittest.main()
