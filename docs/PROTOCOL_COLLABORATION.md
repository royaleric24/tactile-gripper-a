# 传感器接口协作说明（软件组 → 硬件组）

- 日期：2026-11-13
- 对应契约：[docs/INTERFACE_CONTRACT.md](INTERFACE_CONTRACT.md)
- 契约状态：**PROPOSED v0.1**（未冻结、未联调、未获硬件组确认）
- 说明：本文件是软件组的**沟通摘要**，不是新协议，也不替代共享契约。任何字段/语义变更仍需双方评审；软件分支中的实现不能反过来证明硬件已确认。

## 1. 软件组已经实现/提议了什么

软件侧只实现了**主机侧解析与测试**，没有实现真实传感器 transport，也没有声称硬件已发送这些字段：

- `HELLO` / `SAMPLE` / `STATUS` / `ERROR` 的解析、编码（仅测试/回放用）；
- 动态 `channel_config`：扫描通道数、ADC 输入、矩阵行列、有效性；
- 帧序号、`boot_id`、MCU 时间戳、主机接收时间的校验；
- 重复帧、丢帧、序号回退、设备重启、时间戳异常的检测；
- `REPLAY` / `SIMULATION` 只读隔离与合成数据标注。

这些实现是“按提议写的主机解析器”，用于提前暴露接口问题；真实设备是否按此发送仍 PENDING-HW。

## 2. HELLO 最小必要字段

建议硬件组至少提供：

```json
{
  "protocol_version": 1,
  "type": "HELLO",
  "device_id": "sensor-...",
  "boot_id": "unique-per-boot",
  "firmware_version": "sensor-...",
  "scan_mode": "UNKNOWN or confirmed value",
  "sample_rate_hz": null,
  "channel_config": {
    "status": "PROPOSED",
    "matrix_rows": null,
    "matrix_cols": null,
    "adc_count": null,
    "scan_mode": "UNKNOWN",
    "channels": [
      {
        "channel_id": 0,
        "adc_input": null,
        "ads1220_id": null,
        "mux_channel": null,
        "matrix_row": null,
        "matrix_col": null,
        "enabled": true,
        "unit": "ADC_COUNTS"
      }
    ]
  }
}
```

必须可回答：

- 启动时是否发送 HELLO？若不发送，主机只能用显式本地配置并标注 UNKNOWN。
- `channels` 长度是“扫描通道数”，不是矩阵单元数；两者是否相等？
- `adc_input` / `mux_channel` / `matrix_row,col` 哪些真实存在，哪些为 null？
- `unit` 是否只有 `ADC_COUNTS`？若为其它单位，请给出定义，软件不自行换算。

## 3. SAMPLE 最小必要字段

```json
{
  "protocol_version": 1,
  "type": "SAMPLE",
  "device_id": "sensor-...",
  "boot_id": "same-as-hello",
  "frame_seq": 1,
  "mcu_time_us": 1000,
  "channels": [812, 806, null, 799],
  "valid_mask": [true, true, false, true],
  "channel_ids": [0, 1, 2, 3],
  "contact_score": null
}
```

- `channels`、`valid_mask` 必须与 `channel_config.channels` 同长同序。
- 无效通道建议用 `null`；若使用占位数字，`valid_mask=false` 必须能明确标识，主机不会把占位数字当测量值。
- `channel_ids` 可选；若提供，必须与配置顺序一致。
- `contact_score` 可选；若提供，请说明算法/单位/量程/材料差异，否则主机只显示为“设备自报、语义 UNKNOWN”。

## 4. 感测单元 ≠ ADC 物理输入 ≠ 扫描通道

三个概念必须分开：

1. **物理感测单元**：6×6 矩阵中的 36 个接触位置（Stage H1 暂定，未确认）；
2. **ADC 物理输入**：ADS1220 的实际输入/复用器通道；
3. **扫描通道**：一次 `SAMPLE.channels` 中的一项，可能经过多路复用、差分或多次转换。

软件不硬编码 12/16/36，也不假定 36 个单元一定有 36 个 ADC 输入。硬件组需要提供：

- 矩阵单元编号与行列方向；
- 每个扫描通道对应的 ADC 芯片/输入/复用通道；
- 扫描顺序（row-major 或其它）与建立/切换时间。

## 5. 无效通道处理

软件侧规则（已实现于解析器）：

- `valid_mask=false` 的通道可以是 `null` 或占位数字，但**永远不当作零接触**；
- 只在 `valid_mask=true` 的通道上计算显示指标；
- 无效通道计入统计（`invalid_channel_samples` / `frames_with_invalid_channels`），原始帧保留；
- 部分有效帧默认保留整帧，但控制/闭环逻辑必须再次检查有效性。

请硬件组确认：

- 坏通道是固定无效还是动态无效？
- 无效通道的线值用 `null` 还是固定占位值？
- 部分有效帧是否可用，还是必须整帧丢弃？

## 6. 帧序号、时间戳、采样率

软件建议：

- `frame_seq` 同一 `boot_id` 内严格递增；重启后从新值开始；回绕规则需明确。
- `boot_id` 每次启动变化；主机用它检测重启。
- `mcu_time_us` 为 MCU 单调微秒；请说明原点（boot / 上电 / 其它）、是否包含睡眠、抖动。
- `host_received_ns` 由主机 `time.monotonic_ns()` 在收到完整行时写入，不是设备时间。
- `sample_rate_hz` 与实际整帧周期分别记录；请给出标称值、允许抖动、单帧最大延迟。
- 主机不会直接用 MCU 时间减主机时间推断传输延迟；两者时钟域不同。

## 7. 协议版本兼容

- `protocol_version` 是主版本整数；主版本不一致时主机拒绝。
- 删除字段、改变字段语义/单位/时间基准 → 必须提升主版本。
- 新增可选字段可讨论不升主版本，但主机保留原始记录，不据此推断设备能力。
- 固件版本与协议版本分别记录。
- 任何版本规则在双方书面确认前仍是 PROPOSED。

## 8. C-01..C-18 中需要硬件组回答的问题

| 编号 | 问题 | 软件侧当前处理 |
|---|---|---|
| C-01 | 通道数、6×6 单元与物理映射 | 动态配置；不硬编码 36 |
| C-02 | 扫描/复用方式 | 不实现扫描逻辑 |
| C-03 | 三颗 ADS1220 的总线/片选/通道分配 | 只存 `ads1220_id`/`adc_input` 占位 |
| C-04 | 采样率、整帧周期、抖动、同步 | `sample_rate_hz` 可为 null |
| C-05 | 无效通道与部分有效帧策略 | 保留整帧 + valid_mask，不按零 |
| C-06 | 帧序号起点/回绕/重启 | 回退视为错误，重启靠 boot_id |
| C-07 | MCU 时间单位/原点/睡眠 | 只检查非负/递增，不跨时钟相减 |
| C-08 | 错误码、CRC、重试 | 解析 `ERROR.code`，不自动重试控制 |
| C-09 | 版本兼容/弃用 | 主版本严格匹配 |
| C-10 | 传输介质/波特率/编码/边界 | 建议 JSONL，未实现真实 transport |
| C-11 | 原始值单位/基线/标定 | 仅 `ADC_COUNTS`/`UNKNOWN` |
| C-12 | 控制命令/ACK/到位/STOP | 复用现有 S3 协议，ACK≠位置 |
| C-13 | HELLO.channel_config 是否提供 | 未收到则用本地配置并标 UNKNOWN |
| C-14 | 无效通道线值 null/占位 | 两者都接受但需 valid_mask |
| C-15 | contact_score 是否提供/算法 | 可选，缺失显示 UNKNOWN |
| C-16 | 传感器与 S3 是否同一 MCU/串口 | 软件当前按独立源/独立适配器建模 |
| C-17 | 传感器侧心跳/超时 | 主机只做接收新鲜度，不替设备定义 |
| C-18 | 重启时 boot_id 是否变化 | 变化视为重启，不变但序号回退视为错误 |

## 9. 边界

- 软件组不会替硬件组修改 Worktree、固件或扫描逻辑。
- 软件组不会把提案写成 APPROVED，也不会把测试用 SIMULATION 数据当作真实采样。
- 在 C-01..C-18 确认前，真实传感器联调只允许只读采样与回放核对，不进入 AUTO 闭环。
