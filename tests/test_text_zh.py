"""Display-only Chinese mapping tests; internal values must stay unchanged."""

import unittest

from tactile_gripper.ui.text_zh import (
    action_label,
    event_detail_label,
    sensor_label,
    source_label,
    stage_label,
    status_label,
    trial_status_label,
)


class ChineseMappingTests(unittest.TestCase):
    def test_status_terms_keep_internal_english(self):
        self.assertEqual(status_label("MANUAL"), "手动模式（MANUAL）")
        self.assertEqual(status_label("STANDBY"), "待机（STANDBY）")
        self.assertEqual(trial_status_label("INTERRUPTED"), "异常中断（INTERRUPTED）")
        self.assertEqual(status_label("COMPLETED"), "正常完成（COMPLETED）")
        self.assertEqual(status_label("UNKNOWN_VALUE"), "UNKNOWN_VALUE")

    def test_sensor_and_source_terms(self):
        self.assertEqual(sensor_label("SENSOR WAITING"), "等待传感器数据")
        self.assertEqual(sensor_label("SENSOR STREAMING"), "传感器数据正常")
        self.assertEqual(source_label("SIMULATION"), "仿真（SIMULATION）")
        self.assertEqual(source_label("LIVE"), "真实设备（LIVE）")
        self.assertEqual(source_label("REPLAY"), "只读回放（REPLAY）")

    def test_stage_and_action(self):
        self.assertEqual(stage_label("DEVICE_ACK"), "设备确认（ACK）")
        self.assertEqual(action_label("SET_PWM"), "提交 PWM 目标")
        self.assertEqual(action_label("STOP"), "STOP")

    def test_known_details_are_translated(self):
        self.assertEqual(
            event_detail_label("dry-run simulation; no serial write, no device ACK"),
            "仿真模式：未写串口，无设备确认（ACK）",
        )
        self.assertIn("STOP", event_detail_label("STOP revokes permits and calls firmware output.off()"))
        self.assertEqual(event_detail_label("some technical detail"), "some technical detail")


if __name__ == "__main__":
    unittest.main()
