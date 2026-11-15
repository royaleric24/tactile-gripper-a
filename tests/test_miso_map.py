"""Host-side checks for the targeted ADC2/ADC3 MISO mapping decision."""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_NAME = "diag_ads1220_miso_under_test"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, ROOT / "scripts/diag_ads1220_miso.py")
miso = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = miso
SPEC.loader.exec_module(miso)

PATTERN_A = [0x81, 0x80, 0, 0]
PATTERN_B = [0x91, 0x80, 0x80, 0]


def item(adc, cs, candidate, good):
    return {
        "adc": adc,
        "cs": cs,
        "miso": candidate,
        "result": {
            "reset_ok": True,
            "read_a_return": True,
            "read_a": PATTERN_A if good else [0, 0, 0, 0],
            "read_b_return": True,
            "read_b": PATTERN_B if good else [0xFF, 0xFF, 0xFF, 0xFF],
        },
    }


class MisoMapTests(unittest.TestCase):
    def test_confirmed_mapping(self):
        items = [
            item(1, 21, 35, True),
            item(2, 22, 34, False),
            item(2, 22, 26, True),
            item(3, 5, 34, True),
            item(3, 5, 26, False),
        ]
        mapping, problems = miso.infer_mapping(items)
        self.assertEqual(mapping, {1: 35, 2: 26, 3: 34})
        self.assertEqual(problems, [])
        self.assertFalse(miso.item_pass(items[1]))
        self.assertTrue(miso.item_pass(items[2]))

    def test_swapped_mapping_detected(self):
        items = [
            item(1, 21, 35, True),
            item(2, 22, 34, True),
            item(2, 22, 26, False),
            item(3, 5, 34, False),
            item(3, 5, 26, True),
        ]
        mapping, problems = miso.infer_mapping(items)
        self.assertEqual(mapping, {1: 35, 2: 34, 3: 26})
        self.assertEqual(problems, [])

    def test_no_candidate_is_incomplete(self):
        items = [
            item(1, 21, 35, True),
            item(2, 22, 34, False),
            item(2, 22, 26, False),
            item(3, 5, 34, False),
            item(3, 5, 26, False),
        ]
        mapping, problems = miso.infer_mapping(items)
        self.assertEqual(mapping, {1: 35})
        self.assertTrue(problems)

    def test_ambiguous_candidate_is_incomplete(self):
        items = [
            item(1, 21, 35, True),
            item(2, 22, 34, True),
            item(2, 22, 26, True),
            item(3, 5, 34, True),
            item(3, 5, 26, False),
        ]
        mapping, problems = miso.infer_mapping(items)
        self.assertNotIn(2, mapping)
        self.assertTrue(problems)


if __name__ == "__main__":
    unittest.main()
