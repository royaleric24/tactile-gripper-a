# Stage H1 真实硬件验证报告（2026-11-13）

## 0. 结论先行

| 项目 | 结果 | 证据/说明 |
|---|---|---|
| 固件代码完成（3×ADS1220、12 通道、协议、故障隔离） | **PASSED（编译）** | `evidence/sensor/build_sensor.json` |
| 固件编译（旧 ESP32 / `esp32:esp32:nodemcu-32s`） | **PASSED** | 301,504 B application，SHA-256 `ee558ccb…` |
| Python 协议/统计/记录/传输/CLI 自动测试 | **PASSED** | 36 tests，35 pass，1 skipped（sandbox 无 pty） |
| 主机 ADS1220 位操作仿真测试 | **PASSED（非实机）** | `evidence/sensor/host_test/test_ads1220.log` |
| 固件 SAMPLE JSON 精确构建测试 | **PASSED（非实机）** | `evidence/sensor/host_test/frame_builder.json` |
| 三颗 ADS1220 实机通信 | **NOT_TESTED** | Mac 未枚举到任何 USB 串口；用户确认板子不在本机 |
| 12 路真实 ADC 采样 | **NOT_TESTED** | 同上，未读取任何真实 ADC 帧 |
| 60 秒连续实机采集 | **NOT_TESTED** | 未执行 |
| 实机帧率/丢帧/超时/饱和 | **NOT_TESTED** | 未执行 |
| 人工按压/保持/释放响应 | **NOT_TESTED** | 未执行 |

**没有把编译、寄存器仿真或协议测试写成“真实采集成功”。** 由于目标旧 ESP32 当前无法物理连接到运行本会话的 Mac，本报告只报告代码、编译、离线测试和待执行的实机步骤。

## 1. 硬件访问尝试记录

- 2026-11-13 15:26（Asia/Shanghai）`ls /dev/cu.*` 仅有：
  - `/dev/cu.Bluetooth-Incoming-Port`
  - `/dev/cu.debug-console`
- `.venv/bin/python -m tools.tactile_acq list` 同样只列出上述两个非 USB 端口；没有 `/dev/cu.usbserial-*`。
- `ioreg -r -c IOSerialBSDClient` 只显示 debug-console 和 Bluetooth。
- 用户随后确认：**板子不在本机，无法物理连接**。
- 因此没有打开串口、没有运行 esptool、没有读取/擦写 Flash、没有烧录旧 ESP32，也没有接触 ESP32-S3。

这意味着：

- 不能确认三颗 ADS1220 的实际通信。
- 不能确认 12 路真实原始值、符号扩展、参考切换、饱和、固定通道。
- 不能给出真实帧率、丢帧率、超时次数。
- 不能声称人工按压响应。

## 2. 已完成并验证的部分（离线）

### 2.1 固件

- 位置：`firmware/sensor/`
- 版本：`tactile-sense-0.1.0`
- 目标：旧 ESP32 only，FQBN `esp32:esp32:nodemcu-32s`，Arduino-ESP32 3.3.2
- 应用大小：301,504 B（22% of 1,310,720 B）
- 静态 RAM：24,440 B（7%），剩余 303,240 B
- 构建元数据：`evidence/sensor/build_sensor.json`
- 构建日志：`evidence/sensor/build_sensor.txt`
- BIN SHA-256：`ee558ccb2aaa3017060b062f792ffb67a74185ebe6a2e1110513c45b9a2829ea`

实现内容：

- 三颗 ADS1220 独立 CS/MISO，共享 SCLK/MOSI 的 **bit-bang SPI Mode 1**。
- `RESET`、`RREG`、`WREG`、`START/SYNC`、`RDATA` 指令。
- 四配置寄存器写入/读回；复位默认值读取；两组不同配置写读回，拒绝全 0x00/0xFF 固定响应。
- MUX 1000..1011（AIN0..3 vs AVSS），Gain 1，PGA bypass，Normal mode，Single-shot，330 SPS。
- 每次 MUX 切换后重新 START，等待 4500 µs 再 RDATA；官方 330 SPS 单次转换约 3.067 ms + 振荡器唤醒 ≤50 µs，留足裕量。
- 三颗 ADC 在每个 MUX 步骤同时 START/等待/读取；四个步骤串行。
- 24-bit 二进制补码符号扩展到 int32。
- 单颗 ADC 失败时该 ADC 4 路输出 null/valid=false；其他 ADC 继续；每 500 ms 重试。
- 运行中每 256 帧校验配置，发现 `CONFIG_LOST` 重新初始化；设备超过 2 s 没有成功读取数据时标记 `DATA_TIMEOUT` 并重新初始化。
- 通道 flags：饱和、near-rail、单端负值、STUCK_EXTREME、NO_DATA。
- `reference_mode` 支持内部 2.048 V 与 AVDD–AVSS；`SET_REF` 写读回验证，失败回滚。
- DIAG：三颗寄存器读取、两组配置写读回、内部输入短接 offset、AVDD/4 监测、内部温度、12 路读取。
- 启动时先把 GPIO5 输出寄存器置高再使能输出，所有 CS 保持高。

### 2.2 协议与 Mac 工具

- 协议：`docs/hardware/TACTILE_ADC_PROTOCOL.md`
- 硬件说明：`docs/hardware/TACTILE_ADC_HARDWARE.md`
- 采集工具：`tools/tactile_acq/`
- 软件组解析示例：`tools/tactile_acq/software_parser_example.py`
- 工具说明：`tools/tactile_acq/README.md`

固件 SAMPLE 已通过真实构建代码的 host 输出 + 严格 Python 解析器验证，字段与 `docs/hardware/TACTILE_ADC_PROTOCOL.md` 示例一致：

- `protocol_version`、`device_id`、`boot_id`、`frame_seq`、`timestamp_us`、`mcu_time_us`
- `raw_adc`/`channels` 12 个有符号值或 null
- `valid`/`valid_mask` 12 个布尔
- `sample_timestamp_us` 12 个设备时间戳或 null
- `channel_flags`、`reference_mode`、`effective_frame_rate_hz`
- `adc_status` 三颗 ADC 的 state/code/errors/last_error
- 兼容软件组 `parse_sample` 的 `channels`、`valid_mask`、`channel_ids`

### 2.3 自动测试结果

| 测试 | 结果 | 日志 |
|---|---|---|
| Python 协议/统计/记录/传输/CLI | 36 tests，`OK (skipped=1)` | `evidence/sensor/offline_checks/python_unittest.log` |
| 固件编译 | PASS | `evidence/sensor/offline_checks/firmware_build.log` |
| 主机 ADS1220 驱动仿真 | 全部 PASS（probe、寄存器、符号扩展、AVDD、温度、短接、卡死 MISO） | `evidence/sensor/host_test/test_ads1220.log` |
| SAMPLE JSON 精确构建 | PASS | `evidence/sensor/host_test/frame_builder.json` |
| 总离线检查 | PASS | `evidence/sensor/offline_checks/summary.json` |

跳过的一项：pseudo-terminal 测试因当前 sandbox 不允许 `openpty`；传输层另用 in-memory fake serial 测试覆盖了 identify/STREAM/SAMPLE 接收。

### 2.4 主机仿真验证的具体断言

`test_ads1220` 使用模拟 ADS1220（按 SPI Mode 1 在下降沿采样 DIN、上升沿移出 DOUT）验证：

- `probe`（RESET + 两组配置写读回）对三颗模拟 ADC 均通过；
- 复位默认寄存器为 0；
- 正常配置读回 `81 80 00 00`；
- 内部 2.048 V 参考下 0.1/0.2/0.3/0.4 V 对应 `409600/819200/1228800/1638400`；
- AVDD 3.3 V 参考下 0.1 V 对应 `254200`；
- -0.1 V 输入得到 `-409600`（符号扩展正确）；
- 内部短接 offset 为 0；
- AVDD/4 监测得到 `3379200`（换算 3300 mV）；
- 温度 25 °C 原始值 `819200`（14-bit 左对齐）；
- MISO 卡低/卡高时 `probe` 均失败（不会假通过）；
- JSON writer 溢出检测。

**这些是仿真结果，不是 ADS1220 实机数据。**

## 3. 尚未执行的实机步骤

在旧 ESP32 接到本机后，按以下顺序执行（脚本已准备，不会自动烧 S3）：

```bash
cd /home/example/Developer/research/tactile-gripper-a-hw

# 1) 枚举并识别；要求 firmware_version 以 tactile-sense- 开头
.venv/bin/python -m tools.tactile_acq list
.venv/bin/python -m tools.tactile_acq identify --port /dev/cu.usbserial-XXXX

# 2) 编译（已验证可编译）
.venv/bin/python scripts/build_sensor_firmware.py

# 3) 烧录旧 ESP32：脚本先读 chip/MAC，要求 ESP32-D0WDQ6 + MAC 02:00:00:00:00:01，
#    然后全 4 MB Flash 备份到 evidence/sensor/backups/，最后只写应用分区 0x10000 并 verify。
.venv/bin/python scripts/flash_sensor_firmware.py \
  --port /dev/cu.usbserial-XXXX --authorize-write

# 4) 三颗寄存器/两组配置/内部自检/12 路读取
.venv/bin/python -m tools.tactile_acq diag --port /dev/cu.usbserial-XXXX

# 5) 60 秒真实采集（终端 12 路监视）
.venv/bin/python -m tools.tactile_acq run \
  --port /dev/cu.usbserial-XXXX --duration 60 --monitor text

# 6) 一键完整验证并生成 Markdown/JSON 报告
.venv/bin/python scripts/run_h1_validation.py --port /dev/cu.usbserial-XXXX --duration 60

# 7) 复核统计
.venv/bin/python -m tools.tactile_acq analyze data/real/tactile/<run_dir>
```

实机采集后需要记录：

- 三颗 ADC 的 `state`、两次 pattern 写读回、offset、AVDD mV、温度；
- 12 路真实 min/max/mean/std；
- `device_frame_rate_hz`、`host_frame_rate_hz`、`mean_effective_frame_rate_hz`；
- `missing`、`drop_rate`、`host_timeouts`；
- 饱和/固定/无效通道；
- 人工按压/保持/释放的观察（脚本只能标 NOT_TESTED，需现场记录）。

## 4. 数据保存位置

- 真实运行数据将保存到 `data/real/tactile/<UTC 时间>_<端口>/`：
  - `raw_frames.jsonl`（设备原始行）
  - `samples.csv`（含 12 通道、valid、flags、设备/主机时间）
  - `events.jsonl`、`meta.json`、`run.json`
- 本次没有真实运行，因此没有真实数据文件；不要把这些离线证据当成实机数据。
- 离线证据：`evidence/sensor/`（`data/`、`logs/`、`evidence/` 均在 `.gitignore` 中，未提交大数据）。
- 烧录前完整 Flash 备份将写入 `evidence/sensor/backups/`，不覆盖历史 0.9b24/0.9b26 资产。

## 5. 未解决的真实问题/风险

1. **硬件不可达**：当前 Mac 没有枚举到旧 ESP32 的 USB 串口，无法完成任何实机项。
2. **外部传感器未知**：12 路是否已接传感器、传感器类型、供电、共地、输入范围均未在本次验证。
3. **矩阵映射 UNKNOWN**：12 路 ADC 到 6×6/36 单元的对应关系未验证；协议中 `matrix_rows/matrix_cols` 为 null。
4. **未标定**：原始 counts 不能换算为电阻、压力、力、摩擦力或夹持力。
5. **AVDD 参考未实测**：AVDD–AVSS 参考的绝对精度/噪声取决于板级电源；仅提供切换能力。
6. **实机时序未验证**：bit-bang 500 kHz、4500 µs 等待、921600 串口在真实 CP210x/线缆上的误码与帧率未测。
7. **人工按压未做**：没有真实接触响应证据。
8. **Git 提交**：改动位于 `feat/hardware-acquisition` worktree；本次尝试提交时 Git 元数据目录在当前 sandbox 之外，写入被拒绝，因此没有创建提交（也没有 push/merge）。源代码、配置、文档和脚本均已在工作区，可直接审查后提交。

## 6. 判定

- 代码、编译、协议构建、离线测试：**PASSED**
- 实机 ADS1220 通信、12 路采样、60 秒运行、帧率/丢帧/饱和、人工按压：**NOT_TESTED**
- 没有 FAILED 的实机项被隐藏；所有未执行项均明确标为 NOT_TESTED。
