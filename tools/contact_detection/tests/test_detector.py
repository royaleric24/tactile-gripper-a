import unittest

from tools.contact_detection.config import DetectorConfig
from tools.contact_detection.detector import CONTACT, RELEASE, UNKNOWN, QUALITY_UNVERIFIED, ContactDetector


def sample(counts, restored=True, seq=0):
    return {"seq": seq, "counts": counts, "ready": True, "read_ok": True,
            "restored_before_cs": restored, "post_cs_high": restored,
            "mux_before": 9, "mux_after": 9, "vref_before": 3, "vref_after": 3,
            "reg3_before": 2, "reg3_after": 2}


class DetectorTests(unittest.TestCase):
    def detector(self, restored=True):
        cfg = DetectorConfig(avdd_mv=3300, baseline_frames=3, ema_alpha=1.0,
                             contact_drop_v=0.02, release_recover_v=0.01,
                             contact_confirm_frames=2, release_confirm_frames=2,
                             unknown_timeout_s=0.2)
        det = ContactDetector(cfg)
        t = 0
        for i in range(3):
            det.update(sample(8_000_000, restored, i), t); t += 50_000_000
        return det, t

    def test_contact_release_hysteresis(self):
        det, t = self.detector()
        for i in range(2):
            det.update(sample(7_900_000, True, i), t); t += 50_000_000
        self.assertEqual(det.state.state, CONTACT)
        self.assertTrue(det.state.control_eligible)
        for i in range(2):
            det.update(sample(8_000_000, True, i), t); t += 50_000_000
        self.assertEqual(det.state.state, RELEASE)
        self.assertFalse(det.state.control_eligible)

    def test_unverified_candidate_never_control_eligible(self):
        det, t = self.detector()
        for i in range(2):
            det.update(sample(7_900_000, False, i), t); t += 50_000_000
        self.assertEqual(det.state.state, CONTACT)
        self.assertEqual(det.state.quality, QUALITY_UNVERIFIED)
        self.assertFalse(det.state.control_eligible)

    def test_timeout_unknown(self):
        det, t = self.detector()
        det.tick(t + 1_000_000_000)
        self.assertEqual(det.state.state, UNKNOWN)

    def test_invalid_sample_unknown(self):
        det, t = self.detector()
        bad = sample(8_000_000); bad["ready"] = False
        det.update(bad, t)
        self.assertEqual(det.state.state, UNKNOWN)

    def test_recalibrate(self):
        det, t = self.detector()
        det.recalibrate(t)
        self.assertEqual(det.state.state, "CALIBRATING")


if __name__ == "__main__":
    unittest.main()
