"""Offline tests for the read-only log-follow LIVE monitor.

No serial port is opened.  FSR lines use the V2 fixtures from
``tests/fixtures/fsr2/`` with synthetic timestamps and values; console lines use
the real ``transport.jsonl`` event schema copied from the P3-B1 logs.  No real
capture data is stored in the repository.
"""

import copy
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tactile_gripper.control import build_core
from tactile_gripper.devices.log_follow import (
    JsonlTail,
    LogFollowGripper,
    LogFollowSensorAdapter,
    LogFollowSensorTransport,
)
from tactile_gripper.errors import ControlDenied, FrameValidationError
from tactile_gripper.sources import DataSource
from tactile_gripper.ui.charts import unified_timeline_options

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "fsr2"
FSR_FIRMWARE = "tactile-fsr2-0.3.0"


def iso(ns: int) -> str:
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc).isoformat()


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def write_jsonl(path: Path, records: list[dict], *, mode: str = "a") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(mode, encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


# -- console log records ----------------------------------------------------


def console_command(seq: int, command: str, request_id: str, ns: int, pulse: int | None = None) -> dict:
    request = {
        "protocol_version": 1,
        "request_id": request_id,
        "command": command,
        "sequence": seq,
        "boot_id": "console-boot-1",
    }
    if pulse is not None:
        request["pulse_us"] = pulse
    return {"timestamp_utc": iso(ns), "monotonic_ns": ns, "event": "COMMAND", "request": request}


def console_tx(request_id: str, ns: int) -> dict:
    return {"timestamp_utc": iso(ns), "monotonic_ns": ns, "event": "TX", "request_id": request_id}


def console_response(
    request_id: str,
    ns: int,
    *,
    message_type: str = "ACK",
    state: str = "ACTIVE",
    output_state: str = "PWM_COMMANDED_UNMEASURED",
    pulse: int | None = None,
    fault_reason: str = "TARGET_COMMANDED",
    event: str = "MATCHED",
) -> dict:
    response = {
        "protocol_version": 1,
        "firmware_version": "gripper-control-s3-0.9b26.0",
        "request_id": request_id,
        "type": message_type,
        "state": state,
        "output_state": output_state,
        "commanded_pulse_us": pulse,
        "fault_reason": fault_reason,
        "boot_id": "console-boot-1",
        "bench_active": state == "ACTIVE",
        "bench_capable": True,
    }
    return {"timestamp_utc": iso(ns), "monotonic_ns": ns, "event": event, "response": response}


def console_ignored(ns: int, *, reason: str = "corrupt_response", nul_count: int = 7, length: int = 950) -> dict:
    return {
        "timestamp_utc": iso(ns),
        "monotonic_ns": ns,
        "event": "IGNORED",
        "reason": reason,
        "length": length,
        "nul_count": nul_count,
    }


def console_error(ns: int, error: str = "response_timeout") -> dict:
    return {"timestamp_utc": iso(ns), "monotonic_ns": ns, "event": "COMMUNICATION_ERROR", "error": error}


def console_closed(ns: int, output_state: str = "DISABLED_UNMEASURED") -> dict:
    return {"timestamp_utc": iso(ns), "monotonic_ns": ns, "event": "CLOSED"}


def console_controller_closed(ns: int, output_state: str) -> dict:
    return {
        "timestamp_utc": iso(ns),
        "monotonic_ns": ns,
        "event": "CONTROLLER_CLOSED",
        "output_state": output_state,
    }


class FakeClock:
    def __init__(self, seconds: float = 0.0):
        self.seconds = seconds

    def __call__(self) -> float:
        return self.seconds


# -- FSR log records --------------------------------------------------------


def fsr_records(seqs: list[int], *, ns_base: int, valid: bool = True, value: int = 740114, flags: int = 0) -> list[dict]:
    hello = load_fixture("hello_fsr1.json")
    sample = load_fixture("sample_fsr1_valid.json")
    records = [{"host_time_utc": iso(ns_base), "host_monotonic_ns": ns_base, "direction": "RX", "raw": json.dumps(hello), "message": hello}]
    for index, seq in enumerate(seqs):
        ns = ns_base + int((index + 1) * 16_000_000)
        item = copy.deepcopy(sample)
        item.update(
            {
                "frame_seq": seq,
                "timestamp_us": 100_000 + index * 16_000,
                "mcu_time_us": 100_000 + index * 16_000,
                "sample_timestamp_us": [40_000 + index * 16_000],
                "raw_adc": [value if valid else None],
                "channels": [value if valid else None],
                "valid": [valid],
                "valid_mask": [valid],
                "channel_flags": [flags],
            }
        )
        records.append(
            {
                "host_time_utc": iso(ns),
                "host_monotonic_ns": ns,
                "direction": "RX",
                "raw": json.dumps(item),
                "message": item,
            }
        )
    return records


class JsonlTailTests(unittest.TestCase):
    def test_partial_line_is_completed_later(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.jsonl"
            path.write_text('{"a":1}\n{"b":', encoding="utf-8")
            tail = JsonlTail(path)
            self.assertEqual(tail.read_new(), ['{"a":1}'])
            with path.open("a", encoding="utf-8") as handle:
                handle.write("2}\n")
            self.assertEqual(tail.read_new(), ['{"b":2}'])

    def test_truncation_restarts_from_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.jsonl"
            path.write_text("one\ntwo\nthree\n", encoding="utf-8")
            tail = JsonlTail(path)
            self.assertEqual(len(tail.read_new()), 3)
            path.write_text("new\n", encoding="utf-8")
            self.assertEqual(tail.read_new(), ["new"])
            self.assertEqual(tail.truncations, 1)

    def test_rotation_is_detected_by_inode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.jsonl"
            path.write_text("old\n", encoding="utf-8")
            tail = JsonlTail(path)
            self.assertEqual(tail.read_new(), ["old"])
            replacement = Path(tmp) / "b.jsonl"
            replacement.write_text("brand-new\n", encoding="utf-8")
            os.replace(replacement, path)
            self.assertEqual(tail.read_new(), ["brand-new"])
            self.assertEqual(tail.rotations, 1)

    def test_overlong_line_is_dropped_without_blocking_next_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.jsonl"
            path.write_text("x" * 200 + "\n" + "ok\n", encoding="utf-8")
            tail = JsonlTail(path, max_line_bytes=64)
            self.assertEqual(tail.read_new(), ["ok"])
            self.assertEqual(tail.overlong_lines, 1)

    def test_missing_file_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            tail = JsonlTail(Path(tmp) / "missing.jsonl")
            self.assertEqual(tail.read_new(), [])
            self.assertTrue(tail.missing)

    def test_nul_bytes_are_preserved_for_the_parser_to_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.jsonl"
            path.write_bytes(b'{"x":"a\x00b"}\n')
            tail = JsonlTail(path)
            self.assertIn("\x00", tail.read_new()[0])


class LogFollowGripperTests(unittest.TestCase):
    def _build(self, tmp: str, records: list[dict], *, clock_seconds: float | None = None) -> tuple[LogFollowGripper, Path]:
        path = Path(tmp) / "transport.jsonl"
        write_jsonl(path, records, mode="w")
        clock = FakeClock(clock_seconds if clock_seconds is not None else 1.0)
        return LogFollowGripper(path, clock=clock), path

    def test_ordered_session_exposes_ack_then_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = [
                console_command(1, "GET_STATUS", "s1", 1_000_000),
                console_response("s1", 1_100_000, message_type="STATUS", state="DISARMED", output_state="DISABLED_UNMEASURED", fault_reason="BOOT"),
                console_command(2, "BENCH_HOLD", "h1", 2_000_000, 1500),
                console_response("h1", 2_100_000, pulse=1500),
                console_command(3, "STOP", "stop1", 3_000_000),
                console_response("stop1", 3_100_000, state="DISARMED", output_state="DISABLED_UNMEASURED", pulse=None, fault_reason="STOP"),
                console_closed(3_200_000),
            ]
            gripper, _ = self._build(tmp, records, clock_seconds=4.0)
            self.addCleanup(gripper.close)
            gripper.connect()
            gripper.poll()
            snapshot = gripper.monitor_snapshot()
            self.assertEqual(snapshot["counts"]["pwm_commands"], 1)
            self.assertEqual(len(snapshot["pwm_events"]), 1)
            self.assertTrue(snapshot["pwm_events"][0]["ack"])
            self.assertEqual(snapshot["pwm_events"][0]["pulse_us"], 1500)
            # STOP ACK wins: no old target is presented as live output.
            self.assertIsNone(snapshot["current_target_us"])
            self.assertEqual(snapshot["target_status"], "OUTPUT_OFF")
            self.assertEqual(gripper.status().detail["last_pwm_us"], None)
            self.assertEqual(snapshot["output_state"], "DISABLED_UNMEASURED")
            self.assertEqual(snapshot["device_state"], "DISARMED")
            events = gripper.drain_control_events()
            actions = [event.action for event in events]
            self.assertIn("SET_PWM", actions)
            self.assertIn("STOP", actions)
            pwm_events = [event for event in events if event.action == "SET_PWM"]
            self.assertTrue(pwm_events[0].device_ack)
            self.assertEqual(pwm_events[0].commanded_pwm_us, 1500)
            self.assertIsNone(pwm_events[0].actual_pwm_us)

    def test_pwm_without_ack_is_never_confirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = [
                console_command(1, "BENCH_HOLD", "h1", 2_000_000, 1400),
                console_tx("h1", 2_000_100),
                console_ignored(2_050_000, nul_count=7),
                console_error(2_100_000, "response_timeout"),
                console_closed(2_200_000),
                console_controller_closed(2_200_000, "DISABLED_UNMEASURED"),
            ]
            gripper, _ = self._build(tmp, records, clock_seconds=3.0)
            self.addCleanup(gripper.close)
            gripper.connect()
            gripper.poll()
            snapshot = gripper.monitor_snapshot()
            self.assertEqual(snapshot["counts"]["corrupt_responses"], 1)
            self.assertEqual(snapshot["counts"]["nul_bytes"], 7)
            self.assertEqual(snapshot["target_status"], "TIMEOUT")
            self.assertIsNone(snapshot["last_pwm_us"] if "last_pwm_us" in snapshot else None)
            events = gripper.drain_control_events()
            pwm_events = [event for event in events if event.action == "SET_PWM"]
            self.assertTrue(pwm_events)
            self.assertFalse(pwm_events[0].device_ack)
            self.assertEqual(pwm_events[0].stage, "FAILED")
            self.assertIsNone(pwm_events[0].actual_pwm_us)

    def test_stop_without_ack_hides_old_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = [
                console_command(1, "BENCH_HOLD", "h1", 2_000_000, 1200),
                console_response("h1", 2_100_000, pulse=1200),
                console_command(2, "STOP", "stop1", 3_000_000),
                console_closed(3_100_000),
                console_controller_closed(3_100_000, "UNKNOWN"),
            ]
            gripper, _ = self._build(tmp, records, clock_seconds=3.5)
            self.addCleanup(gripper.close)
            gripper.connect()
            gripper.poll()
            snapshot = gripper.monitor_snapshot()
            self.assertIsNone(snapshot["current_target_us"])
            self.assertEqual(snapshot["target_status"], "STOP_UNCONFIRMED")
            self.assertIsNone(gripper.status().detail["last_pwm_us"])

    def test_stale_ack_is_downgraded(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = [
                console_command(1, "BENCH_HOLD", "h1", 2_000_000, 1300),
                console_response("h1", 2_100_000, pulse=1300),
            ]
            gripper, path = self._build(tmp, records, clock_seconds=20.0)
            self.addCleanup(gripper.close)
            old = time.time() - 10
            os.utime(path, (old, old))
            gripper.connect()
            gripper.poll()
            snapshot = gripper.monitor_snapshot()
            self.assertTrue(snapshot["data_stale"])
            self.assertEqual(snapshot["target_status"], "ACK_STALE")
            self.assertIsNone(gripper.status().detail["last_pwm_us"])
            self.assertEqual(gripper.status().state, "STALE")

    def test_duplicate_response_does_not_double_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = [
                console_command(1, "BENCH_HOLD", "h1", 2_000_000, 1500),
                console_response("h1", 2_100_000, pulse=1500),
                console_response("h1", 2_100_500, pulse=1500, event="RESPONSE"),
            ]
            gripper, _ = self._build(tmp, records, clock_seconds=3.0)
            self.addCleanup(gripper.close)
            gripper.connect()
            gripper.poll()
            snapshot = gripper.monitor_snapshot()
            self.assertEqual(len(snapshot["pwm_events"]), 1)
            self.assertEqual(snapshot["counts"]["acked"], 1)
            self.assertEqual(len([e for e in gripper.drain_control_events() if e.action == "SET_PWM"]), 1)

    def test_heartbeats_do_not_become_pwm_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = []
            for index in range(4):
                ns = 1_000_000 + index * 1_000_000
                records.append(console_command(index + 1, "HEARTBEAT", f"hb{index}", ns))
                records.append(console_response(f"hb{index}", ns + 50_000))
            gripper, _ = self._build(tmp, records, clock_seconds=5.0)
            gripper.connect()
            gripper.poll()
            self.assertEqual(gripper.monitor_snapshot()["pwm_events"], [])
            self.assertEqual(gripper.drain_control_events(), [])

    def test_pwm_context_at_uses_recorded_times(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = [
                console_command(1, "BENCH_HOLD", "h1", 2_000_000, 1500),
                console_response("h1", 2_100_000, pulse=1500),
                console_command(2, "STOP", "s1", 3_000_000),
                console_response("s1", 3_100_000, state="DISARMED", output_state="DISABLED_UNMEASURED", pulse=None, fault_reason="STOP"),
            ]
            gripper, _ = self._build(tmp, records, clock_seconds=4.0)
            self.addCleanup(gripper.close)
            gripper.connect()
            gripper.poll()
            self.assertIsNone(gripper.pwm_context_at(1_500_000))
            context = gripper.pwm_context_at(2_500_000)
            self.assertEqual(context["target_pwm_us"], 1500)
            self.assertTrue(context["acknowledged"])
            self.assertIsNone(gripper.pwm_context_at(3_500_000))

    def test_rotated_new_session_resets_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transport.jsonl"
            write_jsonl(
                path,
                [
                    console_command(1, "BENCH_HOLD", "h1", 2_000_000, 1000),
                    console_response("h1", 2_100_000, pulse=1000),
                    console_closed(2_200_000),
                    console_controller_closed(2_200_000, "DISABLED_UNMEASURED"),
                ],
                mode="w",
            )
            clock = FakeClock(3.0)
            gripper = LogFollowGripper(path, clock=clock)
            self.addCleanup(gripper.close)
            gripper.connect()
            gripper.poll()
            self.assertEqual(gripper.monitor_snapshot()["current_target_us"], 1000)

            replacement = Path(tmp) / "new.jsonl"
            write_jsonl(
                replacement,
                [
                    {"timestamp_utc": iso(5_000_000), "monotonic_ns": 5_000_000, "event": "CONNECTED", "path": "/dev/cu.fake"},
                    console_command(1, "BENCH_HOLD", "n1", 5_100_000, 1600),
                    console_response("n1", 5_200_000, pulse=1600),
                ],
                mode="w",
            )
            os.replace(replacement, path)
            gripper.poll()
            snapshot = gripper.monitor_snapshot()
            self.assertEqual(snapshot["session_restarts"], 1)
            self.assertEqual(snapshot["current_target_us"], 1600)
            self.assertEqual(snapshot["target_status"], "ACKED")
            self.assertEqual(len(snapshot["pwm_events"]), 1)

    def test_execute_is_always_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            gripper, _ = self._build(tmp, [], clock_seconds=1.0)
            self.addCleanup(gripper.close)
            with self.assertRaises(ControlDenied):
                gripper.execute(None)
            with self.assertRaises(ControlDenied):
                gripper.hold()
            with self.assertRaises(ControlDenied):
                gripper.release()

    def test_late_created_pwm_log_is_attached(self):
        with tempfile.TemporaryDirectory() as tmp:
            pwm = Path(tmp) / "transport.jsonl"
            gripper = LogFollowGripper(pwm, require_existing=False)
            self.addCleanup(gripper.close)
            result = gripper.connect()
            self.assertTrue(result.get("waiting"))
            self.assertTrue(gripper.monitor_snapshot()["tail"]["missing"])
            base = time.monotonic_ns()
            write_jsonl(
                pwm,
                [
                    console_command(1, "BENCH_HOLD", "h1", base, 1500),
                    console_response("h1", base + 1_000_000, pulse=1500),
                ],
                mode="w",
            )
            gripper.poll()
            snapshot = gripper.monitor_snapshot()
            self.assertFalse(snapshot["tail"]["missing"])
            self.assertEqual(snapshot["current_target_us"], 1500)
            self.assertEqual(snapshot["target_status"], "ACKED")

    def test_connect_fails_when_log_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            gripper = LogFollowGripper(Path(tmp) / "nope.jsonl")
            with self.assertRaises(FileNotFoundError):
                gripper.connect()


class LogFollowSensorTests(unittest.TestCase):
    def test_recorded_host_time_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fsr.jsonl"
            records = fsr_records([1, 2, 3], ns_base=5_000_000_000)
            write_jsonl(path, records, mode="w")
            adapter = LogFollowSensorAdapter(path)
            self.addCleanup(adapter.close)
            adapter.connect()
            frames = []
            for _ in range(10):
                frame = adapter.read_frame(0.0)
                if frame is not None:
                    frames.append(frame)
            self.assertEqual([frame.frame_seq for frame in frames], [1, 2, 3])
            self.assertEqual(frames[0].host_received_utc, records[1]["host_time_utc"])
            self.assertEqual(frames[0].host_received_ns, records[1]["host_monotonic_ns"])
            self.assertEqual(frames[0].source, DataSource.LIVE)

    def test_negative_counts_and_0x04_flag_are_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fsr.jsonl"
            write_jsonl(path, fsr_records([1], ns_base=5_000_000_000, value=-1200, flags=0x04), mode="w")
            adapter = LogFollowSensorAdapter(path)
            self.addCleanup(adapter.close)
            adapter.connect()
            frame = adapter.read_frame(0.0)
            self.assertEqual(frame.channels[0], -1200)
            self.assertEqual(frame.raw["channel_flags"], [4])
            self.assertEqual(adapter.status().detail["channel_flags"], [4])

    def test_nul_corrupted_line_does_not_stop_the_stream(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fsr.jsonl"
            records = fsr_records([1], ns_base=5_000_000_000)
            records.insert(1, {"host_time_utc": iso(5_000_000_001), "host_monotonic_ns": 5_000_000_001, "direction": "RX", "raw": '{"protocol_version":1,\x00\x00'})
            write_jsonl(path, records, mode="w")
            adapter = LogFollowSensorAdapter(path)
            self.addCleanup(adapter.close)
            adapter.connect()
            frame = adapter.read_frame(0.0)
            self.assertIsNotNone(frame)
            self.assertEqual(frame.frame_seq, 1)
            self.assertEqual(adapter.log_transport.tail.lines_read, len(records))

    def test_hello_prefix_is_recovered_for_midfile_attach(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fsr.jsonl"
            write_jsonl(path, fsr_records([1], ns_base=5_000_000_000), mode="w")
            transport = LogFollowSensorTransport(path)
            self.addCleanup(transport.close)
            transport.connect()
            self.assertIsNotNone(transport._bootstrap)
            self.assertIn(b'"type":"HELLO"', transport._bootstrap[0])

    def test_sample_before_hello_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fsr.jsonl"
            records = fsr_records([1], ns_base=5_000_000_000)[1:]
            write_jsonl(path, records, mode="w")
            adapter = LogFollowSensorAdapter(path)
            self.addCleanup(adapter.close)
            adapter.connect()
            with self.assertRaises(FrameValidationError):
                adapter.read_frame(0.0)

    def test_stale_when_frames_are_old(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fsr.jsonl"
            write_jsonl(path, fsr_records([1, 2], ns_base=5_000_000_000), mode="w")
            now = 5_000_000_000 + 60_000_000_000
            adapter = LogFollowSensorAdapter(path, clock_ns=lambda: now)
            adapter.connect()
            adapter.read_frame(0.0)
            adapter.read_frame(0.0)
            status = adapter.status()
            self.assertEqual(status.state, "STALE")
            self.assertGreater(status.detail["log_age_s"], 3.0)


class CoreLogFollowTests(unittest.TestCase):
    def _session(self, tmp: str) -> tuple[Path, Path]:
        base = time.monotonic_ns() - 2_000_000_000
        pwm = Path(tmp) / "transport.jsonl"
        write_jsonl(
            pwm,
            [
                console_command(1, "BEGIN_BENCH", "begin1", base + 100_000_000),
                console_response("begin1", base + 200_000_000, state="ARMED", output_state="DISABLED_UNMEASURED", pulse=None, fault_reason="GRIPPER_ASSEMBLED_AUTHORIZED"),
                console_command(2, "BENCH_HOLD", "h1", base + 300_000_000, 1500),
                console_response("h1", base + 400_000_000, pulse=1500),
                console_command(3, "STOP", "stop1", base + 1_600_000_000),
                console_response("stop1", base + 1_700_000_000, state="DISARMED", output_state="DISABLED_UNMEASURED", pulse=None, fault_reason="STOP"),
            ],
            mode="w",
        )
        fsr = Path(tmp) / "fsr_stream.jsonl"
        # Frames at +266/+282/+298/+314 ms: three before the PWM command at
        # +300 ms and one after it, so the per-frame context can be checked.
        write_jsonl(fsr, fsr_records([1, 2, 3, 4], ns_base=base + 250_000_000, value=700000 + 1000), mode="w")
        return pwm, fsr

    def test_core_records_frames_and_console_pwm_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            pwm, fsr = self._session(tmp)
            core = build_core(source=DataSource.LIVE, root=tmp, follow_pwm_log=pwm, follow_fsr_log=fsr)
            self.assertTrue(core.log_follow)
            core.create_trial("log follow", conditions={"source_kind": "LIVE_LOG_FOLLOW"})
            core.start_trial()
            core.tick()
            snapshot = core.snapshot()
            self.assertTrue(snapshot["log_follow"])
            self.assertGreaterEqual(snapshot["frames_received"], 4)
            self.assertEqual(snapshot["monitor"]["target_status"], "OUTPUT_OFF")
            self.assertFalse(snapshot["apply_enabled"])
            self.assertFalse(snapshot["stop_enabled"])
            self.assertIn("LOG-FOLLOW", snapshot["apply_denial"])
            # Writing through the dashboard is denied, not silently ignored.
            event = core.request_pwm(1500)
            self.assertEqual(event.stage, "REJECTED")
            self.assertFalse(event.device_ack)
            stop_event = core.stop()
            self.assertEqual(stop_event.stage, "REJECTED")
            info = core.stop_trial("test")
            directory = Path(info["directory"])
            control = [
                json.loads(line)
                for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if json.loads(line).get("record_type") == "CONTROL_EVENT"
            ]
            actions = [(item["action"], item["stage"], item.get("commanded_pwm_us")) for item in control]
            self.assertIn(("SET_PWM", "DEVICE_ACK", 1500), actions)
            self.assertIn(("STOP", "DEVICE_ACK", None), actions)
            frames = [
                json.loads(line)
                for line in (directory / "frames.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(frames), snapshot["frames_received"])
            # Frames before the PWM command have no context; frames after it do.
            self.assertIsNone(frames[0]["pwm_target_us"])
            self.assertEqual(frames[-1]["pwm_target_us"], 1500)
            self.assertTrue(frames[-1]["pwm_ack"])
            csv_path = core.trial_store.export_csv(info["trial_id"])
            rows = csv_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), len(frames) + 1)
            replay = core.trial_store.export_replay_jsonl(info["trial_id"])
            self.assertTrue(replay.is_file())
            core.shutdown()

    def test_fsr_only_log_follow_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, fsr = self._session(tmp)
            core = build_core(source=DataSource.LIVE, root=tmp, follow_fsr_log=fsr)
            self.addCleanup(core.shutdown)
            self.assertTrue(core.log_follow)
            self.assertIsNone(core.gripper)
            snapshot = core.snapshot()
            self.assertTrue(snapshot["log_follow"])
            self.assertFalse(snapshot["apply_enabled"])
            self.assertFalse(snapshot["stop_enabled"])
            core.tick()
            self.assertGreaterEqual(core.snapshot()["frames_received"], 4)

    def test_finish_drains_trailing_jsonl_before_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            pwm, fsr = self._session(tmp)
            core = build_core(source=DataSource.LIVE, root=tmp, follow_pwm_log=pwm, follow_fsr_log=fsr)
            self.addCleanup(core.shutdown)
            core.create_trial("drain check", conditions={"source_kind": "LIVE_LOG_FOLLOW"})
            core.start_trial()
            core.tick()
            before = core.snapshot()["frames_received"]
            self.assertGreaterEqual(before, 4)

            now = time.monotonic_ns()
            trailing = fsr_records([5], ns_base=now)[1]
            trailing["message"].update(
                {
                    "timestamp_us": 260_000,
                    "mcu_time_us": 260_000,
                    "sample_timestamp_us": [260_000],
                }
            )
            write_jsonl(fsr, [trailing], mode="a")
            write_jsonl(
                pwm,
                [
                    console_command(7, "BENCH_HOLD", "h9", now, 1300),
                    console_response("h9", now + 1_000_000, pulse=1300),
                ],
                mode="a",
            )

            result = core.finish_log_follow_trial("shutdown test")
            self.assertIsNotNone(result)
            self.assertEqual(result["status"], "COMPLETED")
            self.assertIsNone(core.trial)
            csv_path = Path(result["csv"])
            replay_path = Path(result["replay"])
            self.assertTrue(csv_path.is_file())
            self.assertTrue(replay_path.is_file())
            frames = [
                json.loads(line)
                for line in (Path(result["directory"]) / "frames.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(frames[-1]["frame_seq"], 5)
            self.assertEqual(frames[-1]["pwm_target_us"], 1300)
            self.assertTrue(frames[-1]["pwm_ack"])
            control = [
                json.loads(line)
                for line in (Path(result["directory"]) / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if json.loads(line).get("record_type") == "CONTROL_EVENT"
            ]
            self.assertIn(("SET_PWM", 1300), [(item.get("action"), item.get("commanded_pwm_us")) for item in control])
            rows = csv_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), len(frames) + 1)

    def test_finish_without_recording_trial_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            pwm, fsr = self._session(tmp)
            core = build_core(source=DataSource.LIVE, root=tmp, follow_pwm_log=pwm, follow_fsr_log=fsr)
            self.addCleanup(core.shutdown)
            self.assertIsNone(core.finish_log_follow_trial("nothing"))

    def test_core_attaches_late_pwm_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            pwm = Path(tmp) / "transport.jsonl"
            fsr = Path(tmp) / "fsr_stream.jsonl"
            now = time.monotonic_ns()
            write_jsonl(fsr, fsr_records([1], ns_base=now - 1_000_000_000), mode="w")
            core = build_core(
                source=DataSource.LIVE,
                root=tmp,
                follow_pwm_log=pwm,
                follow_fsr_log=fsr,
                follow_allow_missing=True,
            )
            self.addCleanup(core.shutdown)
            self.assertTrue(core.log_follow)
            snapshot = core.snapshot()
            self.assertTrue(snapshot["monitor"]["tail"]["missing"])
            self.assertFalse(snapshot["apply_enabled"])
            core.create_trial("late pwm", conditions={"source_kind": "LIVE_LOG_FOLLOW"})
            core.start_trial()
            core.tick()
            write_jsonl(
                pwm,
                [
                    console_command(1, "BENCH_HOLD", "late1", now, 1500),
                    console_response("late1", now + 1_000_000, pulse=1500),
                ],
                mode="w",
            )
            core.tick()
            snapshot = core.snapshot()
            self.assertEqual(snapshot["monitor"]["current_target_us"], 1500)
            self.assertEqual(snapshot["monitor"]["target_status"], "ACKED")
            self.assertFalse(snapshot["monitor"]["tail"]["missing"])
            info = core.stop_trial("test")
            events = [
                json.loads(line)
                for line in (Path(info["directory"]) / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if json.loads(line).get("record_type") == "CONTROL_EVENT"
            ]
            self.assertIn(("SET_PWM", 1500), [(e.get("action"), e.get("commanded_pwm_us")) for e in events])

    def test_partial_jsonl_line_waits_for_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            pwm, fsr = self._session(tmp)
            core = build_core(source=DataSource.LIVE, root=tmp, follow_pwm_log=pwm, follow_fsr_log=fsr)
            core.tick()
            before = len(core.snapshot()["monitor"]["commands"])
            # Append half a command line: it must not be parsed as a command.
            with pwm.open("a", encoding="utf-8") as handle:
                handle.write('{"event":"COMMAND","request":{"command":"BENCH_HOLD","request_id":"x"')
            core.tick()
            self.assertEqual(len(core.snapshot()["monitor"]["commands"]), before)
            with pwm.open("a", encoding="utf-8") as handle:
                handle.write(',"pulse_us":1200,"sequence":9}}\n')
            core.tick()
            snapshot = core.snapshot()
            self.assertEqual(len(snapshot["monitor"]["commands"]), before + 1)
            self.assertEqual(snapshot["monitor"]["current_target_us"], 1200)
            self.assertEqual(snapshot["monitor"]["target_status"], "SENT_UNACKED")
            core.shutdown()

    def test_truncated_log_is_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            pwm, fsr = self._session(tmp)
            core = build_core(source=DataSource.LIVE, root=tmp, follow_pwm_log=pwm, follow_fsr_log=fsr)
            core.tick()
            pwm.write_text("", encoding="utf-8")
            with pwm.open("a", encoding="utf-8") as handle:
                base = time.monotonic_ns()
                for record in [
                    console_command(1, "BENCH_HOLD", "z1", base, 1100),
                    console_response("z1", base + 1_000_000, pulse=1100),
                ]:
                    handle.write(json.dumps(record) + "\n")
            core.tick()
            snapshot = core.snapshot()
            self.assertEqual(snapshot["monitor"]["tail"]["truncations"], 1)
            self.assertEqual(snapshot["monitor"]["current_target_us"], 1100)
            self.assertEqual(snapshot["monitor"]["target_status"], "ACKED")
            core.shutdown()


class UnifiedTimelineTests(unittest.TestCase):
    def test_both_series_share_a_numeric_host_axis(self):
        option = unified_timeline_options(
            [
                {"ns": 1_000_000_000, "seq": 1, "raw": 740000.0, "valid": True},
                {"ns": 1_016_000_000, "seq": 2, "raw": None, "valid": False},
                {"ns": 1_032_000_000, "seq": 3, "raw": 750000.0, "valid": True},
            ],
            [
                {"sent_ns": 1_010_000_000, "pulse_us": 1500, "ack": True, "result": "ACKED"},
                {"sent_ns": 1_020_000_000, "pulse_us": 1300, "ack": False, "result": "TIMEOUT"},
            ],
        )
        self.assertEqual(option["xAxis"]["type"], "value")
        self.assertEqual(len(option["series"]), 2)
        fsr = option["series"][0]["data"]
        self.assertEqual(fsr[0], [0.0, 740000.0])
        self.assertIsNone(fsr[1][1])  # invalid frame is a gap, not zero
        pwm = option["series"][1]["data"]
        self.assertEqual(pwm[0]["value"], [0.01, 1500])
        self.assertEqual(pwm[0]["itemStyle"]["color"], "#0ea5e9")
        self.assertEqual(pwm[1]["symbol"], "triangle")

    def test_empty_inputs_return_empty_option(self):
        self.assertEqual(unified_timeline_options([], []), {})
