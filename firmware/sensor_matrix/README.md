# 6×6 matrix prototype (OFFLINE, NOT FLASHED)

This sketch implements the row-scan sequence for the proposed hardware:

- 6 row GPIOs: 4, 13, 14, 25, 27, 32 (through 1 kΩ), selected HIGH / others HIGH_Z
- 6 columns on ADS1220 AIN: ADC1 AIN0/AIN1, ADC2 AIN0/AIN1, ADC3 AIN0/AIN1
- one reference resistor per column to GND
- AVDD–AVSS reference, no IDAC
- two conversion rounds per row (3 ADCs in parallel), 36 cells per frame

**Do not flash this sketch until the row rework, column reference resistors and
electrical checks in `docs/hardware/STAGE_H2_SCAN_DESIGN.md` are confirmed.**
The current flashed firmware is still the validated 12-channel `firmware/sensor`.

Build only:

```bash
.venv/bin/python scripts/build_sensor_matrix_firmware.py
```

The script writes `evidence/sensor_matrix/build_matrix.json` with
`"note": "OFFLINE BUILD ONLY - NOT FLASHED"`.
