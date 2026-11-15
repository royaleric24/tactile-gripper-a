"""Exercise the same adapter, core, CSV and replay path used by the Dashboard."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tactile_gripper.control import build_core
from tactile_gripper.control.auto import AUTO_REAL_ENABLED
from tactile_gripper.devices.firmware_fixture import FIXTURE_ROOT, FirmwareFixtureTransport
from tactile_gripper.devices.sensor import SensorAdapter
from tactile_gripper.errors import ControlDenied
from tactile_gripper.sources import DataSource
from tactile_gripper.ui.charts import bar_options, matrix_view


class Clock:
    now = 10_000_000_000

    def __call__(self):
        return self.now


def drain(core):
    for _ in range(8):
        core.tick()


def load(name):
    return json.loads((FIXTURE_ROOT / (name + ".json")).read_bytes())


def line(value):
    return json.dumps(value).encode() + b"\n"


class FixtureCoreTests(unittest.TestCase):
    def test_dashboard_trials_csv_and_replay_use_original_wire_frames(self):
        cases = (
            ("fsr", 2, 2, "sample_fsr_only_valid"),
            ("fsr-adc4-fault", 2, 0, "sample_fsr_only_no_adc4"),
            ("electrodes12", 12, 12, "sample_electrodes12_mapped_synthetic"),
            ("electrodes12-partial", 12, 8, "sample_electrodes12_mapped_adc_absent"),
            ("electrodes12-fsr2", 14, 2, "sample_electrodes12_fsr2_unmapped"),
            ("electrodes12-fsr2-adc4-fault", 14, 0, "sample_electrodes12_fsr2_fsr_absent"),
        )
        with patch("serial.Serial", side_effect=AssertionError("no hardware")):
            for case, count, valid, fixture in cases:
                with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                    core = build_core(root=tmp, firmware_fixture=case)
                    core.tick()
                    trial_id = core.create_trial(case)["trial_id"]
                    core.start_trial()
                    drain(core)
                    snapshot = core.snapshot()
                    self.assertEqual(snapshot["sensor"]["state"], "FIXTURE_COMPLETE")
                    self.assertEqual(snapshot["source"], "SIMULATION")
                    self.assertEqual(snapshot["latest_frame"]["valid_count"], valid)
                    self.assertEqual(snapshot["latest_frame"]["channel_count"], count)
                    self.assertEqual(snapshot["latest_frame"]["channels"], load(fixture)["raw_adc"])
                    self.assertEqual(snapshot["sensor"]["detail"]["adc_status"], load(fixture)["adc_status"])
                    self.assertIsNone(snapshot["last_sensor_error"])
                    if valid < count:
                        status = snapshot["sensor"]["detail"]["last_status"]
                        if "fault" in case or case == "electrodes12-partial":
                            self.assertEqual(status["detail"]["wire"]["request_id"], "fixture-status-1")
                    config = snapshot["sensor_config"]
                    if count >= 12:
                        self.assertEqual(matrix_view(config), "ELECTRODES")
                        chart = bar_options(snapshot["latest_frame"], config, electrode_only=True)
                        self.assertEqual(chart["xAxis"]["data"], [f"{axis}{i}" for axis in "RC" for i in range(1, 7)])
                        if count == 14:
                            self.assertTrue(all(item["value"] is None for item in chart["series"][0]["data"]))
                    if count in (2, 14):
                        self.assertEqual([reading["name"] for reading in snapshot["fsr_assessment"]["readings"]],
                                         ["FSR_A", "FSR_B"])
                        self.assertTrue(all(reading["voltage_uv"] is None
                                            for reading in snapshot["fsr_assessment"]["readings"]))
                    core.stop_trial()
                    rows = core.read_trial(trial_id)["frames"]
                    self.assertEqual(rows[-1]["raw"], load(fixture))
                    csv_path = core.trial_store.export_csv(trial_id)
                    with csv_path.open(newline="") as handle:
                        last = list(csv.DictReader(handle))[-1]
                    self.assertEqual(int(last["valid_count"]), valid)
                    for idx, value in enumerate(load(fixture)["raw_adc"]):
                        self.assertEqual(last[f"ch_{idx}"], "" if value is None else str(value))
                        self.assertEqual(last[f"valid_{idx}"], "false" if value is None else "true")
                    export = core.trial_store.export_replay_jsonl(trial_id)
                    for path in (export, export.with_name("frames.jsonl")):
                        replay = build_core(source="REPLAY", root=tmp, sensor_file=path)
                        drain(replay)
                        snap = replay.snapshot()
                        self.assertEqual(snap["sensor"]["state"], "REPLAY")
                        self.assertEqual(snap["latest_frame"]["source"], "REPLAY")
                        self.assertEqual(snap["latest_frame"]["valid_count"], valid)
                        self.assertEqual(snap["sensor_config"], config)
                        self.assertIsNone(replay.gripper)
                        with self.assertRaises(ControlDenied):
                            replay.create_trial("read-only")
                        replay.shutdown()
                    self.assertFalse((Path(tmp) / "data" / "real").exists())
                    core.shutdown()

    def test_auto_fails_closed_on_real_fixture_pipeline(self):
        clock = Clock()
        self.assertFalse(AUTO_REAL_ENABLED)
        with tempfile.TemporaryDirectory() as tmp, patch("serial.Serial", side_effect=AssertionError("no hardware")):
            core = build_core(root=tmp, firmware_fixture="fsr")
            core.clock_ns = core.sensor.clock_ns = clock
            drain(core)
            core.capture_fsr_baseline()
            self.assertEqual(core.snapshot()["fsr_assessment"]["state"], "NO_CONTACT")
            with patch.object(core.gripper, "execute", side_effect=AssertionError("no dispatch")):
                self.assertEqual(core.evaluate_auto_contact().action, "STEP")
                core.pending_command = {"command_id": "unacknowledged"}
                self.assertEqual(core.evaluate_auto_contact().action, "WAIT")
                core.pending_command = None
                core.last_pwm_command = {"acknowledged": False}
                self.assertEqual(core.evaluate_auto_contact().action, "WAIT")
                core.last_pwm_command = None
                clock.now += 300_000_000
                self.assertEqual(core.evaluate_auto_contact().action, "FAULT")
                core.sensor.close()
                self.assertEqual(core.evaluate_auto_contact().action, "FAULT")
            core.shutdown()

            for fixture in ("fsr-adc4-fault", "electrodes12-fsr2"):
                bad = build_core(root=tmp, firmware_fixture=fixture)
                bad.clock_ns = bad.sensor.clock_ns = clock
                drain(bad)
                self.assertEqual(bad.evaluate_auto_contact().action, "FAULT")
                bad.shutdown()

    def test_conflicts_restart_wrap_and_invalid_frames(self):
        clock = Clock()
        base_hello = load("hello_fsr_only")
        first = load("sample_fsr_only_valid")
        second = {**first, "frame_seq": 3, "timestamp_us": 0, "mcu_time_us": 0}
        first["timestamp_us"] = first["mcu_time_us"] = 0xFFFFFFFE
        new_hello = {**base_hello, "boot_id": "p3a-synthetic-new-boot"}
        new_first = load("sample_fsr_only_valid")
        new_first["boot_id"] = new_hello["boot_id"]
        conflict = {**base_hello, "channel_config": {**base_hello["channel_config"], "sensor_profile": "MATRIX_ELECTRODES_12"}}
        historical = {**base_hello, "sensor_profile": "HYBRID_6X6_FSR2"}
        status = load("status_fsr_only_no_adc4")
        status["channel_config"]["sensor_profile"] = "MATRIX_ELECTRODES_12"
        bad_null = load("sample_fsr_only_no_adc4")
        bad_null["raw_adc"][0] = 0
        transport = FirmwareFixtureTransport("fsr")
        transport.lines = [
            line(first), line(conflict), line(historical), line(base_hello), line(first),
            line(second), line(first), b"{malformed\n", line(status), line(bad_null),
            line(new_first), line(new_hello), line(new_first),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            core = build_core(root=tmp, firmware_fixture="fsr")
            core.sensor = SensorAdapter(transport, None, source=DataSource.SIMULATION, strict_v2=True, clock_ns=clock)
            core.clock_ns = clock
            core.connect_sensor()
            for code in ("MISSING_CONFIG", "PROFILE_CONFLICT", "PROFILE_HISTORICAL"):
                core.tick()
                self.assertTrue(core.last_sensor_error.startswith(code), core.last_sensor_error)
            core.tick()  # HELLO
            core.tick()  # two good frames; regression rejected
            self.assertEqual(core.snapshot()["latest_frame"]["mcu_time_us"], 0)
            for code in ("SEQUENCE_REGRESSION", "INVALID_JSON", "PROFILE_CONFLICT", "ZERO_FOR_INVALID", "SESSION_CONFLICT"):
                self.assertTrue(core.last_sensor_error.startswith(code), core.last_sensor_error)
                self.assertNotEqual(core.evaluate_auto_contact().action, "STEP")
                core.tick()
            self.assertIsNone(core.latest_frame)
            self.assertFalse(core.contact_assessor.baseline_ready)
            core.tick()
            self.assertEqual(core.snapshot()["sensor"]["restart_count"], 1)
            self.assertEqual(core.latest_frame.boot_id, new_hello["boot_id"])
            core.shutdown()

    def test_missed_hello_and_status_timeouts_use_only_firmware_queries(self):
        clock = Clock()
        class Transport:
            def __init__(self):
                self.lines = []
                self.writes = []
            def connect(self): pass
            def close(self): pass
            def readline(self, timeout_s): return self.lines.pop(0) if self.lines else None
            def write_line(self, payload): self.writes.append(json.loads(payload))

        transport = Transport()
        sensor = SensorAdapter(transport, None, source=DataSource.LIVE, strict_v2=True,
                               request_hello_on_connect=True, clock_ns=clock)
        sensor.connect()
        clock.now += 600_000_000
        sensor.read_frame(0)
        self.assertEqual(transport.writes, [{"cmd": "HELLO"}, {"cmd": "HELLO"}])
        transport.lines.append(line(load("hello_fsr_only")))
        sensor.read_frame(0)
        self.assertEqual(transport.writes[-1]["cmd"], "STATUS")
        query = transport.writes[-1]
        status = load("status_fsr_only_no_adc4")
        status.update({"sensor_state": "STOPPED", "streaming": False})
        transport.lines.append(line(status))
        sensor.read_frame(0)
        self.assertEqual(sensor.status().state, "STOPPED")
        self.assertEqual(sensor.status().detail["status_query_result"], "PENDING")
        status["request_id"] = query["request_id"]
        transport.lines.append(line(status))
        sensor.read_frame(0)
        self.assertEqual(sensor.status().detail["status_query_result"], "RECEIVED")
        sensor.query_status()
        clock.now += 2_100_000_000
        self.assertEqual(sensor.status().detail["status_query_result"], "TIMEOUT")
        sensor.close()
