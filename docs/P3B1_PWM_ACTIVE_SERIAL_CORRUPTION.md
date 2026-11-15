# P3-B1｜真实 PWM 期间串口应答损坏诊断（2026-11-16）

状态：**本轮空杯 MANUAL 未成功；1400 未发送；超时直接原因已确认；PWM 期间 NUL 损坏的
电气机制仍为 LEADING_HYPOTHESIS（待隔离测试）**。未继续发送 PWM、未继续运动。

## 1. 本轮实际时间线（UTC）

| UTC | 事件 | 证据 |
|---|---|---|
| 16:50:51–16:50:56 | GET_STATUS / BEGIN_BENCH / BENCH_HOLD_MODE | 均匹配，ARMED / BENCH_HOLD_SELECTED |
| 16:51:04.790 | `BENCH_HOLD` **1500 μs**，seq 12 | ACK 16:51:04.918，state ACTIVE，`PWM_COMMANDED_UNMEASURED` |
| 16:51:16.506 | `BENCH_HOLD` **1450 μs**，seq 23，request_id `f072a26e…` | ACK 16:51:16.633，state ACTIVE，fault TARGET_COMMANDED，pulse 1450 |
| 16:51:16.6–16:51:24.9 | 1450 保持；多次 HEARTBEAT 均匹配 | 操作者观察：1450 附近机械爪不再运动 |
| 16:51:24.861 | 最后一条 TX：**HEARTBEAT seq 31**，request_id `1584ec4baf6f487eb61c3f759459b7b6` | 不是 1400 |
| 16:51:24.961 | RX 957 B 应答，**7 个 NUL**，首个偏移 364 | `type=ACK`、request_id 与 heartbeat 一致、pulse 1450、last_sequence 31 |
| 16:51:27.869 | 主机 `response_timeout`，关闭串口，主机侧 FAULT | 3 s 超时；不是设备 FAULT |
| 16:56:15 左右 | 只读 STATUS 查询（PM15S 动力断开） | 查询导致端口打开复位；新 boot_id `caff3b25…`，uptime 1919 ms，DISARMED |

## 2. 三项优先结论

### 2.1 1400 是否发送：**没有发送**

完整 console 日志中不存在 `BENCH_HOLD`/`BENCH_PULSE` 且 `pulse_us=1400` 的命令。
最后一条 PWM 命令是 **1450 μs（seq 23）**；最后一条 TX 是 **HEARTBEAT seq 31**。
console 在 16:51:24.961 收到损坏的 heartbeat ACK 后 3 s 超时退出，用户准备输入的 1400
从未到达 S3。终端上是否出现过 1400 的提示不能作为发送证据；日志中没有对应 COMMAND/TX。

### 2.2 `response_timeout` 的直接原因：**heartbeat ACK 被 NUL 损坏**

超时前的 RX：

- 长度 957 B，7 个 `0x00`，首个偏移 364；
- 仍可读出 `type=ACK`、`request_id=1584ec4b…`（与最后 heartbeat 一致）、
  `commanded_pulse_us=1450`、`last_sequence=31`、`boot_id=ba1412…`；
- NUL 出现在 `state`/`fault_reason` 的字符串值中：
  `"state":\x00\x00\x00\x00TIVE"`、`"fault_reason":\x00\x00ARGET_COMMANDED"`；
- `json.loads` 报 `Invalid control character`，主机记录
  `IGNORED reason=corrupt_response length=957 nul_count=7`，不匹配 request_id，等待 3 s 后
  `response_timeout`。

因此：

- **不是没有 RX**；
- **不是 request_id 不匹配**（损坏行中的 request_id 与最后 heartbeat 一致）；
- **不是设备重启**：从 1500/1450 到损坏 ACK，`boot_id` 一直是 `ba1412…`，失败时刻没有 ESP-ROM banner；
- **不是设备 FAULT**：损坏 ACK 仍是 `state=ACTIVE`、`fault=TARGET_COMMANDED`、
  `output=PWM_COMMANDED_UNMEASURED`、`pulse=1450`；主机 FAULT 是本地 3 s 超时后的状态；
- 直接原因是 **PWM 输出期间 S3 的 JSON 应答被 NUL 字节破坏**，主机解析失败后超时。

### 2.3 1450 后机械爪不动：**控制侧已接受并施加 1450；最可能是机械限位/堵转，不是控制拒绝**

1450 的 ACK 明确：

- `state=ACTIVE`、`fault_reason=TARGET_COMMANDED`；
- `output_state=PWM_COMMANDED_UNMEASURED`、`commanded_pulse_us=1450`；
- 没有 `output_api_stage`、`output_write_ok=false`、`READ_MISMATCH`、`FREQ_MISMATCH` 或
  `OUTPUT_API_FAILURE` 诊断字段。

所以 S3 的 `pwm.set()` 没有报告 LEDC 写失败；1450 被接受并作为目标脉宽施加。机械爪不再运动
最可能是 **已到达机械闭合限位/堵转点**，而不是控制层拒绝 1450。需要保留的限制：没有位置/
角度反馈，**精确限位仍是 UNKNOWN**；FSR 只能旁证接触/受力，不能替代机械位置测量。

FSR 对齐（本轮 capture 起点 16:51:15.305，**在 1500 之后、1450 之前**）：

- capture 起点 FSR 已经约 0.5M counts，说明本轮没有干净的空载基线；
- 1450 附近（16:51:16.5–16:51:20）约 0.2–0.9M counts，高于近零基线，符合“闭合/接触/受压”；
- FSR 最大值 2,614,877 counts 出现在 **16:54:17**，已在 16:51:27 超时之后，不能归因于 1450；
- 本轮 **不是空杯抓取成功**：没有 1400，没有完成夹持/释放，没有成功接触判定。

## 3. 为什么无 PWM 64/64 PASS，而真实 PWM 时失败

这是本轮最重要的对比：

| 场景 | 命令/应答 | NUL | 结果 |
|---|---|---|---|
| 2026-11-16 无 PWM 验证 | 64/64 匹配，含 5 次连续会话 + 20 次背靠背心跳 | 应答 0 NUL | PASS |
| 本轮 1500/1450 真实 PWM | 30 条匹配后，第 31 条 heartbeat ACK | **7 NUL** | timeout |

唯一新增因素是 **舵机真实输出并可能在 1450 处堵转**。无 PWM 时 S3 只发 JSON，UART 空闲；
真实 PWM 时舵机电流/地弹/EMI 可能耦合到 S3 的 UART TX 或 USB-UART 链路，造成 NUL 字节。
这解释了：

- 为什么 NUL 出现在 JSON 中间而不是末尾（不是简单的 TX 缓冲区截断）；
- 为什么之前把 TX 预留从 900 B 改为精确 `measureJson(d)+2` 后，NUL 从 12/13 降到 7，
  但仍未消失（固件预留减少了一种诱因，但电气干扰仍在）；
- 为什么 1450 堵转后更容易出现（舵机电流最大、机械/电源扰动最强）。

**这是 LEADING_HYPOTHESIS，不是已证实结论。** 仍需隔离测试区分：

1. **PM15S 动力断开、只发 PWM 命令但舵机不转**：若仍出现 NUL，偏向固件/UART；
2. **PM15S 上电但机械空载（不堵转）**：若 NUL 消失，偏向堵转电流/电源/地弹；
3. 检查独立舵机电源、共地星点、体电容、UART/USB 线与舵机电源线的走向和屏蔽；
4. 可选的主机侧临时缓解：仅对 **heartbeat** 的 `corrupt_response` 做一次重试（不重试 PWM），
   但不能替代电气根因修复。

**不执行**：盲目扩大超时、自动重试 PWM、重发上次目标、继续真实运动。

## 4. 设备状态与 boot_id

- 会话内 boot_id：`ba1412418bb4142df7ca491f1d62eaac`，从连接、1500、1450 到损坏 ACK 未变；
  失败前**没有观察到重启**。
- 16:56:15 的只读 STATUS 查询：`boot_id=caff3b254295c5235ae4ceff4e10de09`、`uptime_ms=1919`、
  `state=DISARMED`、`fault_reason=BOOT`、`output_state=DISABLED_UNMEASURED`。
  **打开 S3 串口会复位板子**，所以新 boot_id/1.9 s uptime 是这次查询造成的，不能当作
  PWM 期间重启的证据；它也说明查询后 S3 通信正常、固件仍是修复版。
- 主机超时后停止心跳，按固件 5 s 通信超时逻辑设备应进入 `COMM_TIMEOUT` FAULT；但该状态
  在只读查询前未被直接观测，查询又复位了板子，因此**post-timeout FAULT 状态为未观测**。

## 5. 证据与数据

- console 日志：`logs/real/bench/2cedfa9ef4e342dda5431b9556a61b44/transport.jsonl`
  SHA-256 `a22cbd6f695be59d3aa4f8ddc4a03b23abfb705b35dd8a4b2cdc59eff3928625`
- 失败证据包：`evidence/p3b1/private/pwm_timeout_20261116/summary.json`
- FSR 原始数据：`evidence/p3b1/private/cup_manual_real_20261115T165114Z/`
  （14,268 SAMPLE、100% valid、231.7 s、max 2,614,877 counts at 16:54:17）
- 本轮未发送 1400，未完成空杯夹持，**不标记为成功**；未继续运动测试。

## 6. 当前判定

| 项 | 状态 |
|---|---|
| 1400 是否发送 | **未发送（VERIFIED_REAL，日志无 1400 COMMAND）** |
| 超时直接原因 | **heartbeat ACK 7 NUL → JSON 损坏 → 3 s timeout（VERIFIED_REAL）** |
| 会话内设备重启 | **未观察到（boot_id 未变）** |
| 设备 FAULT | **超时前无；post-timeout 未观测** |
| 1450 控制接受 | **VERIFIED_REAL（ACK ACTIVE / TARGET_COMMANDED / PWM_COMMANDED_UNMEASURED）** |
| 1450 后不运动 | **LEADING_HYPOTHESIS：机械限位/堵转；精确限位 UNKNOWN** |
| PWM 期间 NUL 机制 | **LEADING_HYPOTHESIS：舵机电流/地弹/EMI；待隔离测试** |
| 空杯抓取 | **NOT_TESTED / 未成功** |
| AUTO / Dashboard LIVE | 未启用 / 未验证 |
