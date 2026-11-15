"""SIMULATED serial input and errors; no OS serial device opened."""
import json,unittest
from pathlib import Path
from gripper_a.serial_client import SerialClient,CommunicationError
class FakePort:
 def __init__(self,rx=b'',fail=False):self.rx=bytearray(rx);self.fail=fail;self.closed=False
 def write(self,raw):
  if self.fail:raise OSError('disconnected')
  return len(raw)
 def read(self,n):
  if self.fail:raise OSError('disconnected')
  return bytes([self.rx.pop(0)]) if self.rx else b''
 def close(self):self.closed=True
class SerialTests(unittest.TestCase):
 def make(self,rx=b'',fail=False):
  self.events=[];self.now=0
  def clock():self.now+=0.001;return self.now
  c=SerialClient(json.loads(Path('config/serial_test.json').read_text()),lambda e,**v:self.events.append((e,v)),clock);c.port=FakePort(rx,fail);return c
 def wire(self,rid='id',kind='PONG'):
  return json.dumps(dict(protocol_version=1,request_id=rid,type=kind,firmware_version='serial-test-0.8.0')).encode()+b'\n'
 def test_boot_ignored_and_id_matched(self):
  c=self.make(b'ets Jun 8\n'+self.wire('other')+self.wire());self.assertEqual(c.exchange(b'test\n','id')['type'],'PONG')
  self.assertTrue(any(e=='IGNORED' for e,v in self.events))
 def test_timeout_closes(self):
  c=self.make();p=c.port
  with self.assertRaises(CommunicationError):c.exchange(b'test\n','id')
  self.assertTrue(p.closed)
 def test_disconnect_closes(self):
  c=self.make(fail=True);p=c.port
  with self.assertRaises(CommunicationError):c.exchange(b'test\n','id')
  self.assertTrue(p.closed)
 def test_oversize_then_resync(self):
  c=self.make(b'x'*1025+b'\n'+self.wire());self.assertEqual(c.exchange(b'test\n','id')['type'],'PONG')
 def test_invalid_utf8_ignored(self):
  c=self.make(b'\xff\n'+self.wire());self.assertEqual(c.exchange(b'test\n','id')['type'],'PONG')
 def test_corrupt_long_response_is_logged_and_can_resync(self):
  good=dict(protocol_version=1,request_id='id',type='PONG',firmware_version='serial-test-0.8.0',pad='x'*300)
  wire=json.dumps(good).encode()+b'\n'
  corrupt=wire[:30]+b'\x00'*12+wire[42:]
  c=self.make(corrupt+self.wire())
  self.assertEqual(c.exchange(b'test\n','id')['type'],'PONG')
  ignored=[v for e,v in self.events if e=='IGNORED']
  self.assertTrue(any(v.get('reason')=='corrupt_response' and v.get('nul_count')==12 for v in ignored),ignored)
 def test_no_motion(self):
  c=self.make()
  with self.assertRaises(ValueError):c.request('ARM')
 def test_error_null_id(self):
  c=self.make(self.wire(None,'ERROR'));self.assertEqual(c.exchange(b'{invalid}\n',None)['type'],'ERROR')
 def test_optional_diagnostic_fields_tolerated(self):
  # Stage 0.9B-20B adds optional failure fields; old clients must still parse them.
  extra=dict(protocol_version=1,request_id='id',type='ERROR',firmware_version='serial-test-0.8.0',
             error='OUTPUT_API_FAILURE',output_api_stage='WRITE_FAIL',output_first_write=True,
             output_write_ok=False,output_off_ok=False,output_expected_duty=4915,
             output_actual_duty=0,output_expected_freq_hz=50,output_actual_freq_hz=0)
  c=self.make(json.dumps(extra).encode()+b'\n')
  r=c.exchange(b'test\n','id')
  self.assertEqual(r['type'],'ERROR');self.assertEqual(r['output_api_stage'],'WRITE_FAIL')
