# V2 双 FSR（FSR_ONLY）串口接口说明

- 状态：**IMPLEMENTED_UNVERIFIED**（固件两 profile 均已离线编译；host 模拟测试通过；**尚未接线、未烧录、未做任何真实采样**）
- 面向读者：软件组（解析 / 记录 / 界面）、总负责人、后续接手的硬件同学
- 协议版本：`protocol_version = 1`（在 V1 基础上**只增字段**，不改变已有字段语义）
- 传输：USB 串口 **`921600 8N1`**，UTF-8 JSON Lines，一行一条消息，以 `\n` 结束
- 设备：旧 ESP32（NodeMCU ESP-32S V1.1）+ **4 × ADS1220**，其中 ADC4 专用于两路独立 FSR 分压
- 固件目录：`firmware/sensor_fsr2/`（旧 `firmware/sensor/` 保持冻结，作为 V1 历史版本，不改动）
- 配置：`config/sensor_esp32_fsr2.json`（FSR_ONLY）、`config/sensor_esp32_fsr2_hybrid.json`（HYBRID_6X6_FSR2）

本文件只承诺 **ADS1220 原始计数**与**明确的无效语义**。没有独立标定前，不得把 counts 说成牛顿、压强或滑移概率。

## 1. 为什么是第四颗 ADC

V1 的三颗 ADS1220 承载 6×6 矩阵的行（每颗 4 个单端输入，实际用到 AIN0/AIN1）。FSR 需要**两个互不干扰**的分压节点，若继续挤在矩阵 ADC 上，任何一次矩阵列扫描都会把激励电流灌进 FSR 节点，读数不再代表纯分压。因此 V2 增加第四颗 ADS1220：

| 器件 | CS | MISO | 用途 |
|---|---:|---:|---|
| ADC1 | 21 | 34 | 矩阵行 1–2（AIN0/AIN1） |
| ADC2 | 22 | 35 | 矩阵行 3–4（AIN0/AIN1） |
| ADC3 | 5 | 26 | 矩阵行 5–6（AIN0/AIN1） |
| **ADC4** | **32** | **33** | **FSR_A = AIN0，FSR_B = AIN1** |

四颗共用 `SCLK = 18`、`MOSI = 23`；每颗独立 CS。`GPIO32` 在 V2 中**只作 ADC4 片选**，不再是矩阵列。历史映射 `miso = [35, 26, 34]` 已作废，不得再用来生成 V2 固件（生成器会直接拒绝 3 颗 ADC 的配置）。

FSR 分压：`3V3 ── R_fsr ──┬── AINx`，`AINx ── 10 kΩ ── GND`。两路各自独立 10 kΩ 下拉，两个节点不得互连（互连后两路读数会被平均，且一路短路会带偏另一路）。

采样配置（FSR profile 强制，生成器校验）：单端、`Gain = 1`、PGA bypass、**参考 = `AVDD_AVSS`**、330 SPS。**不得**使用内部 2.048 V 参考：分压点在有压力时接近 3.3 V，内部参考会让读数削顶到满量程，看起来像"一直压到底"。

换算（AVDD 需实测，未标定时只能算名义值）：

```
V_AIN  ≈ counts × AVDD / 2^23          (Gain = 1，AVDD 名义 3.3 V)
R_fsr  ≈ R_ref × (V_exc / V_AIN − 1)   (R_ref = 10 kΩ，V_exc = 3.3 V)
```

按压使 `R_fsr` 下降，因此 **`V_AIN` 与 counts 上升**（`response_polarity = VOLTAGE_RISES_WITH_FORCE`）。10 kΩ 只是首轮取值，后续可比 4.7 kΩ / 10 kΩ / 47 kΩ；换电阻只改 `config/sensor_esp32_fsr2.json` 的 `divider_resistor_ohm` 并重新生成头文件。

## 2. 串口参数（请软件组改这一处）

| 项 | 值 |
|---|---|
| 波特率 | **921600** |
| 数据格式 | 8N1，无流控 |
| 行结束 | `\n`（固件同时容忍 `\r\n` 输入） |
| 单行上限 | 8192 字节（固件发送缓冲；实测见 §7） |
| 命令上限 | 512 字节 |

固件与 `config/*.json` 中的 `serial_baud` 都是 921600。**软件组旧模板里的 115200 必须改为 921600**，否则会收到乱码字节流而不是 JSON。这一项登记为 `docs/ISSUES.md` I-006。

## 3. Profile 与通道号

同一份固件通过生成头文件切换 profile，线格式完全一致，只有 `sensor_profile`、通道数、`channel_config` 不同。

| profile | 通道数 | 通道含义 |
|---|---:|---|
| `FSR_ONLY` | 2 | `0 = FSR_A`，`1 = FSR_B`；`matrix_rows/cols = null` |
| `HYBRID_6X6_FSR2` | 38 | `0..35` 行优先 `R1C1..R6C6`，`36 = FSR_A`，`37 = FSR_B`；`matrix_rows/cols = 6` |

FSR_ONLY 只做两路分压采样，不驱动任何矩阵列，因而不存在列间串扰，这也是本阶段优先交付它的原因。HYBRID 的矩阵扫描逻辑已实现并离线通过 host 模拟，但**矩阵物理有效性未验证**，不作为本阶段验收项。

## 4. HELLO（设备 → 主机，上电后一次；也可用 `HELLO` 命令重发）

真实字段（样例见 `tests/fixtures/fsr2/hello_fsr_only.json`）：

```json
{"protocol_version":1,"type":"HELLO","sensor_profile":"FSR_ONLY","device_id":"tactile-esp32-01",
 "boot_id":"...","firmware_version":"tactile-fsr2-0.2.0","scan_mode":"FSR_ONLY_2CH",
 "sample_rate_hz":null,"channel_count":2,"spi_mode":"MODE1_BITBANG","data_rate_sps":330,
 "conversion_wait_us":4500,"reference_mode":"AVDD_AVSS","reference_modes_allowed":["AVDD_AVSS"],
 "pins":{"sclk":18,"mosi":23,"miso":[34,35,26,33],"cs":[21,22,5,32]},
 "channel_config":{"status":"IMPLEMENTED_UNVERIFIED","matrix_rows":null,"matrix_cols":null,
   "adc_count":4,"scan_mode":"FSR_ONLY_2CH","unit":"ADC_COUNTS",
   "channels":[{"channel_id":0,"name":"FSR_A","sensor_kind":"FSR","ads1220_id":4,
                "adc_input":0,"mux_channel":8,"matrix_row":null,"matrix_col":null}, ...]},
 "fsr_layout":{"adc_id":4,"independent_pulldowns":true,"divider_resistor_ohm":10000,
   "excitation_mv":3300,"unit":"ADC_COUNTS","response_polarity":"VOLTAGE_RISES_WITH_FORCE",
   "validated":false,"channels":[...]},
 "max_line_bytes":8192,
 "adc_status":[{"id":1,"state":"OK","code":0,...}, ...]}
```

关键点：

- `boot_id` 每次上电/复位都变。**软件必须以 `boot_id` 判断“是否同一次启动”**，不能只看 `frame_seq`；错过的 `frame_seq` 不能跨 `boot_id` 拼接。
- `channel_config.status` 是 `IMPLEMENTED_UNVERIFIED`，只有做过整机实测后才会升级；`fsr_layout.validated` 在真实台架标定前恒为 `false`。
- `pins.miso` / `pins.cs` 长度恒为 4（四颗 ADC 全在配置里，即使 HYBRID profile 的 ADC4 只做 FSR）。
- 重连时先发 `STATUS`（见 §6）即可拿到当前状态，无需复位设备。

## 5. SAMPLE（设备 → 主机，每帧一条）

```json
{"protocol_version":1,"type":"SAMPLE","sensor_profile":"FSR_ONLY","device_id":"tactile-esp32-01",
 "boot_id":"...","firmware_version":"tactile-fsr2-0.2.0","frame_seq":2,
 "timestamp_us":110000,"mcu_time_us":110000,"frame_period_us":10000,
 "channel_ids":[0,1],"channel_count":2,
 "raw_adc":[762601,889701],"channels":[762601,889701],
 "valid":[true,true],"valid_mask":[true,true],
 "sample_timestamp_us":[45895,51208],"channel_flags":[0,0],
 "reference_mode":"AVDD_AVSS","effective_frame_rate_hz":100.00,
 "adc_status":[{"id":1,"state":"OK","code":0,"consecutive_errors":0,"total_errors":0,
                "recovered":0,"last_error":null}, ...]}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `frame_seq` | uint32 | 每帧 +1；只有同一 `boot_id` 内可比 |
| `timestamp_us` | uint32 | 帧级时间戳（`micros()`，未与主机对时） |
| `mcu_time_us` | uint32 | 与 `timestamp_us` 相同；保留 V1 字段名以兼容旧解析器 |
| `frame_period_us` | uint32\|null | 与上一帧的间隔；**首帧为 null** |
| `channel_ids` | int[] | 恒为 `0..channel_count-1` |
| `raw_adc` | (int\|null)[] | 24-bit 有符号计数；无效通道为 **null**，绝不填 0 |
| `channels` | (int\|null)[] | 与 `raw_adc` 相同，保留旧字段名 |
| `valid` / `valid_mask` | bool[] | 两数组必须一致 |
| `sample_timestamp_us` | (uint32\|null)[] | 该通道自己的采样时刻（38 通道**不是**同时采样） |
| `channel_flags` | int[] | 位标记，见下表 |
| `reference_mode` | string | FSR profile 恒为 `AVDD_AVSS` |
| `effective_frame_rate_hz` | number | 最近 32 帧滑动窗口速率，centi 精度 |
| `adc_status` | object[] | 4 个对象，`id` 必须 1..4 顺序 |

`channel_flags` 位（沿用 V1）：`0x01 SAT_HIGH`、`0x02 SAT_LOW`、`0x04 NEGATIVE_SINGLE_ENDED`、`0x08 NEAR_RAIL`、`0x10 STUCK_EXTREME`、`0x20 NO_DATA`。

**无效数据规则（协议红线）**：`valid = false` 时 `raw_adc`、`channels`、`sample_timestamp_us` 必须为 `null`，且 `channel_flags` 必须含 `NO_DATA`。用 0 冒充"没采到"会被参考解析器直接判 `ZERO_FOR_INVALID`。ADC4 掉线时的真实样例（`tests/fixtures/fsr2/sample_fsr_only_no_adc4.json`）：

```json
"raw_adc":[null,null],"channels":[null,null],"valid":[false,false],"valid_mask":[false,false],
"sample_timestamp_us":[null,null],"channel_flags":[32,32],
"adc_status":[...,{"id":4,"state":"NO_RESPONSE","code":2,"consecutive_errors":1,
                  "total_errors":1,"recovered":0,"last_error":"PROBE_OR_CONFIG_READBACK_FAILED"}]
```

## 6. STATUS（命令应答，用于重连查询）

`STATUS` 应答包含 `HELLO` 的身份与环境字段，外加运行态：

| 字段 | 说明 |
|---|---|
| `uptime_ms` | 上电毫秒数 |
| `sensor_state` | `STREAMING` / `STOPPED` |
| `streaming` | 布尔，同上 |
| `effective_frame_rate_hz` | 当前帧率（centi） |
| `last_frame_seq` | 最近发出的帧号 |
| `last_error` | 最近一次错误字符串或 null |
| `channel_config`、`fsr_layout`、`pins`、`adc_status` | 与 HELLO 一致 |
| `config_report` | 仅在 `VERIFY_CONFIG` 应答中出现：逐器件 `expected`/`readback` 寄存器与 `match` |
| `request_id` | 若命令带 `request_id`，原样回传 |

重连流程建议：`PING`（确认在线）→ `STATUS`（拿 `boot_id`、`last_frame_seq`、`sensor_state`）→ `STREAM start`。

## 7. 实测行长度与缓冲

由固件帧构造器在 host 模拟里实际输出测得（不是估算）：

| 帧 | 字节数 |
|---|---:|
| HELLO FSR_ONLY | 1650 |
| SAMPLE FSR_ONLY（健康） | 931 |
| SAMPLE FSR_ONLY（ADC4 掉线） | 964 |
| HELLO HYBRID | 6554 |
| SAMPLE HYBRID（健康） | 2311 |

8192 字节发送缓冲对两种 profile 都有余量（最长 6554，约 80%）。软件侧单行缓冲建议 ≥ 8192；超过即视为协议错，不要拼接跨行内容。

帧率：FSR_ONLY 每帧只做 2 次 330 SPS 转换，模型上远高于 100 Hz；sim 中 `frame_period_us = 10000` 是模拟器步进，**不是**真实帧率。真实值以台架 `STATUS` / `effective_frame_rate_hz` 为准。

## 8. 命令

一行一个 JSON 对象，`{"cmd":"...", "request_id":"..."}`。`request_id` 可选（≤64 字符），会被回传。

| 命令 | 作用 |
|---|---|
| `PING` | 回 `PONG` |
| `HELLO` | 重发 HELLO |
| `STATUS` | 回运行状态 |
| `STREAM`（`value: on/off/start/stop`） | 开/关连续采样 |
| `STOP` | 等同 `STREAM off` |
| `RESET_ADC`（`id`: 0=全部，1..4=单颗） | 重新探测并配置指定 ADC |
| `VERIFY_CONFIG` | 读回四颗 ADC 寄存器并随 STATUS 返回 `config_report` |

错误应答：`{"protocol_version":1,"type":"ERROR","code":"...","message":"...","fatal":false,"request_id":...}`，`code` 取值包括 `UNKNOWN_COMMAND`、`INVALID_JSON`、`COMMAND_TOO_LONG`、`INCOMPLETE_COMMAND`、`INVALID_REQUEST_ID`、`UNSUPPORTED_CHANNEL_LAYOUT`。

**命令层状态**：`.ino` 的命令解析用 ArduinoJson，已随 sketch 编译通过，但**未在 host 上逐命令验证**（仿真不覆盖串口解析），属 `IMPLEMENTED_UNVERIFIED`；实机验收清单第 6 步会覆盖。

## 9. 样例与参考解析器

- fixtures（由固件帧构造器实际输出、脱敏后提交）：`tests/fixtures/fsr2/`
  - `hello_fsr_only.json`、`sample_fsr_only_valid.json`、`sample_fsr_only_no_adc4.json`
  - `hello_hybrid.json`、`sample_hybrid_valid.json`、`sample_hybrid_no_adc4.json`
- 严格参考解析器：`tools/fsr2/protocol_v2.py`（stdlib，无第三方依赖）

```python
from tools.fsr2 import protocol_v2

text = open("tests/fixtures/fsr2/sample_fsr_only_valid.json").read()
sample = protocol_v2.parse_message(text)
print(sample.fsr_values)              # {'FSR_A': 762601, 'FSR_B': 889701}
```

解析器会拒绝：通道数不符、`valid` 与 `valid_mask` 不一致、无效通道带数值、`valid` 与 `NO_DATA` 矛盾、内部 2.048 V 参考、`adc_status` 不是 4 个、`fsr_layout.validated = true`（在真实标定前宣称已验证）等。软件组可以用它当"客户端是否实现正确"的对照。

## 10. 软件组需要同步的已知缺口

1. **`tools/tactile_acq/protocol.py` 仍硬编码 12 通道 / 3 颗 ADC**：`CHANNEL_COUNT = 12`、`ADC_COUNT = 3`，会直接拒绝 FSR_ONLY 的 2 通道帧。需要按 `sensor_profile` 取通道数（2 / 38），并保留旧 12 通道路径。登记为 `docs/ISSUES.md` I-012。
2. **波特率 115200 → 921600**（I-006）。
3. 记录器/CSV 列名沿用 `channel_0..channel_N` 时，需按 profile 生成列；FSR 专用列建议 `fsr_a_counts` / `fsr_b_counts`。
4. 38 通道帧的 `sample_timestamp_us` 各不相同，不要按"整帧同时采样"做微分；滑移判断需要时间对齐或降采样。

## 11. 实机验收清单（现场授权后照做）

前置：**未接线、未烧录前不要执行**；接线、上电、烧录、串口各自需要现场明确授权。

1. **断电接线核对**（断电、拔 USB）：ADC1–3 的 CS/MISO 分别为 21/34、22/35、5/26；ADC4 为 32/33；四颗 SCLK/MOSI 并联到 18/23；ADC4 的 AIN0/AIN1 各接一路独立 10 kΩ 下拉到 GND，两个节点不互连；3V3 与 GND 逐颗确认。
2. **上电前测阻抗**：3V3 对 GND 不短路；每个 FSR 节点对 GND 约 10 kΩ ±5%。
3. **烧录**（现场授权）：`python3 scripts/build_sensor_fsr2_firmware.py --build-dir "$PWD/evidence/fsr2/build_sensor_fsr2" && python3 -m esptool ...` 由现场同学执行；本仓库脚本只编译不烧录。
4. **打开 921600 串口**，应立刻收到一行 `HELLO`：`channel_count = 2`、`pins.miso = [34,35,26,33]`、`reference_mode = "AVDD_AVSS"`、`adc_status` 四项均 `OK`。若 ADC4 为 `NO_RESPONSE`，先查 32/33 与供电，不要下发 `STREAM`。
5. **空载基线**：`STREAM start` 后静置 10 s，两路 counts 应稳定（波动远小于满量程 1%），且两路**不相等**（独立分压，不应对齐）。
6. **命令面**：`STATUS` 回 `STREAMING`、`last_frame_seq` 递增；`VERIFY_CONFIG` 回 4 个器件且 `match` 全为 true；`STREAM stop` 后不再有 SAMPLE。
7. **单路按压**：只按 FSR_A，`channels[0]` 明显上升而 `channels[1]` 基本不动；换 FSR_B 反之。两路同时变化说明节点被互连或激励串扰。
8. **断线语义**：拔掉 ADC4 的 CS（或断电其一）后，SAMPLE 中两通道应为 `null` + `valid=false` + `channel_flags` 含 `NO_DATA`，`adc_status[3].state` 变 `NO_RESPONSE`；**不得**出现 0 值冒充。
9. **恢复**：接回后 `RESET_ADC 4`，数秒内 `adc_status[3]` 回到 `OK`，通道重新有效。
10. **记录**：把实测串口原始帧、帧率、空载/按压 counts、AVDD 实测值写进 `docs/PROGRESS.md`，并将一组真实样例脱敏后补进 `tests/fixtures/fsr2/`（当前 fixtures 全部来自 host 模拟，**不得**当作硬件验证证据）。

## 12. 明确未验证的事项

- 四颗 ADS1220 在同一组 bit-bang SCLK/MOSI 上的实际时序与 MISO 竞争（尤其是 ADC4 与 ADC1–3 同时输出）——**只用逻辑分析仪/实测能确认**。
- 10 kΩ 分压是否覆盖实际 FSR 量程、按压方向与电压极性。
- 921600 下的实际吞吐与丢帧率。
- 矩阵（HYBRID）扫描的物理有效性、列间串扰。
- 命令层的逐条行为（仅编译通过与 README 描述）。

以上在 `docs/ISSUES.md` 以 I-013、I-014 等编号跟踪，状态标记遵循 AGENTS.md：只有实测过的行为才可写 PASS。
