"""P3-B4 launcher gate tests: no PWM console unless the FSR capture is ready.

These tests never touch hardware.  The integration case starts the launcher
with a deliberately missing ``/dev/cu.*`` port so the FSR capture exits
immediately; the launcher must abort before starting the Dashboard or the
PWM console.
"""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_launcher():
    spec = importlib.util.spec_from_file_location(
        "run_live_monitor_under_test", ROOT / "scripts" / "run_live_monitor.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


LAUNCHER = load_launcher()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class FakeProcess:
    def __init__(self, returncode: int | None = None):
        self.returncode = returncode

    def poll(self) -> int | None:
        return self.returncode


class MutableProcess(FakeProcess):
    pass


def write_hello(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "host_time_utc": "2026-11-16T00:00:00+00:00",
        "host_monotonic_ns": 1,
        "direction": "RX",
        "message": {"type": "HELLO", "sensor_profile": "FSR_ONLY"},
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


class FsrHelloGateTests(unittest.TestCase):
    def test_ready_when_hello_exists_and_capture_alive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fsr.jsonl"
            write_hello(path)
            ready, reason = LAUNCHER.wait_for_fsr_hello(
                path, timeout_s=1.0, process=FakeProcess(None)
            )
            self.assertTrue(ready)
            self.assertEqual(reason, "hello")

    def test_hello_after_capture_exit_is_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fsr.jsonl"
            write_hello(path)
            ready, reason = LAUNCHER.wait_for_fsr_hello(
                path, timeout_s=1.0, process=FakeProcess(2)
            )
            self.assertFalse(ready)
            self.assertEqual(reason, "fsr_exited:2")

    def test_capture_exit_before_hello_is_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fsr.jsonl"
            path.write_text("", encoding="utf-8")
            ready, reason = LAUNCHER.wait_for_fsr_hello(
                path, timeout_s=2.0, process=FakeProcess(134)
            )
            self.assertFalse(ready)
            self.assertEqual(reason, "fsr_exited:134")

    def test_timeout_without_hello_is_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fsr.jsonl"
            path.write_text("", encoding="utf-8")
            started = time.monotonic()
            ready, reason = LAUNCHER.wait_for_fsr_hello(
                path, timeout_s=0.4, process=FakeProcess(None)
            )
            self.assertFalse(ready)
            self.assertEqual(reason, "hello_timeout")
            self.assertLess(time.monotonic() - started, 2.0)


class TrialArtifactTests(unittest.TestCase):
    def test_reads_only_this_sessions_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "session"
            session.mkdir()
            (session / "trial.json").write_text(
                json.dumps(
                    {
                        "trial_id": "T-this",
                        "status": "COMPLETED",
                        "csv": "/tmp/this/frames.csv",
                        "replay": "/tmp/this/replay.jsonl",
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(LAUNCHER.read_trial_artifacts(session)["trial_id"], "T-this")

    def test_missing_sidecar_never_falls_back_to_global_newest_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "session"
            session.mkdir()
            newer = Path(tmp) / "data" / "real" / "trials" / "T-other"
            newer.mkdir(parents=True)
            (newer / "frames.csv").write_text("frame_seq\n", encoding="utf-8")
            self.assertIsNone(LAUNCHER.read_trial_artifacts(session))


class ConsoleFailureLifecycleTests(unittest.TestCase):
    def test_abnormal_console_exit_keeps_dashboard_and_fsr_alive(self):
        dashboard = MutableProcess(None)
        fsr = MutableProcess(None)
        sleeps = []

        def sleeper(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 3:
                dashboard.returncode = 0

        result = LAUNCHER.wait_after_console_failure(
            dashboard,
            fsr,
            fsr_enabled=True,
            sleeper=sleeper,
        )
        self.assertEqual(result, "dashboard_exit")
        self.assertEqual(len(sleeps), 3)
        self.assertIsNone(fsr.returncode)

    def test_invalid_sidecar_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "session"
            session.mkdir()
            (session / "trial.json").write_text("{not json", encoding="utf-8")
            self.assertIsNone(LAUNCHER.read_trial_artifacts(session))


class LauncherAbortIntegrationTests(unittest.TestCase):
    def test_fsr_failure_aborts_before_dashboard_and_console(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "session"
            env = dict(os.environ, PYTHONPATH="src:.")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run_live_monitor.py"),
                    "--fsr-port",
                    "/dev/cu.p3b-does-not-exist",
                    "--fsr-timeout",
                    "5",
                    "--session",
                    str(session),
                    "--no-console",
                    "--no-browser",
                    "--web-port",
                    str(free_port()),
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=90,
            )
            self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
            self.assertIn("不会启动 PWM Console", proc.stdout)
            self.assertIn("FSR 未就绪", proc.stdout)
            # Neither writer nor Dashboard may have been started.
            self.assertFalse((session / "transport.jsonl").exists())
            self.assertFalse((session / "dashboard.log").exists())
            metadata = json.loads((session / "session.json").read_text(encoding="utf-8"))
            self.assertIn("aborted", metadata)
            self.assertTrue(
                str(metadata["aborted"]).startswith("fsr_exited")
                or metadata["aborted"] == "hello_timeout"
            )


if __name__ == "__main__":
    unittest.main()
