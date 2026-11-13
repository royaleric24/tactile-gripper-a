# Cup-Grasp Trial Runbook

## Current readiness

| Item | State |
|---|---|
| Single-point wiring plan | READY (user must wire/trace) |
| Single-point 5-cycle validator | READY (`scripts/tactile_single_point_validate.py`), real run NOT_TESTED |
| Cup trial recorder | READY (real tactile-only + simulated fixed/feedback) |
| Fixed clamp controller | Implemented in core; simulated tested; real motion BLOCKED |
| Tactile feedback FSM | Implemented in core; simulated tested; real motion BLOCKED |
| S3 real motion | **BLOCKED** (`hardware_enabled=false`, `UNCALIBRATED`, safe range null) |
| Real tactile signal | **INVALID_OR_FLOATING** until single-point wiring/test passes |
| Current flashed firmware | `tactile-sense-0.1.0`; **must reflash 0.1.3** for correct AVDD reference |
| Real cup trials | **NOT_TESTED** |

## 1. Single-point wiring (user action)

Follow `docs/hardware/STAGE_H2_CUP_GRASP_WIRING.md`:

- R1 -> 3.3 V through 1 kΩ
- C1 -> ADC1 AIN0
- **10 kΩ 1%** from C1 to GND/AVSS (measured 2–36 kΩ)
- other electrodes disconnected/high-Z
- common ground; use `tactile-sense-0.1.3` (0.1.0/0.1.1 select the wrong VREF)
- set reference to AVDD_AVSS and verify Reg2=`0xC0` (validator sends `SET_REF` + `VERIFY_CONFIG`; requires 0.1.3)

Do not connect the S3/gripper for this step.

## 2. Single-point validation

After wiring and visual/electrical checks:

```bash
.venv/bin/python scripts/tactile_single_point_validate.py \
  --port /dev/cu.usbserial-EXAMPLE_ESP32 --channel 0 --cycles 5
```

The script first reports `SCAN_MODE_PASS` only with real HELLO channel-map + ch0-frame evidence, then prompts 5 contact/release cycles, records `samples.jsonl`, and writes
`metrics.json`/`REPORT.md` under `data/real/single_point/<trial_id>/`.
It reports per-cycle baseline, delta, SNR, saturation, latency and recovery.
ADC counts are not pressure/force. If it does not pass, do not proceed to cup
feedback trials.

## 3. Cup trial software

Simulated-only workflow (safe, no hardware; marked SIMULATED):

```bash
.venv/bin/python scripts/cup_grasp_trial.py --simulate --mode fixed --duration 6
.venv/bin/python scripts/cup_grasp_trial.py --simulate --mode feedback --duration 6
```

Real tactile-only recording (no gripper command/motion):

```bash
.venv/bin/python scripts/cup_grasp_trial.py --record-only \
  --tactile-port /dev/cu.usbserial-EXAMPLE_ESP32 --duration 30 \
  --config config/cup_grasp.template.json
```

The run is marked `NO_VALID_TACTILE` unless at least 80% of frames are usable.

Real fixed/feedback motion is intentionally gated:

```bash
.venv/bin/python scripts/cup_grasp_trial.py --real
# BLOCKED_GRIPPER_UNCALIBRATED
```

A real run requires a user-verified S3 open/close range, a calibrated config,
explicit motion authorization, and a valid single-point tactile signal. Do not
invent pulses or bypass the gate.

## 4. Trial output

`data/real/cup_grasp/<trial_id>/` (or `data/simulated/cup_grasp/...`):

- `meta.json`
- `tactile.jsonl`
- `gripper_commands.jsonl`
- `load_events.jsonl`
- `trial_events.jsonl`
- `tactile_curve.svg`
- `metrics.json`
- `REPORT.md`
- optional `video_path` in meta (no automatic video capture/sync in this version)

Aggregate:

```bash
.venv/bin/python scripts/analyze_cup_trials.py data/real/cup_grasp
```

This separates real and simulated trials and reports success/slip/deform/NO_VALID_TACTILE.

## 5. Planned real experiment (after all gates)

A. Single-point 5-cycle validation passes.
B. Fixed clamp: at least 5 trials with a user-verified pulse; gradually add water,
   annotate water/slip/deform; record video.
C. Feedback: same water schedule with the FSM; require valid tactile; FAULT on
   invalid/timeout/saturation; compare fixed vs feedback.
D. At least 5 real closed-loop trials; mark any sensor-invalid run
   `NO_VALID_TACTILE`, never as closed-loop success.

PWM is a command, not force/position. ADC counts are proxies, not Newtons.
Slip/deformation are qualitative unless independently measured.

## 6. Not done

- No actual wiring change or single-point test.
- No real fixed/feedback motion; S3 uncalibrated.
- No real cup trial/video/load data.
- No claim of force, friction or 36-point pressure.
