"""One manual pulse per typed integer; never scans or restores motion."""
import argparse,json,time,select,sys
from pathlib import Path
from gripper_a.gripper_controller import LimitedTrialController
p=argparse.ArgumentParser();p.add_argument('--port');p.add_argument('--hardware-permission',action='store_true');p.add_argument('--motion-permission',action='store_true');p.add_argument('--condition',choices=['LINKAGE_DETACHED','LOCAL_RANGE_CONFIRMED'],required=True);p.add_argument('--low',type=int,required=True);p.add_argument('--high',type=int,required=True);p.add_argument('--initial',type=int,required=True);a=p.parse_args()
real=a.hardware_permission and a.motion_permission
if a.hardware_permission!=a.motion_permission:p.error('both explicit permissions required for REAL_SERIAL; omit both for dry-run')
g=LimitedTrialController(dry_run=not real,hardware_permission=real)
try:
 status=g.connect(a.port)
 if real and (not status.get('trial_capable') or status.get('hardware_enabled') is not False):raise RuntimeError('wrong device/profile')
 print('CONFIRM physical setup externally approved; type BEGIN to open one trial window. No pulse yet.',flush=True)
 if input().strip()!='BEGIN':raise RuntimeError('cancelled')
 g.begin_trial(a.low,a.high,a.initial,condition=a.condition,manual_trigger=True)
 deadline=time.monotonic()+g.config['trial_window_ms']/1000;heartbeat=time.monotonic()
 print('Type one pulse in us and Enter per action; STOP or DISARM exits. Firmware ends each pulse after 500ms.',flush=True)
 while time.monotonic()<deadline:
  if select.select([sys.stdin],[],[],0.1)[0]:
   line=sys.stdin.readline()
   if not line or line.strip().upper() in ('STOP','DISARM'):break
   pulse=int(line.strip());g.trial_pulse(pulse,manual_trigger=True)
   print('Command acknowledged, not actual position. Observe before next independent command.',flush=True)
  if time.monotonic()-heartbeat>=1:g.heartbeat();heartbeat=time.monotonic()
finally:g.close()
