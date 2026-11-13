# H3 Single-Point Reference Audit (offline)

## 1. Correct ADS1220 VREF mapping

Per TI ADS1220 Rev.D, Table 8-13 (page 45), register 2 bits 7:6:

| VREF[1:0] | Reference | Reg2 |
|---|---|---:|
| 00 | internal 2.048 V | 0x00 |
| 01 | external REFP0/REFN0 | 0x40 |
| 10 | external REFP1/REFN1 | 0x80 |
| **11** | **AVDD–AVSS** | **0xC0** |

`tactile-sense-0.1.0` mapped AVDD to code 1 and wrote **0x40** (external REF0).
`0.1.1` mapped AVDD to code 2 and wrote **0x80** (external REF1); that was still
wrong. This correction uses code **3** and Reg2 **0xC0**.

## 2. Firmware fix (0.1.3)

- `scripts/generate_sensor_config.py`: `AVDD_AVSS = 3`; four-entry
  `VREF_ENCODINGS` table for 00/01/10/11.
- `firmware/sensor/sensor.ino`:
  - `SET_REF AVDD_AVSS` sets code 3;
  - `referenceName()` recognizes 0 internal and 3 AVDD;
  - `VERIFY_CONFIG` decodes 0/1/2/3 to internal/REF0/REF1/AVDD.
- `0.1.2` had the correct `0xC0` mapping but its `VERIFY_CONFIG` response wrote
  an extra closing brace (`]}}`) before `request_id`, producing invalid JSON.
  `0.1.3` fixes the response shape; host diagnostics/retries were added.
- Version bumped to `tactile-sense-0.1.3`.
- `VERIFY_CONFIG` reads back Reg0–Reg3 and decoded fields from all three ADCs
  via real SPI `RREG` commands, not cached values.
- Offline build only; **not flashed**.

## 3. Required registers

| Register | Value | Meaning |
|---|---:|---|
| Reg0 | `0x81` | AIN0 vs AVSS, gain 1, PGA bypass |
| Reg1 | `0x80` | Normal, 330 SPS, single-shot |
| Reg2 | `0xC0` | AVDD–AVSS, 50/60=00, PSW=0, IDAC=000 |
| Reg3 | `0x00` | IDAC routing off |

`VERIFY_CONFIG` must return `[0x81,0x80,0xC0,0x00]` on all three ADS1220s.
The host validator also requires decoded `vref_code=3`, `vref=AVDD_AVSS`,
`mux=8`, `gain_code=0`, `pga_bypass=true`, `psw=0`, `idac_code=0`.

## 4. Wiring (unchanged: 1 kΩ + 10 kΩ)

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

The 2.538 V point would saturate the internal 2.048 V reference; AVDD–AVSS is
required.

## 5. AVDD/AVSS/ESP32 compatibility

- ADS1220 AVDD/DVDD must be 3.3 V; measure both at the module.
- ESP32 and ADS1220 grounds must be common.
- Absolute input range is AVSS−0.1 V … AVDD+0.1 V; expected maximum 2.538 V is
  below 3.3 V and the absolute maximum (~3.4 V).
- Divider current at 2 kΩ is about 3.3 V / 13 kΩ ≈ 254 µA; at 36 kΩ about 70 µA.
- Do not use a 5 V supply for the ADS1220. If AVDD is not exactly 3.3 V, pass
  the measured value via `--avdd-mv`.

## 6. AIN0 wiring check (do not trust old labels)

1. Power off; disconnect C1 from every other circuit.
2. Continuity: C1 ↔ ADC1 AIN0; no continuity C1 ↔ 3.3 V/GND/other AINs.
3. Continuity: R1 ↔ 3.3 V through the 1 kΩ; other rows isolated.
4. Install 10 kΩ from C1 to GND; verify 10 kΩ ±1%.
5. Power only old ESP32; measure ADS1220 AVDD/DVDD = 3.3 V.
6. Measure AIN0 at rest/light/heavy: expect ~0.702/1.435/2.538 V. If not, stop.
7. Only after voltage and register checks pass, run the 5-cycle validator.

## 7. Single-point validator

`scripts/tactile_single_point_validate.py`:

- selects channel 0 (ADC1 AIN0);
- sends `SET_REF AVDD_AVSS`;
- sends `VERIFY_CONFIG` and requires `[0x81,0x80,0xC0,0x00]` and vref_code 3;
- records 5 contact/release cycles, raw/filtered/delta, saturation, latency,
  recovery and SNR;
- converts counts to approximate volts using `--avdd-mv`;
- estimates R_cell from `--r-ref-ohm 10000 --r-row-ohm 1000 --v-exc 3.3`;
- writes `data/real/single_point/<trial_id>/`.

```bash
.venv/bin/python scripts/tactile_single_point_validate.py \
  --port /dev/cu.usbserial-EXAMPLE_ESP32 --channel 0 --cycles 5 \
  --avdd-mv 3300 --r-ref-ohm 10000 --r-row-ohm 1000
```

## 7.1 Scan-mode MUX acceptance (host-only fix)

The normal firmware scans `step=0..3`:

```text
setMux(MUX[step]) -> startConversion() -> convert -> channel = adc_index*4 + step
```

`MUX[0..3] = 8..11` (AIN0..AIN3). After step 3 the register is left at AIN3,
so a running-scan `VERIFY_CONFIG` naturally reads Reg0=`0xB1`. This is not a
channel error and does not require a firmware change or reflash.

The host verifier now separates:

- **scan mode**: Reg0 may be `0x81/0x91/0xA1/0xB1`; it still requires
  Reg1=`0x80`, Reg2=`0xC0`, Reg3=`0x00`, gain=1, PGA bypass, VREF AVDD,
  PSW/IDAC off, the 12-channel map (ch0=Ain0, ch1=Ain1, ...), and a fresh
  ch0-valid SAMPLE frame. It reports `SCAN_MODE_PASS`, never a generic
  fixed-mode PASS.
- **fixed mode**: requires Reg0=`0x81` exactly; no fixed single-channel command
  is available on 0.1.3, so fixed mode is not inferred from the scan.

A source test checks that `setMux()` occurs before `startConversion()` and that
`channel = adc_index*4 + step`. This is a code/protocol check; the saved raw
register and frame evidence remain the actual hardware record.

## 7.2 Identity/channel-config propagation

`DeviceIdentity` now carries `channel_config` from the real HELLO payload, and
`HelloMessage.channel_config` exposes the same raw object. The host verifier
uses `identity.channel_config` (falling back to `identity.hello["channel_config"]`
for compatibility), never a nonexistent `identity.raw`. Missing HELLO/channel
config, missing/failed SAMPLE, malformed JSON and timeout each produce an
explicit error and never `SCAN_MODE_PASS`.

## 8. Answers

- **Current flashed 0.1.0 direct test?** No: writes Reg2=0x40 (REF0).
- **0.1.2 direct test?** No: reference mapping is correct, but its `VERIFY_CONFIG`
  JSON is malformed (`]}}`), so the host cannot parse it.
- **Must reflash?** Yes, to 0.1.3 (built offline, not flashed).
- **Is 0xC0 correct?** Yes: VREF=11 AVDD–AVSS.
- **Is 0x80 correct?** No: VREF=10 external REFP1/REFN1.
- **Register readback?** Yes: `VERIFY_CONFIG`; expected
  `[0x81,0x80,0xC0,0x00]`.
- **Circuit unchanged?** Yes: 1 kΩ row + 10 kΩ reference.
- **Git checkpoint:** pre-fix `5ec7c01`; final fix commit reported in the answer.
