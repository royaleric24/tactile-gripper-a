"""Stage 0.9B-1 real serial checks, only after separate upload/test authorization.
Never relax calibration. Refuse to send test ARM/SET unless lock is reported.
"""
import argparse,json,time,uuid
from pathlib import Path
from gripper_a.serial_client import SerialClient,JsonlLog,CommunicationError
p=argparse.ArgumentParser();p.add_argument('--port',required=True);p.add_argument('--log',required=True);p.add_argument('--status-out',required=True);p.add_argument('--check-reboot-from');p.add_argument('--authorized-locked-test',action='store_true');a=p.parse_args()
if not a.authorized_locked_test:p.error('separate authorization required')
c=json.loads(Path('config/gripper_control.json').read_text())
if c['hardware_enabled'] is not False or c['calibration_state']!='UNCALIBRATED':p.error('locked config required')
sc=dict(c['serial']);sc['response_types']=['PONG','STATUS','ACK','ERROR']
log=JsonlLog(a.log,'REAL_SERIAL');client=SerialClient(sc,log)
def send(command, rid=None, **fields):
 rid=rid or uuid.uuid4().hex
 raw=(json.dumps(dict(protocol_version=1,request_id=rid,command=command,**fields))+'\n').encode()
 return client.exchange(raw,rid)
def locked(response):
 assert response['state']=='DISARMED',response
 assert response['hardware_enabled'] is False and response['motion_enabled'] is False,response
 assert response['calibration_state']=='UNCALIBRATED',response
 assert response['commanded_pulse_us'] is None,response
 assert response['output_state']=='DISABLED_UNMEASURED',response
 assert response['actual_angle_deg'] is None and response['actual_opening'] is None,response
try:
 client.connect(a.port);time.sleep(2)
 status=send('GET_STATUS');locked(status)
 if a.check_reboot_from:
  old=json.loads(Path(a.check_reboot_from).read_text());assert old['boot_id']!=status['boot_id'],'restart not proven'
  log('REBOOT_DEFAULT_PASS',before=old['boot_id'],after=status['boot_id'])
 else:
  assert send('PING')['type']=='PONG'
  boot=status['boot_id'];seq=status['last_sequence']+1;rid=uuid.uuid4().hex
  for _ in range(2):
   response=send('ARM',rid=rid,boot_id=boot,sequence=seq)
   assert response['type']=='ERROR' and response['error']=='UNCALIBRATED_OR_DISABLED',response
   locked(response)
  for pulse in (0,0xffffffff):
   response=send('SET_PULSE_US',boot_id=boot,sequence=seq+1,pulse_us=pulse)
   assert response['type']=='ERROR',response;locked(response)
  response=send('NOT_A_COMMAND',boot_id=boot,sequence=seq+1);assert response['type']=='ERROR';locked(response)
  for raw,error in [(b'{invalid}\n','INVALID_JSON'),(b'x'*513+b'\n','FRAME_TOO_LONG'),(b'{"protocol_version":1,"command":"PING"}\n','INVALID_ID')]:
   response=client.exchange(raw,None);assert response['error']==error,response;locked(response)
  response=client.exchange(b'{"protocol_version":',None);assert response['error']=='PARTIAL_TIMEOUT',response;locked(response)
  time.sleep(1.2);locked(send('GET_STATUS'))
  for command in ('STOP','DISARM'):
   response=send(command);assert response['type']=='ACK';locked(response)
  try:client.exchange(b'','intentionally-no-response')
  except CommunicationError as exc:assert str(exc)=='response_timeout'
  else:raise AssertionError('missing host timeout')
  client.connect(a.port);time.sleep(2);locked(send('GET_STATUS'))
  log('LOCKED_SUITE_PASS',scope='default locked state only; active watchdog not exercised')
 final=send('GET_STATUS');locked(final)
 Path(a.status_out).write_text(json.dumps(final,indent=2)+'\n')
 print('Locked serial verification passed')
finally:client.close();log.close()
