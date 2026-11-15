# Stage H2 QC Correction and Corrected ML Evaluation

- Pre-QC Git checkpoint: `310c83d` (`checkpoint: pre-QC multi-round experiment code and analysis`).
- Experiment: `data/real/tactile_36point_multiround/20261113T150928Z__dev_cu.usbserial-EXAMPLE_ESP32/`
- Original raw files: SHA-256 recorded and set read-only; not modified.
- Corrected revision:
  `data/real/tactile_36point_multiround/20261113T150928Z__dev_cu.usbserial-EXAMPLE_ESP32/revision_qc_20261113T162300Z/`

## QC

| round | segment | kind | label | treatment |
|---:|---:|---|---|---|
| 1 | 22 | PRESS | R1C6 | exclude train+eval; OPERATOR_ERROR |
| 1 | 35 | APPROACH | APPROACH-1-R2C3 | exclude train+eval; OPERATOR_ERROR |
| 2 | 10 | PRESS | R6C5 | exclude train+eval; OPERATOR_ERROR |

`actual_action=UNKNOWN`, `source=USER_REPORTED`; no relabeling. After QC:
70 PRESS, 3 APPROACH, 4 NO_CONTACT; 34 common positions; 36 distinct positions
across rounds (each round has 35).

## Corrected results

- Quality remains **INVALID_OR_FLOATING** (QC-filtered baseline/press saturation
  ~30.5%/30.6%); the physical quality gate was not relaxed.
- Strict common-34 point model, whole-round split:
  - best corrected: nearest centroid / per-channel, Top-1 0.088 (3/34),
    Top-3 0.088 (3/34), row 0.294, col 0.235.
  - random: Top-1 1/34=0.029, Top-3 3/34=0.088; no useful spatial signal.
- Artifact-only features (saturation/common-mode) reach Top-3 0.235, higher
  than per-channel; this is evidence of artifact reliance, not pressure.
- Contact 3-class (PRESS/APPROACH/NO_CONTACT), best corrected:
  - accuracy 0.816, balanced accuracy 0.452, macro F1 0.614;
  - APPROACH→PRESS 1.000, NO_CONTACT→PRESS 0.500;
  - test support: PRESS 35, APPROACH 1, NO_CONTACT 2; exploratory only.
- Two-stage contact gate (CONTACT/NON_CONTACT): balanced accuracy 0.5,
  NON_CONTACT→CONTACT 1.0; not a usable contact detector.
- Repeatability: same-point cosine 0.089 vs different 0.019; separation 0.069.

## Recommendation

**Do not proceed to the 3-train + validation + blind stage.** The zero-rewire
signal is still saturation/common-mode dominated, point accuracy is at the
random baseline, and contact detection fails on the few controls. The required
next step is the electrical fix (row drive + column reference resistors), not a
more complex model.

Corrected report:
`revision_qc_20261113T162300Z/REPORT_CORRECTED.md`
