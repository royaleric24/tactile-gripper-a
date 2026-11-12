"""Run AFTER user unplug confirmation and all earlier serial handles closed.
Checks the absent device open failure; does not claim an in-flight I/O disconnect.
"""
import argparse,json,os
from pathlib import Path
from gripper_a.serial_client import SerialClient,JsonlLog,CommunicationError
p=argparse.ArgumentParser();p.add_argument('--port',required=True);p.add_argument('--log',required=True);a=p.parse_args()
log=JsonlLog(a.log,'REAL_SERIAL');client=SerialClient(json.loads(Path('config/serial_test.json').read_text()),log)
try:
 if os.path.exists(a.port):raise RuntimeError('port still exists; no unplug verified')
 try:client.connect(a.port)
 except CommunicationError as exc:
  log('ABSENT_DEVICE_ERROR_HANDLED',error=str(exc));print('Absent device open error handled')
 else:raise AssertionError('unexpected connection')
finally:client.close();log.close()
