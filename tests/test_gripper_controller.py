"""SIMULATED only; synthetic pulse bounds are NOT mechanical calibration."""
import json,unittest,tempfile
from pathlib import Path
from gripper_a.gripper_controller import GripperController
class ControllerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.c=json.loads(Path('config/gripper_control.json').read_text())
 def make(self,cal=False,**kw):
  c=dict(self.c)
  if cal:c.update(hardware_enabled=True,calibration_state='CONFIRMED',safe_min_us=1000,safe_max_us=2000,initial_pulse_us=1400,max_step_us=20,max_total_change_us=50)
  g=GripperController(c,log_path=Path(self.tmp.name)/f'{len(list(Path(self.tmp.name).iterdir()))}.jsonl',**kw);self.addCleanup(g.close);return g
 def test_default_dry_and_uncalibrated(self):
  g=self.make();g.connect();self.assertTrue(g.dry_run);self.assertEqual(g.state,'DISARMED')
  with self.assertRaises(ValueError):g.arm()
  with self.assertRaises(ValueError):g.set_pulse_us(1500)
 def test_no_hardware_permission(self):
  g=self.make(dry_run=False)
  with self.assertRaises(PermissionError):g.connect('/dev/cu.usbserial-EXAMPLE_ESP32')
 def test_fake_integration(self):
  g=self.make(True);g.connect();g.arm();self.assertEqual(g.state,'ARMED');g.set_pulse_us(1400);g.stop();self.assertEqual(g.state,'DISARMED');self.assertIsNone(g.fake.actual_angle)
  self.assertTrue(all(e['run_kind']=='SIMULATED' for e in g.fake.events))
 def test_bad_values(self):
  g=self.make(True);g.connect();g.arm()
  for p in [True,1400.0,999,2500,1410]:
   with self.subTest(p=p):
    with self.assertRaises(ValueError):g.set_pulse_us(p)
 def test_rate_and_step(self):
  g=self.make(True);g.connect();g.arm();g.set_pulse_us(1400)
  with self.assertRaises(ValueError):g.set_pulse_us(1401)
  with self.assertRaises(ValueError):g.set_pulse_us(1500)
 def test_disarm_blocks_new_motion(self):
  g=self.make(True);g.connect();g.arm();g.disarm()
  with self.assertRaises(ValueError):g.set_pulse_us(1400)
 def test_reconnect_resets(self):
  g=self.make(True);g.connect();g.arm();g.connected=False;g.connect();self.assertEqual(g.state,'DISARMED');self.assertIsNone(g.target)
 def test_disconnect_unknown_and_no_auto_recovery(self):
  from unittest.mock import Mock
  from gripper_a.serial_client import CommunicationError
  g=self.make(True,dry_run=False,hardware_permission=True);g.connected=True;g.state='ACTIVE';g.transport=Mock();g.transport.exchange.side_effect=CommunicationError('disconnected')
  with self.assertRaises(CommunicationError):g.get_status()
  self.assertEqual(g.state,'FAULT');self.assertEqual(g.output_state,'UNKNOWN');self.assertFalse(g.connected);g.transport.close.assert_called_once()
 def test_changed_boot_session_faults(self):
  from unittest.mock import Mock
  g=self.make(True,dry_run=False,hardware_permission=True);g.connected=True;g.boot_id='old';g.transport=Mock();g.transport.exchange.return_value={'type':'STATUS','boot_id':'new','state':'DISARMED'}
  with self.assertRaises(RuntimeError):g.get_status()
  self.assertFalse(g.connected);self.assertEqual(g.output_state,'UNKNOWN')
