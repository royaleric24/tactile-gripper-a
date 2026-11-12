"""SIMULATED; candidate limits are not measured servo limits."""
import unittest,tempfile
from pathlib import Path
from gripper_a.gripper_controller import LimitedTrialController
class TrialTests(unittest.TestCase):
 def make(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
  g=LimitedTrialController(log_path=Path(t.name)/'sim.jsonl');self.addCleanup(g.close);g.connect();return g
 def test_no_manual_trigger(self):
  g=self.make()
  with self.assertRaises(ValueError):g.begin_trial(1460,1540,1500,condition='LINKAGE_DETACHED')
 def test_arm_still_locked(self):
  g=self.make()
  with self.assertRaises(ValueError):g.arm()
 def test_range(self):
  g=self.make()
  with self.assertRaises(ValueError):g.begin_trial(500,2500,1500,condition='LINKAGE_DETACHED',manual_trigger=True)
 def test_isolated_reference(self):
  g=self.make()
  with self.assertRaises(ValueError):g.begin_trial(1460,1540,1480,condition='LINKAGE_DETACHED',manual_trigger=True)
 def test_physical_confirmation(self):
  g=self.make()
  with self.assertRaises(ValueError):g.begin_trial(1460,1540,1500,condition='UNKNOWN',manual_trigger=True)
 def test_manual_pulse_stop(self):
  g=self.make();g.begin_trial(1460,1540,1500,condition='LINKAGE_DETACHED',manual_trigger=True)
  g.trial_pulse(1500,manual_trigger=True);g.stop();self.assertFalse(g.trial)
  with self.assertRaises(ValueError):g.trial_pulse(1520,manual_trigger=True)
 def test_first_wrong(self):
  g=self.make();g.begin_trial(1460,1540,1500,condition='LINKAGE_DETACHED',manual_trigger=True)
  with self.assertRaises(ValueError):g.trial_pulse(1520,manual_trigger=True)
 def test_mechanical_local_range(self):
  g=self.make();g.begin_trial(1490,1510,1500,condition='LOCAL_RANGE_CONFIRMED',manual_trigger=True)
  with self.assertRaises(ValueError):g.trial_pulse(1520,manual_trigger=True)
