"""Dashboard startup/accessibility checks without any hardware access."""

import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from tactile_gripper.control import build_core
from tactile_gripper.ui.server import create_ui

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
                for path in ("/", "/experiments", "/analysis"):
                    with self.subTest(path=path):
                        with urllib.request.urlopen(base + path, timeout=5) as response:
                            self.assertEqual(response.status, 200)
                            body = response.read().decode("utf-8")
                            self.assertIn("Tactile Gripper A", body)
                log = self._stop(proc)
                self.assertNotIn("Traceback", log)
                self.assertFalse((Path(tmp) / "data" / "real").exists())
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
                with urllib.request.urlopen(base + "/", timeout=5) as response:
                    self.assertEqual(response.status, 200)
                trials = Path(tmp) / "data" / "simulated" / "trials"
                self.assertTrue(trials.is_dir())
                self.assertTrue(any(trials.iterdir()))
                self.assertFalse((Path(tmp) / "data" / "real").exists())
                log = self._stop(proc)
                self.assertNotIn("Traceback", log)
            finally:
                if proc.poll() is None:
                    proc.kill()


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
