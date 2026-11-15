import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from tools.contact_detection.config import DetectorConfig
from tools.contact_detection.detector import ContactDetector
from tools.contact_detection.state import DemoState
from tools.contact_detection.store import TrialStore
from tools.contact_detection.webapp import start_web


class WebTests(unittest.TestCase):
    def test_state_and_recalibrate_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TrialStore(Path(tmp), source="test", data_kind="SIMULATED", label="R4C3", config={})
            state = DemoState(store, ContactDetector(DetectorConfig(baseline_frames=2)), "test")
            state.on_sample({"seq": 1, "counts": 8_000_000, "ready": True, "read_ok": True,
                             "restored_before_cs": True, "post_cs_high": True})
            server, thread = start_web(state, 0)
            try:
                port = server.server_address[1]
                with urllib.request.urlopen("http://127.0.0.1:{}/api/state".format(port), timeout=3) as r:
                    body = json.loads(r.read().decode())
                self.assertEqual(body["data_kind"], "SIMULATED")
                self.assertIn("detection", body)
                req = urllib.request.Request("http://127.0.0.1:{}/api/recalibrate".format(port), data=b"", method="POST")
                with urllib.request.urlopen(req, timeout=3) as r:
                    recal = json.loads(r.read().decode())
                self.assertIn("detection", recal)
            finally:
                server.shutdown(); server.server_close()
                store.finalize()


if __name__ == "__main__":
    unittest.main()
