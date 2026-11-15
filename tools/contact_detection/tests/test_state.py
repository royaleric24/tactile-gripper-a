import json
import tempfile
import unittest
from pathlib import Path

from tools.contact_detection.config import DetectorConfig
from tools.contact_detection.detector import ContactDetector
from tools.contact_detection.state import DemoState
from tools.contact_detection.store import TrialStore


def sample(counts, restored=True, seq=0):
    return {"seq": seq, "counts": counts, "ready": True, "read_ok": True,
            "restored_before_cs": restored, "post_cs_high": restored,
            "mux_before": 9, "mux_after": 9, "vref_before": 3, "vref_after": 3,
            "reg3_before": 2, "reg3_after": 2}


class StateTests(unittest.TestCase):
    def make(self, tmp):
        cfg = DetectorConfig(avdd_mv=3300, baseline_frames=2, ema_alpha=1.0,
                             contact_drop_v=0.02, release_recover_v=0.01,
                             contact_confirm_frames=1, release_confirm_frames=1)
        store = TrialStore(Path(tmp), source="test", data_kind="SIMULATED", label="R4C3",
                           config={}, firmware="test")
        return DemoState(store, ContactDetector(cfg), "test"), store

    def test_verified_contact_triggers_only_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            state, store = self.make(tmp)
            state.on_sample(sample(8_000_000, True, 1)); state.on_sample(sample(8_000_000, True, 2))
            state.on_sample(sample(7_900_000, True, 3))
            self.assertEqual(state.latest_detection["state"], "CONTACT")
            self.assertEqual(len(state.stop_sink.requests), 1)
            request = state.stop_sink.requests[0]
            self.assertEqual(request["mode"], "DRY_RUN")
            self.assertFalse(request["executed"])
            summary = store.finalize()
            self.assertEqual(summary["data_kind"], "SIMULATED")

    def test_unverified_contact_does_not_trigger_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            state, store = self.make(tmp)
            state.on_sample(sample(8_000_000, False, 1)); state.on_sample(sample(8_000_000, False, 2))
            state.on_sample(sample(7_900_000, False, 3))
            self.assertEqual(state.latest_detection["state"], "CONTACT")
            self.assertEqual(len(state.stop_sink.requests), 0)
            store.finalize()

    def test_snapshot_is_json_serializable(self):
        with tempfile.TemporaryDirectory() as tmp:
            state, store = self.make(tmp)
            state.on_sample(sample(8_000_000))
            snap = state.snapshot()
            json.dumps(snap)
            self.assertIn("detection", snap)
            store.finalize()


if __name__ == "__main__":
    unittest.main()
