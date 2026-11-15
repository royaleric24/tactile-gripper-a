# Stage H4 — Minimal Single-Point Contact Detection V1

## Scope

- Single fixed channel ADC2 AIN1 (ch5), R4C3, diagnostic firmware
  `tactile-sense-diag-ain1-0.1.3`.
- Contact/release candidates only; no pressure, force or friction calibration.
- No S3, no servo/PWM, no real gripper motion. STOP is dry-run only.

## Demo

```bash
.venv/bin/python scripts/contact_demo.py \
  --live --port /dev/cu.usbserial-EXAMPLE_ESP32 --web-port 8765 --label R4C3
```

Open `http://127.0.0.1:8765/`.

## Three-round repeatability

```bash
.venv/bin/python scripts/contact_demo.py \
  --live --port /dev/cu.usbserial-EXAMPLE_ESP32 \
  --rounds 3 --phase-seconds 3 --web-port 8765 --label R4C3
```

Each round: no contact → light pressure → release, 3 s each. Output:

```text
data/real/contact_demo/<trial_id>/
  meta.json
  samples.jsonl
  events.jsonl
  stop_requests.jsonl
  SUMMARY.json
  REPORT.md
  raw.bin / raw_hex.log
```

## Replay real data

```bash
.venv/bin/python scripts/contact_demo.py \
  --replay data/real/diag_fixed_ain1/20261113T205207Z_80fabf/samples.jsonl \
  --web-port 8765
```

Replay is marked `REPLAY_REAL`, never `LIVE_REAL` or `SIMULATED`.

## Detector

- EMA filter, startup baseline (20 frames), adaptive slow baseline only in
  RELEASE, hysteresis, confirmation frames.
- Initial contact drop: 0.08 V relative to baseline; release recovery: 0.03 V.
- These are initial parameters, not a pressure calibration.
- `restored_before_cs=false` / `post_cs_high=false` → **UNVERIFIED**.
- UNVERIFIED contact can be displayed but never sets `control_eligible` and
  never triggers an automatic STOP.
- Malformed JSON, invalid counts, read/ready failure, or timeout → `UNKNOWN`.

## Dry-run STOP

`DryRunStopSink` writes `stop_requests.jsonl` with `executed=false`, `mode=DRY_RUN`.
`S3StopSink` is a reserved interface and raises PermissionError. No real control
until verified signal, S3 calibration/authorization and a real STOP safety test.
