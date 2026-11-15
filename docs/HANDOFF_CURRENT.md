# 当前交接（硬件分支 hw/fsr-v2，2026-11-15 接线修正版）

基线 `origin/feat/hardware-acquisition` @ b38e7bb。上一提交：V2 四 ADC + 双 FSR（2026-11-14）。
本次为增量修正提交，不重写历史。

## 一句话状态

压敏布实为 **12 根独立电极**（R×10 kΩ 下拉 GND、C×1 kΩ 上拉 3.3 V，各自接 ADS1220 AIN），
原 6×6 列扫描/36 点方案已撤回。固件改为 `FSR_ONLY` + `MATRIX_ELECTRODES_12`（12 或 14 逻辑
通道），**三个 profile 离线编译 PASS、host 模拟与 fixtures PASS**；真实接线/烧录/采样**未开始**
（用户明确暂停）。真实 R/C→ADC/AIN 映射仍缺失，固件对未映射通道输出 `null` + `NO_DATA`。

## 目录

| 路径 | 内容 |
|---|---|
| `firmware/sensor_fsr2/` | 自包含 sketch：`sensor_fsr2.ino`、`ads1220_multi.*`、`frame_builder_fsr2.*`、`sampler_fsr2.*`、`fsr2.*`、三个生成的 `fsr2_config*.h` |
| `config/sensor_esp32_fsr2.json` | FSR_ONLY（2 通道，ADC4） |
| `config/sensor_esp32_electrodes12.json` | 12 电极（ADC1–3，映射 MISSING） |
| `config/sensor_esp32_electrodes12_fsr2.json` | 12 电极 + 2 FSR（14 通道，映射 MISSING） |
| `scripts/generate_sensor_fsr2_config.py` | JSON → 头文件；拒绝 HYBRID；未映射 sentinel；映射唯一性校验 |
| `scripts/build_sensor_fsr2_firmware.py` | `--profile fsr\|electrodes12\|electrodes12_fsr2` |
| `scripts/run_fsr2_host_tests.py` | 4 个 host 用例（含未映射与合成映射） |
| `scripts/check_fsr2_frames.py` | 帧往返 + 重建 9 个 fixtures |
| `tools/fsr2_sim/` | 四器件 SPI/ADS1220 模拟 + `electrode_test_profile.h`（合成映射，仅测试） |
| `tools/fsr2/protocol_v2.py` | 软件组参考严格解析器（`PROFILE_HISTORICAL`、mapping 校验） |
| `tests/fixtures/fsr2/` | FSR + 电极（未映射/合成映射）样例，全部来自 host 模拟 |
| `tests/test_fsr2_config.py`、`tests/test_fsr2_protocol.py` | 49 条离线单测 |
| `docs/hardware/FSR_ONLY_INTERFACE_V2.md` | 串口接口、电极语义、行长、验收清单、**电极映射核对表** |

`firmware/sensor/`（V1，3 ADC）与 `firmware/sensor_matrix/`（历史扫描原型）保持冻结，未改动。

## 复现（离线，不接线）

```bash
python3 scripts/run_fsr2_host_tests.py
python3 scripts/check_fsr2_frames.py
PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests -p "test_fsr2_*.py"
ARDUINO_CLI="<arduino-cli>" python3 scripts/build_sensor_fsr2_firmware.py --profile fsr \
  --build-dir "$PWD/evidence/fsr2/build_fsr"
ARDUINO_CLI="<arduino-cli>" python3 scripts/build_sensor_fsr2_firmware.py --profile electrodes12 \
  --build-dir "$PWD/evidence/fsr2/build_electrodes12"
ARDUINO_CLI="<arduino-cli>" python3 scripts/build_sensor_fsr2_firmware.py --profile electrodes12_fsr2 \
  --build-dir "$PWD/evidence/fsr2/build_electrodes12_fsr2"
```

## 下一步（等待用户明确通知）

1. 现场按接口文档 §11 断电核对焊接（R×10 kΩ→GND、C×1 kΩ→3.3 V、无 GPIO 列线）。
2. 填写 §12 电极映射表 → 改配置 `electrodes.map` 与 `mapping_status` → 重新生成头文件。
3. 授权后烧录 14 通道 profile，先看 HELLO（`mapping_status = TABLE_PROVIDED`）再开流。
4. 软件组：`tools/tactile_acq/protocol.py` profile 化（I-101）、波特率 921600（I-006）、
   删除缓存的 hybrid fixtures（I-109）。

## 不要做

- 不要为 HYBRID_6X6_FSR2 生成固件或烧录旧 38 通道镜像（生成器会拒绝，别绕过）。
- 不要把 12 电极渲染成 6×6 热图或写成 36 个压力点。
- 不要用合成映射（`SIM_SYNTHETIC_MAPPING`）当真实接线。
- 不要把 host 模拟写成硬件实测；真实采样前所有固件行为保持 IMPLEMENTED_UNVERIFIED。
- 未授权时不要打开串口、烧录、上电或驱动机械。
