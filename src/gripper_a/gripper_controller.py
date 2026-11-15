"""Offline hardware abstraction. No real transport is implemented."""
from typing import Protocol

from .serial_client import CommunicationError


RETRYABLE_COMMUNICATION_ERRORS = frozenset(("corrupt_response", "response_timeout"))

class Gripper(Protocol):
    def set_target(self, target): ...
    def inhibit_closing(self, reason): ...
    def hold(self): ...
    def release(self): ...
    def disable_pwm(self): ...

class FakeGripper:
    source = "SIMULATED"
    def __init__(self):
        self.events = []
        self.actual_angle = None
    def record(self, action, **values):
        self.events.append(dict(run_kind=self.source, action=action, executed=False,
                                simulated=True, **values))
    def set_target(self, target): self.record("SET_TARGET", target=target)
    def inhibit_closing(self, reason): self.record("INHIBIT_CLOSING", reason=reason)
    def hold(self): self.record("REQUEST_HOLD")
    def release(self): self.record("REQUEST_RELEASE")
    def disable_pwm(self): self.record("DISABLE_PWM")

class SerialGripper:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("Real serial transport disabled in Stage 0.7")

class GripperController:
    """Explicit pulse interface. Defaults to dry-run; no angle/opening conversion."""
    def __init__(self, config=None, *, dry_run=True, hardware_permission=False, log_path=None, transport=None):
        import json, uuid
        from pathlib import Path
        from .serial_client import JsonlLog
        self.config=config or json.loads(Path('config/gripper_control.json').read_text())
        self.dry_run=dry_run;self.permission=hardware_permission
        # A pre-built transport is only used by offline tests (fake serial) and
        # by an explicit caller that already owns a serial session.  It never
        # bypasses the dry_run/hardware_permission checks below.
        self.transport=transport;self.fake=FakeGripper();self.connected=False
        self.total_change=0;self.last_set_time=None
        self.state='DISARMED';self.output_state='UNKNOWN';self.boot_id=None;self.sequence=0;self.target=None
        kind='SIMULATED' if dry_run else 'REAL_SERIAL'
        path=Path(log_path) if log_path else Path('logs/simulated' if dry_run else 'logs/real')/'stage09a'/f'{uuid.uuid4().hex}.jsonl'
        path.parent.mkdir(parents=True,exist_ok=True)
        self.log=JsonlLog(path,kind);self.log('CONTROLLER_CREATED',dry_run=dry_run)
    def calibrated(self):
        c=self.config
        keys=('safe_min_us','safe_max_us','initial_pulse_us','max_step_us','max_total_change_us')
        return c.get('hardware_enabled') is True and c.get('calibration_state')=='CONFIRMED' and all(type(c.get(k)) is int and c[k]>0 for k in keys) and c['safe_min_us']<=c['initial_pulse_us']<=c['safe_max_us']<20000
    def connect(self, port=None):
        if self.connected:raise RuntimeError('already_connected')
        if not self.dry_run:
            if not self.permission:raise PermissionError('explicit hardware permission required')
            if self.transport is None:
                from .serial_client import SerialClient
                c=dict(self.config['serial']);c['response_types']=['PONG','STATUS','ACK','ERROR']
                self.transport=SerialClient(c,self.log)
            connect=getattr(self.transport,'connect',None)
            if connect is not None:connect(port)
        self.connected=True;self.state='DISARMED';self.target=None;self.boot_id=None
        status=self.get_status()
        if self.state!='DISARMED':
            # Connection is a status query, never an implicit recovery command.
            if self.transport:self.transport.close()
            self.connected=False;self.output_state='UNKNOWN'
            raise RuntimeError('device_not_disarmed')
        return status
    def _send(self, command, **payload):
        import json,time,uuid
        if not self.connected:raise RuntimeError('not_connected')
        serial_cfg=self.config.get('serial') or {}
        # Only non-motion, idempotent commands may be retried.  PWM/STOP/DISARM
        # and BEGIN_BENCH are never resent automatically.
        mode_retry = (
            command in ('BENCH_HOLD_MODE','BENCH_PULSE_MODE')
            and getattr(self,'target',None) is None
            and getattr(self,'last_pulse',None) is None
        )
        retryable = command=='HEARTBEAT' or mode_retry
        attempts=1
        if retryable:
            raw=serial_cfg.get('heartbeat_retry_attempts',2)
            attempts=raw if type(raw) is int else 2
            attempts=max(1,min(3,attempts))
        raw_delay=serial_cfg.get('heartbeat_retry_delay_ms',200)
        delay_ms=float(raw_delay) if type(raw_delay) in (int,float) else 200.0
        delay_ms=max(0.0,min(1000.0,delay_ms))
        response=None
        for attempt in range(attempts):
            self.sequence+=1;rid=uuid.uuid4().hex
            request=dict(protocol_version=1,request_id=rid,command=command,sequence=self.sequence,boot_id=self.boot_id,**payload)
            self.log('COMMAND',request=request)
            if self.dry_run:
                self.fake.record(command,**payload)
                next_state={'ARM':'ARMED','SET_PULSE_US':'ACTIVE','STOP':'DISARMED','DISARM':'DISARMED'}.get(command,self.state)
                response=dict(protocol_version=1,request_id=rid,type='STATUS' if command=='GET_STATUS' else 'PONG' if command=='PING' else 'ACK',firmware_version=self.config['firmware_version'],boot_id='SIMULATED_BOOT',state=next_state,output_state='SIMULATED_UNMEASURED',actual_angle_deg=None,actual_opening=None)
                break
            try:
                raw=(json.dumps(request)+'\n').encode()
                if getattr(self.transport,'supports_retryable_exchange',False):
                    response=self.transport.exchange(
                        raw,rid,
                        close_on_error=(attempt==attempts-1),
                        fail_fast_on_corrupt=retryable,
                    )
                else:
                    response=self.transport.exchange(raw,rid)
                if response['type']=='ERROR':raise RuntimeError(response.get('error','device_error'))
                expected='STATUS' if command=='GET_STATUS' else 'PONG' if command=='PING' else 'ACK'
                if response['type']!=expected:raise RuntimeError('unexpected_response_type')
                if self.boot_id is not None and response.get('boot_id')!=self.boot_id:raise RuntimeError('device_restarted')
                break
            except Exception as exc:
                recoverable = (
                    isinstance(exc, CommunicationError)
                    and str(exc) in RETRYABLE_COMMUNICATION_ERRORS
                )
                if attempt<attempts-1 and recoverable:
                    self.log('COMMAND_RETRY',command=command,attempt=attempt+1,request_id=rid,reason=str(exc),delay_ms=delay_ms)
                    time.sleep(delay_ms/1000.0)
                    continue
                self.state='FAULT';self.output_state='UNKNOWN';self.connected=False
                self.transport.close();self.log('FAULT',reason=str(exc),output_state='UNKNOWN');raise
        if response is None:raise RuntimeError('no_response')
        if response.get('boot_id'):self.boot_id=response['boot_id']
        if type(response.get('last_sequence')) is int:self.sequence=max(self.sequence,response['last_sequence'])
        self.state=response.get('state','FAULT');self.output_state=response.get('output_state','UNKNOWN')
        self.log('RESPONSE',response=response);return response
    def get_status(self):return self._send('GET_STATUS')
    def reject(self, reason):
        self.log('LOCAL_REJECTION',reason=reason)
        if self.connected and self.state in ('ARMED','ACTIVE'):
            try:self.stop()
            except Exception:self.output_state='UNKNOWN'
        raise ValueError(reason)
    def arm(self):
        if not self.calibrated():self.reject('UNCALIBRATED_OR_DISABLED')
        if self.state!='DISARMED':self.reject('not_disarmed')
        r=self._send('ARM');self.total_change=0;self.last_set_time=None
        if self.dry_run:self.state='ARMED'
        return r
    def set_pulse_us(self, pulse_us):
        c=self.config
        if not self.calibrated() or self.state not in ('ARMED','ACTIVE'):self.reject('not_armed_or_calibrated')
        if type(pulse_us) is not int or not c['safe_min_us']<=pulse_us<=c['safe_max_us']:self.reject('pulse_limit')
        anchor=c['initial_pulse_us'] if self.target is None else self.target
        if self.target is None and pulse_us!=anchor:self.reject('initial_pulse_required')
        if abs(pulse_us-anchor)>c['max_step_us']:self.reject('step_limit')
        import time
        now=time.monotonic()
        if self.last_set_time is not None and (now-self.last_set_time)*1000<c['min_interval_ms']:self.reject('rate_limit')
        delta=abs(pulse_us-anchor)
        if self.total_change+delta>c['max_total_change_us']:self.reject('total_change_limit')
        r=self._send('SET_PULSE_US',pulse_us=pulse_us);self.target=pulse_us
        self.total_change+=delta;self.last_set_time=now
        if self.dry_run:self.state='ACTIVE';self.output_state='SIMULATED_PWM_UNMEASURED'
        return r
    def heartbeat(self):return self._send('HEARTBEAT')
    def stop(self):
        r=self._send('STOP');self.target=None
        if self.dry_run:self.state='DISARMED';self.output_state='SIMULATED_DISABLED'
        return r
    def disarm(self):
        r=self._send('DISARM');self.target=None
        if self.dry_run:self.state='DISARMED';self.output_state='SIMULATED_DISABLED'
        return r
    def close(self, *, disarm=True):
        try:
            if self.connected and disarm:self.disarm()
        finally:
            if self.transport:self.transport.close()
            self.connected=False;self.boot_id=None;self.target=None;self.log('CONTROLLER_CLOSED',output_state=self.output_state);self.log.close()

class LimitedTrialController(GripperController):
    """Manual limited-trial extension; does not mark the servo calibrated."""
    def __init__(self, config=None, **kwargs):
        import json
        from pathlib import Path
        config=config or json.loads(Path('config/gripper_trial.json').read_text())
        super().__init__(config,**kwargs)
        self.trial=False
    def begin_trial(self, low_us, high_us, initial_us, *, condition, manual_trigger=False):
        if not manual_trigger:self.reject('manual_trigger_required')
        if self.state!='DISARMED' or not self.config.get('trial_enabled'):self.reject('trial_not_available')
        if condition not in ('LINKAGE_DETACHED','LOCAL_RANGE_CONFIRMED'):self.reject('physical_confirmation_required')
        c=self.config
        if any(type(v) is not int for v in (low_us,high_us,initial_us)):self.reject('invalid_trial_range')
        if not c['trial_min_us']<=low_us<=initial_us<=high_us<=c['trial_max_us']:self.reject('trial_range')
        if condition=='LINKAGE_DETACHED' and initial_us!=1500:self.reject('isolated_reference')
        self.trial_range=(low_us,high_us);self.trial_initial=initial_us;self.trial_target=None;self.trial_total=0
        r=self._send('BEGIN_TRIAL',low_us=low_us,high_us=high_us,initial_us=initial_us,physical_condition=condition)
        self.trial=True
        if self.dry_run:self.state='ARMED'
        return r
    def trial_pulse(self, pulse_us, *, manual_trigger=False):
        if not manual_trigger:self.reject('manual_trigger_required')
        if not self.trial or not self.connected or self.state not in ('ARMED','ACTIVE'):self.reject('no_trial')
        lo,hi=self.trial_range
        if type(pulse_us) is not int or not lo<=pulse_us<=hi:self.reject('trial_range')
        anchor=self.trial_initial if self.trial_target is None else self.trial_target
        if self.trial_target is None and pulse_us!=anchor:self.reject('initial_pulse_required')
        delta=abs(pulse_us-anchor)
        if delta>self.config['trial_step_us'] or self.trial_total+delta>self.config['trial_total_us']:self.reject('trial_step_or_total')
        r=self._send('TRIAL_PULSE',pulse_us=pulse_us)
        self.trial_target=pulse_us;self.trial_total+=delta
        if self.dry_run:self.state='ACTIVE'
        return r
    def stop(self):
        self.trial=False
        return super().stop()
    def disarm(self):
        self.trial=False
        return super().disarm()
