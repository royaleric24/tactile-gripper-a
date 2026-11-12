"""Detached PM15S bench session. Commands are targets, never angle feedback."""
import json
import time
from pathlib import Path
from .gripper_controller import GripperController

class BenchController(GripperController):
    def __init__(self, config=None, *, authorized=False, clock=time.monotonic,
                 sleeper=time.sleep, **kwargs):
        super().__init__(config or json.loads(Path('config/gripper_bench.json').read_text()), **kwargs)
        self.last_command_time=None;self.hold_mode=False;self.hold_deadline=None;self.authorized=authorized;self.clock=clock;self.sleep=sleeper
        self._closed=False;self.active=False;self.deadline=0;self.last_heartbeat=0;self.last_pulse=None;self.pending_until=None;self.assembled=False;self.continuous=False

    def begin(self, assembled=False):
        if not self.authorized:raise PermissionError('detached_bench_authorization_required')
        if not self.connected or self.state!='DISARMED':raise ValueError('not_disarmed')
        s=self.get_status()
        if not self.dry_run and (s.get('bench_capable') is not True or s.get('bench_active') is not False or
                                s.get('hardware_enabled') is not False or s.get('calibration_state')!='UNCALIBRATED' or
                                s.get('output_state')!='DISABLED_UNMEASURED'):
            raise RuntimeError('requires_locked_bench_firmware')
        r=self._send('BEGIN_BENCH',physical_condition='GRIPPER_ASSEMBLED' if assembled else 'DETACHED_BENCH')
        self.assembled=assembled
        self.continuous=assembled
        self.active=True;self.deadline=self.clock()+self.config['bench_window_ms']/1000
        self.last_heartbeat=self.clock();self.last_pulse=None;self.pending_until=None
        self.hold_mode=False;self.hold_deadline=None;self.last_command_time=None
        if self.dry_run:self.state='ARMED'
        return r

    def select_mode(self, hold):
        if not self.authorized or not self.active:raise PermissionError('bench_not_active')
        if self.last_pulse is not None:raise ValueError('stop_then_begin_before_changing_mode')
        if hold and not self.config.get('bench_hold_enabled'):raise ValueError('hold_not_enabled')
        r=self._send('BENCH_HOLD_MODE' if hold else 'BENCH_PULSE_MODE')
        self.hold_mode=hold;self.hold_deadline=None
        self.log('BENCH_MODE',mode='HOLD' if hold else 'PULSE')
        return r

    def _send(self, command, **payload):
        try:
            r=super()._send(command, **payload)
            if not self.dry_run and command not in ('STOP','DISARM') and (r.get('state')=='FAULT' or r.get('output_state')=='UNKNOWN'):
                raise RuntimeError('device_fault_or_output_unknown')
            return r
        except Exception:
            self.active=False
            raise

    def poll(self):
        if not self.active:return
        if not self.continuous and self.clock()>=self.deadline:
            self.stop();raise TimeoutError('bench_expired_restart_explicitly_no_auto_renew')
        if self.hold_mode and self.hold_deadline is not None and not self.continuous and self.clock()>=self.hold_deadline:
            ended=self.get_status()
            if self.dry_run or (ended.get('state')=='DISARMED' and ended.get('fault_reason')=='BENCH_HOLD_TIMEOUT' and ended.get('output_state')=='DISABLED_UNMEASURED'):
                self.active=False;self.hold_mode=False;self.hold_deadline=None;self.last_pulse=None
                if self.dry_run:self.state='DISARMED'
                self.log('BENCH_HOLD_ENDED',response=ended)
            elif ended.get('state')!='ACTIVE' or ended.get('hold_mode') is not True:
                raise RuntimeError('unexpected_hold_expiry_state')
            return
        if self.pending_until is not None and self.clock()>=self.pending_until:
            ended=self.get_status()
            if not self.dry_run and (ended.get('state')!='ARMED' or ended.get('bench_active') is not True or
                                    ended.get('fault_reason')!='BENCH_PULSE_ENDED' or ended.get('output_state')!='DISABLED_UNMEASURED'):
                self.active=False;raise RuntimeError('pulse_end_not_confirmed_no_retry')
            self.pending_until=None
            self.log('BENCH_OUTPUT_ENDED',response=ended)
        if self.clock()-self.last_heartbeat>=self.config['host_heartbeat_ms']/1000:
            r=self.heartbeat();self.last_heartbeat=self.clock()
            if not self.dry_run and (r.get('bench_active') is not True or r.get('state')=='FAULT' or r.get('output_state')=='UNKNOWN'):
                self.active=False;raise RuntimeError('bench_fault_or_inactive')

    def pulse(self, value):
        if not self.authorized or not self.active:raise PermissionError('bench_not_authorized_or_active')
        self.poll()
        if not self.active:raise PermissionError('hold_ended_explicit_begin_required')
        if self.state not in ('ARMED','ACTIVE') or self.output_state=='UNKNOWN':
            self.active=False
            raise RuntimeError('bench_fault_or_unknown_no_pulse_sent')
        if self.pending_until is not None:raise ValueError('previous_output_still_active_no_queue')
        c=self.config
        if type(value) is not int or not c['bench_min_us']<=value<=c['bench_max_us']:raise ValueError('range_500_2500')
        if not self.continuous and self.deadline-self.clock()<((c['bench_pulse_ms']+c['host_completion_guard_ms'])/1000):raise ValueError('not_enough_session_time_stop_or_quit')
        if self.last_command_time is not None and (self.clock()-self.last_command_time)*1000<c['min_interval_ms']:raise ValueError('rate_limit_no_queue')
        r=self._send('BENCH_HOLD' if self.hold_mode else 'BENCH_PULSE',pulse_us=value);self.last_pulse=value;self.last_command_time=self.clock()
        # Do not block terminal STOP behind a sleep; poll confirms completion.
        if self.hold_mode:
            if not self.continuous and self.hold_deadline is None:self.hold_deadline=self.clock()+(c['bench_hold_ms']-c['host_completion_guard_ms'])/1000
        else:self.pending_until=self.clock()+(c['bench_pulse_ms']+c['host_completion_margin_ms'])/1000
        self.log('BENCH_ACTION',input_pwm_us=value,ack=r,actual_angle_deg=None)
        return r

    def stop(self):
        self.active=False;self.hold_mode=False;self.hold_deadline=None;self.last_pulse=None;self.pending_until=None;self.continuous=False
        return super().stop()

    def disarm(self):
        self.active=False;self.hold_mode=False;self.hold_deadline=None;self.last_pulse=None;self.pending_until=None;self.continuous=False
        return super().disarm()

    def close(self, **kwargs):
        if self._closed:return
        self.active=False
        try:return super().close(**kwargs)
        finally:self._closed=True
