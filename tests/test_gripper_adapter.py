"""Gripper adapter tests with a fake S3 transport (no serial device)."""

import tempfile
import unittest
from pathlib import Path

from tactile_gripper.devices.gripper import GripperAdapter, WriteAuthority
from tactile_gripper.errors import ControlDenied, OwnershipError, UnsupportedCommand
from tactile_gripper.models import ControlAction, ControlCommand
from tactile_gripper.sources import DataSource

from support import FakeBenchTransport


def make_adapter(tmp: str, transport, *, source=DataSource.LIVE, authority=None) -> GripperAdapter:
    return GripperAdapter(
        source=source,
        transport=transport,
        hardware_permission=source is DataSource.LIVE,
        authority=authority,
        log_path=Path(tmp) / "controller.jsonl",
        clock=lambda: 1000.0,
    )


class GripperProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.transport = FakeBenchTransport()

    def tearDown(self):
        self.tmp.cleanup()

    def test_connect_queries_status_without_pwm(self):
        adapter = make_adapter(self.tmp.name, self.transport)
        status = adapter.connect()
        self.assertEqual(status["state"], "DISARMED")
        self.assertEqual(adapter.status().state, "CONNECTED")
        self.assertEqual(self.transport.pwm_commands(), [])
        self.assertIn("GET_STATUS", [item["command"] for item in self.transport.commands])
        adapter.close()

    def test_begin_session_and_apply_pwm(self):
        adapter = make_adapter(self.tmp.name, self.transport)
        adapter.connect()
        begin = adapter.execute(
            ControlCommand(ControlAction.BEGIN_SESSION, DataSource.LIVE), mode="MANUAL"
        )
        self.assertEqual(begin.stage, "DEVICE_ACK")
        self.assertTrue(begin.serial_write_ok)
        self.assertTrue(begin.device_ack)
        self.assertIn("BEGIN_BENCH", [item["command"] for item in self.transport.commands])
        self.assertEqual(self.transport.pwm_commands(), [])

        applied = adapter.execute(
            ControlCommand(ControlAction.SET_PWM, DataSource.LIVE, target_pwm_us=1500),
            mode="MANUAL",
        )
        self.assertEqual(applied.stage, "DEVICE_ACK")
        self.assertEqual(applied.firmware_command, "BENCH_HOLD")
        self.assertEqual(applied.commanded_pwm_us, 1500)
        self.assertTrue(applied.serial_write_ok)
        self.assertTrue(applied.device_ack)
        self.assertIsNone(applied.actual_pwm_us)
        self.assertFalse(applied.actual_position_known)
        self.assertEqual(self.transport.pwm_commands()[-1]["pulse_us"], 1500)
        adapter.close()

    def test_local_range_rejection_does_not_write_pwm(self):
        adapter = make_adapter(self.tmp.name, self.transport)
        adapter.connect()
        adapter.execute(ControlCommand(ControlAction.BEGIN_SESSION, DataSource.LIVE), mode="MANUAL")
        before = len(self.transport.pwm_commands())
        rejected = adapter.execute(
            ControlCommand(ControlAction.SET_PWM, DataSource.LIVE, target_pwm_us=2600),
            mode="MANUAL",
        )
        self.assertEqual(rejected.stage, "REJECTED")
        self.assertIn("range", rejected.detail)
        self.assertEqual(len(self.transport.pwm_commands()), before)
        adapter.close()

    def test_device_error_response_enters_fault_without_retry(self):
        self.transport.reject_on = "BENCH_HOLD"
        adapter = make_adapter(self.tmp.name, self.transport)
        adapter.connect()
        adapter.execute(ControlCommand(ControlAction.BEGIN_SESSION, DataSource.LIVE), mode="MANUAL")
        failed = adapter.execute(
            ControlCommand(ControlAction.SET_PWM, DataSource.LIVE, target_pwm_us=1500),
            mode="MANUAL",
        )
        self.assertEqual(failed.stage, "FAILED")
        self.assertFalse(adapter.connected)
        self.assertEqual(adapter.state, "FAULT")
        self.assertEqual(len(self.transport.pwm_commands()), 1)
        adapter.close()

    def test_timeout_enters_fault(self):
        self.transport.timeout_on = "BENCH_HOLD"
        adapter = make_adapter(self.tmp.name, self.transport)
        adapter.connect()
        adapter.execute(ControlCommand(ControlAction.BEGIN_SESSION, DataSource.LIVE), mode="MANUAL")
        failed = adapter.execute(
            ControlCommand(ControlAction.SET_PWM, DataSource.LIVE, target_pwm_us=1500),
            mode="MANUAL",
        )
        self.assertEqual(failed.stage, "FAILED")
        self.assertIn("timeout", failed.detail.lower())
        self.assertEqual(adapter.state, "FAULT")
        adapter.close()

    def test_stop_and_stop_updates_are_distinct(self):
        adapter = make_adapter(self.tmp.name, self.transport)
        adapter.connect()
        adapter.execute(ControlCommand(ControlAction.BEGIN_SESSION, DataSource.LIVE), mode="MANUAL")
        adapter.execute(
            ControlCommand(ControlAction.SET_PWM, DataSource.LIVE, target_pwm_us=1500),
            mode="MANUAL",
        )
        updates = adapter.execute(
            ControlCommand(ControlAction.STOP_UPDATES, DataSource.LIVE), mode="MANUAL"
        )
        self.assertEqual(updates.stage, "SOFTWARE_ONLY")
        self.assertFalse(updates.serial_write_ok)
        stopped = adapter.execute(ControlCommand(ControlAction.STOP, DataSource.LIVE), mode="MANUAL")
        self.assertEqual(stopped.stage, "DEVICE_ACK")
        self.assertEqual(self.transport.commands[-1]["command"], "STOP")
        adapter.close()

    def test_hold_and_release_are_unsupported(self):
        adapter = make_adapter(self.tmp.name, self.transport)
        adapter.connect()
        before = len(self.transport.commands)
        for action in (ControlAction.HOLD, ControlAction.RELEASE):
            event = adapter.execute(ControlCommand(action, DataSource.LIVE), mode="MANUAL")
            self.assertEqual(event.stage, "UNSUPPORTED")
            self.assertIsNone(event.firmware_command)
        self.assertEqual(len(self.transport.commands), before)
        with self.assertRaises(UnsupportedCommand):
            adapter.hold()
        with self.assertRaises(UnsupportedCommand):
            adapter.release()
        adapter.close()

    def test_source_mismatch_rejected(self):
        adapter = make_adapter(self.tmp.name, self.transport)
        adapter.connect()
        event = adapter.execute(
            ControlCommand(ControlAction.SET_PWM, DataSource.SIMULATION, target_pwm_us=1500),
            mode="MANUAL",
        )
        self.assertEqual(event.stage, "REJECTED")
        self.assertIn("source mismatch", event.detail)
        adapter.close()

    def test_single_writer_authority(self):
        authority = WriteAuthority()
        first = make_adapter(self.tmp.name, self.transport, authority=authority)
        first.connect()
        second = GripperAdapter(
            source=DataSource.LIVE,
            transport=FakeBenchTransport(),
            hardware_permission=True,
            authority=authority,
            log_path=Path(self.tmp.name) / "controller-2.jsonl",
            clock=lambda: 1000.0,
        )
        with self.assertRaises(OwnershipError):
            second.connect()
        self.assertEqual(authority.owner, first.owner)
        first.close()
        self.assertIsNone(authority.owner)
        second.connect()
        second.close()


class SimulationGripperTests(unittest.TestCase):
    def test_simulation_never_claims_serial_write_or_ack(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = GripperAdapter(
                source=DataSource.SIMULATION,
                log_path=Path(tmp) / "sim.jsonl",
                clock=lambda: 1000.0,
            )
            self.assertTrue(adapter.dry_run)
            adapter.connect()
            begin = adapter.execute(
                ControlCommand(ControlAction.BEGIN_SESSION, DataSource.SIMULATION), mode="MANUAL"
            )
            self.assertEqual(begin.stage, "SIMULATED")
            self.assertFalse(begin.serial_write_ok)
            self.assertFalse(begin.device_ack)
            applied = adapter.execute(
                ControlCommand(ControlAction.SET_PWM, DataSource.SIMULATION, target_pwm_us=1500),
                mode="MANUAL",
            )
            self.assertEqual(applied.stage, "SIMULATED")
            self.assertFalse(applied.serial_write_ok)
            self.assertFalse(applied.device_ack)
            self.assertIsNone(applied.actual_pwm_us)
            adapter.close()

    def test_live_requires_explicit_permission(self):
        with self.assertRaises(ControlDenied):
            GripperAdapter(
                source=DataSource.LIVE,
                transport=FakeBenchTransport(),
                hardware_permission=False,
                log_path=Path(tempfile.gettempdir()) / "never-created.jsonl",
            )

    def test_replay_cannot_create_gripper(self):
        with self.assertRaises(ControlDenied):
            GripperAdapter(source=DataSource.REPLAY)

    def test_pwm_limits_come_from_config_and_are_labeled(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = GripperAdapter(
                source=DataSource.SIMULATION,
                log_path=Path(tmp) / "sim.jsonl",
            )
            limits = adapter.pwm_limits
            self.assertEqual(limits["min_us"], 500)
            self.assertEqual(limits["max_us"], 2500)
            self.assertIn("NOT a verified mechanical safety limit", limits["note"])
            self.assertTrue(limits["source"].endswith("config/gripper_s3.json:bench_min_us..bench_max_us"))


if __name__ == "__main__":
    unittest.main()
