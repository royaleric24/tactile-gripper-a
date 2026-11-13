# 6×6 matrix offline tooling

- `model.py`: 36-cell frame model and strict validation
- `schedule.py`: row-scan action sequence / timing / frame-rate estimate
- `protocol.py`: `MATRIX_FRAME` JSONL parse/encode
- `acquire.py`: record raw frames + cells.csv + run.json (transport injected)
- `analysis.py`: baseline, delta, localization, crosstalk, repeatability
- `cli.py`: `run` / `analyze` commands

Tests (no serial, no GPIO):

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tools/tactile_matrix/tests -t .
```

The firmware prototype is `firmware/sensor_matrix/`; it is compiled but **not
flashed** until the hardware rework is confirmed.
