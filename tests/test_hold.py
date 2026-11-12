"""SIMULATED hold behavior with FakeGripper, no device access."""
import unittest
from unittest.mock import patch
import test_bench
class HoldTests(unittest.TestCase):
 setUp=test_bench.BenchTests.setUp
 sleep=test_bench.BenchTests.sleep
 def commands(self,name):return [e for e in self.g.fake.events if e['action']==name]
 def test_hold_select_does_not_output(self):
  self.g.begin();self.g.select_mode(True);self.assertFalse(self.commands('BENCH_HOLD'))
 def test_hold_updates_do_not_renew(self):
  self.g.begin();self.g.select_mode(True);self.g.pulse(1500);deadline=self.g.hold_deadline
  self.now=1;self.g.pulse(2500);self.now=2;self.g.pulse(500)
  self.assertEqual(self.g.hold_deadline,deadline);self.assertIsNone(self.g.pending_until)
  self.assertEqual(len(self.commands('BENCH_HOLD')),3)
 def test_hold_expiry_revokes_permission(self):
  self.g.begin();self.g.select_mode(True);self.g.pulse(1500);self.now=5;self.g.poll()
  self.assertFalse(self.g.active)
  with self.assertRaises(PermissionError):self.g.pulse(1550)
  self.g.begin();self.assertFalse(self.g.hold_mode)
 def test_hold_stop_disarm(self):
  self.g.begin();self.g.select_mode(True);self.g.pulse(1500);self.g.stop();self.assertIsNone(self.g.hold_deadline)
  self.g.begin();self.g.select_mode(True);self.g.pulse(1500);self.g.disarm();self.assertFalse(self.g.active)
 def test_hold_first_target_and_mode_switch(self):
  self.g.begin();self.g.select_mode(True)
  self.g.pulse(1550)  # arbitrary first target now allowed
  with self.assertRaises(ValueError):self.g.select_mode(False)
 def test_hold_no_permission(self):
  with self.assertRaises(PermissionError):self.g.select_mode(True)
 def test_hold_disconnect(self):
  self.g.begin();self.g.select_mode(True);self.g.pulse(1500)
  with patch('gripper_a.gripper_controller.GripperController._send',side_effect=RuntimeError('disconnected')):
   self.now=1
   with self.assertRaises(RuntimeError):self.g.poll()
  self.assertFalse(self.g.active)
