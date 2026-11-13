# Cup-Grasp Single-Point Wiring and Trial Safety

## Current status

- Tactile 36-point/QC data is `INVALID_OR_FLOATING`; it is **not** a usable
  pressure signal.
- ESP32-S3 gripper config: `hardware_enabled=false`, `calibration_state=UNCALIBRATED`,
  `safe_min_us/safe_max_us/initial_pulse_us = null`. **No real gripper motion is
  allowed** by the current configuration.
- No wiring change, firmware upload, PWM output or mechanical motion was done by
  this task.

## Minimal single-point topology (existing board; 0.1.2 reflash required)

Use one row and one column of the existing cloth; keep the validated 12-channel
firmware.

```
3.3 V ──1k── R1 (row electrode)
                  │
             one pressure cell
                  │
C1 (column) ──────┼── ADC1 AIN0 (module pin)
                  │
                R_ref
                  │
                GND/AVSS
```

### Exact connections

| Item | Connection |
|---|---|
| R1 row | 3.3 V through 1 kΩ (or GPIO4 if a single-point firmware is later used) |
| C1 column | ADS1220 ADC1 **AIN0** |
| R_ref | C1 to GND/AVSS, **10 kΩ 1%** (selected from measured 2–36 kΩ) |
| Other 5 rows | disconnected from any drive; leave high-Z |
| Other 5 columns | disconnected from ADC inputs or left high-Z; do not add references |
| Grounds | ESP32 GND, ADS1220 AVSS/DGND, 3.3 V supply ground common |
| Optional | 1 kΩ in series from C1 to AIN0, 100 pF AIN0 to GND |

If C1 is currently on a different AIN, either move it to ADC1 AIN0 or record the
actual AIN and update the host channel. **Do not guess the row/column-to-AIN
mapping; trace it first.**

### R_ref choice

With 3.3 V row excitation:

`V_col = 3.3 V × R_ref / (R_cell + R_ref + R_row)` (R_row = 1 kΩ)

With measured R1–C1 = 36 kΩ (no contact), 12 kΩ (light), 2 kΩ (heavier) and
R_ref = 10 kΩ, the predicted AIN0 voltages are:

| R_cell | V_AIN0 predicted | expected raw at AVDD=3.3 V |
|---|---:|---:|
| 36 kΩ | 0.702 V | ~1.78 M counts |
| 12 kΩ | 1.435 V | ~3.65 M counts |
| 2 kΩ | 2.538 V | ~6.45 M counts |

Use AVDD–AVSS reference (not internal 2.048 V) so 0–3.3 V can be read; at 2 kΩ
the 2.538 V would saturate the internal 2.048 V reference.

| measured R_cell | suggested R_ref | note |
|---|---|---|
| 1–10 kΩ | 1–10 kΩ | row current higher; keep 1 k series |
| 10–100 kΩ | 10–100 kΩ | **10 k selected for 2–36 kΩ measured range** |
| 100 kΩ–1 MΩ | 100 kΩ–1 MΩ | 100 k only if the measured range is higher |
| >1 MΩ | 1–10 MΩ | noise/leakage; longer settling |

Do not use the internal 2.048 V reference and assume 0–3.3 V is measurable. With
internal 2.048 V, any column voltage above 2.048 V saturates; choose R_ref so
`V_col < 2.0 V` or switch to AVDD–AVSS.

### ADS1220 configuration for the single point

- MUX = AIN0 vs AVSS (`0x81` with gain 1, PGA bypass)
- 330 SPS, normal, single-shot (`Reg1=0x80`)
- AVDD–AVSS reference (`Reg2=0xC0`)
- IDAC off, PSW off
- Gain 1; no PGA
- input must stay within AVSS−0.1 V … AVDD+0.1 V

The currently flashed `tactile-sense-0.1.0` **cannot** perform the AVDD–AVSS
single-point test correctly: its `SET_REF` maps AVDD to VREF code 1, writing
Reg2=`0x40` (external REFP0/REFN0). A corrected `tactile-sense-0.1.2` build
maps AVDD to code 3 (`0xC0`) and adds `VERIFY_CONFIG` register readback.
The single-point test therefore requires a **new flash** after user authorization;
it cannot run on the current 0.1.0 firmware with a valid AVDD reference.

The selected host channel is `ch0` = ADC1_AIN0. `0xC0` is AVDD: VREF[1:0]=11;
`0x80` would select external REFP1/REFN1 and is wrong.

### Single-point validation procedure

1. Power off; wire as above; check R1–C1 resistance with the cloth unpresssed and
   lightly pressed; confirm no short to 3.3 V/GND.
2. Power only the old ESP32 via Mac USB; do not connect the S3/gripper.
3. Flash/confirm `tactile-sense-0.1.2` (user-authorized), set reference AVDD_AVSS,
   and verify raw registers `[0x81,0x80,0xC0,0x00]` before trusting channel 0.
4. Run at least 5 contact/release cycles at R1C1, 2 s contact / 2 s release.
5. Compute per-cycle baseline, delta, noise, SNR, saturation, response latency
   and recovery. PASS requires repeatable response above noise, no saturation,
   and return to baseline; otherwise stop and report the electrical cause.

## Cup-grasp trial constraints

- Fixed mode requires a **user-verified** open/close pulse range and explicit
  hardware permission; the current S3 config is uncalibrated and will be refused.
- Feedback mode requires a valid single-point tactile signal, a verified gripper
  range, and a finite state controller with hysteresis/rate/step limits. If the
  sensor is invalid, timeout or saturating, the tool must set `NO_VALID_TACTILE`
  and must not command further closing.
- PWM commands are commands, not measured force/position. No Newton values.
- Video-derived slip is qualitative unless the camera is scale-calibrated.

## Real hardware still required

1. User traces R1/C1 and performs the single-point wiring.
2. User measures AIN0 at rest/light/heavy and checks against 0.702/1.435/2.538 V.
3. User authorizes the 0.1.2 flash and performs the 5-cycle test; verify registers
   `[0x81,0x80,0xC0,0x00]` and AVDD/DVDD = 3.3 V.
4. User provides a verified S3 open/close range and authorizes motion; current
   config cannot move.
5. Only then can real fixed/feedback cup trials be executed.
