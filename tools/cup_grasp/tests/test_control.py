import unittest

from tools.cup_grasp.control import FakeCupGripper, FixedClampMode, TactileFeedbackFSM
from tools.cup_grasp.model import load_config
from tools.cup_grasp.tactile import TactileProcessor


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config("config/cup_grasp.simulated.json")
        self.gripper = FakeCupGripper()

    def test_fixed_mode(self):
        mode = FixedClampMode(self.config, self.gripper)
        mode.start(0)
        self.assertEqual(mode.state.value, "HOLD")
        self.assertEqual([c["pulse_us"] for c in self.gripper.commands], [1500, 1600])
        mode.stop(1)
        self.assertEqual(mode.state.value, "DONE")
        self.assertEqual(self.gripper.commands[-1]["kind"], "STOP")

    def test_feedback_contact_hold_release(self):
        processor = TactileProcessor(self.config.tactile)
        fsm = TactileFeedbackFSM(self.config, self.gripper)
        fsm.start(0)
        now = 0
        for i in range(1, 11):
            now = i * 40_000_000
            fsm.update(processor.update(self._frame(1000, i), now), now, processor.sensor_ok(now))
        for i in range(11, 41):
            now = i * 40_000_000
            fsm.update(processor.update(self._frame(1700, i), now), now, processor.sensor_ok(now))
        self.assertEqual(fsm.state.value, "HOLD")
        self.assertGreaterEqual(fsm.pulse, 1500)
        fsm.release(now + 1)
        self.assertEqual(fsm.state.value, "RELEASE")

    def test_invalid_sensor_faults_and_stops(self):
        processor = TactileProcessor(self.config.tactile)
        fsm = TactileFeedbackFSM(self.config, self.gripper)
        fsm.start(0)
        for i in range(1, 11):
            now = i * 40_000_000
            fsm.update(processor.update(self._frame(1000, i), now), now, processor.sensor_ok(now))
        # saturated/invalid sample must fault, not continue closing
        now = 11 * 40_000_000
        fsm.update(processor.update(self._frame(8388607, 11, flag=0x01), now), now, True)
        self.assertEqual(fsm.state.value, "FAULT")
        self.assertEqual(fsm.fault_reason, "NO_VALID_TACTILE")
        self.assertEqual(self.gripper.commands[-1]["kind"], "STOP")

    def test_tactile_timeout_faults(self):
        processor = TactileProcessor(self.config.tactile)
        fsm = TactileFeedbackFSM(self.config, self.gripper)
        fsm.start(0)
        for i in range(1, 11):
            now = i * 40_000_000
            fsm.update(processor.update(self._frame(1000, i), now), now, processor.sensor_ok(now))
        fsm.tick(10 * 40_000_000 + 2_000_000_000, False)
        self.assertEqual(fsm.state.value, "FAULT")
        self.assertEqual(fsm.fault_reason, "TACTILE_TIMEOUT")

    @staticmethod
    def _frame(value, seq, flag=0):
        from types import SimpleNamespace
        return SimpleNamespace(raw_adc=[value] + [0] * 11,
                               valid=[True] * 12,
                               channel_flags=[flag] + [0] * 11,
                               timestamp_us=seq * 40000,
                               frame_seq=seq,
                               host_monotonic_ns=seq * 40_000_000)


if __name__ == "__main__":
    unittest.main()
