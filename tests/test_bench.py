"""SIMULATED bench policy and FakeGripper tests, never hardware."""
import tempfile,unittest,json,subprocess,sys
from pathlib import Path
from unittest.mock import patch
from gripper_a.bench import BenchController
class BenchTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.now=0
  self.g=BenchController(authorized=True,clock=lambda:self.now,sleeper=self.sleep,log_path=Path(self.tmp.name)/'log.jsonl')
  self.addCleanup(self.g.close);self.g.connect()
 def sleep(self,x):self.now+=x
 def pulses(self):return [e for e in self.g.fake.events if e.get('action')=='BENCH_PULSE']
 def test_start_has_no_pulse(self):
  self.g.begin();self.assertFalse(self.pulses())
 def test_continuous_manual_targets(self):
  self.g.begin()
  for x in (1500,2000,500,2500,1000,1500):self.g.pulse(x);self.now+=.7;self.g.poll()
  self.assertEqual(len(self.pulses()),6)
 def test_no_authorization(self):
  self.g.authorized=False
  with self.assertRaises(PermissionError):self.g.begin()
  self.assertFalse(self.pulses())
 def test_no_session(self):
  with self.assertRaises(PermissionError):self.g.pulse(1500)
 def test_arbitrary_first_target(self):
  self.g.begin();self.g.pulse(2000);self.assertEqual(len(self.pulses()),1)
  self.now+=.7;self.g.poll()
  with self.assertRaises(ValueError):self.g.pulse(499)
 def test_range_rejected(self):
  self.g.begin();self.g.pulse(1500);self.now+=.7;self.g.poll()
  for x in (499,2501,True,1500.0):
   with self.assertRaises(ValueError):self.g.pulse(x)
  self.assertEqual(len(self.pulses()),1)
 def test_arbitrary_step_accepted(self):
  self.g.begin();self.g.pulse(1500);self.now+=.7;self.g.poll()
  self.g.pulse(2500);self.now+=.7;self.g.poll()
  self.g.pulse(500);self.now+=.7;self.g.poll()
  self.assertEqual(len(self.pulses()),3)
 def test_repeated_poll_does_not_move(self):
  self.g.begin()
  for i in range(5):self.now+=1;self.g.poll()
  self.assertFalse(self.pulses())
 def test_expiry_no_renew(self):
  self.g.begin();self.now=301
  with self.assertRaises(TimeoutError):self.g.poll()
  with self.assertRaises(PermissionError):self.g.pulse(1500)
  self.assertFalse(self.g.active)
 def test_stop_disarm_revoke(self):
  self.g.begin();self.g.pulse(1500);self.g.stop()
  with self.assertRaises(PermissionError):self.g.pulse(1550)
  self.g.begin();self.g.pulse(2000);self.assertEqual(len(self.pulses()),2)
  self.g.disarm();self.assertFalse(self.g.active)
 def test_communication_failure_no_retry(self):
  self.g.begin()
  with patch('gripper_a.gripper_controller.GripperController._send',side_effect=RuntimeError('disconnect')) as call:
   with self.assertRaises(RuntimeError):self.g.pulse(1500)
   call.assert_called_once()
  self.assertFalse(self.g.active)
 def test_fault_blocks_new_pulse(self):
  self.g.begin();self.g.state='FAULT'
  with self.assertRaises(RuntimeError):self.g.pulse(1500)
  self.assertFalse(self.pulses());self.assertFalse(self.g.active)
 def test_close_saves_log(self):
  self.g.begin();self.g.close()
  self.assertFalse(self.g.connected)
  rows=[json.loads(x) for x in (Path(self.tmp.name)/'log.jsonl').read_text().splitlines()]
  self.assertEqual(rows[-1]['event'],'CONTROLLER_CLOSED')
  self.g.close() # idempotent cleanup
 def test_mechanical_begin_condition(self):
  self.g.begin(assembled=True)
  e=[x for x in self.g.fake.events if x.get('action')=='BEGIN_BENCH'][-1]
  self.assertEqual(e.get('physical_condition'),'GRIPPER_ASSEMBLED')

 def test_mechanical_continuous_ignores_5s(self):
  self.g.begin(assembled=True);self.g.select_mode(True);self.g.pulse(1500)
  self.assertIsNone(self.g.hold_deadline)
  self.now=6;self.g.poll();self.assertTrue(self.g.active)
  self.now=100;self.g.poll();self.assertTrue(self.g.active)
  self.g.pulse(1400)
  self.assertEqual(len([e for e in self.g.fake.events if e.get('action')=='BENCH_HOLD']),2)

 def test_mechanical_heartbeat_when_idle(self):
  self.g.begin(assembled=True);self.g.select_mode(True);self.g.pulse(1500)
  self.now=10;self.g.poll()
  self.assertTrue(any(e.get('action')=='HEARTBEAT' for e in self.g.fake.events))

 def test_detached_still_times_out(self):
  self.g.begin();self.g.select_mode(True);self.g.pulse(1500)
  self.now=6;self.g.poll();self.assertFalse(self.g.active)

 def test_real_rejects_pipe_before_open(self):
  r=subprocess.run([sys.executable,'scripts/pwm_console.py','--real','--port','/dev/cu.SIMULATED','--authorize-detached-bench'],input='',text=True,capture_output=True)
  self.assertNotEqual(r.returncode,0);self.assertIn('interactive terminal',r.stderr)

 def test_stop_during_output_does_not_wait(self):
  self.g.begin();self.g.pulse(1500);self.assertIsNotNone(self.g.pending_until)
  self.g.stop();self.assertIsNone(self.g.pending_until);self.assertEqual(self.now,0)
 def test_active_pulse_does_not_queue_next(self):
  self.g.begin();self.g.pulse(1500)
  with self.assertRaises(ValueError):self.g.pulse(1550)
  self.assertEqual(len(self.pulses()),1)
