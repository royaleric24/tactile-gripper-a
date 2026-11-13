# H3 Single-Point Reference Audit (offline)

## 1. `SET_REF AVDD_AVSS` audit

Current flashed firmware: `tactile-sense-0.1.0`.

The 0.1.0 implementation mapped `AVDD_AVSS` to `reference_mode=1`; `buildNormalConfig()`
then wrote `reference_mode << 6` = **Reg2 = 0x40**. ADS1220 VREF[1:0]=01 is
**external REFP0/REFN0**, not AVDD. Therefore the old firmware cannot provide a
valid AVDD–AVSS reference for the single-point test.

Correct encoding (ADS1220 register 2, bits 7:6):

| VREF[1:0] | Reference | Reg2 bits |
|---|---|---:|
| 00 | internal 2.048 V | 0x00 |
| 01 | external REFP0/REFN0 | 0x40 |
| **10** | **AVDD–AVSS** | **0x80** |
| 11 | external REFP1/REFN1 | 0xC0 |

`0xC0` is **not** AVDD; it selects external REFP1/REFN1. The correct value is
`0x80`.

## 2. Firmware fix

- `scripts/generate_sensor_config.py`: `REFERENCE_CODES["AVDD_AVSS"] = 2`.
- `firmware/sensor/sensor.ino`: `SET_REF AVDD_AVSS` sets code 2; comment documents
  VREF=10.
- Added command `VERIFY_CONFIG`: reads back Reg0–Reg3 from each ADS1220 and
  returns the raw registers plus decoded MUX/gain/PGA/VREF/PSW/IDAC fields.
- Firmware version bumped to `tactile-sense-0.1.1`.
- Built offline: 306,208 B, SHA-256 `42838a433d48afe006f46058142abbf1dc0c34bdd3caaa4a276a55475fafc3dd`.
- **Not flashed.**

## 3. Required registers for the single point

| Register | Value | Meaning |
|---|---:|---|
| Reg0 | `0x81` | AIN0 vs AVSS, gain 1, PGA bypass |
| Reg1 | `0x80` | Normal, 330 SPS, single-shot |
| Reg2 | `0x80` | AVDD–AVSS, 50/60=00, PSW=0, IDAC=000 |
| Reg3 | `0x00` | IDAC routing off |

`VERIFY_CONFIG` must return `[0x81,0x80,0x80,0x00]` on all three ADS1220s.
The host script `scripts/verify_single_point_config.py` checks the raw bytes and
decoded fields and saves evidence.

## 4. Wiring (measured R1–C1: 36/12/2 kΩ)

| Item | Connection |
|---|---|
| R1 | 3.3 V through **1 kΩ 1%** |
| C1 | ADS1220 **ADC1 AIN0** |
| C1 reference | **10 kΩ 1%** to GND/AVSS |
| Other electrodes | disconnected/high-Z, isolated |
| Grounds | ESP32, ADS1220 AVSS/DGND, 3.3 V common |

Predicted AIN0 with the 1 kΩ row and 10 kΩ reference:

| R1–C1 | Predicted V | Approx raw at AVDD 3.3 V |
|---|---:|---:|
| 36 kΩ | 0.702 V | ~1.78 M |
| 12 kΩ | 1.435 V | ~3.65 M |
| 2 kΩ | 2.538 V | ~6.45 M |

The 2.538 V point would saturate the internal 2.048 V reference, so the
AVDD–AVSS reference is required.

## 5. AVDD/AVSS/ESP32 compatibility

- ADS1220 AVDD/DVDD must be 3.3 V; measure both at the module.
- ESP32 and ADS1220 grounds must be common.
- Absolute input range is AVSS−0.1 V … AVDD+0.1 V; the expected maximum 2.538 V
  is below 3.3 V and below the absolute maximum (~3.4 V).
- Maximum divider current at 2 kΩ is about 3.3 V / 13 kΩ ≈ 254 µA; at 36 kΩ
  about 70 µA; within a normal 3.3 V rail.
- Do not use a 5 V supply/5 V logic module for this measurement; verify the
  actual module AVDD/DVDD.
- If AVDD is not exactly 3.3 V, pass the measured value to the validator via
  `--avdd-mv`; the conversion uses it.

## 6. AIN0 wiring check (do not trust labels)

1. Power off; disconnect C1 from every other circuit.
2. Continuity: C1 ↔ ADC1 AIN0; no continuity C1 ↔ 3.3 V/GND/other AINs.
3. Continuity: R1 ↔ 3.3 V through the 1 kΩ; no other row connected.
4. Install the 10 kΩ from C1 to GND; verify 10 kΩ ±1%.
5. Power only the old ESP32 via Mac USB; measure ADS1220 AVDD/DVDD = 3.3 V.
6. Measure AIN0 at rest/light/heavy: expect ~0.702/1.435/2.538 V. If not, stop
   and report the actual value; do not run the trial.
7. Only after the voltage and register checks pass, run the 5-cycle validator.

## 7. Single-point validator

`scripts/tactile_single_point_validate.py`:

- selects channel 0 (ADC1 AIN0);
- sends `SET_REF AVDD_AVSS`;
- sends `VERIFY_CONFIG` and requires `[0x81,0x80,0x80,0x00]` on all three ADCs;
- records 5 contact/release cycles with prompts;
- records raw/filtered/baseline/delta, saturation, latency, recovery;
- converts counts to approximate volts using `--avdd-mv` and estimates R_cell
  from `--r-ref-ohm 10000 --r-row-ohm 1000 --v-exc 3.3`;
- writes `data/real/single_point/<trial_id>/`.

Command:

```bash
.venv/bin/python scripts/tactile_single_point_validate.py \
  --port /dev/cu.usbserial-EXAMPLE_ESP32 --channel 0 --cycles 5 \
  --avdd-mv 3300 --r-ref-ohm 10000 --r-row-ohm 1000
```

## 8. Answers

- **Can the currently flashed firmware directly run the single-point test?**
  No. `tactile-sense-0.1.0` writes Reg2=`0x40` for AVDD, which is external REF0,
  not AVDD–AVSS.
- **Must it be reflashed?** Yes, to `tactile-sense-0.1.1` (built offline, not
  flashed). Internal 2.048 V would saturate the 2 kΩ/2.538 V point and is not a
  valid substitute for the full range.
- **Is 0xC0 correct?** No. `0xC0` = VREF 11 = external REFP1/REFN1; correct AVDD
  is `0x80` = VREF 10.
- **Register readback added?** Yes, `VERIFY_CONFIG`; host script verifies raw
  bytes and decoded fields.
- **Git checkpoint:** pre-fix `fe8d1a8`; this H3 change is committed separately
  after tests.
