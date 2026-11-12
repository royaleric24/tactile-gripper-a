"""Manual calibration shell. Defaults to SIMULATED; no reference, no movement."""
import argparse,json,select,shlex,sys,time,uuid
from pathlib import Path
from gripper_a.gripper_controller import LimitedTrialController
from gripper_a.calibration import CalibrationSession

def main():
 p=argparse.ArgumentParser();p.add_argument('--real',action='store_true');p.add_argument('--port');p.add_argument('--hardware-permission',action='store_true');p.add_argument('--motion-permission',action='store_true');p.add_argument('--output')
 a=p.parse_args()
 if a.real and (not a.port or not a.hardware_permission):p.error('--real requires explicit --port and --hardware-permission')
 if not a.real and (a.hardware_permission or a.motion_permission):p.error('permission flags require explicit --real')
 folder=Path(a.output) if a.output else Path('logs/real' if a.real else 'logs/simulated')/'calibration'/uuid.uuid4().hex
 folder.parent.mkdir(parents=True,exist_ok=True)
 transport_log=folder.parent/(folder.name+'_transport.jsonl')
 g=LimitedTrialController(dry_run=not a.real,hardware_permission=a.hardware_permission,log_path=transport_log)
 s=CalibrationSession(g,folder,motion_permission=a.motion_permission)
 print('REAL_SERIAL — not motion-authorized' if a.real and not a.motion_permission else 'REAL — reference and per-action confirmation still required' if a.real else 'SIMULATED — no device access')
 print('Commands: status | reference FILE | locate | step SIGNED_US | observe | stop | disarm | export MARGIN_US | quit')
 print('No reference is created automatically. 1500us is NOT a safe default. STOP disables PWM, not motor power.')
 print('Logs:',folder)
 try:
  print(json.dumps(s.connect(a.port),ensure_ascii=False))
  while True:
   s.poll()
   if not select.select([sys.stdin],[],[],0.1)[0]:continue
   line=sys.stdin.readline()
   if not line:break
   try:
    args=shlex.split(line);cmd=args[0].lower() if args else ''
    if cmd in ('quit','exit'):break
    if cmd=='status':print(json.dumps(s.status(),ensure_ascii=False))
    elif cmd=='reference' and len(args)==2:
     ref=json.loads(Path(args[1]).read_text());print('Reference evidence:',json.dumps(ref,ensure_ascii=False))
     if input('Type REVIEWED to confirm this evidence and initial path (not to discover them): ').strip()!='REVIEWED':continue
     s.confirm_reference(ref);print('REFERENCE_CONFIRMED; no pulse sent')
    elif cmd in ('locate','step'):
     if s.reference is None:raise ValueError('initial_reference_not_established')
     target=s.reference['initial_us'] if cmd=='locate' else s.current+int(args[1]) if s.current is not None and len(args)==2 else None
     if target is None:raise ValueError('locate_required_or_invalid_step')
     print('Proposed commanded pulse:',target,'us; may cause a large first positioning move; NOT actual angle')
     if input(f'Type EXECUTE {target} to request ONE action: ').strip()!=f'EXECUTE {target}':continue
     s.poll()
     r=s.locate(confirmed=True) if cmd=='locate' else s.step(int(args[1]),confirmed=True)
     print(json.dumps(r,ensure_ascii=False));print('Wait for pulse end, observe, then enter observe. No further movement until observation.')
    elif cmd=='observe':
     d=input('Direction OPENING/CLOSING/NONE/UNKNOWN: ').strip().upper()
     v=input('Measured opening mm (blank if unmeasured): ').strip();method=input('Measurement method (blank if none): ').strip() if v else None
     abnormal=input('Any interference/stall/unusual behavior? YES/no: ').strip().upper()!='NO'
     safe=input('Observed safe at this position? Type SAFE, otherwise unsafe: ').strip()=='SAFE'
     note=input('Observation note: ')
     s.observe(direction=d,safe=safe,abnormal=abnormal,opening_mm=float(v) if v else None,measurement_method=method,note=note)
     print('Observation recorded. If abnormal: physically cut independent servo power; do not reset to clear fault.')
    elif cmd=='stop':s.stop()
    elif cmd=='disarm':s.stop(disarm=True)
    elif cmd=='export' and len(args)==2:print(json.dumps(s.export_candidate(int(args[1])),ensure_ascii=False))
    elif cmd:raise ValueError('unknown_command_or_arguments')
   except (ValueError,PermissionError) as exc:s.record('LOCAL_REJECTION',reason=str(exc));print('Rejected:',exc)
   except Exception as exc:s.fail(str(exc));print('FAULT:',exc,'Cut independent servo power if necessary; no automatic recovery.');break
 except KeyboardInterrupt:print('\nInterrupted; closing (DISARM only with motion permission or simulation)')
 finally:s.close()
if __name__=='__main__':main()
