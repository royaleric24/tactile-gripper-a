"""SIMULATED operator records, not actual calibration or device access."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from gripper_a.gripper_controller import LimitedTrialController
from gripper_a.calibration import CalibrationSession

def ref():return dict(source_kind='SIMULATED',installation_id='SIM_FIXTURE',evidence_source='SYNTHETIC_TEST_ONLY',safe_initial_reason='synthetic reference, not hardware guidance',reviewer='unit_test',approval='INITIAL_TARGET_AND_PATH_REVIEWED',safe_path_confirmed=True,low_us=1480,high_us=1540,initial_us=1500)
class CalibrationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.now=0
  self.g=LimitedTrialController(log_path=Path(self.tmp.name)/'transport.jsonl')
  self.s=CalibrationSession(self.g,Path(self.tmp.name)/'session',clock=lambda:self.now);self.addCleanup(self.s.close);self.s.connect()
 def begin(self):self.s.confirm_reference(ref());self.s.locate(confirmed=True)
 def observe(self,**kw):
  self.now+=0.6;self.s.observe(direction=kw.pop('direction','OPENING'),safe=kw.pop('safe',True),**kw)
 def test_no_reference_no_motion(self):
  count=len(self.g.fake.events)
  with self.assertRaises(ValueError):self.s.locate(confirmed=True)
  self.assertEqual(len(self.g.fake.events),count)
 def test_template_rejected(self):
  with self.assertRaises(ValueError):self.s.confirm_reference(json.loads(Path('config/calibration_reference.template.json').read_text()))
 def test_no_implicit_confirmation(self):
  self.s.confirm_reference(ref())
  with self.assertRaises(ValueError):self.s.locate()
 def test_reference_only_no_begin(self):
  self.s.confirm_reference(ref());self.assertEqual(self.s.state,'REFERENCE_CONFIRMED');self.assertFalse(self.g.trial)
 def test_must_observe(self):
  self.begin()
  with self.assertRaises(ValueError):self.s.step(20,confirmed=True)
 def test_wait_output_end(self):
  self.begin()
  with self.assertRaises(ValueError):self.s.observe(direction='OPENING',safe=True)
 def test_local_step_and_measurement(self):
  self.begin();self.observe(opening_mm=3.2,measurement_method='SIM_RULER');self.s.step(20,confirmed=True);self.observe()
  self.assertEqual(self.s.current,1520);self.assertIsNone(self.s.points[-1]['opening_mm']);self.assertIsNone(self.s.points[-1]['actual_angle_deg'])
 def test_unmeasured_has_no_default_number(self):
  self.begin();self.observe();self.assertIsNone(self.s.points[0]['opening_mm'])
 def test_nonfinite_opening_rejected(self):
  self.begin();self.now=1
  with self.assertRaises(ValueError):self.s.observe(direction='OPENING',safe=True,opening_mm=float('nan'),measurement_method='fake')
 def test_range_and_step_reject(self):
  self.begin();self.observe()
  for delta in (21,True,0,-40):
   with self.assertRaises(ValueError):self.s.step(delta,confirmed=True)
 def test_abnormal_fault_latches(self):
  self.begin();self.observe(abnormal=True);self.assertEqual(self.s.state,'FAULT');self.assertFalse(self.s.active)
  with self.assertRaises(ValueError):self.s.confirm_reference(ref())
  with self.assertRaises(ValueError):self.s.export_candidate(5)
 def test_timeout_no_auto_restart(self):
  self.begin();self.now=31;self.s.poll();self.assertFalse(self.s.active);self.assertIsNone(self.s.reference)
 def test_stop_disarm_exit(self):
  self.begin();self.s.stop(disarm=True);self.assertFalse(self.g.trial);self.assertIsNone(self.s.current)
  self.s.close();self.s.close();self.assertTrue(self.s.closed)
  rows=[json.loads(x) for x in (self.s.folder/'calibration.jsonl').read_text().splitlines()];self.assertEqual(rows[-1]['operation'],'CLOSED')
 def test_no_unauthorized_real_motion(self):
  self.s.confirm_reference(ref());self.g.dry_run=False
  try:
   with self.assertRaises(PermissionError):self.s.locate(confirmed=True)
  finally:self.g.dry_run=True
 def test_reference_requires_real_evidence_kind(self):
  self.g.dry_run=False
  try:
   with self.assertRaises(ValueError):self.s.confirm_reference(ref())
  finally:self.g.dry_run=True
 def test_candidate_interior_points(self):
  self.begin();self.observe(direction='UNKNOWN')
  for delta,d in [(-20,'CLOSING'),(20,'OPENING'),(20,'OPENING'),(20,'OPENING')]:
   self.s.step(delta,confirmed=True);self.observe(direction=d)
  result=self.s.export_candidate(10)
  self.assertEqual((result['low_us'],result['high_us']),(1500,1520));self.assertEqual(result['pulse_increase_direction'],'OPENING')
  self.assertEqual(result['run_kind'],'SIMULATED');self.assertFalse(result['automatic_hardware_enable']);self.assertFalse(result['continuous_interval_verified'])
 def test_not_enough_points(self):
  self.begin();self.observe()
  with self.assertRaises(ValueError):self.s.export_candidate(1)
 def test_installation_cannot_mix(self):
  self.s.confirm_reference(ref());other=ref();other['installation_id']='other'
  with self.assertRaises(ValueError):self.s.confirm_reference(other)
 def test_communication_failure_logs_and_stops(self):
  self.begin()
  with patch.object(self.g,'heartbeat',side_effect=RuntimeError('disconnect')):
   self.now=1.1;self.s.poll()
  self.assertEqual(self.s.state,'FAULT');self.assertFalse(self.s.active)
 def test_no_serial_in_fake(self):
  with patch('serial.Serial',side_effect=AssertionError('hardware touched')):
   self.begin();self.observe();self.s.close()
