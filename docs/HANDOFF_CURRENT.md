# 当前交接（硬件分支 hw/fsr-v2）

更新：2026-11-14。基线 `origin/feat/hardware-acquisition` @ b38e7bb。

## 一句话状态

V2 四 ADC + 双 FSR 的固件、离线测试、fixtures 与接口文档已完成；**两 profile 离线编译 PASS、
host 模拟 PASS**；真实接线/烧录/采样**未开始**（未授权）。FSR_ONLY 已可交付软件组解析。

## 分支与工作区

- 工作区：`~/Developer/research/tactile-gripper-v2-hw`，分支 `hw/fsr-v2`。
- 旧工作区 `~/Developer/research/tactile-gripper-a-hw` 的 7 修改 + 7 未跟踪 WIP **原样保留**，
  备份在 `~/Developer/research/tactile-gripper-v2-hw-wip-backup-20261114/`（含 tar、SHA256SUMS、diff、stash sha）。
  本分支未合并旧本地历史。
- `docs/demo-v2`（PR #1）未合入；V2 计划/接线/协议提案以其为基准阅读，本分支不改写它们。

## 目录

| 路径 | 内容 |
|---|---|
| `firmware/sensor_fsr2/` | 自包含 sketch：`sensor_fsr2.ino`、`ads1220_multi.*`、`frame_builder_fsr2.*`、`sampler_fsr2.*`、`fsr2.*`、`fsr2_config*.h`（生成） |
| `config/sensor_esp32_fsr2.json` | FSR_ONLY：2 通道，ADC4 = CS32/MISO33 |
| `config/sensor_esp32_fsr2_hybrid.json` | HYBRID_6X6_FSR2：38 通道（36 矩阵 + 2 FSR） |
| `scripts/generate_sensor_fsr2_config.py` | JSON → 头文件，含 4 ADC / AVDD 参考 / 布局校验 |
| `scripts/build_sensor_fsr2_firmware.py` | 离线编译（`--profile fsr|hybrid`） |
| `scripts/run_fsr2_host_tests.py` | g++ host 模拟测试 |
| `scripts/check_fsr2_frames.py` | 帧构造 → 严格解析 → 重建 fixtures |
| `tools/fsr2_sim/` | 四器件确定性 SPI/ADS1220 模拟 |
| `tools/fsr2/protocol_v2.py` | 软件组参考解析器（stdlib） |
| `tests/fixtures/fsr2/` | 6 个真实结构样例（来自 host 模拟） |
| `tests/test_fsr2_config.py`、`tests/test_fsr2_protocol.py` | 41 条离线单测 |
| `docs/hardware/FSR_ONLY_INTERFACE_V2.md` | 给软件组的接口说明 + 实机验收清单 |

`firmware/sensor/`（V1，3 ADC）保持冻结，未改动。

## 复现（离线）

```bash
python3 scripts/run_fsr2_host_tests.py
python3 scripts/check_fsr2_frames.py
PYTHONPATH=src:. python3 -m unittest discover -s tests -p "test_fsr2_*.py"
ARDUINO_CLI="<arduino-cli>" python3 scripts/build_sensor_fsr2_firmware.py --build-dir "$PWD/evidence/fsr2/build_sensor_fsr2"
ARDUINO_CLI="<arduino-cli>" python3 scripts/build_sensor_fsr2_firmware.py --profile hybrid --build-dir "$PWD/evidence/fsr2/build_sensor_fsr2_hybrid"
```

## 下一步（按优先级）

1. 现场授权后：接线核对 → 烧录 → 921600 收 HELLO → 空载/按压/断线恢复，按接口文档 §11 执行。
2. 把真实样例（脱敏）补入 `tests/fixtures/fsr2/`，并把 `docs/PROGRESS.md` 的状态从
   host 仿真升级为实测。
3. 软件组：`tools/tactile_acq/protocol.py` profile 化（I-012）、波特率改 921600（I-006）。
4. 合并 PR #1 后，把本分支 `docs/{PROGRESS,ISSUES,HANDOFF_CURRENT}.md` 与 demo-v2 版本对齐（I-016）。

## 不要做

- 不要用 `miso=[35,26,34]` 生成 V2 固件（生成器会拒绝，别绕过）。
- 不要用内部 2.048 V 参考测 FSR 分压（会削顶）。
- 不要把 host 模拟结果写成"硬件已验证"。
- 不要在未授权时打开串口、烧录、接线、上电或驱动机械。
