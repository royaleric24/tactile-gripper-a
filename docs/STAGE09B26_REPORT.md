# Stage 0.9B-26｜ESP32-S3 机械爪控制迁移及 A/B 验证

日期：2026-11-12（Asia/Shanghai）
状态：**已验收**。S3 固件上传/verify PASS，通信 PASS；用户已亲自完成真实机械爪测试并报告开合 PASS。精确位置误差与长期稳定性 UNKNOWN。本验收步骤未重新烧录、未重复舵机测试。

## 1. 设备识别（实机，非猜测）

| 项目 | 结果 | 来源 |
|---|---|---|
| 串口 | `/dev/cu.usbserial-EXAMPLE_S3` | `ioreg` + `esptool` |
| USB 桥 | FT232R USB UART，序列号 EXAMPLE_S3 | `ioreg` |
| 芯片 | ESP32-S3 (QFN56) revision v0.2 | `esptool 5.1.0` |
| MAC | `02:00:00:00:00:03` | `esptool` |
| 晶振 | 40 MHz | `esptool` |
| Flash | 16 MB，quad 4 data lines，3.3V eFuse | `esptool flash_id` |
| PSRAM | 8 MB embedded | `esptool` 特性 + 固件 `getPsramSize()` |
| 旧 ESP32 端口 | 本次未出现；旧板为 ESP32-D0WDQ6，端口 `/dev/cu.usbserial-EXAMPLE_ESP32` | 历史证据 + 本次枚举 |

证据：`evidence/stage09b26/device_identify.txt`、`flash_identify.txt`。原始 16 MB Flash 在写入前已只读备份：`s3_pre_migration_flash_16MB_460800.bin`，SHA-256 `cd0f30ac9491da499eaf2167f07b5accf23cf6779c506110431aa766f346273e`。

## 2. 最小代码改动

- `config/gripper_s3.json`：S3 独立运行配置，GPIO4、50Hz、14-bit、500–2500μs、Bench/Hold 语义与旧版一致。
- `config/board_s3.json`：S3 构建目标、FQBN 选项、已检测到的 Flash/PSRAM 与串口信息。
- `config/board_esp32.json`：旧 ESP32 基线目标说明，保持 GPIO23/16-bit/0.9b24.0。
- `firmware/gripper_control/SafetyCore.h`：删除 `bits==16` 与 `hz==50` 硬编码，改为板级 `pwmConfigValid()`；`pulseDuty()` 按任意 8–20 bit 计算并阻止越界 duty。
- `firmware/gripper_control/gripper_control.ino`：按 `GRIPPER_BOARD_S3` 选择 `generated_config_s3.h`；读回等待改为 `CFG_FIRST_READBACK_SETTLE_MS` / `CFG_READBACK_SETTLE_MS`；STATUS 增加板级/芯片/Flash/PSRAM 诊断字段。启动仍不 attach LEDC、不输出 PWM。
- `scripts/generate_gripper_config.py`：支持 `--output`，允许 14/16-bit，校验读回等待参数。
- `scripts/build_firmware.py`：`esp32` / `s3` 两个独立构建目标，不共享生成头、FQBN 或构建目录。
- `scripts/pwm_console.py`：新增 `--target {esp32,s3}`、`--config`、`--list-ports`；端口仍必须显式提供，不写死 S3 端口。握手继续按固件版本精确匹配。
- `tests/native_control/s3_adapter_test.cpp`、`tests/test_s3_config.py`、`tests/test_pwm_console.py`：新增 S3 14-bit、GPIO4、多目标、Hold、STOP、FAULT、诊断和主机目标选择测试。
- `tests/native_control/bench_test.cpp`：仅更新两条已过时的 Bench 断言，使其匹配 Stage 0.9B-20C 的任意首目标/无 50μs 步幅规则。

旧 ESP32 的 `evidence/stage09b24/build_bench/`、旧 BIN、旧配置和真实日志均未修改。旧 ESP32 未上传本阶段固件。

## 3. 编译与测试

### 构建

| 目标 | FQBN | 结果 | BIN | SHA-256 |
|---|---|---|---|---|
| S3 | `esp32:esp32:esp32s3:FlashSize=16M,FlashMode=qio,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB,UploadSpeed=921600,USBMode=hwcdc,CDCOnBoot=default,UploadMode=default,EraseFlash=none` | PASS | `evidence/stage09b26/build_s3/gripper_control.ino.bin` | `04c77eed02c1d300f1d6aede842069489295f9fab4638ad2612acecb519c9348` |
| 旧 ESP32 | `esp32:esp32:nodemcu-32s` | PASS（兼容性构建，未上传） | `evidence/stage09b26/build_esp32_bench/gripper_control.ino.bin` | `8f3bdf2aa299f10bb2cf4c5ea45a21de1cb47bc6fd5b0054f334d56ddbf596f1` |

S3 构建产物：app 316,272 bytes（10% of 3 MB），分区表 `app0/app1/ffat/coredump`，16 MB Flash 参数。旧基线 BIN `bd02b1d2...` 保持原样。上传时因 921600 只读备份出现过数据损坏，实际改用 460800 上传；构建产物的 `UploadSpeed=921600` 只影响默认上传参数，不改变固件内容。

### 离线测试

- 原生 Bench/状态机：11/11 PASS（含 `bench_adapter`、`bench_range`、`bench_test`、`hold`、`mech_*`、`output_diag` 等）。
- 原生 Trial 回归：2/2 PASS（`ledc_regression`、`trial_adapter`）。
- 原生 S3 适配：1/1 PASS（GPIO4、50Hz、14-bit duty、1500→1400→1200→1150→1500、>5s Hold、STOP、FAULT、LEDC 诊断、旧 16-bit 兼容）。
- Python：107/107 PASS（含新增 S3 配置/控制台目标测试）。

日志：`evidence/stage09b26/native/`、`python_tests.txt`。

## 4. 上传与启动状态

- 上传：`arduino-cli upload ... -t`，PASS；每段均 `Hash of data verified`。
- 串口：`/dev/cu.usbserial-EXAMPLE_S3`（已确认是 ESP32-S3，不是旧 ESP32）。
- 固件：`gripper-control-s3-0.9b26.0`。
- 启动 STATUS：`state=DISARMED`、`fault_reason=BOOT`、`calibration_state=UNCALIBRATED`、`hardware_enabled=false`、`bench_capable=true`、`bench_active=false`、`output_state=DISABLED_UNMEASURED`、`commanded_pulse_us=null`。
- 设备回报：`board_target=esp32s3`、`pwm_gpio=4`、`pwm_frequency_hz=50`、`pwm_resolution_bits=14`、`pwm_first_readback_settle_ms=25`、`chip_model=ESP32-S3`、`flash_size_bytes=16777216`、`psram_size_bytes=8388608`。

上传与状态证据：`upload_s3.txt`、`s3_status.json`、`s3_status_transport.jsonl`。状态查询日志只有 `GET_STATUS` 和 `DISARM`，没有 PWM 命令。

## 5. 真实验收结果（用户执行）

| 验收项 | 结果 | 依据 |
|---|---|---|
| 固件上传 | **PASS** | `upload_s3.txt`，逐段 `Hash of data verified` |
| 通信 | **PASS** | 真实日志中 `gripper-control-s3-0.9b26.0` 的 STATUS/ACK、69 次心跳、0 个 ERROR、0 个 FAULT |
| 用户报告真实机械爪开合 | **PASS（USER_REPORTED）** | 用户亲自完成测试，确认实际开合效果与旧 ESP32 基本一致 |
| 精确位置误差 | **UNKNOWN** | 无独立角度/位移测量，未把 PWM 目标当实际位置 |
| 长期稳定性 | **UNKNOWN** | 未做长时间重复性、温漂、供电波动或寿命统计 |

真实日志：[transport.jsonl](<logs/real/bench/0e0571fd739d4f638541df1ccae5cc9b/transport.jsonl>)，SHA-256 `a8721adfca98471a602266aff2418fb74eaee8abc2f1619d1a44e4037512e241`。时间 2026-11-12 13:29:32–13:30:55（Asia/Shanghai），端口 `/dev/cu.usbserial-EXAMPLE_S3`，版本 `gripper-control-s3-0.9b26.0`。

日志中的目标序列为 1500 → 1300 → 1200 → 1160 → 1150 → 1500；1500 最长连续约 38.3 s，1150 约 10.6 s，满足连续 Hold >5 s 的软件时间线。日志以 `DISARM` 结束，最终 `DISARMED` / `DISABLED_UNMEASURED`。**该日志没有记录 1400 μs，也没有记录 STOP 命令；日志只证明命令/ACK/状态时间线，不证明机械位置。** 机械开合 PASS 来自用户观察，不是 Agent 观察或日志推断。

## 6. 当前主控制器与回退方案

- **主控制器：ESP32-S3**（YD-ESP32-23 2022-V1.3 / S3-N16R8），GPIO4、50 Hz、14-bit LEDC，固件 `gripper-control-s3-0.9b26.0`，串口 `/dev/cu.usbserial-EXAMPLE_S3`。
- **回退控制器：旧 ESP32**（NodeMCU ESP-32S V1.1），GPIO23、50 Hz、16-bit，稳定固件 `gripper-control-bench-0.9b24.0`。旧 BIN `bd02b1d2...`、旧配置、旧构建产物与历史日志全部保留，未覆盖、未重新上传。
- S3 已成为后续开发主控制器；旧 ESP32 仅在 S3 出现回归或需要对照时作为回退，不主动改写。

## 7. 验收边界与后续

- `precise_position_error`、`long_term_stability`、实际 PWM 波形/毛刺、堵转/温升与长期重复性仍为 UNKNOWN。
- 最新日志未覆盖 STOP；STOP/DISARM/FAULT 的设备端语义仍以固件和离线测试为准，不能把本次日志当作 STOP 实机验收。
- 不因本次验收而扩大 500–2500 μs 为机械安全行程，也不把 15 kg·cm 标称值当作连续安全夹持力。

## 8. 4×4 触觉接入待确认项（仅清单，未开发）

1. **接口类型**：16 通道是 16 路 ADC、行列扫描、还是外部 ADC/多路复用器；采样率、分辨率、时钟与数据格式 UNKNOWN。
2. **GPIO/ADC 映射**：必须先确认 C 组传感器引脚图。GPIO4 已被舵机 PWM 占用，禁止复用；USB/UART、Flash/PSRAM、strapping 引脚需按 S3 模组与 YD-ESP32-23 原理图核对，当前无原理图，不能猜。
3. **ADC 可用性**：若使用 S3 内部 ADC，需确认 ADC1/ADC2 与 Wi-Fi 的互斥关系、可用通道和校准；当前未确定是否启用 Wi-Fi。
4. **串口/USB 资源**：控制台走 COM USB（FT232R）；传感器若也走 UART，需确认独立 UART 引脚、波特率、缓冲与心跳/命令带宽，不能与现有 JSONL 控制链路混用。
5. **电源与电平**：传感器供电电压/电流、S3 3V3 稳压余量、是否需要独立电源、输出是否超过 3.3 V、共地与电平转换均 UNKNOWN；未确认前不得接线。
6. **机械/电气布置**：16 通道走线、屏蔽、连接器、抗干扰和与舵机 PWM/电源的耦合未验证。
7. **协议与安全联动**：`SENSOR_CONTRACT.md` 的 16 通道 row-major 仍是约定，C 组是否实际提供 16 通道未联调；触觉阈值、超时、STOP/释放策略未定义。

本轮未进行任何触觉传感器接线、采样或固件开发。
