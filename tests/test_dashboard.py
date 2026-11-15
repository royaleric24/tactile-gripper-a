"""Dashboard startup/accessibility checks without any hardware access."""

import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from datetime import datetime
from pathlib import Path

from tactile_gripper.control import build_core
from tactile_gripper.ui.charts import (
    bar_options,
    fsr_trend_options,
    moving_median,
    pwm_timeline_options,
    unified_timeline_options,
)
from tactile_gripper.ui.pages.analysis import _matches
from tactile_gripper.ui.server import create_ui
from tactile_gripper.ui.theme import clock_label

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for(url: str, timeout: float = 25.0) -> None:
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001 - startup polling
            last_error = exc
            time.sleep(0.25)
    raise AssertionError(f"server did not start: {last_error}")


class DashboardServerTests(unittest.TestCase):
    def _run_server(self, *extra: str):
        port = free_port()
        env = dict(os.environ, PYTHONPATH="src")
        proc = subprocess.Popen(
            [sys.executable, "-m", "tactile_gripper.ui", "--no-browser", "--port", str(port), *extra],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return proc, port

    def _stop(self, proc) -> str:
        proc.terminate()
        try:
            stdout, stderr = proc.communicate(timeout=12)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=5)
        return (stdout or "") + (stderr or "")

    def test_offline_pages_are_accessible(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, port = self._run_server("--data-root", tmp)
            base = f"http://127.0.0.1:{port}"
            try:
                wait_for(base + "/")
                for path in ("/", "/experiments", "/analysis", "/demo-6x6"):
                    with self.subTest(path=path):
                        with urllib.request.urlopen(base + path, timeout=5) as response:
                            self.assertEqual(response.status, 200)
                            body = response.read().decode("utf-8")
                            self.assertIn("触觉闭环机械爪 A", body)
                            if path == "/demo-6x6":
                                self.assertIn("36/36 格有值", body)
                                self.assertIn("SIMULATION ONLY", body)
                                self.assertNotIn("提交 PWM", body)
                log = self._stop(proc)
                self.assertNotIn("Traceback", log)
                self.assertFalse((Path(tmp) / "data" / "real").exists())
                self.assertFalse((Path(tmp) / "data" / "simulated").exists())
            finally:
                if proc.poll() is None:
                    proc.kill()

    def test_demo_mode_starts_and_writes_only_simulated_trials(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, port = self._run_server("--demo", "--data-root", tmp)
            base = f"http://127.0.0.1:{port}"
            try:
                wait_for(base + "/")
                time.sleep(1.0)
                # Demo mode has an active trial, so all three pages render their
                # populated branches (metadata/event tables), not just empty states.
                for path in ("/", "/experiments", "/analysis"):
                    with self.subTest(path=path):
                        with urllib.request.urlopen(base + path, timeout=5) as response:
                            self.assertEqual(response.status, 200)
                            self.assertIn("触觉闭环机械爪 A", response.read().decode("utf-8"))
                trials = Path(tmp) / "data" / "simulated" / "trials"
                self.assertTrue(trials.is_dir())
                self.assertTrue(any(trials.iterdir()))
                self.assertFalse((Path(tmp) / "data" / "real").exists())
                log = self._stop(proc)
                self.assertNotIn("Traceback", log)
            finally:
                if proc.poll() is None:
                    proc.kill()


    def test_follow_session_serves_readonly_monitor(self):
        import json

        fixtures = ROOT / "tests" / "fixtures" / "fsr2"
        hello = json.loads((fixtures / "hello_fsr1.json").read_text(encoding="utf-8"))
        sample = json.loads((fixtures / "sample_fsr1_valid.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "session"
            (session / "fsr").mkdir(parents=True)
            base = time.monotonic_ns() - 1_000_000_000
            now = datetime.fromtimestamp(base / 1e9).isoformat()
            records = [
                {"host_time_utc": now, "host_monotonic_ns": base, "direction": "RX", "message": hello},
                {"host_time_utc": now, "host_monotonic_ns": base + 16_000_000, "direction": "RX", "message": sample},
            ]
            (session / "fsr" / "fsr_stream.jsonl").write_text(
                "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
            )
            console = [
                {"timestamp_utc": now, "monotonic_ns": base, "event": "COMMAND",
                 "request": {"protocol_version": 1, "request_id": "h1", "command": "BENCH_HOLD", "sequence": 1, "pulse_us": 1500}},
                {"timestamp_utc": now, "monotonic_ns": base + 1_000_000, "event": "MATCHED",
                 "response": {"protocol_version": 1, "type": "ACK", "request_id": "h1",
                              "firmware_version": "gripper-control-s3-0.9b26.0", "state": "ACTIVE",
                              "output_state": "PWM_COMMANDED_UNMEASURED", "commanded_pulse_us": 1500,
                              "fault_reason": "TARGET_COMMANDED", "boot_id": "b1", "bench_active": True}},
            ]
            (session / "transport.jsonl").write_text(
                "".join(json.dumps(item) + "\n" for item in console), encoding="utf-8"
            )
            proc, port = self._run_server(
                "--source", "LIVE", "--follow-session", str(session), "--data-root", tmp
            )
            base_url = f"http://127.0.0.1:{port}"
            try:
                wait_for(base_url + "/")
                for path in ("/", "/experiments", "/analysis"):
                    with self.subTest(path=path):
                        with urllib.request.urlopen(base_url + path, timeout=5) as response:
                            self.assertEqual(response.status, 200)
                            self.assertIn("触觉闭环机械爪 A", response.read().decode("utf-8"))
                log = self._stop(proc)
                self.assertIn("LOG_FOLLOW", log)
                self.assertNotIn("Traceback", log)
                self.assertFalse((Path(tmp) / "data" / "real" / "trials").exists())
            finally:
                if proc.poll() is None:
                    proc.kill()


    def test_follow_record_writes_trial_sidecar_for_this_session(self):
        import json

        fixtures = ROOT / "tests" / "fixtures" / "fsr2"
        hello = json.loads((fixtures / "hello_fsr1.json").read_text(encoding="utf-8"))
        sample = json.loads((fixtures / "sample_fsr1_valid.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "session"
            (session / "fsr").mkdir(parents=True)
            base = time.monotonic_ns() - 1_000_000_000
            now = datetime.fromtimestamp(base / 1e9).isoformat()
            records = [
                {"host_time_utc": now, "host_monotonic_ns": base, "direction": "RX", "message": hello},
                {"host_time_utc": now, "host_monotonic_ns": base + 16_000_000, "direction": "RX", "message": sample},
            ]
            (session / "fsr" / "fsr_stream.jsonl").write_text(
                "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
            )
            console = [
                {"timestamp_utc": now, "monotonic_ns": base, "event": "COMMAND",
                 "request": {"protocol_version": 1, "request_id": "h1", "command": "BENCH_HOLD", "sequence": 1, "pulse_us": 1500}},
                {"timestamp_utc": now, "monotonic_ns": base + 1_000_000, "event": "MATCHED",
                 "response": {"protocol_version": 1, "type": "ACK", "request_id": "h1",
                              "firmware_version": "gripper-control-s3-0.9b26.0", "state": "ACTIVE",
                              "output_state": "PWM_COMMANDED_UNMEASURED", "commanded_pulse_us": 1500,
                              "fault_reason": "TARGET_COMMANDED", "boot_id": "b1", "bench_active": True}},
            ]
            (session / "transport.jsonl").write_text(
                "".join(json.dumps(item) + "\n" for item in console), encoding="utf-8"
            )
            proc, port = self._run_server(
                "--source", "LIVE", "--follow-session", str(session),
                "--follow-record", "--data-root", tmp,
            )
            base_url = f"http://127.0.0.1:{port}"
            try:
                wait_for(base_url + "/")
                time.sleep(1.5)
                log = self._stop(proc)
                self.assertNotIn("Traceback", log)
                sidecar = json.loads((session / "trial.json").read_text(encoding="utf-8"))
                self.assertEqual(sidecar["status"], "COMPLETED")
                trial_id = sidecar["trial_id"]
                self.assertTrue(trial_id)
                csv_path = Path(sidecar["csv"])
                replay_path = Path(sidecar["replay"])
                self.assertTrue(csv_path.is_file())
                self.assertTrue(replay_path.is_file())
                self.assertIn(trial_id, str(csv_path))
                rows = csv_path.read_text(encoding="utf-8").splitlines()
                self.assertGreaterEqual(len(rows), 2)
                self.assertIn("frame_seq", rows[0])
            finally:
                if proc.poll() is None:
                    proc.kill()


    def test_follow_session_attaches_pwm_log_created_after_start(self):
        import json

        fixtures = ROOT / "tests" / "fixtures" / "fsr2"
        hello = json.loads((fixtures / "hello_fsr1.json").read_text(encoding="utf-8"))
        sample = json.loads((fixtures / "sample_fsr1_valid.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "session"
            (session / "fsr").mkdir(parents=True)
            base = time.monotonic_ns() - 1_000_000_000
            now = datetime.fromtimestamp(base / 1e9).isoformat()
            records = [
                {"host_time_utc": now, "host_monotonic_ns": base, "direction": "RX", "message": hello},
                {"host_time_utc": now, "host_monotonic_ns": base + 16_000_000, "direction": "RX", "message": sample},
            ]
            (session / "fsr" / "fsr_stream.jsonl").write_text(
                "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
            )
            proc, port = self._run_server(
                "--source", "LIVE", "--follow-session", str(session),
                "--follow-record", "--data-root", tmp,
            )
            base_url = f"http://127.0.0.1:{port}"
            try:
                wait_for(base_url + "/")
                time.sleep(1.0)
                console = [
                    {"timestamp_utc": now, "monotonic_ns": base, "event": "COMMAND",
                     "request": {"protocol_version": 1, "request_id": "late1", "command": "BENCH_HOLD", "sequence": 1, "pulse_us": 1500}},
                    {"timestamp_utc": now, "monotonic_ns": base + 1_000_000, "event": "MATCHED",
                     "response": {"protocol_version": 1, "type": "ACK", "request_id": "late1",
                                  "firmware_version": "gripper-control-s3-0.9b26.0", "state": "ACTIVE",
                                  "output_state": "PWM_COMMANDED_UNMEASURED", "commanded_pulse_us": 1500,
                                  "fault_reason": "TARGET_COMMANDED", "boot_id": "b1", "bench_active": True}},
                ]
                (session / "transport.jsonl").write_text(
                    "".join(json.dumps(item) + "\n" for item in console), encoding="utf-8"
                )
                time.sleep(1.5)
                log = self._stop(proc)
                self.assertNotIn("Traceback", log)
                sidecar = json.loads((session / "trial.json").read_text(encoding="utf-8"))
                events = [
                    json.loads(line)
                    for line in (Path(sidecar["directory"]) / "events.jsonl").read_text(encoding="utf-8").splitlines()
                ]
                self.assertIn(
                    ("SET_PWM", 1500),
                    [(item.get("action"), item.get("commanded_pwm_us")) for item in events],
                )
            finally:
                if proc.poll() is None:
                    proc.kill()


class DashboardDisplayTests(unittest.TestCase):
    def test_bar_chart_shows_units_and_electrode_counts(self):
        frame = {"channels": [1500.0, None], "valid_mask": [True, False], "channel_ids": [0, 1]}
        options = bar_options(frame, None)
        self.assertEqual(options["yAxis"]["name"], "ADC 计数")
        self.assertTrue(options["series"][0]["label"]["show"])
        self.assertIsNone(options["series"][0]["data"][1]["value"])  # invalid stays absent, not zero

    def test_clock_label_converts_utc_to_local_and_keeps_bad_input(self):
        stamp = "2026-11-15T12:00:00+00:00"
        expected = datetime.fromisoformat(stamp).astimezone()
        self.assertEqual(clock_label(stamp, with_date=False), expected.strftime("%H:%M:%S"))
        self.assertEqual(clock_label(stamp), expected.strftime("%Y-%m-%d %H:%M:%S"))
        self.assertEqual(clock_label("not-a-stamp"), "not-a-stamp")
        self.assertEqual(clock_label(None), "—")


class DashboardChartTests(unittest.TestCase):
    def test_pwm_timeline_uses_command_not_position(self):
        events = [
            {
                "record_type": "CONTROL_EVENT",
                "action": "SET_PWM",
                "commanded_pwm_us": 1500,
                "timestamp_utc": "2026-11-13T06:00:00+00:00",
                "stage": "DEVICE_ACK",
                "device_ack": True,
            },
            {
                "record_type": "CONTROL_EVENT",
                "action": "SET_PWM",
                "commanded_pwm_us": 1520,
                "timestamp_utc": "2026-11-13T06:00:01+00:00",
                "stage": "FAILED",
                "device_ack": False,
            },
        ]
        options = pwm_timeline_options(events)
        self.assertEqual([item["value"] for item in options["series"][0]["data"]], [1500, 1520])
        self.assertEqual(options["yAxis"]["name"], "μs")
        self.assertNotIn("actual", str(options))


class FsrSmoothingTests(unittest.TestCase):
    def test_moving_median_preserves_length_and_invalid_gaps(self):
        values = [1.0, 100.0, 2.0, None, 4.0]
        smoothed = moving_median(values, 3)
        self.assertEqual(len(smoothed), len(values))
        self.assertEqual(smoothed[0], 50.5)
        self.assertEqual(smoothed[1], 2.0)
        self.assertIsNone(smoothed[3])

    def test_smoothed_trend_keeps_raw_series(self):
        history = [
            {"frame_seq": 1, "score": None, "readings": [{"channel_id": 0, "name": "FSR_A", "raw": 1000.0, "valid": True}]},
            {"frame_seq": 2, "score": None, "readings": [{"channel_id": 0, "name": "FSR_A", "raw": 900000.0, "valid": True}]},
            {"frame_seq": 3, "score": None, "readings": [{"channel_id": 0, "name": "FSR_A", "raw": 1100.0, "valid": True}]},
        ]
        raw = fsr_trend_options(history)
        smooth = fsr_trend_options(history, smooth_window=3)
        self.assertEqual(len(raw["series"]), 2)  # raw + score
        raw_data = smooth["series"][0]["data"]
        self.assertEqual(raw_data, [1000.0, 900000.0, 1100.0])  # raw never replaced
        names = [item["name"] for item in smooth["series"]]
        self.assertTrue(any("平滑" in name for name in names))
        smoothed = smooth["series"][1]["data"]
        self.assertLess(smoothed[1], 900000.0)

    def test_smoothed_timeline_keeps_raw_and_pwm(self):
        points = [
            {"ns": 1_000_000_000, "seq": 1, "raw": 1000.0, "valid": True},
            {"ns": 1_016_000_000, "seq": 2, "raw": 900000.0, "valid": True},
            {"ns": 1_032_000_000, "seq": 3, "raw": 1100.0, "valid": True},
        ]
        option = unified_timeline_options(
            points,
            [{"sent_ns": 1_010_000_000, "pulse_us": 1500, "ack": True, "result": "ACKED"}],
            smooth_window=3,
        )
        self.assertEqual(len(option["series"]), 3)  # raw + smooth + PWM
        self.assertEqual(option["series"][0]["data"][1][1], 900000.0)
        self.assertLess(option["series"][1]["data"][1][1], 900000.0)
        self.assertEqual(option["series"][2]["data"][0]["value"], [0.01, 1500])


class AnalysisFilterTests(unittest.TestCase):
    def test_filters_source_status_and_search(self):
        item = {
            "trial_id": "T-1",
            "name": "cup baseline",
            "source": "SIMULATION",
            "status": "COMPLETED",
            "operator": "eric",
            "video_path": "/tmp/cup.mov",
            "tags": ["cup"],
            "conditions": {"cup_type": "glass"},
        }
        self.assertTrue(_matches(item, "ALL", "ALL", ""))
        self.assertTrue(_matches(item, "SIMULATION", "COMPLETED", "glass"))
        self.assertTrue(_matches(item, "ALL", "ALL", "cup.mov"))
        self.assertFalse(_matches(item, "LIVE", "ALL", ""))
        self.assertFalse(_matches(item, "ALL", "INTERRUPTED", ""))
        self.assertFalse(_matches(item, "ALL", "ALL", "not-present"))


class DashboardStructureTests(unittest.TestCase):
    def test_pages_do_not_create_adapters(self):
        ui_root = ROOT / "src" / "tactile_gripper" / "ui"
        for path in ui_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertNotIn("GripperAdapter(", text)
                self.assertNotIn("serial.Serial", text)
                self.assertNotIn("SocketSerial", text)

    def test_analysis_page_has_no_control_write_path(self):
        text = (ROOT / "src" / "tactile_gripper" / "ui" / "pages" / "analysis.py").read_text(encoding="utf-8")
        for forbidden in ("request_pwm", "core.stop(", "core.connect_gripper", "begin_manual_session", "GripperAdapter"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_create_ui_does_not_replace_core_gripper(self):
        with tempfile.TemporaryDirectory() as tmp:
            core = build_core(source="SIMULATION", root=tmp)
            owner = core.gripper.owner
            create_ui(core)
            self.assertEqual(core.gripper.owner, owner)
            self.assertIs(core.gripper, core.gripper)


if __name__ == "__main__":
    unittest.main()
