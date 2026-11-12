"""Operator-led local calibration. No default pulse and no automatic motion."""
import json
import math
import time
from pathlib import Path
from datetime import datetime, timezone

class CalibrationSession:
    def __init__(self, controller, folder, *, motion_permission=False, clock=time.monotonic):
        self.g=controller;self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=False)
        self.clock=clock;self.permission=motion_permission;self.kind='SIMULATED' if controller.dry_run else 'REAL_CALIBRATION'
        self.file=(self.folder/'calibration.jsonl').open('x',encoding='utf-8')
        self.state='UNREFERENCED';self.reference=None;self.current=None;self.pending=None;self.points=[]
        self.installation_id=None;self.connected=False;self.active=False;self.deadline=0;self.last_poll=0;self.closed=False
        self.record('CREATED')
    def record(self, command, **fields):
        row=dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),monotonic_s=self.clock(),run_kind=self.kind,
                 firmware_version=self.g.config['firmware_version'],operation=command,calibration_state=self.state,
                 target_pwm_us=self.current,device_response=None,observed_direction=None,opening_mm=None,
                 abnormal=None,user_safe_range=None,**{})
        row.update(fields);self.file.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');self.file.flush()
    def connect(self, port=None):
        try:
            status=self.g.connect(port);self.connected=True
            if not self.g.dry_run:
                if status.get('state')!='DISARMED' or status.get('trial_active') is not False or status.get('trial_capable') is not True or status.get('hardware_enabled') is not False or status.get('motion_enabled') is not False or status.get('calibration_state')!='UNCALIBRATED':
                    raise RuntimeError('device_not_locked_trial_firmware')
            self.record('CONNECT',device_response=status);return status
        except Exception as exc:self.fail(str(exc));raise
    def confirm_reference(self, reference):
        if self.state=='FAULT':raise ValueError('fault_latched_restart_tool_after_investigation')
        if self.active or self.pending:raise ValueError('stop_before_reference_review')
        required=('installation_id','evidence_source','safe_initial_reason','reviewer','approval')
        if any(not isinstance(reference.get(k),str) or not reference[k].strip() for k in required):raise ValueError('reference_evidence_required')
        if reference['approval']!='INITIAL_TARGET_AND_PATH_REVIEWED' or reference.get('safe_path_confirmed') is not True:raise ValueError('initial_path_not_reviewed')
        if not self.g.dry_run and reference.get('source_kind')!='HUMAN_REVIEWED_REAL_EVIDENCE':raise ValueError('real_reference_evidence_required')
        lo,hi,initial=[reference.get(k) for k in ('low_us','high_us','initial_us')]
        if any(type(v) is not int for v in (lo,hi,initial)) or not self.g.config['trial_min_us']<=lo<=initial<=hi<=self.g.config['trial_max_us']:raise ValueError('reference_range')
        if self.installation_id is not None and self.installation_id!=reference['installation_id']:raise ValueError('new_installation_requires_new_session')
        self.installation_id=reference['installation_id']
        self.reference=dict(reference);self.state='REFERENCE_CONFIRMED';self.current=None
        (self.folder/'reference.json').write_text(json.dumps(reference,ensure_ascii=False,indent=2)+'\n')
        self.record('REFERENCE_CONFIRMED',reference=reference)
    def guard(self, confirmed):
        if not self.connected:raise ValueError('not_connected')
        if not confirmed:raise ValueError('explicit_per_action_confirmation_required')
        if not self.g.dry_run and not self.permission:raise PermissionError('motion_permission_required')
        if self.reference is None:raise ValueError('initial_reference_not_established')
        if self.state=='FAULT':raise ValueError('fault_latched')
        if self.pending:raise ValueError('observe_previous_action_first')
    def locate(self, *, confirmed=False):
        self.guard(confirmed)
        if self.active:raise ValueError('already_in_trial')
        ref=self.reference
        try:
            self.g.begin_trial(ref['low_us'],ref['high_us'],ref['initial_us'],condition='LOCAL_RANGE_CONFIRMED',manual_trigger=True)
            self.active=True;self.deadline=self.clock()+self.g.config['trial_window_ms']/1000
            return self._pulse(ref['initial_us'])
        except Exception as exc:self.fail(str(exc));raise
    def invalidate_candidate(self, reason):
        p=self.folder/'candidate_range.json'
        if p.exists():
            d=json.loads(p.read_text());d['review_status']='STALE_REVIEW_REQUIRED';d['invalidation_reason']=reason
            p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
    def _pulse(self, pulse):
        self.invalidate_candidate('new_action_after_export')
        previous=self.current
        response=self.g.trial_pulse(pulse,manual_trigger=True)
        self.current=pulse;self.pending=dict(pulse_us=pulse,previous_pulse_us=previous,sent_s=self.clock(),response=response)
        self.state='LOCAL_CALIBRATING';self.record('PULSE',target_pwm_us=pulse,device_response=response)
        return response
    def step(self, delta, *, confirmed=False):
        self.guard(confirmed)
        if not self.active or self.current is None:raise ValueError('locate_required')
        if type(delta) is not int or delta==0 or abs(delta)>self.g.config['trial_step_us']:raise ValueError('step_limit')
        target=self.current+delta
        if not self.reference['low_us']<=target<=self.reference['high_us']:raise ValueError('reference_range')
        if self.clock()>=self.deadline:self.stop('TRIAL_EXPIRED');raise ValueError('trial_expired')
        try:return self._pulse(target)
        except Exception as exc:self.fail(str(exc));raise
    def observe(self, *, direction, safe, abnormal=False, opening_mm=None, measurement_method=None, note=''):
        if self.pending is None:raise ValueError('no_pending_action')
        if direction not in ('OPENING','CLOSING','NONE','UNKNOWN'):raise ValueError('direction')
        if type(safe) is not bool or type(abnormal) is not bool:raise ValueError('boolean_confirmation')
        if opening_mm is not None:
            if type(opening_mm) not in (int,float) or not math.isfinite(opening_mm) or opening_mm<0 or not measurement_method:raise ValueError('measured_opening_requires_method')
        if self.clock()-self.pending['sent_s']<self.g.config['trial_pulse_ms']/1000:raise ValueError('wait_until_pulse_ended')
        point=dict(self.pending,run_kind=self.kind,installation_id=self.installation_id,observed_direction=direction,opening_mm=opening_mm,measurement_method=measurement_method,
                   abnormal=abnormal,safe_confirmed=safe,operator_note=note,actual_angle_deg=None,confirmation='OPERATOR_OBSERVED_NOT_POSITION_FEEDBACK')
        self.points.append(point);self.pending=None
        self.record('OBSERVATION',observed_direction=direction,opening_mm=opening_mm,abnormal=abnormal,point=point)
        self.save_points()
        if abnormal or not safe:self.fail('operator_reported_unsafe')
    def save_points(self):
        (self.folder/'observed_positions.json').write_text(json.dumps(dict(run_kind=self.kind,points=self.points),ensure_ascii=False,indent=2)+'\n')
    def poll(self):
        if not self.active:return
        now=self.clock()
        if now>=self.deadline:self.stop('TRIAL_EXPIRED');return
        if now-self.last_poll<1:return
        self.last_poll=now
        try:
            r=self.g.heartbeat()
            if not self.g.dry_run and (r.get('state') not in ('ARMED','ACTIVE') or r.get('trial_active') is not True):raise RuntimeError('trial_no_longer_active')
            self.record('HEARTBEAT',device_response=r)
        except Exception as exc:self.fail(str(exc))
    def status(self):
        try:
            r=self.g.get_status()
            if r.get('state')=='FAULT' or r.get('output_state')=='UNKNOWN':self.fail('device_fault_or_unknown')
            self.record('STATUS',device_response=r);return dict(calibration_state=self.state,last_commanded_pulse_us=self.current,last_operator_safe_pulse_us=next((p['pulse_us'] for p in reversed(self.points) if p['safe_confirmed'] and not p['abnormal']),None),pending_observation=self.pending is not None,device=r)
        except Exception as exc:self.fail(str(exc));raise
    def stop(self, reason='OPERATOR_STOP', disarm=False):
        try:
            allowed=self.g.dry_run or self.permission
            r=(self.g.disarm() if disarm else self.g.stop()) if allowed and self.connected and self.g.connected else None
            if not allowed:self.record('READ_ONLY_NO_CONTROL_SENT',reason=reason)
            self.record('DISARM' if disarm else 'STOP',reason=reason,device_response=r)
        except Exception as exc:
            self.state='FAULT';self.record('STOP_FAILED',error=str(exc),output_state='UNKNOWN')
        finally:
            self.active=False;self.reference=None;self.current=None
            if self.state!='FAULT':self.state='UNREFERENCED'
    def fail(self, reason):
        self.invalidate_candidate(reason)
        self.state='FAULT';self.record('FAULT',reason=reason,output_state='UNKNOWN')
        self.stop(reason)
    def export_candidate(self, margin_us):
        if self.state=='FAULT':raise ValueError('fault_latched')
        if self.pending:raise ValueError('pending_observation')
        if type(margin_us) is not int or margin_us<=0:raise ValueError('positive_conservative_margin_required')
        if any(p['abnormal'] or not p['safe_confirmed'] for p in self.points):raise ValueError('unsafe_observation_in_dataset')
        pulses=sorted(set(p['pulse_us'] for p in self.points if p['safe_confirmed']))
        if len(pulses)<4:raise ValueError('need_four_distinct_observed_positions_for_interior_bounds')
        inside=[x for x in pulses if pulses[0]+margin_us<=x<=pulses[-1]-margin_us]
        if len(inside)<2:raise ValueError('insufficient_interior_observed_positions')
        relations=set()
        for p in self.points:
            prev=p['previous_pulse_us'];d=p['observed_direction']
            if prev is not None and prev!=p['pulse_us'] and d in ('OPENING','CLOSING'):
                relations.add(d if p['pulse_us']>prev else ('CLOSING' if d=='OPENING' else 'OPENING'))
        relation=next(iter(relations)) if len(relations)==1 else 'UNKNOWN' if not relations else 'INCONSISTENT'
        if relation=='INCONSISTENT':raise ValueError('inconsistent_direction_records')
        result=dict(run_kind=self.kind,calibration_state='LOCAL_RANGE_COMPLETE',status='CANDIDATE_ONLY_NOT_DEVICE_CALIBRATION',review_status='OPERATOR_REVIEW_REQUIRED',
                    low_us=inside[0],high_us=inside[-1],margin_us=margin_us,observed_envelope=[pulses[0],pulses[-1]],
                    observed_points=pulses,pulse_increase_direction=relation,actual_angle_mapping=None,
                    continuous_interval_verified=False,automatic_hardware_enable=False)
        (self.folder/'candidate_range.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        self.state='LOCAL_RANGE_COMPLETE';self.record('EXPORT_CANDIDATE',user_safe_range=result);return result
    def close(self):
        if self.closed:return
        try:
            if self.connected:self.stop('EXIT',disarm=True)
            self.g.close(disarm=self.g.dry_run or self.permission)
        finally:
            self.active=False;self.connected=False;self.save_points();self.record('CLOSED');self.file.close();self.closed=True
