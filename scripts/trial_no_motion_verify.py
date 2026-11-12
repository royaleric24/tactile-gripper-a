"""Stage 0.9B-3 ONLY. Never sends a valid BEGIN_TRIAL or usable pulse.
Run only after user isolation confirmation and upload/no-motion authorization.
"""
import argparse,json,time,uuid
from pathlib import Path
from gripper_a.serial_client import SerialClient,JsonlLog
p=argparse.ArgumentParser();p.add_argument('--port',required=True);p.add_argument('--log',required=True);p.add_argument('--status-out',required=True);p.add_argument('--before-restart');p.add_argument('--authorized-no-motion',action='store_true');a=p.parse_args()
if not a.authorized_no_motion:p.error('authorization required')
c=json.loads(Path('config/gripper_trial.json').read_text())['serial'];c['response_types']=['PONG','STATUS','ACK','ERROR']
log=JsonlLog(a.log,'REAL_SERIAL');client=SerialClient(c,log)
def locked(r):
 assert r['state']=='DISARMED' and r['hardware_enabled'] is False and r['calibration_state']=='UNCALIBRATED',r
 assert r['motion_enabled'] is False and r['calibrated_motion_enabled'] is False and r['trial_active'] is False and r['trial_capable'] is True,r
 assert r['commanded_pulse_us'] is None and r['output_state']=='DISABLED_UNMEASURED',r
 assert r['trial_window_remaining_ms']==0,r
 return r
def exchange(command,**extra):
 rid=uuid.uuid4().hex
 req=dict(protocol_version=1,request_id=rid,command=command,**extra)
 r=client.exchange((json.dumps(req)+'\n').encode(),rid);locked(r);return r
try:
 client.connect(a.port);time.sleep(2)
 initial=exchange('GET_STATUS');assert exchange('PING')['type']=='PONG'
 if a.before_restart:
  old=json.loads(Path(a.before_restart).read_text());assert old['boot_id']!=initial['boot_id']
  log('RESTART_LOCKED_PASS',old_boot=old['boot_id'],new_boot=initial['boot_id'])
 else:
  # Regular ARM is permanently denied by the reviewed disabled calibration config.
  r=exchange('ARM',boot_id=initial['boot_id'],sequence=initial['last_sequence']+1)
  assert r['error']=='UNCALIBRATED_OR_DISABLED'
  # Rejected in DISARMED before output.set; pulse=0 is not a usable trial target.
  r=exchange('TRIAL_PULSE',boot_id=initial['boot_id'],sequence=initial['last_sequence']+1,pulse_us=0)
  assert r['error']=='NOT_ARMED'
  r=exchange('SET_PULSE_US',boot_id=initial['boot_id'],sequence=initial['last_sequence']+1,pulse_us=0)
  assert r['error']=='NOT_ARMED'
  wrong='INVALID_SESSION_NEVER_AUTHORIZE';assert wrong!=initial['boot_id']
  # Two independent failures before trialPermit: incorrect session AND no physical confirmation.
  r=exchange('BEGIN_TRIAL',boot_id=wrong,sequence=initial['last_sequence']+1,low_us=1460,high_us=1540,initial_us=1500,physical_condition='NOT_CONFIRMED')
  assert r['error']=='SESSION_OR_REPLAY'
  log('NO_MOTION_REJECTION_SUITE_PASS')
 final=exchange('GET_STATUS');Path(a.status_out).write_text(json.dumps(final,indent=2)+'\n');print('No-motion trial-capable firmware verification passed')
finally:client.close();log.close()
