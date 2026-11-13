# 12 通道 ADS1220 触觉采集协议（硬件组实现）

- 状态：**IMPLEMENTED（固件已编译；真实硬件验证结果见 `STAGE_H1_REPORT.md`）**
- 协议版本：`protocol_version = 1`
- 传输：USB 串口，`921600 8N1`（可在 `config/sensor_esp32.json` 调整）
- 编码：UTF-8 JSON Lines，一行一条消息，以 `\n` 结束
- 设备：旧 ESP32（NodeMCU ESP-32S V1.1）+ 3 × ADS1220
- 本文档只承诺 **12 路原始 ADC 计数**；36 点矩阵坐标映射 **未实现、未验证**，不得从 12 路直接推断。

相关文件：

- 固件：`firmware/sensor/`
- 配置：`config/sensor_esp32.json`
- 采集工具：`tools/tactile_acq/`
- 最简解析示例：`tools/tactile_acq/software_parser_example.py`

## 1. 通道定义（固定顺序）

| 通道 | ADC | ADS1220 输入 | MUX[3:0] | 说明 |
|---:|---|---|---:|---|
| 0 | ADC1 | AIN0 vs AVSS | 1000b | 单端 |
| 1 | ADC1 | AIN1 vs AVSS | 1001b | 单端 |
| 2 | ADC1 | AIN2 vs AVSS | 1010b | 单端 |
| 3 | ADC1 | AIN3 vs AVSS | 1011b | 单端 |
| 4 | ADC2 | AIN0 vs AVSS | 1000b | 单端 |
| 5 | ADC2 | AIN1 vs AVSS | 1001b | 单端 |
| 6 | ADC2 | AIN2 vs AVSS | 1010b | 单端 |
| 7 | ADC2 | AIN3 vs AVSS | 1011b | 单端 |
| 8 | ADC3 | AIN0 vs AVSS | 1000b | 单端 |
| 9 | ADC3 | AIN1 vs AVSS | 1001b | 单端 |
| 10 | ADC3 | AIN2 vs AVSS | 1010b | 单端 |
| 11 | ADC3 | AIN3 vs AVSS | 1011b | 单端 |

`channel_ids = [0..11]`，`channel_count = 12`。`raw_adc[i]` 是 ADS1220 的 24-bit 二进制补码有符号值，范围 `[-8388608, 8388607]`，单位是 **ADC counts**，不是电阻、力、压强或矩阵坐标。

## 2. 消息类型

| type | 方向 | 用途 |
|---|---|---|
| `HELLO` | 设备 → Mac | 启动后发送一次；设备 ID、通道配置、引脚、初始状态 |
| `SAMPLE` | 设备 → Mac | 每个完整 12 通道帧一条 |
| `STATUS` | 设备 → Mac | 对 `STATUS`/`DIAG`/`SET_REF`/`STREAM`/`RESET_ADC` 的响应；也包含 ADC 状态 |
| `ERROR` | 设备 → Mac | 命令或内部错误 |
| `PONG` | 设备 → Mac | 对 `PING` 的响应（仅诊断用） |

所有消息都带 `protocol_version`、`device_id`、`boot_id`（除 `ERROR` 外）。`boot_id` 每次复位/上电变化，用于识别会话边界。

## 3. SAMPLE 字段

| 字段 | 类型 | 含义 |
|---|---|---|
| `protocol_version` | int | 固定 `1` |
| `type` | string | `"SAMPLE"` |
| `device_id` | string | 配置的 `tactile-esp32-01` |
| `boot_id` | string | 本次启动唯一 ID |
| `firmware_version` | string | 例如 `tactile-sense-0.1.0` |
| `frame_seq` | int | 从 1 递增；复位后重新开始 |
| `timestamp_us` | int | 帧开始扫描时的设备 `micros()` |
| `mcu_time_us` | int | 与 `timestamp_us` 相同；兼容软件组现有字段名 |
| `frame_period_us` | int/null | 与上一帧起始时间的差；首帧为 null |
| `channel_ids` | int[12] | `[0..11]` |
| `channel_count` | int | `12` |
| `raw_adc` | (int\|null)[12] | 有符号 24-bit 原始值；无效通道为 null |
| `channels` | (int\|null)[12] | 与 `raw_adc` 完全相同的兼容字段 |
| `valid` | bool[12] | 该通道本次是否成功读出 |
| `valid_mask` | bool[12] | 与 `valid` 完全相同的兼容字段 |
| `sample_timestamp_us` | (int\|null)[12] | 每通道读取完成时的设备 `micros()`；无效为 null |
| `channel_flags` | int[12] | 通道质量位掩码，见下表 |
| `reference_mode` | string | `INTERNAL_2V048` 或 `AVDD_AVSS` |
| `effective_frame_rate_hz` | number | 固件最近 32 帧窗口的完整帧率，保留两位小数 |
| `adc_status` | object[3] | 三颗 ADC 的状态，见第 6 节 |

### 3.1 有效性与“不得伪造”

- `valid[i] == true`：`raw_adc[i]` 必须是整数，且在 `[-8388608, 8388607]`。
- `valid[i] == false`：`raw_adc[i]` **必须是 null**，`sample_timestamp_us[i]` 必须为 null，`channel_flags[i]` 必须包含 `0x20`（`NO_DATA`）。
- 不允许用 `0` 填充无效通道；`0` 是一个合法的 ADC count。
- `channel_flags` 只描述质量，不改变 `valid`。例如饱和通道仍然是成功转换的真实值，`valid=true`，但带 `SAT_HIGH`。

### 3.2 channel_flags 位定义

| 位 | 名称 | 含义 |
|---:|---|---|
| `0x01` | `SAT_HIGH` | 原始值等于 `+8388607`（正满量程） |
| `0x02` | `SAT_LOW` | 原始值等于 `-8388608`（负满量程） |
| `0x04` | `NEGATIVE_SINGLE_ENDED` | 单端 AINx/AVSS 出现负值；可能是输入低于 AVSS、参考/接线或配置问题 |
| `0x08` | `NEAR_RAIL` | `|raw| > 0.98 × 2^23` |
| `0x10` | `STUCK_EXTREME` | 连续 ≥16 帧出现相同的极值（`+FS`、`-FS` 或 `0`）；诊断标记，不等于无效 |
| `0x20` | `NO_DATA` | 本次未读到数据；必然 `valid=false` |

多个位可以同时存在。`0` 表示没有已知质量标记。

## 4. 示例 SAMPLE（示例值，不是实测数据）

```json
{"protocol_version":1,"type":"SAMPLE","device_id":"tactile-esp32-01","boot_id":"tactile-esp32-01-1a2b3c4d","firmware_version":"tactile-sense-0.1.0","frame_seq":42,"timestamp_us":1234567,"mcu_time_us":1234567,"frame_period_us":21400,"channel_ids":[0,1,2,3,4,5,6,7,8,9,10,11],"channel_count":12,"raw_adc":[1234,-567,0,8388607,null,100,200,300,400,500,600,700],"channels":[1234,-567,0,8388607,null,100,200,300,400,500,600,700],"valid":[true,true,true,true,false,true,true,true,true,true,true,true],"valid_mask":[true,true,true,true,false,true,true,true,true,true,true,true],"sample_timestamp_us":[1235000,1235100,1235200,1235300,null,1235400,1235500,1235600,1235700,1235800,1235900,1236000],"channel_flags":[0,0,0,1,32,0,0,0,0,0,0,0],"reference_mode":"INTERNAL_2V048","effective_frame_rate_hz":46.73,"adc_status":[{"id":1,"state":"OK","code":0,"consecutive_errors":0,"total_errors":0,"recovered":0,"last_error":null},{"id":2,"state":"OK","code":0,"consecutive_errors":0,"total_errors":0,"recovered":0,"last_error":null},{"id":3,"state":"NO_RESPONSE","code":2,"consecutive_errors":0,"total_errors":4,"recovered":0,"last_error":"PROBE_OR_CONFIG_READBACK_FAILED"}]}
```

## 5. HELLO

启动后发送一次，内容包含：

- `device_id`、`boot_id`、`firmware_version`
- `scan_mode = "SINGLE_SHOT_3X4"`
- `channel_count = 12`、`channel_ids = [0..11]`
- `channel_config`：软件组 `ChannelConfiguration.from_dict` 可直接解析的结构；`matrix_rows`/`matrix_cols` 为 null（矩阵映射 UNKNOWN）
- 0.1.3 的实际 HELLO 不发送顶层 `channel_ids`；主机从真实
  `channel_config.channels[].channel_id` 推导，不伪造映射。兼容旧样例中带
  `channel_ids` 的 HELLO。
- `pins`：SCLK/MOSI/MISO/CS
- `reference_mode`、`reference_modes_allowed`
- `data_rate_sps = 330`、`conversion_wait_us = 4500`
- `adc_status`

示例（省略部分通道对象）：

```json
{"protocol_version":1,"type":"HELLO","device_id":"tactile-esp32-01","boot_id":"tactile-esp32-01-1a2b3c4d","firmware_version":"tactile-sense-0.1.0","scan_mode":"SINGLE_SHOT_3X4","sample_rate_hz":null,"channel_count":12,"spi_mode":"MODE1_BITBANG","data_rate_sps":330,"conversion_wait_us":4500,"reference_mode":"INTERNAL_2V048","reference_modes_allowed":["INTERNAL_2V048","AVDD_AVSS"],"pins":{"sclk":18,"mosi":23,"miso":[34,35,26],"cs":[21,22,5]},"channel_config":{"status":"IMPLEMENTED","matrix_rows":null,"matrix_cols":null,"adc_count":3,"scan_mode":"SINGLE_SHOT_3X4","channels":[{"channel_id":0,"adc_input":0,"ads1220_id":1,"mux_channel":8,"matrix_row":null,"matrix_col":null,"enabled":true,"unit":"ADC_COUNTS"}]},"adc_status":[]}
```

## 6. adc_status / 状态码

每颗 ADC 一个对象：

| 字段 | 含义 |
|---|---|
| `id` | 1..3，顺序固定 |
| `state` | `OK` / `CONFIG_ERROR` / `NO_RESPONSE` / `RECOVERING` / `FAILED` |
| `code` | 与 state 对应的数字：0/1/2/3/4 |
| `consecutive_errors` | 连续错误计数 |
| `total_errors` | 本次启动累计错误 |
| `recovered` | 从故障恢复成功的次数 |
| `last_error` | 最近错误字符串或 null |

`last_error` 当前可能的值：

| 字符串 | 含义 |
|---|---|
| `PROBE_OR_CONFIG_READBACK_FAILED` | 复位/两组配置写读回/正常配置写读回失败 |
| `CONFIG_READ_FAILED` | 周期配置校验读取失败 |
| `CONFIG_LOST` | 周期配置校验发现寄存器被改写 |
| `DATA_TIMEOUT` | 设备超过 2 s 没有成功读取数据，触发重新初始化 |
| `RDATA_FAILED` | RDATA 读取失败 |
| `SET_REF_FAILED` | 切换参考失败 |
| `DIAG_RESTORE_FAILED` | DIAG 后恢复配置失败 |
| `FRAME_BUFFER_OVERFLOW` | 输出行超出固件缓冲（不应发生） |

单颗 ADC 故障时，该 ADC 的 4 个通道输出 `null`/`valid=false`，其他 ADC 继续工作；固件每 500 ms 尝试重新初始化故障 ADC。

## 7. reference_mode

| 值 | ADS1220 VREF[1:0] | 单端输入范围（PGA bypass, gain 1） |
|---|---|---|
| `INTERNAL_2V048` | `00` 内部 2.048 V | 约 0 … +2.048 V 对应 0 … +8388607 |
| `AVDD_AVSS` | `11` AVDD–AVSS | 约 0 … AVDD 对应 0 … +8388607 |

AVDD 参考用于合法输入可能超过 2.048 V 的场合；它不是“提高精度”，且 AVDD 噪声/精度会影响结果。切换命令见第 8 节。单端测量下负值通常是异常，固件会标记 `NEGATIVE_SINGLE_ENDED`，但原始值仍保留。

VREF 编码必须写对：`AVDD_AVSS` 是 VREF=11，即 Reg2=`0xC0`；`0x80` 是 VREF=10（外部 REFP1/REFN1），不是 AVDD。`tactile-sense-0.1.0` 曾把 AVDD 映射成代码 1，写 `0x40`（REF0）；`0.1.2` 改为代码 3（`0xC0`）并保留 `VERIFY_CONFIG` 原始寄存器读回。

## 8. 命令（Mac → 设备）

命令是单行 JSON 对象，字段：

| 字段 | 必需 | 说明 |
|---|---|---|
| `cmd` | 是 | `PING` / `STATUS` / `DIAG` / `DIAG_SPI` / `GPIO_DIAG` / `MISO_MAP` / `VERIFY_CONFIG` / `SET_REF` / `STREAM` / `RESET_ADC` |
| `request_id` | 否 | 最长 64 字符；响应原样带回 |
| `value` | 视命令 | `SET_REF` 用字符串；`STREAM` 用布尔 |
| `id` | 视命令 | `RESET_ADC` 用 1..3 |

示例：

```json
{"cmd":"STATUS","request_id":"a1"}
{"cmd":"DIAG","request_id":"a2"}
{"cmd":"SET_REF","value":"AVDD_AVSS","request_id":"a3"}
{"cmd":"VERIFY_CONFIG","request_id":"a3b"}
{"cmd":"STREAM","value":false,"request_id":"a4"}
{"cmd":"RESET_ADC","id":2,"request_id":"a5"}
```

- `STATUS`：返回 `STATUS`，包含帧率、参考、ADC 状态。
- `DIAG`：执行三颗 ADC 的寄存器读取、两组不同配置写读回、内部输入短接 offset、AVDD/4 监测、内部温度转换、12 路读取；返回 `STATUS`，其 `diag` 字段包含结果。DIAG 是硬件诊断，不是软件组正常运行流的一部分。
- `SET_REF`：切换参考并写读回验证；失败时返回 `ERROR` 并尝试恢复旧参考。
- `VERIFY_CONFIG`：每颗 ADC 读回 Reg0–Reg3，返回 `config_report`（原始寄存器、MUX、gain code、PGA bypass、VREF code、PSW、IDAC code）。AVDD 单点配置应为 `[0x81,0x80,0xC0,0x00]`。
- `STREAM false/true`：暂停/恢复 SAMPLE 输出；STATUS 仍可用。
- `RESET_ADC`：重新初始化指定 ADC。

错误响应：

```json
{"protocol_version":1,"type":"ERROR","device_id":"tactile-esp32-01","code":"UNKNOWN_COMMAND","message":"supported: PING, STATUS, DIAG, SET_REF, STREAM, RESET_ADC","fatal":false,"request_id":"x"}
```

错误码：`INVALID_JSON`、`INVALID_COMMAND`、`INVALID_REQUEST_ID`、`INVALID_VALUE`、`UNKNOWN_COMMAND`、`BUSY`、`COMMAND_TOO_LONG`、`INCOMPLETE_COMMAND`、`SET_REF_FAILED`、`FRAME_BUFFER_OVERFLOW`。

## 9. 采样时序与帧率

- 每颗 ADC：330 SPS、Normal mode、Single-shot、PGA bypass、Gain 1、内部 2.048 V（默认）。
- 单次转换官方时间：`12562 × tCLK`（330 SPS，normal mode）；`tCLK = 1/4.096 MHz`，约 3.067 ms；加内部振荡器唤醒 ≤50 µs。
- 固件等待 `4500 µs`，超过官方时间 + 振荡器容差 + 裕量，才发 RDATA；避免读到上一 MUX 的旧结果。
- 三颗 ADC 在同一个 MUX 步骤同时 START、同时等待、随后依次 RDATA；四个 MUX 步骤串行。理想帧周期约 `4 × (4500 µs + 开销)` ≈ 19–24 ms（约 42–52 Hz），串口发送会进一步限制；以 `effective_frame_rate_hz` 和 Mac 实测为准。
- `frame_seq` 在完整 12 通道帧完成后递增；丢帧由 Mac 根据序号缺口统计。

## 10. 与软件组现有解析器的兼容性

软件组 `src/tactile_gripper/protocol.py` 的 `parse_sample` 需要：

- `protocol_version`、`type`、`device_id`、`boot_id`、`frame_seq`、`mcu_time_us`
- `channels`、`valid_mask`
- 可选 `channel_ids`

本协议全部提供，并且 `channels == raw_adc`、`valid_mask == valid`、`mcu_time_us == timestamp_us`。因此软件组现有 `parse_sample` 可以直接消费 SAMPLE；额外的 `raw_adc`、`valid`、`sample_timestamp_us`、`channel_flags`、`adc_status`、`reference_mode`、`effective_frame_rate_hz` 会被其 `raw` 字典保留。

`HELLO` 的 `channel_config` 符合 `ChannelConfiguration.from_dict`：`channels` 列表、`adc_count=3`、`scan_mode`、`status`；`matrix_rows`/`matrix_cols` 为 null。**不要**在没有电气扫描证据时填 6×6/36 点。

最简独立解析示例见 `tools/tactile_acq/software_parser_example.py`。

## 11. 明确未承诺的内容

- 12 路 ADC 与 6×6 矩阵 36 个单元的对应关系：**UNKNOWN**。
- 原始 counts 到电阻、压力、力、摩擦力、夹持力的换算：**UNKNOWN**，没有标定。
- 多路复用/行列扫描方案：当前硬件是每颗 ADS1220 四个单端输入，**没有** 36:12 多路复用器。
- 传感器是否已安装、实际接触响应：以真实按压实验为准；没有按压就写 NOT_TESTED。
- 长时间稳定性、温漂、噪声、通道间串扰：需要后续实验。
