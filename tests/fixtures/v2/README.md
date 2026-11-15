# P2-S 传感 fixtures

这些 JSONL 文件全部由当前分支的编码器生成，仅用于离线解析、Dashboard、
Trial/CSV/REPLAY 与异常路径测试。它们不是真实设备日志，也不代表协议已联调冻结。

| 文件 | 内容 | 主要用途 |
|---|---|---|
| `fsr_only.jsonl` | `FSR_ONLY` HELLO + 3 帧 SAMPLE；第 3 帧 FSR_B 无效（`null` / `false`） | 两路 FSR、无效通道、相对变化、CSV/REPLAY |
| `hybrid.jsonl` | `HYBRID_6X6_FSR2` HELLO + 38 通道 SAMPLE；36 个矩阵单元 + FSR 36/37 | 矩阵热图只消费 MATRIX_CELL、FSR 卡片与通道顺序 |
| `short_sample.jsonl` | HELLO 后跟一个仅含 1 个通道的 SAMPLE | 短帧拒绝，确认不会把缺通道当 0 或补值 |

重新生成或检查：

```bash
PYTHONPATH=src .venv/bin/python - <<'PY'
from tactile_gripper.devices.sensor import ReplaySensorAdapter
for name in ("fsr_only", "hybrid", "short_sample"):
    adapter = ReplaySensorAdapter(f"tests/fixtures/v2/{name}.jsonl")
    adapter.connect()
    print(name, adapter.channel_config.sensor_profile if adapter.channel_config else None)
PY
```

`short_sample` 在读取 SAMPLE 时会抛出 `FrameValidationError`，这是预期结果。
真实采集、烧录和机械动作不在这些 fixtures 的覆盖范围内。
