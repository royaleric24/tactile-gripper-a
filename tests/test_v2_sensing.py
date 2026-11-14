"""Offline P2-S tests: FSR-only/hybrid profiles, contact policy, trial replay.

No serial port is opened and no PWM command is sent here.
"""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from tactile_gripper.control.auto import AutoGate, AutoLimits, RuleBasedAutoPolicy
from tactile_gripper.control.core import ApplicationCore
from tactile_gripper.control.contact import (
    INVALID,
    NORMAL,
    NOT_APPLICABLE,
    NO_CONTACT,
    TIGHT,
    UNCALIBRATED,
    ContactAssessment,
    FsrContactAssessor,
    FsrThresholds,
)
from tactile_gripper.devices.sensor import JsonlReplayTransport, ReplaySensorAdapter, SensorAdapter
from tactile_gripper.devices.sensor_serial import SerialSensorConfig
from tactile_gripper.errors import ControlDenied, FrameValidationError
from tactile_gripper.experiments.store import TrialStore
from tactile_gripper.models import ChannelConfig, ChannelConfiguration, ControlEvent, TactileFrame
from tactile_gripper.protocol import encode_hello_query, encode_status_query, parse_sample
from tactile_gripper.sources import DataSource
from tactile_gripper.ui.charts import fsr_trend_options, heatmap_options

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "v2"
FSR_CONFIG_PATH = ROOT / "config/sensor_channels.fsr_only.demo.json"
HYBRID_CONFIG_PATH = ROOT / "config/sensor_channels.hybrid.demo.json"
SPAN = 2 ** 23 * 0.05


def load_config(path: Path) -> ChannelConfiguration:
    return ChannelConfiguration.from_dict(json.loads(path.read_text()))


def make_frame(
    config: ChannelConfiguration,
    seq: int,
    values: list,
    *,
    mask: list | None = None,
    host_ns: int | None = None,
    boot_id: str = "boot-test-1",
) -> TactileFrame:
    if mask is None:
        mask = [True] * len(values)
    return TactileFrame(
        protocol_version=1,
        device_id="sensor-test",
        boot_id=boot_id,
        frame_seq=seq,
        mcu_time_us=seq * 1000,
        host_received_ns=seq * 1_000_000_000 if host_ns is None else host_ns,
        channels=tuple(values),
        valid_mask=tuple(mask),
        source=DataSource.SIMULATION,
        channel_ids=tuple(channel.channel_id for channel in config.channels),
        matrix_rows=config.matrix_rows,
        matrix_cols=config.matrix_cols,
    ).validate(config)


def fsr_frame(counts: list[float], *, seq: int, host_ns: int | None = None, mask=None) -> TactileFrame:
    config = load_config(FSR_CONFIG_PATH)
    return make_frame(config, seq, list(counts), mask=mask, host_ns=host_ns)


def counts_for_score(score: float, baseline: float = 80_000.0) -> float:
    return baseline + score * SPAN


class ProfileTests(unittest.TestCase):
    def test_fsr_only_profile_and_voltage_basis(self):
        config = load_config(FSR_CONFIG_PATH)
        self.assertEqual(config.sensor_profile, "FSR_ONLY")
        self.assertEqual([channel.channel_id for channel in config.fsr_channels], [0, 1])
        self.assertEqual(config.matrix_channels, ())
        channel = config.fsr_channels[0]
        self.assertTrue(channel.voltage_basis_complete)
        self.assertAlmostEqual(channel.count_to_voltage_uv(80_000), 80_000 / 2 ** 23 * 3.3e6, places=2)

    def test_voltage_is_absent_without_explicit_basis(self):
        channel = ChannelConfig(channel_id=0, sensor_kind="FSR")
        self.assertFalse(channel.voltage_basis_complete)
        self.assertIsNone(channel.count_to_voltage_uv(100))

    def test_hybrid_profile_has_36_matrix_and_2_fsr(self):
        config = load_config(HYBRID_CONFIG_PATH)
        self.assertEqual(config.sensor_profile, "HYBRID_6X6_FSR2")
        self.assertEqual(len(config.matrix_channels), 36)
        self.assertEqual([channel.channel_id for channel in config.fsr_channels], [36, 37])
        self.assertEqual(
            {(channel.matrix_row, channel.matrix_col) for channel in config.matrix_channels},
            {(row, col) for row in range(6) for col in range(6)},
        )

    def test_profile_counts_are_validated(self):
        payload = json.loads(HYBRID_CONFIG_PATH.read_text())
        payload["channels"] = payload["channels"][:-1]
        with self.assertRaises(ValueError):
            ChannelConfiguration.from_dict(payload)

    def test_unknown_kind_is_inferred_only_from_profile_or_position(self):
        payload = json.loads(FSR_CONFIG_PATH.read_text())
        for channel in payload["channels"]:
            channel.pop("sensor_kind", None)
        config = ChannelConfiguration.from_dict(payload)
        self.assertTrue(all(channel.sensor_kind == "UNKNOWN" for channel in config.channels))
        self.assertEqual([channel.channel_id for channel in config.fsr_channels], [0, 1])

    def test_heatmap_excludes_fsr_even_if_ids_would_fit_grid(self):
        config = load_config(HYBRID_CONFIG_PATH)
        values = [2048.0 + index for index in range(36)] + [80_000, 100_000]
        frame = make_frame(config, 1, values)
        options = heatmap_options(frame.to_dict(), config)
        points = options["series"][0]["data"]
        self.assertEqual(len(points), 36)
        self.assertTrue(all(point[0] < 6 and point[1] < 6 for point in points))
        fsr_options = heatmap_options(fsr_frame([80_000, 100_000], seq=1).to_dict(), load_config(FSR_CONFIG_PATH))
        self.assertEqual(fsr_options["series"][0]["data"], [])

    def test_fsr_trend_uses_channel_names(self):
        config = load_config(FSR_CONFIG_PATH)
        frame = fsr_frame([80_000, 100_000], seq=1)
        assessment = FsrContactAssessor().assess(frame, config, now_ns=frame.host_received_ns)
        options = fsr_trend_options([
            {"frame_seq": 1, "score": 0.0, "readings": [reading.to_dict() for reading in assessment.readings]}
        ])
        names = [series["name"] for series in options["series"]]
        self.assertIn("FSR_A 原始 ADC", names)
        self.assertIn("FSR_B 原始 ADC", names)


class ContactTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(FSR_CONFIG_PATH)

    def assess(self, counts, *, seq=1, now_ns=None, mask=None):
        frame = fsr_frame(counts, seq=seq, mask=mask)
        now = frame.host_received_ns if now_ns is None else now_ns
        return FsrContactAssessor().assess(frame, self.config, now_ns=now)

    def test_baseline_capture_and_contact_states(self):
        assessor = FsrContactAssessor()
        frame = fsr_frame([80_000, 100_000], seq=1)
        baseline = assessor.capture_baseline(frame, self.config)
        self.assertTrue(baseline.baseline_ready)
        self.assertEqual(baseline.state, NO_CONTACT)
        self.assertEqual(baseline.score, 0.0)

        insufficient = assessor.assess(fsr_frame([counts_for_score(.20), counts_for_score(.20, 100_000)], seq=2), self.config, now_ns=2_000_000_000)
        self.assertEqual(insufficient.state, "INSUFFICIENT")
        normal = assessor.assess(fsr_frame([counts_for_score(.50), counts_for_score(.50, 100_000)], seq=3), self.config, now_ns=3_000_000_000)
        self.assertEqual(normal.state, NORMAL)
        tight = assessor.assess(fsr_frame([counts_for_score(.85), counts_for_score(.85, 100_000)], seq=4), self.config, now_ns=4_000_000_000)
        self.assertEqual(tight.state, TIGHT)

    def test_hysteresis_prevents_chatter(self):
        assessor = FsrContactAssessor()
        assessor.capture_baseline(fsr_frame([80_000, 100_000], seq=1), self.config)
        normal = assessor.assess(fsr_frame([counts_for_score(.50), counts_for_score(.50, 100_000)], seq=2), self.config, now_ns=2_000_000_000)
        self.assertEqual(normal.state, NORMAL)
        # 0.42 is below the enter threshold but above normal - hysteresis.
        held = assessor.assess(fsr_frame([counts_for_score(.42), counts_for_score(.42, 100_000)], seq=3), self.config, now_ns=3_000_000_000)
        self.assertEqual(held.state, NORMAL)
        dropped = assessor.assess(fsr_frame([counts_for_score(.30), counts_for_score(.30, 100_000)], seq=4), self.config, now_ns=4_000_000_000)
        self.assertEqual(dropped.state, "INSUFFICIENT")
        tight = assessor.assess(fsr_frame([counts_for_score(.85), counts_for_score(.85, 100_000)], seq=5), self.config, now_ns=5_000_000_000)
        self.assertEqual(tight.state, TIGHT)
        held_tight = assessor.assess(fsr_frame([counts_for_score(.77), counts_for_score(.77, 100_000)], seq=6), self.config, now_ns=6_000_000_000)
        self.assertEqual(held_tight.state, TIGHT)

    def test_invalid_frame_resets_hysteresis_and_cannot_be_actionable(self):
        assessor = FsrContactAssessor()
        assessor.capture_baseline(fsr_frame([80_000, 100_000], seq=1), self.config)
        assessor.assess(fsr_frame([counts_for_score(.85), counts_for_score(.85, 100_000)], seq=2), self.config, now_ns=2_000_000_000)
        invalid = assessor.assess(
            fsr_frame([counts_for_score(.77), None], seq=3, mask=[True, False]),
            self.config,
            now_ns=3_000_000_000,
        )
        self.assertEqual(invalid.state, INVALID)
        self.assertFalse(invalid.actionable)
        recovered = assessor.assess(
            fsr_frame([counts_for_score(.77), counts_for_score(.77, 100_000)], seq=4),
            self.config,
            now_ns=4_000_000_000,
        )
        self.assertEqual(recovered.state, NORMAL)

    def test_stale_and_missing_baseline(self):
        frame = fsr_frame([80_000, 100_000], seq=1)
        assessor = FsrContactAssessor()
        uncalibrated = assessor.assess(frame, self.config, now_ns=frame.host_received_ns)
        self.assertEqual(uncalibrated.state, UNCALIBRATED)
        stale = assessor.assess(frame, self.config, now_ns=frame.host_received_ns + 500_000_000)
        self.assertEqual(stale.state, INVALID)

    def test_saturated_channel_invalidates_assessment(self):
        assessor = FsrContactAssessor()
        frame = fsr_frame([80_000, 100_000], seq=1)
        assessor.capture_baseline(frame, self.config)
        saturated = assessor.assess(fsr_frame([2 ** 23, 100_000], seq=2), self.config, now_ns=2_000_000_000)
        self.assertEqual(saturated.state, INVALID)

    def test_two_fsr_uses_weaker_channel(self):
        assessor = FsrContactAssessor()
        assessor.capture_baseline(fsr_frame([80_000, 100_000], seq=1), self.config)
        frame = fsr_frame([counts_for_score(.50), counts_for_score(.10, 100_000)], seq=2)
        assessment = assessor.assess(frame, self.config, now_ns=2_000_000_000)
        self.assertAlmostEqual(assessment.score, 0.10, places=4)

    def test_no_fsr_is_not_applicable(self):
        config = load_config(HYBRID_CONFIG_PATH)
        matrix_only = ChannelConfiguration(
            channels=tuple(
                ChannelConfig(
                    channel_id=channel.channel_id,
                    sensor_kind="MATRIX_CELL",
                    matrix_row=channel.matrix_row,
                    matrix_col=channel.matrix_col,
                )
                for channel in config.matrix_channels
            ),
            matrix_rows=6,
            matrix_cols=6,
        )
        assessment = FsrContactAssessor().assess(None, matrix_only, now_ns=0)
        self.assertEqual(assessment.state, NOT_APPLICABLE)


class AutoPolicyTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(FSR_CONFIG_PATH)
        self.frame = fsr_frame([counts_for_score(.15), counts_for_score(.15, 100_000)], seq=9)
        self.policy = RuleBasedAutoPolicy(AutoLimits(step_us=20, max_total_us=100), AutoGate(allow_simulation=True))

    def assessment(self, state, score):
        return ContactAssessment(state=state, score=score, quality=1.0, reason="test")

    def evaluate(self, state, score, **kwargs):
        return self.policy.evaluate_contact(
            self.frame,
            self.assessment(state, score),
            now_ns=self.frame.host_received_ns,
            target_us=1400,
            steps=0,
            total_change_us=0,
            **kwargs,
        )

    def test_insufficient_steps_up_but_invalid_never_steps(self):
        decision = self.evaluate("INSUFFICIENT", .15)
        self.assertEqual(decision.action, "STEP")
        self.assertEqual(decision.target_delta_us, 20)
        invalid = self.evaluate(INVALID, None)
        self.assertEqual(invalid.action, "FAULT")
        self.assertIsNone(invalid.target_delta_us)

    def test_tight_steps_down_and_bounds(self):
        decision = self.evaluate(TIGHT, .9, min_pwm_us=1300, max_pwm_us=1500)
        self.assertEqual(decision.action, "STEP")
        self.assertEqual(decision.target_delta_us, -20)
        at_limit = self.policy.evaluate_contact(
            self.frame,
            self.assessment(TIGHT, .9),
            now_ns=self.frame.host_received_ns,
            target_us=1300,
            steps=0,
            total_change_us=0,
            min_pwm_us=1300,
            max_pwm_us=1500,
        )
        self.assertEqual(at_limit.action, "STOP")

    def test_unfinished_command_waits_before_any_step(self):
        decision = self.evaluate("INSUFFICIENT", .15, pending_command=True)
        self.assertEqual(decision.action, "WAIT")
        self.assertIsNone(decision.target_delta_us)

    def test_stale_and_non_streaming_are_faults(self):
        stale = self.policy.evaluate_contact(
            self.frame,
            self.assessment("INSUFFICIENT", .15),
            now_ns=self.frame.host_received_ns + 1_000_000_000,
            target_us=1400,
            steps=0,
            total_change_us=0,
        )
        self.assertEqual(stale.action, "FAULT")
        not_streaming = self.evaluate("INSUFFICIENT", .15, sensor_state="STALE")
        self.assertEqual(not_streaming.action, "FAULT")

    def test_real_gate_is_unavailable(self):
        policy = RuleBasedAutoPolicy(AutoLimits(), AutoGate(source=DataSource.LIVE, real_sensor=True, protocol_confirmed=True, calibration_confirmed=True, hardware_armed=True))
        decision = policy.evaluate_contact(self.frame, self.assessment("INSUFFICIENT", .15), now_ns=1, target_us=1400, steps=0, total_change_us=0)
        self.assertEqual(decision.action, "UNAVAILABLE")


class FixtureAndTrialTests(unittest.TestCase):
    def test_fixture_replay_fsr_only(self):
        adapter = ReplaySensorAdapter(FIXTURES / "fsr_only.jsonl")
        adapter.connect()
        frame = adapter.read_frame(timeout_s=1.0)
        self.assertEqual(frame.channel_ids, (0, 1))
        self.assertEqual(frame.channels, (80_000, 100_000))
        self.assertEqual(adapter.channel_config.sensor_profile, "FSR_ONLY")
        adapter.close()

    def test_fixture_hybrid_replay(self):
        adapter = ReplaySensorAdapter(FIXTURES / "hybrid.jsonl")
        adapter.connect()
        frame = adapter.read_frame(timeout_s=1.0)
        self.assertEqual(len(frame.channels), 38)
        self.assertEqual(frame.matrix_rows, 6)
        self.assertEqual(adapter.channel_config.sensor_profile, "HYBRID_6X6_FSR2")
        adapter.close()

    def test_short_sample_is_rejected_against_hello(self):
        lines = [
            (FIXTURES / "fsr_only.jsonl").read_text().splitlines()[0].encode(),
            (FIXTURES / "short_sample.jsonl").read_text().strip().encode(),
        ]
        class Lines:
            def __init__(self):
                self.lines = lines
                self.offset = 0
            def connect(self): pass
            def close(self): pass
            def readline(self, timeout_s):
                if self.offset >= len(self.lines):
                    return None
                line = self.lines[self.offset]
                self.offset += 1
                return line + b"\n"
        adapter = SensorAdapter(Lines(), None, source=DataSource.REPLAY)
        adapter.connect()
        with self.assertRaises(FrameValidationError):
            adapter.read_frame(timeout_s=1.0)

    def test_status_query_is_explicit_and_opt_in(self):
        class QueryTransport:
            def __init__(self):
                self.queries = []
            def connect(self): pass
            def close(self): pass
            def readline(self, timeout_s): return None
            def write_line(self, payload): self.queries.append(payload)

        transport = QueryTransport()
        adapter = SensorAdapter(transport, load_config(FSR_CONFIG_PATH), source=DataSource.SIMULATION)
        adapter.connect()
        self.assertTrue(adapter.query_status(request_id="q-1"))
        self.assertTrue(adapter.query_hello(request_id="q-2"))
        self.assertEqual(
            transport.queries,
            [encode_status_query(request_id="q-1"), encode_hello_query(request_id="q-2")],
        )
        self.assertIn(b'"query":"STATUS"', transport.queries[0])
        self.assertIn(b'"query":"HELLO"', transport.queries[1])

    def test_serial_baud_921600_is_configurable_but_queries_stay_off(self):
        config = SerialSensorConfig.from_dict({"baudrate": 921600, "queries_enabled": False}).with_port("tty-test", 921600)
        self.assertEqual(config.baudrate, 921600)
        self.assertFalse(config.queries_enabled)

    def test_real_auto_commissioning_entry_is_explicitly_denied(self):
        core = ApplicationCore(source=DataSource.SIMULATION)
        available, reasons = core.auto_available()
        self.assertFalse(available)
        self.assertTrue(reasons)
        with self.assertRaises(ControlDenied):
            core.request_real_auto_commissioning()
        self.assertTrue(core.real_auto_commissioning_requested)
        events = list(core.events)
        self.assertIn("AUTO_COMMISSIONING_DENIED", [event["action"] for event in events])

    def test_replay_assessment_uses_recorded_timebase(self):
        config = load_config(FSR_CONFIG_PATH)
        frame = make_frame(config, 1, [80_000, 100_000], host_ns=1_000_000_000)

        class NoopTransport:
            def connect(self): pass
            def close(self): pass
            def readline(self, timeout_s): return None

        core = ApplicationCore(
            source=DataSource.REPLAY,
            sensor=SensorAdapter(NoopTransport(), config, source=DataSource.REPLAY),
        )
        core.contact_assessor.capture_baseline(frame, config, source="REPLAY_TEST")
        assessed = core._assess_latest_frame(frame)
        self.assertEqual(assessed.contact_score, 0.0)
        self.assertEqual(core.last_assessment.state, NO_CONTACT)

    def test_trial_persists_raw_assessment_identity_and_replay(self):
        config = load_config(FSR_CONFIG_PATH)
        sample = json.loads((FIXTURES / "fsr_only.jsonl").read_text().splitlines()[1])
        frame = parse_sample(
            sample,
            config,
            source=DataSource.SIMULATION,
            host_received_ns=1_000_000_000,
            host_received_utc="2026-01-01T00:00:00+00:00",
        )
        assessor = FsrContactAssessor()
        assessment = assessor.capture_baseline(frame, config)
        event = ControlEvent(
            action="SET_PWM",
            stage="DEVICE_ACK",
            source=DataSource.SIMULATION,
            mode="MANUAL",
            command_id="cmd-1",
            commanded_pwm_us=1320,
            serial_write_ok=True,
            device_ack=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = TrialStore(Path(tmp), DataSource.SIMULATION)
            recorder = store.create_trial(
                "P2-S fixture",
                mode="MANUAL",
                parameters={
                    "sensor_config": config.to_dict(),
                    "device_identities": {
                        "sensor": {"device_id": "sensor-fsr-01", "boot_id": "boot-test-1", "firmware_version": "acq-v2-fixture"},
                        "gripper": {"device_id": "s3-test", "boot_id": "s3-boot", "firmware_version": "gripper-test"},
                    },
                },
            )
            recorder.start()
            recorder.record_control(event)
            recorder.record_frame(
                frame,
                sensor_identity={"device_id": "sensor-fsr-01", "boot_id": "boot-test-1", "firmware_version": "acq-v2-fixture"},
                assessment=assessment.to_dict(),
                sensor_profile=config.sensor_profile,
                control_context={"command_id": "cmd-1", "target_pwm_us": 1320, "acknowledged": True},
            )
            recorder.stop("test")
            self.assertEqual(recorder.frame_count, 1)

            rows = [json.loads(line) for line in (recorder.directory / "frames.jsonl").read_text().splitlines()]
            self.assertEqual(rows[0]["raw"]["type"], "SAMPLE")
            self.assertEqual(rows[0]["sensor_profile"], "FSR_ONLY")
            self.assertEqual(rows[0]["sensor_identity"]["device_id"], "sensor-fsr-01")
            self.assertEqual(rows[0]["contact_assessment"]["readings"][0]["name"], "FSR_A")
            self.assertEqual(rows[0]["pwm_command_id"], "cmd-1")
            self.assertEqual(rows[0]["pwm_target_us"], 1320)
            self.assertTrue(rows[0]["pwm_ack"])

            csv_path = recorder.export_csv()
            with open(csv_path, newline="", encoding="utf-8") as handle:
                header = next(csv.reader(handle))
            for column in ("device_id", "sensor_profile", "contact_state", "pwm_command_id", "pwm_target_us", "pwm_ack"):
                self.assertIn(column, header)

            replay_path = store.export_replay_jsonl(recorder.metadata.trial_id)
            replay_lines = replay_path.read_text().splitlines()
            self.assertIn('"type":"HELLO"', replay_lines[0])
            self.assertIn('"FSR_ONLY"', replay_lines[0])
            replay = ReplaySensorAdapter(replay_path)
            replay.connect()
            replayed = replay.read_frame(timeout_s=1.0)
            self.assertEqual(replayed.channel_ids, (0, 1))
            replay.close()

            direct = ReplaySensorAdapter(recorder.directory / "frames.jsonl")
            direct.connect()
            direct_frame = direct.read_frame(timeout_s=1.0)
            self.assertEqual(direct_frame.channel_ids, (0, 1))
            self.assertEqual(direct_frame.device_id, "sensor-fsr-01")
            direct.close()


if __name__ == "__main__":
    unittest.main()
