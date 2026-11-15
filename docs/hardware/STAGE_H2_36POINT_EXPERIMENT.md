# 36-Point Press Experiment (existing 12-channel hardware)

## Status

- Software: implemented and offline-tested; a short **software dry run** completed
  36/36 points with no press, only to verify the runner.
- Real experiment: **NOT STARTED**; requires the user to press and confirm.
- Hardware/firmware: unchanged; existing `tactile-sense-0.1.0`; no IDAC/PSW, no
  new excitation, no rewiring, no S3 access.

## Run command

```bash
cd /home/example/Developer/research/tactile-gripper-a-hw
.venv/bin/python scripts/tactile_36point_experiment.py --port /dev/cu.usbserial-EXAMPLE_ESP32
```

Before the script starts: confirm Mac USB only, no external supply on the cloth,
no short/loose electrode, and the ESP32-S3/gripper untouched. The script asks
for `START`, then:

1. 10 s no-contact baseline.
2. For point 1..36, in R1C1..R6C6 order:
   - position the tool at the printed point;
   - press Enter;
   - press and hold 3 s at the prompt;
   - release and wait 3 s at the prompt.
3. 10 s no-contact post baseline.
4. Automatic analysis and report.

Use one non-conductive tool with the same contact area/force; do not touch bare
electrodes. If serial/acquisition fails, Ctrl+C stops and keeps partial data.

## Recorded files

- `raw_frames.jsonl`: every raw JSON line
- `samples.csv`: frame seq, device/host timestamps, 12 channels, valid/flags
- `events.jsonl`: `POINT_READY`, `USER_READY`, `PRESS_START`, `RELEASE_START`,
  `POINT_DONE`, baseline start/end, experiment start/end; each event includes
  host monotonic/unix time and the latest device timestamp/frame sequence
- `meta.json`: identity, runtime config, 36-point protocol and point map
- `run.json`: duration, frame rate, missing/duplicate/out-of-order, valid ratio
- `analysis.json`, `responses.csv`, `REPORT.md`
- `timeseries.svg`: 12 raw channels with press/release event lines
- `response_map.svg`: 6x6 per-point statistic, explicitly **not** a simultaneous
  pressure heatmap

## Analysis and boundaries

- Baseline mean/std/drift/saturation and common-mode/MUX artifact metrics.
- Each point's 12-channel delta vs its local pre-press baseline.
- Response similarity and event alignment; no classifier accuracy is reported
  because one press per class cannot validate 36-class recognition.
- Raw counts are not pressure/force. If baseline saturation/common-mode exceeds
  the thresholds, the run is marked `INVALID_OR_FLOATING` and no spatial claim
  is made.
- A responsive or separable pattern is at most a **candidate**, requiring
  independent repeats.

## Dry-run result

A 0.2/0.1/0.1 s short dry run (`/tmp/tactile_36_dryrun`, not real experiment
data) completed 36/36 and produced all files. Its signal quality was
`INVALID_OR_FLOATING` (any-channel saturation 100%), consistent with the
zero-excitation input condition; it is **not** evidence of pressure response.
