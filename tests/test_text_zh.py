"""Display-only Chinese mapping tests; internal values must stay unchanged."""

import unittest

from tactile_gripper.ui.text_zh import (
    action_label,
    contact_reason_label,
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




class ContactReasonTests(unittest.TestCase):
    def test_known_reasons_are_chinese_and_keep_unknown_text(self):
        self.assertEqual(
            contact_reason_label("relative contact above tight threshold; do not keep tightening"),
            "相对接触超过偏紧阈值；不要再继续夹紧",
        )
        self.assertEqual(contact_reason_label("no sensor frame"), "没有传感器帧")
        self.assertEqual(contact_reason_label("some future reason"), "some future reason")
        self.assertEqual(contact_reason_label(None), "")

    def test_dynamic_reasons_keep_their_numbers(self):
        self.assertEqual(
            contact_reason_label("stale frame (250.0 ms > 200.0 ms)"),
            "帧已过期：250.0 ms > 200.0 ms",
        )
        self.assertEqual(
            contact_reason_label("invalid or saturated FSR channel(s): FSR_A, FSR_B"),
            "无效或饱和的 FSR 通道：FSR_A, FSR_B",
        )


class DynamicEventDetailTests(unittest.TestCase):
    def test_profile_specific_simulation_detail_is_translated(self):
        self.assertEqual(
            event_detail_label("SIMULATION sensor connected (MATRIX_ELECTRODES_12); not real hardware"),
            "已连接仿真传感器；不是真实硬件",
        )
        self.assertEqual(event_detail_label("SIMULATION sensor disconnected"), "仿真传感器已断开")
        self.assertEqual(event_detail_label("some unmapped detail"), "some unmapped detail")


if __name__ == "__main__":
    unittest.main()
