"""Real serial-only timeout and recovery checks; no motor commands."""
import argparse,json,time
from pathlib import Path
from gripper_a.serial_client import SerialClient,JsonlLog,CommunicationError
p=argparse.ArgumentParser();p.add_argument('--port',required=True);p.add_argument('--log',required=True);a=p.parse_args()
c=json.loads(Path('config/serial_test.json').read_text());log=JsonlLog(a.log,'REAL_SERIAL');client=SerialClient(c,log)
try:
 client.connect(a.port);time.sleep(c['boot_wait_s'])
 response=client.exchange(b'{"protocol_version":',None)
 assert response['type']=='ERROR' and response['error']=='INCOMPLETE_FRAME_TIMEOUT'
 log('FIRMWARE_PARTIAL_TIMEOUT_PASS')
 assert client.request('PING')['type']=='PONG'
 # Deliberately send nothing: verify the real host read deadline and close.
 start=time.monotonic()
 try:client.exchange(b'', 'deliberately-no-request')
 except CommunicationError as exc:
  assert str(exc)=='response_timeout' and client.port is None
  log('HOST_TIMEOUT_PASS',elapsed_s=time.monotonic()-start)
 else:raise AssertionError('missing timeout')
 client.connect(a.port);time.sleep(c['boot_wait_s'])
 assert client.request('PING')['type']=='PONG'
 log('TIMEOUT_RECOVERY_PASS');print('Firmware timeout, host deadline and recovery passed')
finally:client.close();log.close()
