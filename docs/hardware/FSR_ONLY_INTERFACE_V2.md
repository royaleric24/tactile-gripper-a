# V2 触觉采集串口接口（FSR + 12 电极）

> **2026-11-15 接线修正**：压敏布实际是 **12 根独立电极**——R1–R6 各接一颗 ADS1220 的
> 一个 AIN，并各用 10 kΩ 下拉到 GND；C1–C6 各接一个 AIN，并各用 1 kΩ 上拉到 3.3 V。
> **没有 GPIO 逐列激励、没有 HI_Z 切换、没有 36 点扫描矩阵**。本文件原先关于
> `HYBRID_6X6_FSR2` / `COLUMN_SCAN_6X6` 的描述已撤回（见 §3 与 §12），当前 profile 为
> `FSR_ONLY` 与 `MATRIX_ELECTRODES_12`。12 路电极电压**不等于** 36 个压力点。
> 电极到 ADC/AIN 的分配**仍缺失**，代码以显式未映射通道处理，不猜引脚。

- 状态：**IMPLEMENTED_UNVERIFIED**（三个 profile 均已离线编译；host 模拟测试通过；**尚未接线、未烧录、未做任何真实采样**）
- 面向读者：软件组（解析 / 记录 / 界面）、总负责人、后续接手的硬件同学
- 协议版本：`protocol_version = 1`（在 V1 基础上**只增字段**，不改变已有字段语义）
- 传输：USB 串口 **`921600 8N1`**，UTF-8 JSON Lines，一行一条消息，以 `\n` 结束
- 设备：旧 ESP32（NodeMCU ESP-32S V1.1）+ **4 × ADS1220**，其中 ADC4 专用于两路独立 FSR 分压
- 固件目录：`firmware/sensor_fsr2/`（旧 `firmware/sensor/` 保持冻结，作为 V1 历史版本，不改动）
- 配置：`config/sensor_esp32_fsr2.json`（FSR_ONLY）、`config/sensor_esp32_electrodes12.json`（12 电极）、`config/sensor_esp32_electrodes12_fsr2.json`（12 电极 + 2 FSR = 14 逻辑通道）

本文件只承诺 **ADS1220 原始计数**与**明确的无效语义**。没有独立标定前，不得把 counts 说成牛顿、压强或滑移概率。

## 1. 电极拓扑与第四颗 ADC

压敏布是**被动 12 电极**网络，不是可扫描矩阵：

| 电极 | 偏置 | 读数 |
|---|---|---|
| R1–R6 | 每根各经 10 kΩ 下拉到 GND | 每根独立接一个 ADS1220 单端 AIN |
| C1–C6 | 每根各经 1 kΩ 上拉到 3.3 V | 每根独立接一个 ADS1220 单端 AIN |

- 没有 GPIO 列驱动，没有 HI_Z 切换，也没有"逐列选通得到 36 点"的时序。任何按
  `COLUMN_SCAN_6X6` / `driveColumn()` / `parkColumns()` 建模的固件都与实物不符，已从本分支移除。
- 12 个电极都是**同时存在的独立电位节点**，12 路电压只是 12 个测量值；它们不能唯一还原 36 个
  接触点的压力分布，界面不得画成 36 格热图。
- **R/C 到 ADC 编号与 AIN 的对应关系尚未记录**（现场焊接表还没有）。固件与配置因此支持
  "未映射"状态，而不是编一组看起来合理的引脚号。

ADC 分配（SPI 固定）：

| 器件 | CS | MISO | 用途 |
|---|---:|---:|---|
| ADC1 | 21 | 34 | 电极 AIN（具体分配 PENDING） |
| ADC2 | 22 | 35 | 电极 AIN（具体分配 PENDING） |
| ADC3 | 5 | 26 | 电极 AIN（具体分配 PENDING） |
| **ADC4** | **32** | **33** | **FSR_A = AIN0，FSR_B = AIN1** |

四颗共用 `SCLK = 18`、`MOSI = 23`；每颗独立 CS。`GPIO32` 在 V2 中**只作 ADC4 片选**。历史映射
`miso = [35, 26, 34]` 已作废，不得再用来生成 V2 固件（生成器会直接拒绝 3 颗 ADC 的配置）。
ADC4 保留给 FSR：电极如果被错误分配到 ADC4，生成器会拒绝该配置。

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

固件与 `config/*.json` 中的 `serial_baud` 都是 921600。P3-A 的 Dashboard 配置已同步。S3 控制器是另一条链路；实际 Mac 串口尚未验证。

## 3. Profile 与通道号

同一份固件通过生成头文件切换 profile，线格式完全一致，只有 `sensor_profile`、通道数、
`electrode_layout` 与 `fsr_layout` 不同。

| profile | 通道数 | 通道含义 |
|---|---:|---|
| `FSR_ONLY` | 2 | `0 = FSR_A`，`1 = FSR_B`；`matrix_rows/cols = null` |
| `MATRIX_ELECTRODES_12`（仅电极） | 12 | `0..5 = R1..R6`，`6..11 = C1..C6` |
| `MATRIX_ELECTRODES_12`（电极 + FSR） | 14 | 同上，`12 = FSR_A`，`13 = FSR_B` |

- 通道 0..11 的顺序是**协议顺序**（R1..R6 再 C1..C6），不是物理接线顺序；物理映射以
  `electrode_layout.channels[i].adc_id/adc_input` 为准，未记录时两者均为 `null`。
- `HYBRID_6X6_FSR2`（38 通道、36 个扫描单元）已**撤回**：它与实物接线不符。解析器收到该
  `sensor_profile` 会直接报 `PROFILE_HISTORICAL`；生成器拒绝为它生成固件。代码与旧样例只留在
  git 历史里，不得向当前布料烧录或用于任何"36 点已实测"的表述。
- 电极 profile 不驱动任何 GPIO，所有通道都是静态单端读数。

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
- `pins.miso` / `pins.cs` 长度恒为 4（四颗 ADC 全在配置里；12 电极 profile 也会探测 ADC4，只是不读通道）。
- 重连时先发 `STATUS`（见 §6）即可拿到当前状态，无需复位设备。

### 4.1 电极 profile 的 HELLO 追加字段

`MATRIX_ELECTRODES_12` 在 §4 的字段之外增加 `electrode_layout`，并在 `channel_config.channels`
里把前 12 项标成 `sensor_kind = "ELECTRODE"`：

```json
{"electrode_layout":{"count":12,"rows":6,"columns":6,"mapping_status":"PENDING_REAL_WIRING",
 "row_bias":"PULLDOWN_10K_TO_GND","column_bias":"PULLUP_1K_TO_3V3",
 "protocol_order":"R1..R6 THEN C1..C6","gpio_excitation":false,"validated":false,
 "channels":[{"channel_id":0,"name":"R1","role":"ROW","position":1,
              "bias":"PULLDOWN_10K_TO_GND","adc_id":null,"adc_input":null,"mux_channel":null}, ...]},
 "channel_config":{"matrix_rows":null,"matrix_cols":null,
   "channels":[{"channel_id":0,"name":"R1","sensor_kind":"ELECTRODE","ads1220_id":null,
                "adc_input":null,"mux_channel":null,"matrix_row":null,"matrix_col":null,
                "electrode_role":"ROW","electrode_position":1}, ...]}}
```

- `mapping_status`：`PENDING_REAL_WIRING`（真实接线表尚未记录，所有 `adc_id/adc_input/mux_channel`
  为 `null`）或 `TABLE_PROVIDED`（现场表已填满且唯一）。fixtures 里的 `SIM_SYNTHETIC_MAPPING`
  只出现在 host 测试合成表，**不是**真实接线，软件应照常显示但不得当成实测映射。
- `validated` 在真实台架记录前恒为 `false`；`gpio_excitation` 恒为 `false`。
- 14 通道变体（电极 + FSR）会同时带 `fsr_layout`；12 通道变体不带。

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

电极 profile（12 或 14 通道）的语义：

- 未映射电极：`raw_adc/channels/sample_timestamp_us` 全为 `null`，`valid=false`，`channel_flags`
  含 `NO_DATA`。**这是正确状态**，不是故障、不是 0 值。
- FSR 通道（14 通道变体的 12/13）独立于电极映射：即使 12 个电极全部未映射，FSR 两路仍可有效。
- 不要把这 12/14 个通道拼成 6x6 热图；`matrix_rows/cols` 恒为 `null`。

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
| HELLO FSR_ONLY | 1750 |
| SAMPLE FSR_ONLY（健康） | 931 |
| SAMPLE FSR_ONLY（ADC4 掉线） | 964 |
| HELLO 12 电极 + FSR（未映射） | 5972 |
| SAMPLE 12 电极 + FSR（未映射） | 1348 |
| HELLO 12 电极（合成映射） | 5070 |
| SAMPLE 12 电极（合成映射） | 1326 |

8192 字节发送缓冲对三种 profile 都有余量（最长 5972，约 73%）。软件侧单行缓冲建议 ≥ 8192；
超过即视为协议错，不要拼接跨行内容。

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
  - FSR_ONLY：`hello_fsr_only.json`、`sample_fsr_only_valid.json`、`sample_fsr_only_no_adc4.json`
  - 12 电极 + FSR（真实映射缺失）：`hello_electrodes12_fsr2_unmapped.json`、
    `sample_electrodes12_fsr2_unmapped.json`、`sample_electrodes12_fsr2_fsr_absent.json`
  - 12 电极**合成映射**（仅测试用，非真实接线）：`hello_electrodes12_mapped_synthetic.json`、
    `sample_electrodes12_mapped_synthetic.json`、`sample_electrodes12_mapped_absent.json`
- 严格参考解析器：`tools/fsr2/protocol_v2.py`（stdlib，无第三方依赖）

```python
from tools.fsr2 import protocol_v2

text = open("tests/fixtures/fsr2/sample_fsr_only_valid.json").read()
sample = protocol_v2.parse_message(text)
print(sample.fsr_values)              # {'FSR_A': 762601, 'FSR_B': 889701}
```

解析器会拒绝：通道数不符、`valid` 与 `valid_mask` 不一致、无效通道带数值、`valid` 与 `NO_DATA` 矛盾、内部 2.048 V 参考、`adc_status` 不是 4 个、`fsr_layout.validated = true`（在真实标定前宣称已验证）等。软件组可以用它当"客户端是否实现正确"的对照。

## 10. P3-A 主机消费路径

1. Dashboard 直接复用 `tools/fsr2/protocol_v2.py` 校验固件帧并适配现有应用模型。旧 `tools/tactile_acq` 保持 V1 三颗 ADC 协议。
2. `HELLO` 和 `STATUS` 采用固件 `cmd` 格式，主机处理超时和身份冲突。完整行为见 [接口契约](../INTERFACE_CONTRACT.md)。
3. Trial 保存原始 wire JSON；CSV 按通道 ID 生成 `ch_N` / `valid_N`，无效数值列留空；导出的文件可只读回放。
4. 时间戳按通道保留，不把通道样本时刻视为同一个点；滑移判断与现场时序仍需验证。

## 11. 实机验收清单（现场授权后照做）

前置：**未接线、未烧录前不要执行**；接线、上电、烧录、串口各自需要现场明确授权。

1. **断电接线核对**：ADC1–3 的 CS/MISO 分别为 21/34、22/35、5/26；ADC4 为 32/33；四颗
   SCLK/MOSI 并联到 18/23；**R1–R6 每根各串一颗 10 kΩ 到 GND，C1–C6 每根各串一颗 1 kΩ 到
   3.3 V，12 根电极分别接到 ADS1220 的某个 AIN，不接任何 GPIO 列驱动**；ADC4 的 AIN0/AIN1
   各接一路独立 10 kΩ 下拉到 GND，两个节点不互连；3V3 与 GND 逐颗确认。
   同时把每根电极的 ADC/AIN 实测结果填进本文 §12 的映射表（V2 文档基线
   `docs/WIRING_FREEZE_V2.md` 合并后以该文档 §4.1 为准），未填表前不要给配置填 `map`。
2. **上电前测阻抗**：3V3 对 GND 不短路；每个 FSR 节点对 GND 约 10 kΩ ±5%。
3. **烧录**（现场授权）：`python3 scripts/build_sensor_fsr2_firmware.py --build-dir "$PWD/evidence/fsr2/build_sensor_fsr2" && python3 -m esptool ...` 由现场同学执行；本仓库脚本只编译不烧录。
4. **打开 921600 串口**，应立刻收到一行 `HELLO`：`channel_count = 2`、`pins.miso = [34,35,26,33]`、`reference_mode = "AVDD_AVSS"`、`adc_status` 四项均 `OK`。若 ADC4 为 `NO_RESPONSE`，先查 32/33 与供电，不要下发 `STREAM`。
5. **空载基线**：`STREAM start` 后静置 10 s，两路 counts 应稳定（波动远小于满量程 1%），且两路**不相等**（独立分压，不应对齐）。
6. **命令面**：`STATUS` 回 `STREAMING`、`last_frame_seq` 递增；`VERIFY_CONFIG` 回 4 个器件且 `match` 全为 true；`STREAM stop` 后不再有 SAMPLE。
7. **单路按压**：只按 FSR_A，`channels[0]` 明显上升而 `channels[1]` 基本不动；换 FSR_B 反之。两路同时变化说明节点被互连或激励串扰。
8. **断线语义**：拔掉 ADC4 的 CS（或断电其一）后，SAMPLE 中两通道应为 `null` + `valid=false` + `channel_flags` 含 `NO_DATA`，`adc_status[3].state` 变 `NO_RESPONSE`；**不得**出现 0 值冒充。
9. **恢复**：接回后 `RESET_ADC 4`，数秒内 `adc_status[3]` 回到 `OK`，通道重新有效。
10. **记录**：把实测串口原始帧、帧率、空载/按压 counts、AVDD 实测值写进 `docs/PROGRESS.md`，并将一组真实样例脱敏后补进 `tests/fixtures/fsr2/`（当前 fixtures 全部来自 host 模拟，**不得**当作硬件验证证据）。

## 12. 电极映射核对表（现场填写）

| 电极 | ADC id (1–3) | AIN (0–3) | 偏置电阻 | 实测空载电压 | 核线人 | 日期 |
|---|---|---|---|---|---|---|
| R1 | | | 10 kΩ → GND | | | |
| R2 | | | 10 kΩ → GND | | | |
| R3 | | | 10 kΩ → GND | | | |
| R4 | | | 10 kΩ → GND | | | |
| R5 | | | 10 kΩ → GND | | | |
| R6 | | | 10 kΩ → GND | | | |
| C1 | | | 1 kΩ → 3.3 V | | | |
| C2 | | | 1 kΩ → 3.3 V | | | |
| C3 | | | 1 kΩ → 3.3 V | | | |
| C4 | | | 1 kΩ → 3.3 V | | | |
| C5 | | | 1 kΩ → 3.3 V | | | |
| C6 | | | 1 kΩ → 3.3 V | | | |

填完表后：把 `config/sensor_esp32_electrodes12*.json` 的 `electrodes.map` 按表填满，并把
`mapping_status` 改为 `TABLE_PROVIDED`，重新生成头文件并编译。在那之前，固件对 12 个通道
输出的都是 `null` + `NO_DATA`，这是正确行为而不是故障。

## 13. 明确未验证的事项

- 四颗 ADS1220 在同一组 bit-bang SCLK/MOSI 上的实际时序与 MISO 竞争（尤其是 ADC4 与 ADC1–3 同时输出）。
- R1–R6 / C1–C6 到 ADC/AIN 的真实分配（**映射缺失**，见 §13）。
- 12 电极在静止/按压/持杯下的实际电压范围与 C 极上拉对相邻节点的影响。
- 10 kΩ FSR 分压是否覆盖实际量程、按压方向与极性。
- 921600 下的实际吞吐与丢帧率。
- 电极布局能否支持任何"位置分辨"结论（12 路电压不是 36 点压力图）。
- 命令层的逐条行为（仅编译通过与 host 模拟，未逐命令实测）。

以上在 `docs/ISSUES.md` 以 I-102、I-014 等编号跟踪，状态标记遵循 AGENTS.md：只有实测过的行为才可写 PASS。
