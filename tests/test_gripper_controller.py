"""SIMULATED only; synthetic pulse bounds are NOT mechanical calibration."""
import json,unittest,tempfile
from pathlib import Path
from gripper_a.gripper_controller import GripperController
class RetryTransport:
    """Offline fake with the retryable-exchange capability."""
    supports_retryable_exchange = True
    def __init__(self, outcomes):
        self.outcomes=list(outcomes);self.calls=[];self.closed=False
    def exchange(self, raw, request_id, *, close_on_error=True, fail_fast_on_corrupt=False):
        self.calls.append((raw, request_id, close_on_error, fail_fast_on_corrupt))
        outcome=self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    def close(self):self.closed=True


def ack(state='ARMED', output_state='PWM_COMMANDED_UNMEASURED', pulse=None, boot='b1'):
    return {'type':'ACK','state':state,'output_state':output_state,
            'commanded_pulse_us':pulse,'boot_id':boot,'fault_reason':'BENCH_HOLD_SELECTED'}


class RespondingPort:
    """Fake serial port: a corrupt ACK is queued, each write appends a clean ACK."""
    def __init__(self, initial: bytes, firmware='serial-test-0.8.0'):
        self.rx=bytearray(initial);self.firmware=firmware;self.writes=[];self.closed=False
    def write(self, raw):
        self.writes.append(raw)
        request=json.loads(raw.decode())
        response={'protocol_version':1,'request_id':request['request_id'],'type':'ACK',
                  'firmware_version':self.firmware,'boot_id':'b1','state':'ACTIVE',
                  'output_state':'PWM_COMMANDED_UNMEASURED','commanded_pulse_us':1500}
        self.rx.extend(json.dumps(response).encode()+b'\n')
        return len(raw)
    def read(self, n):
        return bytes([self.rx.pop(0)]) if self.rx else b''
    def close(self):self.closed=True


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
 def test_heartbeat_retries_once_and_recovers(self):
  from gripper_a.serial_client import CommunicationError
  from pathlib import Path
  c=dict(self.c);c['serial']={'heartbeat_retry_attempts':2,'heartbeat_retry_delay_ms':0}
  log_path=Path(self.tmp.name)/'heartbeat_retry.jsonl'
  transport=RetryTransport([CommunicationError('response_timeout'),ack()])
  g=GripperController(c,dry_run=False,hardware_permission=True,transport=transport,log_path=log_path)
  self.addCleanup(g.close)
  g.connected=True;g.state='ARMED';g.boot_id='b1'
  response=g.heartbeat()
  self.assertEqual(response['type'],'ACK')
  self.assertEqual(len(transport.calls),2)
  self.assertFalse(transport.calls[0][2])
  self.assertTrue(transport.calls[1][2])
  self.assertTrue(transport.calls[0][3])
  self.assertFalse(transport.closed)
  self.assertEqual(g.state,'ARMED')
  events=[json.loads(line) for line in log_path.read_text().splitlines()]
  self.assertTrue(any(e.get('event')=='COMMAND_RETRY' for e in events))
  self.assertEqual(sum(1 for e in events if e.get('event')=='COMMAND'),2)
  g.connected=False

 def test_heartbeat_retry_is_bounded_and_closes(self):
  from gripper_a.serial_client import CommunicationError
  from pathlib import Path
  c=dict(self.c);c['serial']={'heartbeat_retry_attempts':2,'heartbeat_retry_delay_ms':0}
  transport=RetryTransport([CommunicationError('response_timeout'),CommunicationError('response_timeout')])
  g=GripperController(c,dry_run=False,hardware_permission=True,transport=transport,log_path=Path(self.tmp.name)/'heartbeat_fail.jsonl')
  self.addCleanup(g.close)
  g.connected=True;g.state='ACTIVE';g.output_state='PWM_COMMANDED_UNMEASURED';g.boot_id='b1'
  with self.assertRaises(CommunicationError):g.heartbeat()
  self.assertEqual(len(transport.calls),2)
  self.assertTrue(transport.closed)
  self.assertEqual(g.state,'FAULT');self.assertEqual(g.output_state,'UNKNOWN');self.assertFalse(g.connected)

 def test_pwm_command_is_not_retried(self):
  from gripper_a.serial_client import CommunicationError
  from pathlib import Path
  c=dict(self.c);c['serial']={'heartbeat_retry_attempts':2,'heartbeat_retry_delay_ms':0}
  transport=RetryTransport([CommunicationError('response_timeout')])
  g=GripperController(c,dry_run=False,hardware_permission=True,transport=transport,log_path=Path(self.tmp.name)/'pwm_no_retry.jsonl')
  self.addCleanup(g.close)
  g.connected=True;g.state='ACTIVE';g.boot_id='b1'
  with self.assertRaises(CommunicationError):g._send('BENCH_HOLD',pulse_us=1500)
  self.assertEqual(len(transport.calls),1)
  self.assertTrue(transport.closed)

 def test_mode_selection_retries_before_any_target(self):
  from gripper_a.serial_client import CommunicationError
  from pathlib import Path
  c=dict(self.c);c['serial']={'heartbeat_retry_attempts':2,'heartbeat_retry_delay_ms':0}
  transport=RetryTransport([CommunicationError('corrupt_response'),ack(state='ARMED',output_state='DISABLED_UNMEASURED')])
  g=GripperController(c,dry_run=False,hardware_permission=True,transport=transport,log_path=Path(self.tmp.name)/'mode_retry.jsonl')
  self.addCleanup(g.close)
  g.connected=True;g.state='ARMED';g.boot_id='b1';g.target=None;g.last_pulse=None
  response=g._send('BENCH_HOLD_MODE')
  self.assertEqual(response['type'],'ACK')
  self.assertEqual(len(transport.calls),2)
  g.connected=False

 def test_mode_selection_not_retried_after_pwm(self):
  from gripper_a.serial_client import CommunicationError
  from pathlib import Path
  c=dict(self.c);c['serial']={'heartbeat_retry_attempts':2,'heartbeat_retry_delay_ms':0}
  transport=RetryTransport([CommunicationError('corrupt_response')])
  g=GripperController(c,dry_run=False,hardware_permission=True,transport=transport,log_path=Path(self.tmp.name)/'mode_no_retry.jsonl')
  self.addCleanup(g.close)
  g.connected=True;g.state='ACTIVE';g.boot_id='b1';g.target=None;g.last_pulse=1500
  with self.assertRaises(CommunicationError):g._send('BENCH_HOLD_MODE')
  self.assertEqual(len(transport.calls),1)

 def test_corrupt_ack_pattern_recovers_with_heartbeat_retry(self):
  from pathlib import Path
  from gripper_a.serial_client import SerialClient
  clean={'protocol_version':1,'request_id':'first','type':'ACK','firmware_version':'serial-test-0.8.0','boot_id':'b1','state':'ACTIVE','output_state':'PWM_COMMANDED_UNMEASURED','commanded_pulse_us':1500,'fault_reason':'TARGET_COMMANDED'}
  wire=json.dumps(clean).encode()
  # Replace 4 bytes inside commanded_pulse_us with NULs, same pattern as a804.
  pos=wire.index(b'"commanded_pulse_us"')+16
  corrupt=wire[:pos]+b'\x00'*4+wire[pos+4:]+b'\n'
  cfg=json.loads(Path('config/serial_test.json').read_text())
  cfg['heartbeat_retry_attempts']=2;cfg['heartbeat_retry_delay_ms']=0
  cfg['response_types']=['PONG','STATUS','ACK','ERROR']
  c={'firmware_version':'serial-test-0.8.0','serial':cfg}
  log_path=Path(self.tmp.name)/'corrupt_pattern.jsonl'
  g=GripperController(c,dry_run=False,hardware_permission=True,log_path=log_path)
  self.addCleanup(g.close)
  port=RespondingPort(corrupt)
  g.transport=SerialClient(cfg,g.log);g.transport.port=port
  g.connected=True;g.state='ACTIVE';g.output_state='PWM_COMMANDED_UNMEASURED';g.boot_id='b1'
  response=g.heartbeat()
  self.assertEqual(response['type'],'ACK')
  self.assertEqual(len(port.writes),2)
  self.assertFalse(port.closed)
  events=[json.loads(line) for line in log_path.read_text().splitlines()]
  self.assertTrue(any(e.get('event')=='COMMAND_RETRY' for e in events))
  self.assertTrue(any(e.get('event')=='IGNORED' and e.get('nul_count')==4 for e in events))
  g.connected=False

 def test_changed_boot_session_faults(self):
  from unittest.mock import Mock
  g=self.make(True,dry_run=False,hardware_permission=True);g.connected=True;g.boot_id='old';g.transport=Mock();g.transport.exchange.return_value={'type':'STATUS','boot_id':'new','state':'DISARMED'}
  with self.assertRaises(RuntimeError):g.get_status()
  self.assertFalse(g.connected);self.assertEqual(g.output_state,'UNKNOWN')
