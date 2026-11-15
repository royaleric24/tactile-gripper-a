"""AUTO policy tests: synthetic frames only; no control writes."""

import unittest

from tactile_gripper.control import AutoGate, AutoLimits, RuleBasedAutoPolicy, SimulatedAutoSession
from tactile_gripper.errors import ControlDenied
from tactile_gripper.sources import DataSource

from support import frame

NOW = 10_000_000_000


def simulation_gate(source=DataSource.SIMULATION, **kwargs):
    return AutoGate(source=source, allow_simulation=source is DataSource.SIMULATION, **kwargs)


class AutoGateTests(unittest.TestCase):
    def test_real_auto_is_blocked_by_default(self):
        gate = AutoGate(source=DataSource.LIVE)
        available, reasons = gate.evaluate()
        self.assertFalse(available)
        self.assertIn("协议未确认", " ".join(reasons))
        self.assertIn("标定", " ".join(reasons))

    def test_simulation_policy_is_explicit(self):
        policy = RuleBasedAutoPolicy(AutoLimits(), simulation_gate())
        available, reasons = policy.availability()
        self.assertTrue(available, reasons)
        blocked = RuleBasedAutoPolicy(AutoLimits(), AutoGate(source=DataSource.LIVE))
        self.assertFalse(blocked.availability()[0])


class AutoPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = RuleBasedAutoPolicy(
            AutoLimits(
                stale_after_ms=1000,
                min_valid_channels=2,
                contact_threshold=0.8,
                step_us=10,
                min_interval_ms=100,
                max_steps=3,
                max_total_us=30,
            ),
            simulation_gate(),
        )

    def test_manual_simulation_steps_are_bounded(self):
        session = SimulatedAutoSession(self.policy)
        frame1 = frame(seq=1, source=DataSource.SIMULATION, contact_score=0.1, host_received_ns=NOW)
        first = session.step(frame1, now_ns=NOW)
        self.assertEqual(first.action, "STEP")
        second = session.step(frame1, now_ns=NOW + 100_000_000)
        self.assertEqual(second.action, "STEP")
        third = session.step(frame1, now_ns=NOW + 200_000_000)
        self.assertEqual(third.action, "STEP")
        stopped = session.step(frame1, now_ns=NOW + 300_000_000)
        self.assertEqual(stopped.action, "STOP")
        self.assertEqual(session.target_us, 30)

    def test_contact_stops_before_step_limit(self):
        decision = self.policy.evaluate(
            frame(seq=1, source=DataSource.SIMULATION, contact_score=0.95, host_received_ns=NOW),
            now_ns=NOW,
            target_us=0,
            steps=0,
            total_change_us=0,
        )
        self.assertEqual(decision.action, "STOP")
        self.assertIn("contact", decision.reason)

    def test_stale_frame_faults(self):
        decision = self.policy.evaluate(
            frame(seq=1, source=DataSource.SIMULATION, contact_score=0.1, host_received_ns=NOW - 1_500_000_000),
            now_ns=NOW,
            target_us=0,
            steps=0,
            total_change_us=0,
        )
        self.assertEqual(decision.action, "FAULT")
        self.assertIn("older", decision.reason)

    def test_sensor_stale_state_faults(self):
        decision = self.policy.evaluate(
            frame(seq=1, source=DataSource.SIMULATION, contact_score=0.1, host_received_ns=NOW),
            now_ns=NOW,
            target_us=0,
            steps=0,
            total_change_us=0,
            sensor_state="STALE",
        )
        self.assertEqual(decision.action, "FAULT")

    def test_invalid_channels_fault(self):
        decision = self.policy.evaluate(
            frame(seq=1, values=[10, None, 30, 40], mask=[True, False, True, True], source=DataSource.SIMULATION, contact_score=0.1, host_received_ns=NOW),
            now_ns=NOW,
            target_us=0,
            steps=0,
            total_change_us=0,
        )
        # 3 valid channels >= 2; use a policy requiring 4.
        strict = RuleBasedAutoPolicy(AutoLimits(min_valid_channels=4, contact_threshold=0.8), simulation_gate())
        decision = strict.evaluate(
            frame(seq=1, values=[10, None, 30, 40], mask=[True, False, True, True], source=DataSource.SIMULATION, contact_score=0.1, host_received_ns=NOW),
            now_ns=NOW,
            target_us=0,
            steps=0,
            total_change_us=0,
        )
        self.assertEqual(decision.action, "FAULT")
        self.assertIn("valid channels", decision.reason)

    def test_missing_contact_metric_never_inferred(self):
        decision = self.policy.evaluate(
            frame(seq=1, source=DataSource.SIMULATION, contact_score=None, host_received_ns=NOW),
            now_ns=NOW,
            target_us=0,
            steps=0,
            total_change_us=0,
        )
        self.assertEqual(decision.action, "FAULT")
        self.assertIn("contact metric", decision.reason)

    def test_rate_limit_waits(self):
        session = SimulatedAutoSession(self.policy)
        item = frame(seq=1, source=DataSource.SIMULATION, contact_score=0.1, host_received_ns=NOW)
        self.assertEqual(session.step(item, now_ns=NOW).action, "STEP")
        self.assertEqual(session.step(item, now_ns=NOW + 10_000_000).action, "WAIT")

    def test_no_frame_waits(self):
        decision = self.policy.evaluate(None, now_ns=NOW, target_us=0, steps=0, total_change_us=0)
        self.assertEqual(decision.action, "WAIT")

    def test_unavailable_session_cannot_start(self):
        with self.assertRaises(ControlDenied):
            SimulatedAutoSession(RuleBasedAutoPolicy(AutoLimits(), AutoGate(source=DataSource.LIVE)))


if __name__ == "__main__":
    unittest.main()
