"""Real serial-only tests. Requires explicit port and user authorization flags."""
import argparse,json,time
from pathlib import Path
from gripper_a.serial_client import SerialClient,JsonlLog,CommunicationError
p=argparse.ArgumentParser();p.add_argument('--port',required=True);p.add_argument('--log',required=True);p.add_argument('--authorized-serial-test',action='store_true');p.add_argument('--disconnect-only',action='store_true');a=p.parse_args()
if not a.authorized_serial_test:p.error('explicit serial test authorization required')
c=json.loads(Path('config/serial_test.json').read_text());log=JsonlLog(a.log,'REAL_SERIAL');client=SerialClient(c,log)
try:
 client.connect(a.port);time.sleep(c['boot_wait_s'])
 if a.disconnect_only:
  raise RuntimeError('Use serial_disconnect_check.py after user unplug confirmation; no open handle during manual unplug')
 else:
  assert client.request('PING')['type']=='PONG'
  status=client.request('GET_STATUS');assert status['type']=='STATUS' and status['motion_enabled'] is False
  assert status['state']=='SERIAL_ONLY_NO_MOTION' and type(status['uptime_ms']) is int
  assert client.request('TEST_UNKNOWN')['error']=='UNKNOWN_COMMAND'
  assert client.exchange(b'{invalid}\n',None)['error']=='INVALID_JSON'
  assert client.exchange(b'x'*(c['max_request_bytes']+1)+b'\n',None)['error']=='FRAME_TOO_LONG'
  assert client.request('PING')['type']=='PONG'
  log('SUITE_PASS');print('Serial suite passed')
finally:client.close();log.close()
