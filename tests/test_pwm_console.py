"""SIMULATED console menu over pipes; no serial device is opened."""
import os, subprocess, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

import scripts.pwm_console as pwm_console


def run_menu(lines, timeout=20, extra=None):
    p = subprocess.Popen(
        [sys.executable, "-u", "scripts/pwm_console.py", *(extra or [])],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=dict(os.environ, PYTHONPATH="src"),
    )
    try:
        for line in lines:
            p.stdin.write(line + "\n")
            p.stdin.flush()
            time.sleep(0.2)
        p.stdin.close()
        out = p.stdout.read()
        err = p.stderr.read()
        p.wait(timeout=timeout)
        p.stdout.close()
        p.stderr.close()
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
    return p.returncode, out, err


class ConsoleMenuTests(unittest.TestCase):
    def test_session_error_returns_distinct_nonzero_exit(self):
        instances = []

        class FailingController:
            def __init__(self, **kwargs):
                self.config = {"firmware_version": "test-firmware"}
                self.events = []
                instances.append(self)

            def connect(self, _port):
                return {"state": "DISARMED"}

            def begin(self, *, assembled):
                raise RuntimeError("response_timeout")

            def log(self, event, **values):
                self.events.append((event, values))

            def close(self):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            argv = ["pwm_console.py", "--log-dir", str(Path(tmp) / "session")]
            with (
                patch.object(sys, "argv", argv),
                patch.object(pwm_console, "BenchController", FailingController),
                patch.object(pwm_console, "choose_menu", return_value="mech"),
            ):
                rc = pwm_console.main()
        self.assertEqual(rc, pwm_console.EXIT_COMMUNICATION_ERROR)
        exits = [values for event, values in instances[0].events if event == "CONSOLE_EXIT"]
        self.assertEqual(exits[-1]["status"], "COMMUNICATION_ERROR")
        self.assertEqual(exits[-1]["exit_code"], pwm_console.EXIT_COMMUNICATION_ERROR)

    def test_mechanical_continuous_flow(self):
        rc, out, err = run_menu(["1", "1500", "1400", "1200", "stop", "0"])
        self.assertEqual(rc, 0, err)
        self.assertIn("GRIPPER_ASSEMBLED", out)
        self.assertIn("ACK 1500", out)
        self.assertIn("ACK 1400", out)
        self.assertIn("ACK 1200", out)
        self.assertIn("STOP sent", out)

    def test_detached_flow(self):
        rc, out, err = run_menu(["2", "1500", "stop", "0"])
        self.assertEqual(rc, 0, err)
        self.assertIn("DETACHED_BENCH", out)
        self.assertIn("ACK 1500", out)

    def test_exit_without_pwm(self):
        rc, out, err = run_menu(["0"])
        self.assertEqual(rc, 0, err)
        self.assertNotIn("ACK", out)

    def test_help_and_status(self):
        rc, out, err = run_menu(["1", "help", "status", "stop", "0"])
        self.assertEqual(rc, 0, err)
        self.assertIn("number (500..2500", out)
        self.assertIn("firmware_version", out)

    def test_invalid_choice_and_range(self):
        rc, out, err = run_menu(["9", "1", "2501", "1500", "stop", "0"])
        self.assertEqual(rc, 0, err)
        self.assertIn("Invalid choice", out)
        self.assertIn("range_500_2500", out)
        self.assertIn("ACK 1500", out)

    def test_s3_target_profile(self):
        rc, out, err = run_menu(
            ["1", "1500", "1400", "1200", "1150", "stop", "0"],
            extra=["--target", "s3"],
        )
        self.assertEqual(rc, 0, err)
        self.assertIn("Target: s3", out)
        self.assertIn("gripper-control-s3-0.9b26.0", out)
        for pulse in ("1500", "1400", "1200", "1150"):
            self.assertIn(f"ACK {pulse}", out)
        self.assertIn("STOP sent", out)
