# 软硬件接口契约（触觉夹爪）

- **状态：PROPOSED v0.1（未生效、未联调；本分支只包含软件侧提议）**
- **唯一约定路径：`docs/INTERFACE_CONTRACT.md`**
- 初版日期：2026-11-12；S1 软件提议更新：2026-11-12
- 责任方：软件组 + 硬件组共同维护
- 本文件在 S1 由软件组补充传感器消息、错误与版本兼容建议；**不代表硬件组已确认，也不代表真实传感器已联调**。协议状态仍为 PROPOSED，未经双方确认不得改为 APPROVED。

> 阅读约定：本文每个字段都标注为 **FACT（已有证据）**、**SW-PROPOSAL（软件组提议）** 或 **PENDING-HW（等待硬件组确认）**。只有 FACT 可直接用于实现；SW-PROPOSAL 只用于主机侧解析器/测试与联调准备，不得据此宣称设备行为。PENDING-HW 不得用猜测值补齐。

## 1. 目的与约束

本文件约定后续软件组与硬件组之间的触觉采集、控制命令、状态、错误与时间信息接口。任何字段在双方书面确认前均视为 **UNKNOWN / 待确认**，不得写成已验证事实，也不得据此启用真实运动。

### 1.1 已确认事实（FACT）

- 旧 ESP32（NodeMCU ESP-32S V1.1，GPIO23，50 Hz，16-bit）稳定固件 `gripper-control-bench-0.9b24.0` 保留为回退。
- ESP32-S3（YD-ESP32-S3 N16R8，GPIO4，50 Hz，14-bit LEDC）固件 `gripper-control-s3-0.9b26.0` 已由用户报告真实机械开合 PASS；精确位置误差与长期稳定性 UNKNOWN。
- 现有控制链路是 UTF-8 JSON Lines、115200 8N1、`protocol_version=1`、`request_id`、有界行长；固件命令与回复见 `docs/GRIPPER_PROTOCOL.md`。软件组已实现 `src/gripper_a/serial_client.py` 与 `src/gripper_a/gripper_controller.py`，PWM Console 复用它们。
- 现有 S3 Bench 固件支持 `PING`、`GET_STATUS`、`BEGIN_BENCH`、`BENCH_PULSE_MODE`、`BENCH_HOLD_MODE`、`BENCH_PULSE`、`BENCH_HOLD`、`HEARTBEAT`、`STOP`、`DISARM`。`BEGIN_BENCH` 不输出 PWM。
- 硬件组 Stage H1 目标为单侧 **6×6 触觉矩阵、36 个感测单元、三颗 ADS1220、旧 ESP32 采集**；这是暂定目标，不是已验证的通道/扫描事实。
- 三颗 ADS1220 **不能直接提供 36 路独立模拟输入**；实际扫描/复用方案仍待硬件组确认。
- 现有 `docs/SENSOR_CONTRACT.md` 是 Stage 0 的 4×4/16 通道 row-major 草案，保留为历史资料；不能直接作为 6×6/36 单元的实现依据。

### 1.2 软件侧提议（SW-PROPOSAL，未实现为设备协议）

软件组在 S1 建议传感器侧使用与现有控制链路一致的 UTF-8 JSON Lines 封装：

- 每行一个 JSON 对象，以 `\n` 结束；单行上限由配置给出（建议 16384 字节，PENDING-HW）。
- 顶层必须包含整数 `protocol_version` 与字符串 `type`；未知 `type` 必须拒绝，不得忽略。
- 必需字段缺失、类型错误、非有限数值、长度不匹配、重复 JSON 键、非法 UTF-8、超长行都必须记录原因并拒绝该行。
- 消息类型：`HELLO`、`SAMPLE`、`STATUS`、`ERROR`。
- 通道数量、矩阵尺寸、ADC 物理输入与矩阵位置全部由 `HELLO.channel_config` 动态描述；主机不得硬编码 12、16 或 36。
- 主机为每帧补充接收时间（`host_received_ns`，基于主机单调时钟）与数据来源标签（LIVE/REPLAY/SIMULATION）；这些字段不来自设备。
- 本提议的类型/字段定义是“可供联调讨论的草案”，不是设备已实现协议。

### 1.3 等待硬件组确认（PENDING-HW）

| 编号 | 待确认项 | 当前状态 |
|---|---|---|
| C-01 | 通道数量、矩阵尺寸及物理映射 | PENDING-HW（6×6=36 为目标） |
| C-02 | 6×6 扫描方式/复用结构 | PENDING-HW |
| C-03 | 三颗 ADS1220 的总线、片选/地址、通道分配 | PENDING-HW |
| C-04 | 采样率、整帧周期、抖动、同步精度、丢帧定义 | PENDING-HW |
| C-05 | 通道有效性与部分有效帧策略 | PENDING-HW |
| C-06 | 帧序号起点、回绕、重启行为 | PENDING-HW |
| C-07 | MCU 时间戳单位/原点/同步方式 | PENDING-HW |
| C-08 | 错误码、校验/CRC、重试策略 | PENDING-HW |
| C-09 | 版本字段与兼容规则 | PENDING-HW |
| C-10 | 传输介质、波特率、编码、消息边界 | PENDING-HW（软件建议 JSONL） |
| C-11 | 原始数值物理意义、单位、基线、标定 | PENDING-HW |
| C-12 | 控制命令与状态语义（目标/实际、ACK 与到位） | PENDING-HW |
| C-13 | `HELLO.channel_config` 是否由设备在启动时提供 | PENDING-HW |
| C-14 | 无效通道的线值（null 或占位数字） | PENDING-HW |
| C-15 | 采样数据是否包含 `contact_score` 及其算法 | PENDING-HW |
| C-16 | 传感器设备与 S3 控制器是否同一 MCU/同一串口 | PENDING-HW |
| C-17 | 传感器侧独立心跳/超时策略 | PENDING-HW |
| C-18 | 传感器重启时 `boot_id` 是否变化 | PENDING-HW |

## 2. 双方职责

| 区域 | 硬件组 | 软件组 |
|---|---|---|
| 传感器与采集 | 矩阵、ADS1220、扫描/复用、接线、供电、采集固件、时序与数据质量 | 接收适配器、有效性处理、记录、回放与分析 |
| 控制执行 | 控制固件、PWM/LEDC 安全限制、设备端超时 | Gripper Adapter、Control Manager、Trial Recorder |
| 协议 | 提供采样、通道、时序、错误与版本事实 | 提供主机侧接口、日志、错误处理与兼容性需求 |
| 共享文件 | 共同评审 `AGENTS.md`、`README.md`、本文件 | 共同评审 `AGENTS.md`、`README.md`、本文件 |

## 3. 传感器消息草案（SW-PROPOSAL）

### 3.1 通用封装

```json
{
  "protocol_version": 1,
  "type": "SAMPLE",
  "device_id": "sensor-esp32-01",
  "boot_id": "8f3c1d2a",
  "frame_seq": 1042,
  "mcu_time_us": 18342011
}
```

| 字段 | 类型 | 说明 | 状态 |
|---|---|---|---|
| `protocol_version` | int | 主版本；主机只接受自己支持的主版本 | SW-PROPOSAL |
| `type` | string | `HELLO` / `SAMPLE` / `STATUS` / `ERROR` | SW-PROPOSAL |
| `device_id` | string | 设备标识，用于日志与多设备区分 | SW-PROPOSAL |
| `boot_id` | string | 每次启动重新生成；用于重启检测 | SW-PROPOSAL（C-18） |
| `frame_seq` | int ≥ 0 | 设备帧序号；同一 `boot_id` 内严格递增 | SW-PROPOSAL（C-06） |
| `mcu_time_us` | int ≥ 0 | MCU 单调时间，单位微秒；原点/是否含睡眠时间 PENDING-HW | SW-PROPOSAL（C-07） |

主机的 `host_received_ns` 由主机在收到整行时写入，使用 `time.monotonic_ns()`，不写入设备数据。**不同时钟域不得直接相减推断传输延迟**。

### 3.2 `HELLO`

```json
{
  "protocol_version": 1,
  "type": "HELLO",
  "device_id": "sensor-esp32-01",
  "boot_id": "8f3c1d2a",
  "firmware_version": "sensor-h1-proposal.0",
  "scan_mode": "UNKNOWN",
  "sample_rate_hz": null,
  "channel_config": {
    "status": "PROPOSED",
    "matrix_rows": 6,
    "matrix_cols": 6,
    "adc_count": 3,
    "scan_mode": "UNKNOWN",
    "channels": [
      {
        "channel_id": 0,
        "adc_input": 0,
        "ads1220_id": 0,
        "mux_channel": 0,
        "matrix_row": 0,
        "matrix_col": 0,
        "enabled": true,
        "unit": "ADC_COUNTS"
      }
    ]
  }
}
```

说明：

- `channel_config.channels` 的长度是该设备的**扫描通道数**，不要求等于矩阵感测单元数。6×6 矩阵可以有 36 个单元但扫描通道数不同；主机不得推断其相等。
- `adc_input` 是 ADC 物理输入编号；`mux_channel`（若存在）是多路复用通道；`matrix_row`/`matrix_col` 是物理位置映射。三者是不同概念，允许为 `null`（UNKNOWN）。
- `unit` 只是描述性标签；本轮软件只接受 `ADC_COUNTS`（原始计数）与 `UNKNOWN`，不把计数换算为电阻、力或角度。
- `HELLO` 不是 `SAMPLE` 的替代；未收到 `HELLO` 前，主机可以使用显式配置启动，但必须把映射标为 UNKNOWN/PROPOSED。

### 3.3 `SAMPLE`

```json
{
  "protocol_version": 1,
  "type": "SAMPLE",
  "device_id": "sensor-esp32-01",
  "boot_id": "8f3c1d2a",
  "frame_seq": 1042,
  "mcu_time_us": 18342011,
  "channels": [812, 806, null, 799],
  "valid_mask": [true, true, false, true],
  "channel_ids": [0, 1, 2, 3],
  "contact_score": null
}
```

| 字段 | 类型 | 规则 | 状态 |
|---|---|---|---|
| `channels` | array | 长度必须等于 `channel_config.channels` 长度；有效通道为有限数值，无效通道建议为 `null` | SW-PROPOSAL（C-14） |
| `valid_mask` | array[bool] | 与 `channels` 同长同序；`false` 表示该通道数据无效 | SW-PROPOSAL（C-05） |
| `channel_ids` | array[int] | 可选；若提供，必须与配置通道顺序一致 | SW-PROPOSAL |
| `contact_score` | number/null | 设备侧接触指标；算法/单位/量程 UNKNOWN | SW-PROPOSAL（C-15） |

**无效通道不得按“无接触”或零值处理。** 主机计算任何指标时只能使用 `valid_mask=true` 的通道，并保留 `valid_mask`。

### 3.4 `STATUS`

`STATUS` 用于应答/周期上报设备状态，建议字段：

```json
{
  "protocol_version": 1,
  "type": "STATUS",
  "device_id": "sensor-esp32-01",
  "boot_id": "8f3c1d2a",
  "firmware_version": "sensor-h1-proposal.0",
  "uptime_ms": 18342,
  "sample_rate_hz": null,
  "scan_mode": "UNKNOWN",
  "channel_count": 4,
  "sensor_state": "STREAMING",
  "last_frame_seq": 1042,
  "last_error": null
}
```

`STATUS` 不包含“已采集到真实接触”的断言；`sensor_state` 只是设备自述。主机状态由主机根据自己的接收情况独立判定。

### 3.5 `ERROR`

```json
{
  "protocol_version": 1,
  "type": "ERROR",
  "device_id": "sensor-esp32-01",
  "code": "ADC_TIMEOUT",
  "message": "ADC conversion timed out",
  "request_id": null,
  "fatal": false
}
```

| 字段 | 说明 | 状态 |
|---|---|---|
| `code` | 大写机器可读标识；具体枚举 PENDING-HW | SW-PROPOSAL |
| `message` | 人类可读说明，不得作为控制依据 | SW-PROPOSAL |
| `request_id` | 若错误对应请求则回填；否则 `null` | SW-PROPOSAL |
| `fatal` | 设备是否认为需要重启；主机不能只凭该字段自动恢复 | SW-PROPOSAL |

## 4. 主机侧校验与流状态（SW-PROPOSAL）

### 4.1 单帧校验

主机必须拒绝并记录以下情况：

| 情况 | 主机行为 | 错误码 |
|---|---|---|
| 非法 JSON、重复键、非法 UTF-8 | 拒绝该行 | `INVALID_JSON` |
| 超长行 / 无界缓冲 | 丢弃并记录 | `FRAME_TOO_LARGE` |
| 缺少必需字段 | 拒绝 | `MISSING_FIELD` |
| `protocol_version` 不匹配 | 拒绝 | `PROTOCOL_VERSION` |
| 未知消息类型 | 拒绝 | `UNKNOWN_MESSAGE` |
| `channels`/`valid_mask` 长度与配置不一致 | 拒绝整帧 | `LENGTH_MISMATCH` |
| 有效通道出现 NaN/Inf/非数值 | 拒绝整帧 | `INVALID_VALUE` |
| `valid_mask` 非布尔或与通道不同序 | 拒绝整帧 | `INVALID_MASK` |
| 未知/无效 `channel_id` | 拒绝整帧 | `INVALID_CHANNEL` |
| `frame_seq`/`mcu_time_us` 类型或范围非法 | 拒绝整帧 | `INVALID_VALUE` |

数据无效与设备离线必须区分：

- **无效数据**：链路仍在、收到一行但校验失败；主机记录 `INVALID_FRAME`，不更新“最后有效帧”，也不产生控制动作。
- **设备离线/无数据**：连接关闭、传输异常，或超过配置的新鲜度窗口没有收到任何完整行；主机状态为 `STALE`/`OFFLINE`，不得把最后一帧继续当当前接触状态。

### 4.2 多帧/会话状态

| 情况 | 判定 | 主机行为 |
|---|---|---|
| 同 `boot_id`，`frame_seq` 等于上一帧 | 重复帧 | 拒绝 (`DUPLICATE_FRAME`) |
| 同 `boot_id`，`frame_seq` 小于上一帧 | 序号回退 | 拒绝 (`SEQUENCE_REGRESSION`) |
| 同 `boot_id`，`frame_seq` 跳号 | 丢帧 | 接受当前帧，记录 `FRAME_GAP` 与丢失计数 |
| `boot_id` 变化 | 设备重启 | 记录 `DEVICE_RESTART`，重置序号/时间基线，接受新会话首帧 |
| 同 `boot_id`，`mcu_time_us` 不递增 | 时间戳异常 | 拒绝 (`TIMESTAMP_ANOMALY`) |
| `host_received_ns` 回退 | 主机时钟异常 | 记录 `HOST_CLOCK_ANOMALY`，拒绝该帧用于控制 |

帧序号回绕规则尚未确认（C-06）。在确认前，主机把回退视为错误而不是回绕。

### 4.3 新鲜度

建议每个传感器配置一个有界新鲜度窗口（SW-PROPOSAL，具体值 PENDING-HW）。超过窗口无完整帧：

- 主机传感器状态置 `STALE`；
- 记录 `SENSOR_STALE` 事件；
- 不得用旧帧继续闭环，不得据此继续夹紧；
- 不自动重连、不自动恢复运动。

## 5. 控制接口（事实 + 软件抽象）

### 5.1 复用现有 S3 协议（FACT）

软件组不新增第二套串口控制实现。`tactile_gripper.devices.GripperAdapter` 复用现有 `src/gripper_a/gripper_controller.py` / `src/gripper_a/serial_client.py`，实际写入者只有 `BenchController`。

| 软件抽象动作 | 实际固件命令 | 说明 |
|---|---|---|
| `QUERY_STATUS` | `GET_STATUS` | 只读；不刷新运动许可 |
| `BEGIN_SESSION` | `BEGIN_BENCH` + `BENCH_HOLD_MODE` | 建立 Bench 会话；`BEGIN_BENCH` 不输出 PWM |
| `SET_PWM` | `BENCH_HOLD`（人工模式） | 目标脉宽；ACK 只表示逻辑接受，不是机械位置 |
| `STOP` | `STOP` | 撤销后续输出许可并尝试禁用 PWM；不保证保持或释放 |
| `DISARM` | `DISARM` | 撤销许可；不保证机械停止 |
| `HEARTBEAT` | `HEARTBEAT` | 只刷新通信存活；不延长旧运动许可 |
| `STOP_UPDATES` | 无 | 纯主机行为：不再提交新目标；不等于设备已停止 |
| `HOLD` | 无已验证命令 | 软件接口显式拒绝；不得把持续 PWM 称为“保持夹持” |
| `RELEASE` | 无已验证命令 | 软件接口显式拒绝；释放是独立运动，可能掉落负载 |

### 5.2 语义边界

- **请求发送 PWM**、**成功写入串口**、**设备 ACK**、**机械爪实际位置** 是四个不同事实。`ControlEvent` 分别记录 `stage`、`serial_write_ok`、`device_ack`，而 `actual_pwm_us`/实际位置始终为 `null`（UNKNOWN），不得复制目标值。
- `STOP` 的具体输出行为已按 `firmware/gripper_control/SafetyCore.h::command` 源码确认（FACT）：`STOP`/`DISARM` 先清除 trial/bench/hold/mech 许可，再调用 `output.off()`；`LedcOutput::off()` 写 `ledcWrite(GPIO, 0)` 并 `ledcDetach`。成功时 state=`DISARMED`，失败时 state=`FAULT`、`outputUnknown`，不承诺保持力、不承诺释放，且不是硬件急停。
- **STOP 与 DISARM 的 FAULT 行为不同（FACT）**：若固件已经处于 `FAULT`，`STOP` 只重试 `output.off()`；成功后仍返回 ACK 但 **state 仍为 FAULT**，不会清除故障。`DISARM` 走通用撤销分支，`output.off()` 成功时把 state 置为 `DISARMED`。主机不得把 STOP 的 ACK 当作故障已清除。
- 现有 S3 固件已按源码确认存在上述路径，但真实机械停止、保持、释放与掉落行为仍 **NOT_TESTED**；软件 STOP 仍不是硬件急停。
- 停止更新目标（`STOP_UPDATES`）、停止 PWM 输出（`STOP`）、保持夹持（无已验证命令）、松开（无已验证命令）在软件接口与 UI 中必须分开显示。
- 现有 PWM 范围来自 `config/gripper_s3.json` 的 `bench_min_us`/`bench_max_us`（500–2500 μs，Bench 配置），仅是配置值，**不是机械安全边界**；`safe_min_us`/`safe_max_us` 仍为 `null`。

## 6. 版本兼容规则（SW-PROPOSAL）

1. `protocol_version` 是主版本整数；主版本不一致时主机必须拒绝连接/拒绝消息，不能猜测字段。
2. 新增可选字段可在不提升主版本的情况下讨论，但主机必须把未知字段保留在原始记录中，且不得据此推断设备能力。
3. 删除字段、改变字段语义、改变单位、改变时间基准属于不兼容变更，必须提升主版本并保留旧版本处理策略。
4. 固件版本与协议版本分别记录；版本字符串不得作为能力探测的唯一依据。
5. `HELLO` 是能力/通道配置的协商入口；未收到 `HELLO` 时主机只能使用显式本地配置，并标注 `config_source=LOCAL_PROPOSED`。
6. 状态块（`STATUS`）与样本块（`SAMPLE`）的版本必须一致；混合版本会话视为错误。
7. 任何兼容性规则在双方书面确认前都是 PROPOSED，不能据此拒绝已确认的旧固件行为。

## 7. 数据来源隔离（SW-PROPOSAL，主机已实现）

| 来源 | 含义 | 允许控制真实硬件 | 保存位置 |
|---|---|---|---|
| `LIVE` | 真实设备/真实传感器 | 是（仍需逐次授权） | `data/real/`、`logs/real/` |
| `REPLAY` | 读取已保存数据 | **否** | 只读；不写真实实验目录 |
| `SIMULATION` | 合成/测试数据 | **否**（只能驱动模拟适配器） | `data/simulated/`、`logs/simulated/` |

- 传感器帧、控制事件、Trial 元数据都必须带来源标签。
- REPLAY 会话不得调用任何真实串口写入；软件在 Adapter/Core 两层拒绝。
- SIMULATION 不得写入 `data/real/`；Trial 目录由来源决定，不能由调用者任意指定。
- 测试样本必须标 `TEST`/`SIMULATION`，不得计入真实实验 Trial。

## 8. 变更流程

1. 任一方在本文件提出变更（字段、语义、版本、待确认项）。
2. 双方评审并明确仍为 UNKNOWN 的部分；不得把未验证假设写成事实。
3. 更新状态与日期；重大不兼容变更提升版本号。
4. 经审查后合入 `main`；两个功能分支同步该共享基线。
5. 涉及真实硬件的行为变更，仍须单独的接线/上电/烧录/运动授权。
6. 软件分支的实现只能作为“按提议实现的解析器/测试”，不能反过来证明协议已被硬件确认。

## 9. 与既有文档的关系

- `docs/GRIPPER_PROTOCOL.md`：现有控制协议（FACT），本文件不修改其已验证行为。
- `docs/FIRMWARE_PROTOCOL_DRAFT.md`：Stage 0.7 草案，保留追溯。
- `docs/SENSOR_CONTRACT.md`：Stage 0 的 4×4/16 通道草案，保留追溯；不作为 6×6/36 单元或新协议的最终依据。
- `docs/STAGE_S1_S2A_REPORT.md`：S1/S2-A 实现与测试报告，记录哪些是实现、哪些只是提议。
- `docs/PROTOCOL_COLLABORATION.md`：面向硬件组的简洁协作摘要（最小 HELLO/SAMPLE 字段、感测单元与 ADC 输入区别、C-01..C-18 问题清单）。

## 10. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-12 | PROPOSED v0.1 (S0) | 建立占位草案与 C-01..C-12 待确认项 |
| 2026-11-12 | PROPOSED v0.1 (S1 software) | 增加 HELLO/SAMPLE/STATUS/ERROR 草案、通道配置、帧序号/重启/时间戳规则、版本兼容、数据来源隔离；C-13..C-18 新增；状态仍为 PROPOSED |
| 2026-11-13 | PROPOSED v0.1 (S2-B software) | 按固件源码补充 STOP/DISARM 的 output.off、FAULT 不清除与 DISARM 清除行为；仍为 PROPOSED，等待硬件组评审 |
