"""S1 model validation tests.  All data is TEST/SIMULATION, no hardware."""

import math
import unittest

from tactile_gripper.errors import FrameValidationError
from tactile_gripper.models import (
    ChannelConfig,
    ChannelConfiguration,
    ControlAction,
    ControlCommand,
    ControlEvent,
    DeviceStatus,
    TactileFrame,
    TrialMetadata,
)
from tactile_gripper.sources import DataSource

from support import channel_config, demo_config, frame


class ChannelConfigTests(unittest.TestCase):
    def test_dynamic_channel_counts(self):
        for count in (1, 4, 12, 36):
            self.assertEqual(channel_config(count).expected_channel_count, count)
        self.assertEqual(demo_config().expected_channel_count, 36)
        self.assertEqual(demo_config().matrix_cells, 36)

    def test_matrix_cells_need_not_equal_scan_channels(self):
        # 36 sensing cells can be scanned through a different number of ADC
        # channels; the model must not enforce an equality that hardware has
        # not confirmed.
        config = ChannelConfiguration(
            channels=tuple(ChannelConfig(channel_id=i) for i in range(12)),
            matrix_rows=6,
            matrix_cols=6,
        )
        self.assertEqual(config.expected_channel_count, 12)
        self.assertEqual(config.matrix_cells, 36)

    def test_rejects_duplicate_channel_and_bad_mapping(self):
        with self.assertRaises(ValueError):
            ChannelConfiguration(
                channels=(
                    ChannelConfig(channel_id=0),
                    ChannelConfig(channel_id=0),
                )
            )
        with self.assertRaises(ValueError):
            ChannelConfig(channel_id=0, matrix_row=0, matrix_col=None)
        with self.assertRaises(ValueError):
            ChannelConfiguration(
                channels=(ChannelConfig(channel_id=0, matrix_row=2, matrix_col=0),),
                matrix_rows=2,
                matrix_cols=2,
            )

    def test_known_unit_only(self):
        with self.assertRaises(ValueError):
            ChannelConfig(channel_id=0, unit="NEWTON")

    def test_config_dict_roundtrip(self):
        original = demo_config()
        restored = ChannelConfiguration.from_dict(original.to_dict())
        self.assertEqual(restored.expected_channel_count, original.expected_channel_count)
        self.assertEqual(restored.channel_ids, original.channel_ids)


class FrameValidationTests(unittest.TestCase):
    def setUp(self):
        self.config = channel_config(4)

    def test_valid_frame(self):
        item = frame()
        self.assertEqual(item.channel_count, 4)
        self.assertEqual(item.source, DataSource.LIVE)
        self.assertEqual(item.validate(self.config), item)

    def test_length_mismatch_against_config(self):
        with self.assertRaises(FrameValidationError) as ctx:
            frame(count=3).validate(self.config)
        self.assertEqual(ctx.exception.code, "LENGTH_MISMATCH")

    def test_nan_and_inf_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            values = [100, value, 102, 103]
            with self.subTest(value=value):
                with self.assertRaises(FrameValidationError) as ctx:
                    frame(values=values).validate(self.config)
                self.assertEqual(ctx.exception.code, "INVALID_VALUE")

    def test_invalid_mask_must_be_bool(self):
        with self.assertRaises(FrameValidationError) as ctx:
            frame(mask=[True, 1, True, True]).validate(self.config)
        self.assertEqual(ctx.exception.code, "INVALID_MASK")

    def test_valid_channel_cannot_be_null(self):
        with self.assertRaises(FrameValidationError) as ctx:
            frame(values=[100, None, 102, 103]).validate(self.config)
        self.assertEqual(ctx.exception.code, "INVALID_VALUE")

    def test_invalid_channel_kept_but_not_zero(self):
        item = frame(values=[100, None, 102, 103], mask=[True, False, True, True])
        item.validate(self.config)
        self.assertEqual(item.invalid_channels, (1,))
        self.assertIsNone(item.channels[1])
        self.assertEqual(item.valid_channel_count, 3)

    def test_unknown_channel_id(self):
        item = frame()
        item = TactileFrame(
            **{
                **item.__dict__,
                "channel_ids": (99, 1, 2, 3),
                "raw": None,
            }
        )
        with self.assertRaises(FrameValidationError) as ctx:
            item.validate(self.config)
        self.assertEqual(ctx.exception.code, "INVALID_CHANNEL")

    def test_wrong_protocol_version(self):
        item = frame()
        item = TactileFrame(**{**item.__dict__, "protocol_version": 2, "raw": None})
        with self.assertRaises(FrameValidationError) as ctx:
            item.validate(self.config)
        self.assertEqual(ctx.exception.code, "PROTOCOL_VERSION")

    def test_bool_is_not_an_integer_sequence(self):
        item = frame()
        item = TactileFrame(**{**item.__dict__, "frame_seq": True, "raw": None})
        with self.assertRaises(FrameValidationError) as ctx:
            item.validate(self.config)
        self.assertEqual(ctx.exception.code, "INVALID_VALUE")

    def test_source_is_never_defaulted_to_live(self):
        self.assertEqual(frame(source=DataSource.SIMULATION).source, DataSource.SIMULATION)


class ControlModelTests(unittest.TestCase):
    def test_firmware_mapping_distinguishes_unsupported_actions(self):
        pwm = ControlCommand(ControlAction.SET_PWM, DataSource.LIVE, target_pwm_us=1500)
        self.assertEqual(pwm.firmware_command, "BENCH_HOLD")
        hold = ControlCommand(ControlAction.HOLD, DataSource.LIVE)
        self.assertTrue(hold.unsupported)
        self.assertIsNone(hold.firmware_command)
        updates = ControlCommand(ControlAction.STOP_UPDATES, DataSource.LIVE)
        self.assertTrue(updates.software_only)

    def test_ack_is_not_actual_position(self):
        command = ControlCommand(ControlAction.SET_PWM, DataSource.LIVE, target_pwm_us=1500)
        event = ControlEvent.from_command(command, "DEVICE_ACK", "MANUAL", device_ack=True)
        self.assertEqual(event.commanded_pwm_us, 1500)
        self.assertIsNone(event.actual_pwm_us)
        self.assertFalse(event.actual_position_known)
        with self.assertRaises(ValueError):
            ControlEvent(
                action="SET_PWM",
                stage="DEVICE_ACK",
                source=DataSource.LIVE,
                mode="MANUAL",
                actual_pwm_us=1500,
            )

    def test_event_serialization_keeps_stage_flags(self):
        command = ControlCommand(ControlAction.SET_PWM, DataSource.LIVE, target_pwm_us=1500)
        event = ControlEvent.from_command(
            command, "DEVICE_ACK", "MANUAL", serial_write_ok=True, device_ack=True
        )
        data = event.to_dict()
        self.assertTrue(data["serial_write_ok"])
        self.assertTrue(data["device_ack"])
        self.assertIsNone(data["actual_pwm_us"])
        self.assertFalse(data["actual_position_known"])


class StatusAndTrialModelTests(unittest.TestCase):
    def test_device_status_serialization(self):
        status = DeviceStatus(
            device_id="sensor-test",
            kind="SENSOR",
            source=DataSource.SIMULATION,
            connected=True,
            state="STREAMING",
            channel_count=36,
        )
        data = status.to_dict()
        self.assertEqual(data["source"], "SIMULATION")
        self.assertEqual(data["state"], "STREAMING")

    def test_trial_metadata_roundtrip(self):
        metadata = TrialMetadata(
            trial_id="T-TEST-001",
            name="offline test",
            source=DataSource.SIMULATION,
            mode="MANUAL",
            conditions={"object": "none"},
            parameters={"pwm_min_us": 500},
        )
        restored = TrialMetadata.from_dict(metadata.to_dict())
        self.assertEqual(restored.trial_id, metadata.trial_id)
        self.assertEqual(restored.source, DataSource.SIMULATION)


if __name__ == "__main__":
    unittest.main()
