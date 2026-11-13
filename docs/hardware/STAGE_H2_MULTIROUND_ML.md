# 36-Point Multi-Round Randomized Experiment + Preliminary ML

## Status

- Two-round runner: implemented, offline-tested, and software dry-run verified.
- Real two-round data: **not collected yet**; requires the user to press.
- Current hardware: unchanged `tactile-sense-0.1.0`; no IDAC/PSW/rewiring/S3.
- Full 3-train + 1-validation + 1-blind run: **not executed**; gated on the
  two-round data showing a stable, non-artifact signal.
- The previous single-round 36-point data was `INVALID_OR_FLOATING`; the
  two-round run is expected to confirm or reject that, not to turn floating
  noise into pressure.

## Run command (two randomized rounds)

```bash
cd /home/example/Developer/research/tactile-gripper-a-hw
.venv/bin/python scripts/tactile_multiround_experiment.py \
  --port /dev/cu.usbserial-EXAMPLE_ESP32 --rounds 2
```

Defaults: 36 presses + 2 approach + 2 no-contact controls per round; press 3 s,
release 3 s; 10 s pre/post baseline; 20 s rest between rounds; different random
seed per round. The script asks `START` once and Enter before each segment.

Estimated: ~4.5 min/round plus Enter/rest; two rounds ~10–12 min.

During the run:

- follow the printed randomized order exactly;
- press/hold 3 s at `PRESS ... NOW`, release 3 s;
- for `APPROACH`: move the tool close but **do not touch**, hold 3 s, withdraw;
- for `NO_CONTACT`: keep the tool completely away for the full segment;
- same non-conductive tool/area/force; do not touch bare electrodes.

Each round is saved separately under a new session:

```text
data/real/tactile_36point_multiround/<UTC>_<port>/
  session.json                 # seeds, random order, round paths
  round_01/
    raw_frames.jsonl
    samples.csv
    events.jsonl               # PRESS/APPROACH/NO_CONTACT + baseline events
    schedule.json              # seed + full randomized segment order
    meta.json                  # identity/config/protocol/schedule
    run.json                   # frame rate, missing, valid ratio
  round_02/...
  features.csv                 # metadata + raw-signal features (labels separate)
  ml_report.json
  confusion_matrix.svg
  REPORT.md
```

## Labels and leakage

- The schedule/order/labels are saved for scoring only.
- Feature vectors contain **only** raw-signal statistics: local baseline,
  press mean/median/std/slope, delta, z, saturation/valid fractions, post delta.
  They contain no point id, row/column, round, seed, order or event label.
- Train/test splits are **whole rounds**, never adjacent frames.

## Preliminary models

- Nearest centroid
- KNN (k=3)
- Regularized multinomial logistic regression
- Feature sets: per-channel only; per-channel + common-mode features (ablation)
- Metrics: Top-1, Top-3, row/column accuracy, control false-contact rate,
  confidence, confusion matrix, same/different-point repeatability.
- Random baselines: Top-1 = 1/36, Top-3 = 3/36, row/col = 1/6.
- A control predicted as PRESS is a false-contact; APPROACH/NO_CONTACT can be
  treated as UNKNOWN rather than forced to a point.

A single press per point per round is **not** enough to validate 36-class
recognition. The two-round report is explicitly preliminary.

## Dry-run result

`/tmp/tactile_multiround_dryrun` (not real data): 2 rounds × 36 presses completed,
38 segments/round, `features.csv` 77 rows, `ml_report.json` generated.
Signal quality: `INVALID_OR_FLOATING` (baseline saturation ~31%, press ~31%),
consistent with the zero-excitation input. No spatial/pressure claim.

## Gating for the full blind test

Only if the real two-round data show a stable, non-saturation/non-common-mode
signal and cross-round repeatability above chance should the project proceed to:

- 3 independent randomized training rounds;
- 1 validation round;
- 1 independent blind round;
- freeze model/preprocessing/threshold before revealing blind labels;
- report Top-1/Top-3/row/column, confusion, UNKNOWN rate, confidence, and
  random baselines.

That stage is not implemented/run in this delivery.
