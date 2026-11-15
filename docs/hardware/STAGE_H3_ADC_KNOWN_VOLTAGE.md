# H3 ADC2 AIN1 Known-Voltage Test

Use this only after the all-channel passive diagnostic shows no channel following
the measured 1.0 V → 2.4 V node. Do not change the existing cloth circuit until
the user authorizes this test.

## Safety

- Power off the old ESP32/ADS1220 before changing wiring.
- Disconnect R4 from ADC2 AIN1 and isolate the cloth node during injection.
- Keep the old ESP32 and ADS1220 grounds common.
- Do not connect the ESP32-S3 or gripper.
- Do not exceed ADS1220 AVDD/AVSS (3.3 V / 0 V).

## Test A: 0 V at ADC2 AIN1

```text
3.3 V ──/ (not connected)
ADC2 AIN1 ──1k── GND/AVSS
```

Measure AIN1–GND = 0.0 V with a DMM, then run:

```bash
.venv/bin/python scripts/diag_all_channels.py \
  --port /dev/cu.usbserial-EXAMPLE_ESP32 \
  --baseline-only --seconds 4 --avdd-mv <measured AVDD> \
  --label KNOWN_0V
```

Expected: ch5 (ADC2_AIN1) raw ≈ 0 and ≈ 0 V. Other channels may float; focus on ch5.

## Test B: ~1.65 V at ADC2 AIN1

```text
3.3 V ──10k──+──10k── GND/AVSS
              │
            1k
              │
        ADC2 AIN1
```

Measure AIN1–GND ≈ 1.65 V, then run the same command with
`--label KNOWN_1V65`.

Expected: ch5 raw ≈ `1.65 / AVDD × 8388607` ≈ 4.19 M at AVDD=3.3 V,
and ≈ 1.65 V in the report.

## Interpretation

- ch5 follows 0 V and 1.65 V → ADC2 AIN1 input/MUX path is basically working;
  the earlier R4 node was not actually reaching the ADC pin, or the cloth
  circuit/grounding is wrong.
- ch5 remains near 3.3 V for both 0 V and 1.65 V → ADC2 AIN1/MUX/front-end
  problem; do not blame the cloth. Record raw SPI register readback and repeat
  the known-voltage test on ADC2 AIN0/AIN2/AIN3 to distinguish MUX vs input.
- Any test requires all 12 channels and actual raw frames; do not infer from
  the final Reg0=0xB1 alone.

No firmware change or reflash is proposed until these measurements exist.
