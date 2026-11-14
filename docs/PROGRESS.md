# 进度（硬件组）

本文件只记录硬件分支 `hw/fsr-v2` 的进展与证据等级。`docs/demo-v2`（PR #1）尚未合入，
其 `docs/PROGRESS.md` 是另一条基线上的版本，两边合并时以"证据等级 + 可复现命令"为准对齐。

## 2026-11-14｜V2 四 ADC + 双 FSR（FSR_ONLY 优先）

| 项 | 状态 | 证据类型 |
|---|---|---|
| V2 引脚与 profile 配置（`config/sensor_esp32_fsr2*.json`） | IMPLEMENTED | 生成器校验 + 单测 |
| 第四颗 ADS1220 driver（`ads1220_multi.*`，无 V1 配置依赖） | IMPLEMENTED_UNVERIFIED | host 模拟 31 条断言 |
| 帧构造器 / 采样器 / 命令层（`frame_builder_fsr2.*`、`sampler_fsr2.*`、`sensor_fsr2.ino`） | IMPLEMENTED_UNVERIFIED | host 模拟 + 离线编译 |
| FSR_ONLY 固件离线编译 | **PASS（离线编译）** | `evidence/fsr2/build_sensor_fsr2/` |
| HYBRID_6X6_FSR2 固件离线编译 | **PASS（离线编译）** | `evidence/fsr2/build_sensor_fsr2_hybrid/` |
| host 模拟（driver + sampler + hybrid sampler） | **PASS（host 仿真，非硬件）** | `evidence/fsr2/host_tests/` |
| 帧往返检查与 fixtures 生成 | **PASS（host 仿真，非硬件）** | `evidence/fsr2/frames/`、`tests/fixtures/fsr2/` |
| 参考解析器 `tools/fsr2/protocol_v2.py` | IMPLEMENTED | 18 条协议单测 |
| 真实接线 / 烧录 / 采样 | **NOT_STARTED（未授权）** | — |

### 可复现命令（离线，不接线）

```bash
python3 scripts/generate_sensor_fsr2_config.py                      # FSR_ONLY 头文件
python3 scripts/generate_sensor_fsr2_config.py \
  --config config/sensor_esp32_fsr2_hybrid.json \
  --output firmware/sensor_fsr2/fsr2_config_hybrid.h
python3 scripts/run_fsr2_host_tests.py                              # g++ host 模拟
python3 scripts/check_fsr2_frames.py                                # 帧检查 + 重建 fixtures
ARDUINO_CLI="/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli" \
  python3 scripts/build_sensor_fsr2_firmware.py --build-dir "$PWD/evidence/fsr2/build_sensor_fsr2"
ARDUINO_CLI="..." \
  python3 scripts/build_sensor_fsr2_firmware.py --profile hybrid \
  --build-dir "$PWD/evidence/fsr2/build_sensor_fsr2_hybrid"
PYTHONPATH=src:. python3 -m unittest discover -s tests -p "test_fsr2_*.py"
```

`--build-dir` 必须是绝对路径（脚本用 `Path.relative_to` 记录证据路径）。

### 构建体积（离线编译结果）

| profile | program | 全局变量 |
|---|---:|---:|
| FSR_ONLY | 303471 B (23%) | 32872 B (10%) |
| HYBRID_6X6_FSR2 | 312695 B (23%) | 32872 B (10%) |

fqbn `esp32:esp32:nodemcu-32s`，arduino-cli 1.5.1，Arduino-ESP32 core 3.3.2。

### 实测行长度（帧构造器真实输出，非估算）

HELLO FSR_ONLY 1650 B；SAMPLE FSR_ONLY 931 B（ADC4 掉线 964 B）；
HELLO HYBRID 6554 B；SAMPLE HYBRID 2311 B。发送缓冲 8192 B。

### 下一步（需要现场授权）

接线核对 → 烧录 → 921600 打开串口收 HELLO → 空载基线 → 单路按压 → ADC4 断线/恢复语义。
逐条动作见 `docs/hardware/FSR_ONLY_INTERFACE_V2.md` §11。做完后把原始帧与 AVDD 实测值补到本文件，
并用真实样例替换/补充 `tests/fixtures/fsr2/`（现有一律来自 host 模拟）。
