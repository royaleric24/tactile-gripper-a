# Stage H1 真实硬件验证报告（2026-11-13）

## 0. 结论先行

| 项目 | 结果 | 证据/说明 |
|---|---|---|
| 固件代码完成（3×ADS1220、12 通道、协议、故障隔离） | **PASSED（编译）** | `evidence/sensor/build_sensor.json` |
| 固件编译（旧 ESP32 / `esp32:esp32:nodemcu-32s`） | **PASSED** | 305,504 B application，SHA-256 `b24330e9…` |
| Python 协议/统计/记录/传输/CLI 自动测试 | **PASSED** | 新增诊断/解析测试 32 项 + tactile_acq 36 项（1 skipped） |
| 主机 ADS1220 位操作仿真测试 | **PASSED（非实机）** | `evidence/sensor/host_test/test_ads1220.log` |
| 固件 SAMPLE JSON 精确构建测试 | **PASSED（非实机）** | `evidence/sensor/host_test/frame_builder.json` |
| ADC1/2/3 MISO 实际映射 | **PASSED** | ADC1=GPIO35、ADC2=GPIO26、ADC3=GPIO34；见 §10 |
| 三颗 ADS1220 实机通信 | **PASSED** | 2026-11-13 20:57 DIAG：三颗 `OK`，寄存器 A/B 写读回、内部 offset/AVDD/温度全部通过；见 §10 |
| ADC1 GPIO 静态输出 A/B/C | **PASS（仅 ESP32 侧）** | GPIO21/18/23 回读与 A/B/C 一致，ADC2/3 CS 保持 HIGH；模块焊盘待用户测量；见 §9 |
| 12 路真实 ADC 采样 | **PASSED（输入悬空）** | 60 s 采集中每路 1573/1579 有效；未接压敏布，饱和/近轨不代表压力；见 §10 |
| 60 秒连续实机采集 | **PASSED** | 1579 帧 / 59.992 s，0 丢帧，0 malformed；见 §10 |
| 实机帧率/丢帧/超时/饱和 | **PASSED** | 设备帧率 26.302 Hz、0 丢帧、0 host timeout；悬空输入有饱和/近轨；见 §10 |
| 人工按压/保持/释放响应 | **NOT_TESTED** | 未执行 |

**最终状态（2026-11-13 20:57）：三颗 ADS1220 通信、内部转换、12 路采集和 60 秒真实采集均 PASSED；压力响应仍 NOT_TESTED，因为 12 个鳄鱼夹未接压敏布。** 早期 §7–§9 记录了修复过程：MISO 映射错误 `{34,35,26}` 导致全失败，实际映射为 `{35,26,34}`；ADC1 的 MISO 导线在 GPIO35。修正映射后又发现 DIAG 的 `patterns_differ` 判定缺陷（任一字节相同即判失败），修复后 DIAG 通过。详见 §10。§1–§6 保留首次（15:26）板子不在本机时的历史记录，不代表当前状态。

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

## 7. 2026-11-13 18:38–19:00 实机尝试（当前状态）

旧 ESP32 已重新连接本机（`/dev/cu.usbserial-EXAMPLE_ESP32`，CP2102 `10C4:EA60`）。本次只操作该板，未接触 ESP32-S3，未修改 `firmware/gripper_control/`。

### 7.1 身份与烧录

| 步骤 | 结果 | 证据 |
|---|---|---|
| esptool v5.1.0 `chip-id` | **PASS** | `ESP32-D0WDQ6` revision v1.1，MAC `02:00:00:00:00:01` |
| 全片 4 MB 备份 | **PASS** | `evidence/sensor/backups/old_esp32_fullflash_20261113T105432Z_2cbcbba3d220.bin`，SHA-256 `4ae8eba364e99374…`（完整值见同名 .json） |
| 应用分区写入 `0x10000` | **PASS** | 301,504 B，压缩后 168,045 B；esptool 报告 `Hash of data verified` |
| `verify-flash 0x10000` | **PASS** | `Verification successful (digest matched)` |
| 烧录元数据 | **PASS** | `evidence/sensor/flash_20261113T105432Z.json` |

- 应用 SHA-256：`aa95dd103abc4e3aeb2fdb0cf8fe18213e4e26524e21725d7e30ed3dae9c8144`。
- 第一次 460800 读取备份在 1.06 MB 处出现 `Invalid head of packet (0x75)`，脚本按设计拒绝写入；改用 230400 后完整通过。**没有在备份失败后写入。**
- 烧录脚本已修复 esptool v5.1.0 解析：支持 `Chip type: ... (revision v1.1)`、ANSI/CSI 控制序列、大小写/空格/CR，并严格校验 family、model 和 MAC；错误 MAC、ESP32-S3、其他 ESP32 型号均被拒绝。回归测试 `tests/test_flash_sensor_firmware.py` 18 项 PASS。

### 7.2 固件软件问题（已在实机上修复并复测）

1. `handleCommand()` 用 `command.has_id` 决定是否回传 `request_id`，而 PING/STATUS/DIAG 没有 `id`，导致主机永远匹配不到响应。改为按 `request_id[0]` 判断后，`identify` 与 `diag` 均能收到响应。
2. `DIAG` 响应超过 2048 B 输出缓冲，返回 `FRAME_BUFFER_OVERFLOW`。将 `config/sensor_esp32.json` 的 `max_line_bytes` 提高到 8192 并重新生成/编译/烧录后，`diag` 能完整返回。

### 7.3 三颗 ADS1220 DIAG（FAILED）

命令：`.venv/bin/python -m tools.tactile_acq diag --port /dev/cu.usbserial-EXAMPLE_ESP32 --diag-timeout 30`

结果：`overall: FAILED`，证据 `evidence/sensor/diagnostics_20261113T105828Z.json`。

| ADC | 状态 | 寄存器读回 | 两组配置写读回 | 内部 offset / AVDD / 温度 | AIN0..3 |
|---|---|---|---|---|---|
| ADC1 | `NO_RESPONSE` | `[0,0,0,0]` | FAIL | FAIL（0 / 0 mV / 0.00 °C） | 全部 null |
| ADC2 | `NO_RESPONSE` | `[0,0,0,0]` | FAIL | FAIL（0 / 0 mV / 0.00 °C） | 全部 null |
| ADC3 | `NO_RESPONSE` | `[0,0,0,0]` | FAIL | FAIL（0 / 0 mV / 0.00 °C） | 全部 null |

说明：`ADCn register read = PASSED` 仅表示 SPI 事务完成并读到复位默认值 `0x00`，**不表示器件已响应**；决定性证据是写入 `81 80 00 00` / `91 80 80 00` 后读回仍为全 `0x00`，以及 12 路转换无数据。三颗 ADC 同时出现相同症状，指向共用 SCLK/MOSI/GND/供电或三块模块均未上电/未真正接入，而非单颗器件故障。

### 7.4 12 通道真实采集（FAILED）

命令：`.venv/bin/python -m tools.tactile_acq run --port /dev/cu.usbserial-EXAMPLE_ESP32 --duration 5 --monitor none`

- 数据目录：`data/real/tactile/20261113T105939Z__dev_cu.usbserial-EXAMPLE_ESP32/`
- 150 帧 / 4.972 s；设备帧率 **29.936 Hz**，主机 29.97 Hz；`missing=0`、`duplicates=0`、`out_of_order=0`、`drop_rate=0.0`、host timeouts 0、malformed lines 0。
- 12 路 `valid=0/12`，`raw_adc`/`channels` 全部为 `null`，`channel_flags=0x20 (NO_DATA)`。
- 60 秒采集**未执行**：条件要求 DIAG 通过，实际未通过；没有用 5 秒数据冒充 60 秒结果。

### 7.5 当前阻塞与下一步（需要现场硬件检查）

1. 用万用表确认每颗 ADS1220 的 `AVDD`、`DVDD` 对 `DGND` 均为 3.3 V，且与 ESP32 共地。
2. 确认三块模块实际接在旧 ESP32 的 SCLK=18、MOSI=23、MISO=34/35/26、CS=21/22/5，而不是接在 ESP32-S3 或其他引脚。
3. 逐颗检查 `CS` 在空闲时为 3.3 V、选中时接近 0 V；检查 `DOUT` 是否有推挽输出（空闲/选中时不应恒为 0 V）。
4. 若以上均正常，再考虑降低 bit-bang SCLK（当前半周期 1 µs）或用示波器/逻辑分析仪抓 CS/SCLK/MOSI/DOUT；这属于硬件接线/测量，需用户现场执行，助手不自行改线。

**结论：烧录与命令通道 PASS；三颗 ADS1220 实机通信 FAILED；12 路原始数据不可得；60 秒实机采集未执行。**

## 8. 2026-11-13 19:00–19:30 低速 SPI 原始字节定位（历史）

> 本节是映射修正前的定位记录；最终根因是 MISO 映射错误，结论已被 §10 取代。

为排除 CPOL/CPHA、采样边沿和时钟速度，新增固件命令 `DIAG_SPI`：停止主采集循环，以 **20 kHz**（半周期 25 µs）逐颗选中 ADC，读复位默认寄存器、写 `81 80 00 00` 与 `91 80 80 00`、逐字节读回，并分别用 **上升沿后采样** 和 **下降沿后采样** 各跑一遍；响应包含 CS/MISO GPIO、空闲 MISO 电平和全部原始字节。主机端 `scripts/diag_ads1220_spi.py` 独立重新比对字节，不依赖固件自报的 `pass`。

- 固件：应用 303,120 B，SHA-256 `d78ec1ce991f2ba07be5d7c2feea571789bc8cc324aff9c4114f8057c690b1a3`
- 烧录：`evidence/sensor/flash_20261113T112302Z.json`，`verify-flash` digest matched；备份 `old_esp32_fullflash_20261113T112302Z_2cbcbba3d220.bin`，SHA-256 `465cef6389195a7f7940b943d6a13e4ef070ac347738e480357791c0d84b5d52`
- 证据：`evidence/sensor/spi_diag_20261113T112652Z.json`、`evidence/sensor/spi_diag_20261113T112729Z.json`

### 8.1 两次运行的实际字节（节选）

| 运行 | ADC | CS/MISO | 边沿 | reset 读回 | 写 A 后读回 | 写 B 后读回 |
|---|---|---|---|---|---|---|
| 1 | 1 | 21/34 | 上升 | `03 FF FF FF` | `FF FF FF FF` | `00 00 00 00` |
| 1 | 1 | 21/34 | 下降 | `00 00 00 00` | `FF FF FF FF` | `F8 00 00 00` |
| 1 | 2 | 22/35 | 上升 | `00 00 00 00` | `00 00 FF FF` | `FF FF FF FF` |
| 1 | 2 | 22/35 | 下降 | `00 00 00 00` | `00 00 00 00` | `FF FF FF FF` |
| 1 | 3 | 5/26 | 上升 | `00 00 00 00` | `00 00 00 00` | `00 00 1F FF` |
| 1 | 3 | 5/26 | 下降 | `FF FF FF FF` | `C0 00 00 00` | `00 00 00 00` |
| 2 | 1 | 21/34 | 上升 | `00 00 00 00` | `FF FF FF FF` | `FF FF FF FF` |
| 2 | 1 | 21/34 | 下降 | `00 00 00 00` | `00 00 00 3F` | `FF FF FF FF` |
| 2 | 2 | 22/35 | 下降 | `FF FF FF FF` | `00 00 00 00` | `00 00 00 00` |
| 2 | 3 | 5/26 | 下降 | `00 00 00 07` | `FF FF FF FF` | `00 00 00 00` |

- 两次运行、两种边沿的原始字节**不可重复**；空闲 MISO 电平也在 `0/1` 之间变化。
- 三颗 ADC 均未出现 `81 80 00 00` / `91 80 80 00` 的正确读回，所有 `pass=false`。
- `reset_ok=true` 只表示 CS/SCLK 事务执行完毕并读到了字节，**不表示 ADC 已响应**。

### 8.2 故障定位

20 kHz 远低于 ADS1220 4 MHz 上限，且两种 MISO 采样边沿都失败；因此可以基本排除：

- CPOL/CPHA 或采样沿错误（两种边沿均失败，且字节随运行变化而不是固定移一位）；
- SCLK 速度过高（已降到 20 kHz）；
- 固件寄存器命令格式/字节数错误（RESET=`0x06`、WREG=`0x43`、RREG=`0x23`、START=`0x08`、RDATA=`0x10` 均按 Rev. D）；
- CS 在事务中途被拉高（`writeRegisters`/`readRegisters` 各自在整个命令+数据期间保持 CS 低）。

**结论：MISO/DOUT 没有被 ADS1220 确定驱动，读到的是悬空/噪声电平。** 最可能的物理原因是：模块未上电、DVDD 电压不对、CLK 未按内部振荡器模式接 DGND、RESET/PWDN 被拉低或悬空、CS/DOUT 断线或接错（含 DIN/DOUT 互换、CS/MISO 配对错误）。

### 8.3 当前软件改动

| 文件 | 改动 |
|---|---|
| `firmware/sensor/ads1220.h/.cpp` | 运行时可设半周期与 MISO 采样边沿；默认仍为配置半周期、上升沿后采样 |
| `firmware/sensor/sensor.ino` | 新增 `DIAG_SPI`，停止采集后逐颗低速探测并输出原始字节 |
| `config/sensor_esp32.json` | 新增 `ads1220.diag_half_period_us=25` |
| `scripts/generate_sensor_config.py` | 生成 `SENSOR_DIAG_SPI_HALF_PERIOD_US` |
| `scripts/diag_ads1220_spi.py` | 主机端发送 `DIAG_SPI`、独立比对原始字节并保存 JSON |
| `tests/test_spi_diag.py` | 主机端原始字节比对/解析回归测试 |

> 注：本次为诊断固件，固件版本字符串仍为 `tactile-sense-0.1.0`，实际二进制以 SHA-256 `d78ec1ce…` 区分。

### 8.4 12 路采集现状

当前固件 5 s 真实采集（`data/real/tactile/20261113T112750Z__dev_cu.usbserial-EXAMPLE_ESP32/`）：155 帧 / 4.964 s，设备帧率 **29.946 Hz**，丢帧 0、malformed 0、host timeout 0；**12 路有效数 0**，三颗 ADC 全程 `NO_RESPONSE`。

标准 `diag` 在当前固件上仍为 `overall: FAILED`（`evidence/sensor/diagnostics_20261113T112851Z.json`）：三颗 ADC 的两组配置写读回均失败（写入 `81 80 00 00` / `91 80 80 00`，读回全 `00 00 00 00`），内部 offset 返回 0、AVDD 0 mV、温度 0.00 °C。由于寄存器写入未生效，**这些内部转换数值不是有效的 ADC 测量**，只能说明转换路径没有拿到真实数据。60 s 采集未执行。

### 8.5 一次性的现场测量清单（按优先级）

请在 ADS1220 模块引脚处测量，不要只测 ESP32 排针：

1. **DVDD–DGND**：每颗均为 3.3 V；**AVDD–AGND** 同样为 3.3 V。若为 0 V，先查模块供电/跳线。
2. **共地**：ESP32 GND 与每颗模块 DGND/AGND 连续性 < 1 Ω。
3. **CLK–DGND**：内部振荡器模式要求 CLK 接 DGND；若悬空或接 3.3 V，内部时钟不工作，必须接 DGND。
4. **RESET/PWDN（如模块有）**：应为高电平（DVDD），不能悬空或为低。
5. **CS 空闲电平**：每颗 CS 对 DGND 应为 3.3 V；确认实际接到 GPIO21/22/5，而不是 S3 或其他引脚。
6. **断线/接错**：断电测 ESP32 GPIO18→模块 SCLK、GPIO23→DIN、GPIO34/35/26→DOUT、GPIO21/22/5→CS 的连续性；确认 DIN/DOUT 未互换、三组 CS/MISO 未交叉。
7. 若以上都正常：用示波器/逻辑分析仪在 `DIAG_SPI` 期间抓 CS、SCLK、DIN、DOUT；正常应看到 CS 拉低、SCLK 20 kHz、DOUT 在 RREG 后被驱动。

在完成上述测量前，不再继续改 SPI 代码或重复烧录；当前证据指向硬件供电/时钟/接线，而不是软件时序。

## 9. 2026-11-13 19:45–19:52 ADC1 GPIO 静态电平诊断（历史）

> 本节是映射修正前的 GPIO 分层记录；最终映射与 PASS 见 §10。

用户已用万用表确认一颗 ADC 的电源、共地、CLK 和 CS 静态电平正常。为区分“ESP32 GPIO 输出”“物理线路”和“ADC1 协议”三层问题，新增 `GPIO_DIAG` 命令：停止采集，ADC2/ADC3 的 CS 保持 HIGH，仅对 ADC1 依次保持以下状态各约 5 秒，并通过串口打印状态名、期望电平、ESP32 回读电平和时间戳：

| 状态 | GPIO21 / CS1 | GPIO18 / SCLK | GPIO23 / MOSI | ADC1 模块焊盘预期 |
|---|---|---|---|---|
| A | HIGH | LOW | LOW | CS1 ≈ 3.3 V，SCLK ≈ 0 V，MOSI ≈ 0 V |
| B | LOW | LOW | LOW | CS1 ≈ 0 V，SCLK ≈ 0 V，MOSI ≈ 0 V |
| C | LOW | HIGH | HIGH | CS1 ≈ 0 V，SCLK ≈ 3.3 V，MOSI ≈ 3.3 V |

状态结束后恢复 CS1/CS2/CS3=HIGH、SCLK=LOW，并对 ADC1 单独执行一次 20 kHz 最小寄存器序列（RESET → 写 A → 读 A → 写 B → 读 B），保存真实原始字节。

### 9.1 本次实机运行结果

命令（1 个循环用于验证）：

```bash
.venv/bin/python scripts/diag_ads1220_gpio.py --port /dev/cu.usbserial-EXAMPLE_ESP32 --cycles 1
```

串口实际输出：

```text
GPIO_DIAG state=A t_ms=17761 cs1=HIGH sclk=LOW mosi=LOW hold_ms=5000 esp_read cs1=HIGH sclk=LOW mosi=LOW cs2=HIGH cs3=HIGH
GPIO_DIAG state=B t_ms=22772 cs1=LOW sclk=LOW mosi=LOW hold_ms=5000 esp_read cs1=LOW sclk=LOW mosi=LOW cs2=HIGH cs3=HIGH
GPIO_DIAG state=C t_ms=27783 cs1=LOW sclk=HIGH mosi=HIGH hold_ms=5000 esp_read cs1=LOW sclk=HIGH mosi=HIGH cs2=HIGH cs3=HIGH
```

- ESP32 侧 GPIO 输出/回读与 A/B/C 完全一致，ADC2/ADC3 CS 全程 HIGH；GPIO 配置和输出寄存器层面 **PASS**。
- 证据：`evidence/sensor/gpio_diag_20261113T115029Z.json`、`.txt`。
- 固件：304,608 B，SHA-256 `50b297b6eab01c414bb4edbe147a72865970ecb94f15282a4b19fad86154252e`；烧录元数据 `evidence/sensor/flash_20261113T114620Z.json`，备份 `old_esp32_fullflash_20261113T114620Z_2cbcbba3d220.bin`，SHA-256 `37722cac343787d45c618645d1faa23e9a2e90d4612c6561215e6854b8760e17`。

### 9.2 ADC1 最小寄存器写读回（真实字节）

| 步骤 | 发送 | 读回 |
|---|---|---|
| RESET | `06` | `[00 00 00 00]` |
| WREG A | `43` + `[81 80 00 00]` | — |
| RREG A | `23` + 4 字节 | `[00 00 00 00]`（不匹配） |
| WREG B | `43` + `[91 80 80 00]` | — |
| RREG B | `23` + 4 字节 | `[FF FF FF FF]`（不匹配） |

- 结果：`pass=false`，失败点在“写配置后读回”。
- **重要**：RESET 后读回全 `00` 是 ADS1220 复位默认值，单独看是正常的，不能作为失败证据；决定性证据是写入 `81 80 00 00` / `91 80 80 00` 后仍读不到写入值。
- B 次读回全 `FF` 与此前 A 次全 `00` 不一致，仍提示 DOUT 侧没有稳定返回数据，但不能据此单独证明 DOUT 已悬空；需要结合模块焊盘的动态测量和 DOUT 检查。

### 9.3 供用户测量用的运行命令

建议测量时使用多循环（每个 A/B/C 5 秒，6 个循环共 90 秒）：

```bash
.venv/bin/python scripts/diag_ads1220_gpio.py --port /dev/cu.usbserial-EXAMPLE_ESP32 --cycles 6
```

脚本会实时打印每个状态的名称和时间戳。请在 **ADC1 模块焊盘**（不是 ESP32 排针）测量以下三个点对模块 GND 的电压：

1. **CS1 焊盘**：A 应为 3.3 V；B、C 应约为 0 V。
2. **SCLK 焊盘**：A、B 应为 0 V；C 应为 3.3 V。
3. **MOSI/DIN 焊盘**：A、B 应为 0 V；C 应为 3.3 V。

### 9.4 结果判读

| 观察 | 结论/下一步 |
|---|---|
| ESP32 回读与 A/B/C 一致，模块焊盘也一致 | GPIO 输出和三条线均正常；ADC1 最小写读回 FAIL 指向 ADC1 的 DOUT/MISO、CLK/RESET 或器件本身，下一步查 DOUT 焊盘到 GPIO34 的连续性与活动 |
| ESP32 回读一致，但某个模块焊盘不变 | 该条线断线、短路或接错；CS1 不动查 GPIO21→CS，SCLK 不动查 GPIO18→SCLK，MOSI 不动查 GPIO23→DIN |
| 模块焊盘在 B/C 仍为 3.3 V（CS1） | CS1 线对 3.3 V 短路或未接到 ADC1 CS |
| 模块焊盘在 C 仍为 0 V（SCLK/MOSI） | 对应线断线或接错，先修线，不继续判 ADC 协议 |
| 三焊盘均正确但最小测试仍 FAIL | 检查 ADC1 DOUT 到 GPIO34 的连续性/波形、DIN 与 DOUT 是否互换、CLK 是否在 ADC 引脚处为 0 V、RESET/PWDN 是否为高；这些都正常时才考虑 ADC1 器件/协议问题 |

在拿到模块焊盘测量结果前，不把当前 ADC1 最小测试的 FAIL 单独解释为“ADC1 芯片损坏”。

## 10. 2026-11-13 20:42–20:58 MISO 映射修正与最终实机 PASS

### 10.1 实际 MISO 映射（实测确定）

用户实测 ADC1 的 MISO 导线在 **GPIO35**；ADC2/ADC3 分别接 GPIO34/GPIO26，但对应关系未定。固件新增 `MISO_MAP`：ADC1 只测 GPIO35，ADC2/ADC3 各测 GPIO34 和 GPIO26（不做九种组合），20 kHz，RESET + 两组非零配置写读回。

| ADC | CS | 候选 MISO | RREG A 读回 | RREG B 读回 | 结果 |
|---|---:|---:|---|---|---|
| 1 | 21 | 35 | `81 80 00 00` | `91 80 80 00` | **PASS** |
| 2 | 22 | 34 | `00 00 00 00` | `FF FF FF FF` | FAIL |
| 2 | 22 | 26 | `81 80 00 00` | `91 80 80 00` | **PASS** |
| 3 | 5 | 34 | `81 80 00 00` | `91 80 80 00` | **PASS** |
| 3 | 5 | 26 | `07 FF FF FF` | `00 00 00 00` | FAIL |

**最终映射：ADC1=GPIO35、ADC2=GPIO26、ADC3=GPIO34**，配置 `pins.miso=[35,26,34]`。证据：`evidence/sensor/miso_map_20261113T124627Z.json`。

- 原配置 `[34,35,26]` 把 ADC1 接到 GPIO34、ADC2 接到 GPIO35，三颗全部错位；这是此前全失败的根因。
- 用户实测的 ADC1 MISO=GPIO35 与本次映射结果一致。

### 10.2 第二个软件缺陷：DIAG 的 `patterns_differ`

映射修正后，三颗 ADC 的寄存器 A/B 读回字节已经正确，但 DIAG 仍把 `patA/patB` 判为 FAIL，并跳过内部 offset/AVDD/温度测试。原因是：

```cpp
// 错误：任一字节相同就置 false；两模式第 1 字节都是 0x80
item.patterns_differ = true;
for (r) if (a[r] == b[r]) { patterns_differ = false; break; }
```

已改为“只有四个字节全部相同才表示不 differ”：

```cpp
item.patterns_differ = false;
for (r) if (a[r] != b[r]) { patterns_differ = true; break; }
```

修复后 DIAG 通过。

### 10.3 最终烧录

- 应用：305,504 B，SHA-256 `b24330e9daf740c2fe5c3fe22c5f00ac0f6f0a68a138f6aa514f15cdb62406fe`
- esptool v5.1.0：`ESP32-D0WDQ6` rev v1.1，MAC `02:00:00:00:00:01`；`verify-flash` digest matched
- 元数据：`evidence/sensor/flash_20261113T125331Z.json`
- 备份：`old_esp32_fullflash_20261113T125331Z_2cbcbba3d220.bin`，SHA-256 `f2ed10eb6011a2b0f53012780431ea09b1134cd56a916bad92d5ad93e4be8301`

### 10.4 三颗 ADS1220 最终 DIAG：PASSED

证据：`evidence/sensor/diagnostics_20261113T125728Z.json`。

| ADC | 寄存器读 | 模式 A 写读回 | 模式 B 写读回 | differ | offset_raw | AVDD | 温度 | monitor | AIN0..3 |
|---|---|---|---:|---:|---:|---:|---:|---|---|
| 1 | OK | `81 80 00 00` | `91 80 80 00` | YES | 502 | 3386 mV | 25.00 °C | OK | 5252793, 5422118, 1012720, 2456433 |
| 2 | OK | `81 80 00 00` | `91 80 80 00` | YES | 428 | 3390 mV | 24.15 °C | OK | 5623250, 3793730, 318406, 3471079 |
| 3 | OK | `81 80 00 00` | `91 80 80 00` | YES | 383 | 3394 mV | 29.00 °C | OK | 6412623, 4101788, 1808785, 2978383 |

三颗均通过：寄存器读、两组非零配置写读回、内部短接 offset、AVDD/4 监测、内部温度、AIN0..AIN3 转换。内部温度约 24–29 °C，合理且可重复。

### 10.5 60 秒真实采集

命令：`.venv/bin/python -m tools.tactile_acq run --port /dev/cu.usbserial-EXAMPLE_ESP32 --duration 60 --monitor none`

数据目录：`data/real/tactile/20261113T125742Z__dev_cu.usbserial-EXAMPLE_ESP32/`

| 指标 | 实测 |
|---|---:|
| 帧数 / 时长 | 1579 帧 / 59.992 s |
| 设备帧率 | **26.302 Hz** |
| 主机帧率 | 26.303 Hz |
| 固件窗口均值 | 26.292 Hz |
| 丢帧 / 重复 / 乱序 | 0 / 0 / 0 |
| host timeout / malformed | 0 / 0 |
| 12 路有效比 | 0.9962（每路 1573/1579） |
| ADC 状态 | ADC1/2/3 全程 OK（启动前 6 帧为 CONFIG_ERROR） |

每通道统计（原始 counts，未标定；输入悬空）：

| CH | 通道 | 有效 | 最小 | 最大 | 均值 | 饱和高 |
|---:|---|---:|---:|---:|---:|---:|
| 0 | ADC1_AIN0 | 1573 | 275560 | 8388607 | 3694683.0 | 154 |
| 1 | ADC1_AIN1 | 1573 | 201029 | 8388607 | 3762087.9 | 172 |
| 2 | ADC1_AIN2 | 1573 | 974141 | 7702535 | 3164770.5 | 0 |
| 3 | ADC1_AIN3 | 1573 | 715702 | 8316411 | 3437522.4 | 0 |
| 4 | ADC2_AIN0 | 1573 | 421056 | 8388607 | 3492853.3 | 17 |
| 5 | ADC2_AIN1 | 1573 | 830552 | 8004601 | 3092063.9 | 0 |
| 6 | ADC2_AIN2 | 1573 | 218900 | 8388607 | 3664999.0 | 158 |
| 7 | ADC2_AIN3 | 1573 | 89312 | 8388607 | 3799495.1 | 206 |
| 8 | ADC3_AIN0 | 1573 | 168936 | 8388607 | 3769790.9 | 188 |
| 9 | ADC3_AIN1 | 1573 | 789059 | 8232743 | 3332422.7 | 0 |
| 10 | ADC3_AIN2 | 1573 | 1775074 | 4429639 | 2860327.3 | 0 |
| 11 | ADC3_AIN3 | 1573 | 577879 | 8388607 | 3525241.9 | 5 |

- 12 个鳄鱼夹未接压敏布，AIN 输入悬空；上述数值是真实 ADC 转换结果，但**不是压力/接触/摩擦力测量**。
- 悬空输入导致部分通道 SAT_HIGH / NEAR_RAIL，属预期；不能据此判定通道损坏。
- 原始文件：`raw_frames.jsonl`（1579 行）、`samples.csv`（表头 + 1579 行）、`events.jsonl`、`run.json`。
- 人工按压/保持/释放响应：**NOT_TESTED**。

### 10.6 最终判定

- MISO 映射：**CONFIRMED**（35/26/34）
- 三颗 ADS1220 寄存器与内部转换：**PASSED**
- 12 路真实原始数据：**PASSED（每路 1573 个有效值）**
- 60 秒真实采集：**PASSED**，26.302 Hz，0 丢帧
- 压力/接触响应：**NOT_TESTED**（压敏布未接）
- 未操作 ESP32-S3，未修改机械爪控制固件。
