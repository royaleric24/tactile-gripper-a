"""Generate a build-time safety configuration; null bounds NEVER unlock output."""
import json
import argparse
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--config',default='config/gripper_control.json')
parser.add_argument('--output',default='firmware/gripper_control/generated_config.h')
args=parser.parse_args()
c=json.loads(Path(args.config).read_text())
assert type(c['gpio']) is int and 0<=c['gpio']<=48
assert c['frequency_hz']==50
assert type(c['resolution_bits']) is int and 8<=c['resolution_bits']<=20
assert all(type(c[k]) is int and 0<c[k]<60000 for k in ['min_interval_ms','communication_timeout_ms','max_output_ms','max_line_bytes','partial_timeout_ms'])
readback=c.get('readback_settle_ms',25);first_readback=c.get('first_readback_settle_ms',0)
assert type(readback) is int and 0<=readback<=100
assert type(first_readback) is int and 0<=first_readback<=100
cal=c['calibration_state']=='CONFIRMED'
keys=['safe_min_us','safe_max_us','initial_pulse_us','max_step_us','max_total_change_us']
if cal:
 assert all(type(c[k]) is int and c[k]>0 for k in keys)
 assert c['safe_min_us']<=c['initial_pulse_us']<=c['safe_max_us']<1000000//c['frequency_hz']
assert type(c['hardware_enabled']) is bool
h='#pragma once\n'
h+='#define CFG_BOARD_TARGET '+json.dumps(c.get('board_target','esp32'))+'\n'
for key in ['firmware_version','gpio','frequency_hz','resolution_bits','hardware_enabled']+keys+['min_interval_ms','communication_timeout_ms','max_output_ms','max_line_bytes','partial_timeout_ms']:
 v=c[key]
 if v is None:v=0
 h+='#define CFG_'+key.upper()+' '+json.dumps(v)+'\n'
h+='#define CFG_READBACK_SETTLE_MS '+str(readback)+'\n'
h+='#define CFG_FIRST_READBACK_SETTLE_MS '+str(first_readback)+'\n'
trial=c.get('trial_enabled',False)
assert type(trial) is bool
if trial:
 assert c['hardware_enabled'] is False and not cal
 assert 1460<=c['trial_min_us']<=1500<=c['trial_max_us']<=1540
 assert 0<c['trial_step_us']<=20 and 0<c['trial_total_us']<=80
 assert 0<c['trial_pulse_ms']<=500 and 0<c['trial_window_ms']<=30000
 assert 0<c['trial_comm_timeout_ms']<=5000
h+='#define CFG_TRIAL_ENABLED '+str(trial).lower()+'\n'
for k,default in [('trial_min_us',1460),('trial_max_us',1540),('trial_step_us',20),('trial_total_us',80),('trial_window_ms',30000),('trial_pulse_ms',500),('trial_comm_timeout_ms',5000)]:
 h+='#define CFG_'+k.upper()+' '+str(c.get(k,default))+'\n'
bench=c.get('bench_enabled',False)
assert type(bench) is bool
bench_defaults=dict(bench_min_us=500,bench_max_us=2500,bench_initial_us=1500,bench_step_us=2000,bench_window_ms=300000,bench_pulse_ms=500,bench_comm_timeout_ms=5000)
if bench:
 assert not trial and c['hardware_enabled'] is False and not cal
 for k,v in bench_defaults.items():assert type(c[k]) is int and c[k]==v
h+='#define CFG_BENCH_ENABLED '+str(bench).lower()+'\n'
for k,v in bench_defaults.items():h+='#define CFG_'+k.upper()+' '+str(c.get(k,v))+'\n'
hold=c.get('bench_hold_enabled',False)
assert type(hold) is bool
assert not hold or (bench and type(c.get('bench_hold_ms')) is int and c['bench_hold_ms']==5000)
h+='#define CFG_BENCH_HOLD_ENABLED '+str(hold).lower()+'\n'
h+='#define CFG_BENCH_HOLD_MS '+str(c.get('bench_hold_ms',5000))+'\n'
h+='#define CFG_CALIBRATED '+str(cal).lower()+'\n'
out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(h)
