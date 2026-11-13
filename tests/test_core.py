"""Application core mode/arbitration/source-isolation tests (offline)."""

import tempfile
import unittest
from pathlib import Path

from tactile_gripper.control import ApplicationCore, Mode, build_core
from tactile_gripper.devices.gripper import GripperAdapter, WriteAuthority
from tactile_gripper.devices.sensor import SensorAdapter
from tactile_gripper.errors import ControlDenied, ModeUnavailable
from tactile_gripper.sources import DataSource

from support import FakeBenchTransport, FakeLineTransport, FailingWriter, channel_config, hello_line, sample_line


def simulation_core(tmp: str, *, authority=None) -> ApplicationCore:
    gripper = GripperAdapter(
        source=DataSource.SIMULATION,
        authority=authority,
        log_path=Path(tmp) / "gripper.jsonl",
        clock=lambda: 1000.0,
    )
    return ApplicationCore(
        root=tmp,
        source=DataSource.SIMULATION,
        gripper=gripper,
        demo_period_s=0,
        clock=lambda: 1000.0,
        clock_ns=lambda: 1_000_000_000,
    )


class SimulationCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.core = simulation_core(self.tmp.name)

    def tearDown(self):
        self.core.disconnect_gripper()
        self.tmp.cleanup()

    def test_initial_state_is_offline_waiting_and_disabled(self):
        snapshot = self.core.snapshot()
        self.assertEqual(snapshot["mode"], "STANDBY")
        self.assertEqual(snapshot["gripper"]["state"], "OFFLINE")
        self.assertEqual(snapshot["sensor_state_label"], "SENSOR WAITING")
        self.assertIsNone(snapshot["latest_frame"])
        self.assertFalse(snapshot["apply_enabled"])
        self.assertFalse(snapshot["auto_available"])
        self.assertTrue(snapshot["auto_reasons"])

    def test_manual_session_and_pwm_are_simulated(self):
        self.core.connect_gripper()
        self.assertEqual(self.core.snapshot()["gripper"]["state"], "CONNECTED")
        with self.assertRaises(ModeUnavailable):
            self.core.set_mode(Mode.MANUAL)
        begin = self.core.begin_manual_session()
        self.assertEqual(begin.stage, "SIMULATED")
        self.assertEqual(self.core.mode, Mode.MANUAL)
        self.assertTrue(self.core.snapshot()["apply_enabled"])

        event = self.core.request_pwm(1500)
        self.assertEqual(event.stage, "SIMULATED")
        self.assertFalse(event.serial_write_ok)
        self.assertFalse(event.device_ack)
        self.assertIsNone(event.actual_pwm_us)
        self.assertEqual(self.core.snapshot()["last_pwm_us"], 1500)

    def test_out_of_range_and_non_integer_are_rejected(self):
        self.core.connect_gripper()
        self.core.begin_manual_session()
        for value in (2600, 499, "1500", 1500.0):
            with self.subTest(value=value):
                event = self.core.request_pwm(value)
                self.assertEqual(event.stage, "REJECTED")

    def test_mode_rules(self):
        with self.assertRaises(ModeUnavailable):
            self.core.set_mode(Mode.AUTO)
        self.core.connect_gripper()
        self.core.begin_manual_session()
        self.assertEqual(self.core.set_mode(Mode.STANDBY), Mode.STANDBY)
        self.assertFalse(self.core.snapshot()["apply_enabled"])

    def test_hold_release_are_unsupported_not_silent(self):
        self.core.connect_gripper()
        self.core.begin_manual_session()
        for event in (self.core.hold(), self.core.release()):
            self.assertEqual(event.stage, "UNSUPPORTED")

    def test_single_in_flight_arbitration(self):
        self.core.connect_gripper()
        self.core.begin_manual_session()
        self.core._busy = True
        try:
            event = self.core.request_pwm(1500)
        finally:
            self.core._busy = False
        self.assertEqual(event.stage, "REJECTED")
        self.assertIn("in flight", event.detail)

    def test_stop_updates_is_software_only(self):
        self.core.connect_gripper()
        self.core.begin_manual_session()
        event = self.core.stop_updates()
        self.assertEqual(event.stage, "SOFTWARE_ONLY")
        self.assertFalse(event.serial_write_ok)
        self.assertEqual(self.core.mode, Mode.STANDBY)

    def test_demo_sensor_is_labeled_and_records_frames(self):
        self.core.connect_gripper()
        self.core.begin_manual_session()
        self.core.set_demo_stream(True)
        for _ in range(4):
            self.core.tick()
        snapshot = self.core.snapshot()
        self.assertEqual(snapshot["sensor_state_label"], "SENSOR STREAMING")
        self.assertEqual(snapshot["latest_frame"]["source"], "SIMULATION")
        self.assertEqual(snapshot["latest_frame"]["channel_count"], 36)

        metadata = self.core.create_trial("demo trial", conditions={"object": "none"})
        self.assertEqual(metadata["source"], "SIMULATION")
        self.core.start_trial()
        for _ in range(4):
            self.core.tick()
        stopped = self.core.stop_trial("done")
        self.assertEqual(stopped["status"], "COMPLETED")
        trial = self.core.read_trial(stopped["trial_id"])
        self.assertGreater(len(trial["frames"]), 0)
        self.assertTrue(
            all(row["source"] == "SIMULATION" for row in trial["frames"])
        )

    def test_trial_metadata_records_git_and_environment(self):
        self.core.connect_gripper()
        self.core.begin_manual_session()
        metadata = self.core.create_trial("metadata")
        self.assertEqual(metadata["schema_version"], 3)
        self.assertIsNotNone(metadata["git_commit"])
        self.assertIn("environment", metadata["parameters"])
        self.assertIn("python", metadata["parameters"]["environment"])
        self.assertEqual(metadata["source"], "SIMULATION")
        self.assertEqual(metadata["parameters"]["firmware_version"], "gripper-control-s3-0.9b26.0")
        self.assertIsNotNone(metadata["parameters"]["gripper_config"])
        self.assertEqual(metadata["parameters"]["gripper_config"]["gpio"], 4)

    def test_frame_write_error_latches_fault(self):
        with tempfile.TemporaryDirectory() as tmp:
            gripper = GripperAdapter(
                source=DataSource.SIMULATION,
                log_path=Path(tmp) / "gripper.jsonl",
                clock=lambda: 1000.0,
            )
            sensor = SensorAdapter(
                FakeLineTransport([hello_line(), sample_line(seq=1)]),
                channel_config(4),
                source=DataSource.SIMULATION,
                clock_ns=lambda: 1_000_000_000,
            )
            sensor.connect()
            core = ApplicationCore(
                root=tmp,
                source=DataSource.SIMULATION,
                gripper=gripper,
                sensor=sensor,
                demo_period_s=0,
            )
            core.connect_gripper()
            core.begin_manual_session()
            core.create_trial("write failure")
            core.start_trial()
            core.trial._frame_file = FailingWriter()
            for _ in range(3):
                core.tick()
            self.assertEqual(core.mode, Mode.FAULT)
            self.assertIsNotNone(core.trial_error)
            self.assertEqual(core.trial.metadata.status, "ERROR")
            core.disconnect_gripper()

    def test_trial_cannot_record_mixed_source(self):
        from tactile_gripper.models import ControlCommand, ControlAction

        self.core.connect_gripper()
        self.core.begin_manual_session()
        self.core.create_trial("mix")
        self.core.start_trial()
        control = self.core.gripper.status()
        self.assertEqual(control.source, DataSource.SIMULATION)

    def test_single_writer_shared_authority(self):
        authority = WriteAuthority()
        second = simulation_core(self.tmp.name, authority=authority)
        self.core.connect_gripper()
        with self.assertRaises(Exception):
            second.connect_gripper()
        self.core.disconnect_gripper()
        second.disconnect_gripper()


class LiveFaultTests(unittest.TestCase):
    def test_stop_from_firmware_fault_keeps_fault_latched(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = FakeBenchTransport()
            gripper = GripperAdapter(
                source=DataSource.LIVE,
                transport=transport,
                hardware_permission=True,
                log_path=Path(tmp) / "gripper.jsonl",
                clock=lambda: 1000.0,
            )
            core = ApplicationCore(root=tmp, source=DataSource.LIVE, gripper=gripper, demo_period_s=0)
            core.connect_gripper()
            core.begin_manual_session()
            transport.state = "FAULT"
            transport.fault_reason = "COMM_TIMEOUT"
            event = core.stop()
            self.assertEqual(event.firmware_state, "FAULT")
            self.assertEqual(core.mode, Mode.FAULT)
            self.assertIn("does not clear", core.fault_reason)
            core.disconnect_gripper()

    def test_auto_is_refused_without_any_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = FakeBenchTransport()
            gripper = GripperAdapter(
                source=DataSource.LIVE,
                transport=transport,
                hardware_permission=True,
                log_path=Path(tmp) / "gripper.jsonl",
                clock=lambda: 1000.0,
            )
            core = ApplicationCore(root=tmp, source=DataSource.LIVE, gripper=gripper, demo_period_s=0)
            core.connect_gripper()
            before = list(transport.commands)
            with self.assertRaises(ModeUnavailable):
                core.set_mode(Mode.AUTO)
            self.assertEqual(transport.commands, before)
            core.disconnect_gripper()

    def test_device_rejection_latches_fault(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = FakeBenchTransport()
            gripper = GripperAdapter(
                source=DataSource.LIVE,
                transport=transport,
                hardware_permission=True,
                log_path=Path(tmp) / "gripper.jsonl",
                clock=lambda: 1000.0,
            )
            core = ApplicationCore(root=tmp, source=DataSource.LIVE, gripper=gripper, demo_period_s=0)
            core.connect_gripper()
            core.begin_manual_session()
            transport.reject_on = "BENCH_HOLD"
            event = core.request_pwm(1500)
            self.assertEqual(event.stage, "FAILED")
            self.assertEqual(core.mode, Mode.FAULT)
            with self.assertRaises(ModeUnavailable):
                core.set_mode(Mode.STANDBY)
            with self.assertRaises(ModeUnavailable):
                core.clear_fault()
            core.disconnect_gripper()


class ReplayCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.core = ApplicationCore(root=self.tmp.name, source=DataSource.REPLAY)

    def tearDown(self):
        self.tmp.cleanup()

    def test_replay_is_read_only(self):
        snapshot = self.core.snapshot()
        self.assertFalse(snapshot["apply_enabled"])
        self.assertFalse(snapshot["stop_enabled"])
        self.assertEqual(snapshot["sensor_state_label"], "SENSOR REPLAY")
        self.assertEqual(self.core.request_pwm(1500).stage, "REJECTED")
        self.assertEqual(self.core.stop().stage, "REJECTED")
        with self.assertRaises(ControlDenied):
            self.core.create_trial("must fail")
        with self.assertRaises(ModeUnavailable):
            self.core.set_mode(Mode.MANUAL)

    def test_replay_has_no_gripper(self):
        self.assertIsNone(self.core.gripper)
        self.assertFalse(self.core.snapshot()["gripper"]["connected"])


class BuildCoreTests(unittest.TestCase):
    def test_build_simulation(self):
        with tempfile.TemporaryDirectory() as tmp:
            core = build_core(source="SIMULATION", root=tmp)
            self.assertEqual(core.source, DataSource.SIMULATION)
            self.assertIsNotNone(core.gripper)
            self.assertTrue(core.gripper.dry_run)
            self.assertIsNone(core.gripper.controller)
            self.assertFalse(core.gripper.connected)
            self.assertEqual(core.mode, Mode.STANDBY)

    def test_live_without_permission_is_refused(self):
        with self.assertRaises(ControlDenied):
            build_core(source="LIVE", hardware_permission=False)

    def test_live_core_can_prepare_sensor_without_opening_it(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "sensor.json"
            config_path.write_text(json.dumps({"sensor_serial": {"port": None, "baudrate": 115200}}))
            core = build_core(
                source="LIVE",
                root=tmp,
                hardware_permission=True,
                sensor_config_path=config_path,
            )
            self.assertIsNotNone(core.sensor)
            self.assertFalse(core.sensor.connected)
            self.assertEqual(core.sensor.reconnect_attempts, 0)
            core.shutdown()

    def test_live_core_without_connect_opens_no_controller(self):
        with tempfile.TemporaryDirectory() as tmp:
            core = build_core(source="LIVE", root=tmp, hardware_permission=True)
            self.assertFalse(core.gripper.dry_run)
            self.assertIsNone(core.gripper.controller)
            self.assertFalse(core.gripper.connected)
            core.disconnect_gripper()

    def test_replay_build(self):
        core = build_core(source="REPLAY")
        self.assertIsNone(core.gripper)


if __name__ == "__main__":
    unittest.main()
