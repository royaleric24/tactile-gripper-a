# P3-B1｜S3 控制台 response_timeout 诊断与 TX 背压修复（2026-11-16）

状态：**根因已定位、最小修复已离线编译通过；真实 S3 复测尚未执行（等待重烧授权）**。
两次失败会话均未发送 PWM、未产生 `BENCH_ACTION`、未做机械运动。

## 1. 两次失败会话的真实时间线（UTC）

### 会话 1：`99f2a8023a344652b1a5c4e18e2756a6`

| UTC | 事件 | 命令 / 应答 | request_id / 状态 |
|---|---|---|---|
| 16:28:53.723 | COMMAND | GET_STATUS seq 1 | `1fd165d3…` |
| 16:28:53.820 | RESPONSE | STATUS | state=DISARMED, fault=BOOT |
| 16:29:47.926 | COMMAND | GET_STATUS seq 2 | `cbe5f25a…` |
| 16:29:48.024 | RESPONSE | STATUS | state=DISARMED |
| 16:29:48.025 | COMMAND | BEGIN_BENCH seq 3 | `a1ed8bbc…` |
| 16:29:48.131 | RESPONSE | ACK | state=ARMED, fault=GRIPPER_ASSEMBLED_AUTHORIZED |
| 16:29:48.131 | COMMAND | BENCH_HOLD_MODE seq 4 | `6a08282b…` |
| 16:29:48.231 | RESPONSE | ACK | state=ARMED, fault=BENCH_HOLD_SELECTED |
| 16:29:49.167–16:30:16.348 | COMMAND/RESPONSE | HEARTBEAT seq 5–29 | 全部匹配 ACK，state=ARMED |
| **16:30:17.482** | **COMMAND** | **HEARTBEAT seq 30** | **`e4fddfe2f3f749f5b405adc071747545`** |
| **16:30:17.581** | **RX（损坏）** | **ACK，950 B，12 个 NUL** | request_id 仍是 `e4fddfe2…`，state=ARMED，last_sequence=30 |
| 16:30:20.577 | COMMUNICATION_ERROR | `response_timeout` | 主机侧 FAULT，output=UNKNOWN |

### 会话 2：`297580c6c93a4978921634193f34d3c6`

| UTC | 事件 | 命令 / 应答 | request_id / 状态 |
|---|---|---|---|
| 16:31:43.852 | COMMAND | GET_STATUS seq 1 | `85026bb1…` |
| 16:31:43.948 | RESPONSE | STATUS | state=DISARMED, fault=BOOT |
| 16:31:45.725 | COMMAND | GET_STATUS seq 2 | `75f5a68a…` |
| 16:31:45.823 | RESPONSE | STATUS | state=DISARMED |
| 16:31:45.823 | COMMAND | BEGIN_BENCH seq 3 | `7854715a…` |
| 16:31:45.928 | RESPONSE | ACK | state=ARMED, fault=GRIPPER_ASSEMBLED_AUTHORIZED |
| **16:31:45.928** | **COMMAND** | **BENCH_HOLD_MODE seq 4** | **`4d0c5503cd794368b2b171fa20c57e17`** |
| **16:31:46.027** | **RX（损坏）** | **ACK，948 B，13 个 NUL** | request_id 仍是 `4d0c5503…`，state=ARMED，last_sequence=4 |
| 16:31:49.026 | COMMUNICATION_ERROR | `response_timeout` | 主机侧 FAULT，output=UNKNOWN |

关键时序：会话 2 的 `BENCH_HOLD_MODE` 在 `BEGIN_BENCH` ACK 后 **约 0.00004 s** 发出，ACK（962 B）仍在 TX 缓冲区中；下一次应答只有约 900–949 B 空间。

## 2. 超时前最后命令与故障分类

| 会话 | 最后命令 | request_id | 超时前 RX | 分类 |
|---|---|---|---|---|
| 1 | HEARTBEAT seq 30 | `e4fddfe2f3f749f5b405adc071747545` | 950 B ACK，**12 个 NUL**，首个 NUL 偏移 103 | **RX 内容损坏（不完整）** |
| 2 | BENCH_HOLD_MODE seq 4 | `4d0c5503cd794368b2b171fa20c57e17` | 948 B ACK，**13 个 NUL**，首个 NUL 偏移 595 | **RX 内容损坏（不完整）** |

结论：

- **不是完全没有 RX**：两次都收到了完整长度附近的 ACK。
- **不是 request_id 不匹配**：损坏行中的 `request_id` 与最后命令完全一致；JSON 解析在匹配前就失败。
- **不是固件重启**：失败时刻没有 ESP-ROM 启动 banner，`boot_id` 与之前的 ACK 相同（`9359bf2c…` / `0d938804…`）；启动 banner 只出现在连接初期。
- **不是设备 FAULT**：损坏 ACK 中 `state=ARMED`、`fault_reason=BENCH_HOLD_SELECTED`、`output_state=DISABLED_UNMEASURED`；主机的 FAULT 是本地 3 s 超时后的状态。
- **是 TX 背压导致的 NUL 空洞**：应答在 JSON 中间出现 12/13 个 `0x00`，尾部仍完整；`json.loads` 报 `Invalid control character`，主机按 `boot_or_invalid_json` 丢弃，等待 3 s 后 `response_timeout`。

## 3. 根因

`firmware/gripper_control/gripper_control.ino` 的 `respond()` 原来使用固定阈值：

```cpp
if (Serial.availableForWrite() < 900) { safety->fault("TX_BACKPRESSURE"); return; }
serializeJson(d, Serial); Serial.println();
```

实测正常 ACK/STATUS 长度为 **942–963 B**（不含 CRLF），而阈值只有 900 B。当 TX 缓冲区剩余 900–949 B 时：

1. 检查通过；
2. `serializeJson` 写入约 950 B，超出可用空间；
3. 串口输出出现 12/13 B 的 NUL 空洞，JSON 中间被破坏；
4. 主机 `SerialClient.exchange` 解析失败，记录 `IGNORED boot_or_invalid_json`，不匹配 request_id；
5. 3 s 后 `response_timeout`，`BenchController` 关闭串口并置主机侧 FAULT。

第二个缺陷：当 `availableForWrite() < 900` 时，原代码只调用 `safety->fault()` 并 `return`，**不向主机返回任何 ERROR**；主机只能等到超时，看不到具体原因。

主机侧 `SerialClient` 的匹配逻辑本身正确：它按 `protocol_version`、`request_id`、`firmware_version` 匹配，并在 JSON 解析失败时继续等待；`BenchController` 在 `BEGIN_BENCH` 后立即调用 `select_mode()` 发送 `BENCH_HOLD_MODE`，这是最容易触发背压的连续命令时序。问题不在超时值，而在设备端 TX 空间预留不足。

## 4. 最小修复

### 固件

- 不再使用固定 900 B 阈值，改为按实际序列化长度预留：
  `const size_t need = measureJson(d) + 2;`（JSON + CRLF）。
- `waitForTxSpace(need, 150 ms)`：有界等待 TX 缓冲区腾出足够空间。按 115200、约 950 B ≈ 82 ms，150 ms 小于主机 3 s 超时。
- 若仍不足或帧超过 1800 B：尝试发送一条紧凑的匹配 `ERROR`（`TX_BACKPRESSURE`，含 request_id），再 `safety->fault()`；不再把半帧写入缓冲区。
- 保留 `Serial.setTxBufferSize(2048)`、FAULT、STOP/DISARM 和超时保护，未删除任何通信保护。

### 主机诊断

`src/gripper_a/serial_client.py` 对“长且以 `{"protocol_version"` 开头但 JSON 解析失败”的行记录：

```
IGNORED reason=corrupt_response length=<n> nul_count=<n>
```

不再与 boot 文本混为 `boot_or_invalid_json`。解析失败后的重同步/3 s 超时行为不变，没有修改超时参数。

## 5. 离线验证

- `python3 scripts/build_firmware.py s3`：**PASS**。
- 修复后 app：`bd039a8ae54bb908c3d8afefcf1eb60326ff7c80d9fd3cca9620faec05cb48ee`（317840 B）。
- 新增 `tests/test_serial_client.py::test_corrupt_long_response_is_logged_and_can_resync`：构造 12 个 NUL 的长 ACK，验证主机记录 `corrupt_response` 并能在后续有效帧上重同步。
- 全套离线测试：**380 OK，1 skipped（PTY）**。
- 未重新烧录 S3；未发送 PWM。

## 6. 失败实验的 FSR 原始数据

失败会话期间的 FSR 采集（无 PWM、无 `BENCH_ACTION`、无机械运动）：

- 目录：`evidence/p3b1/private/cup_raw_20261115T163014Z/`
- 样本：17,392；有效 17,391；1 条 malformed SAMPLE（frame 10260，已排除统计）
- 时长：281.708 s；实测 61.734 Hz；帧号 1–17393
- 基线中位：1,810 counts；均值 2,226.9；范围 −25,323 … +30,220
- `0x04` 负帧：7,908（近零空载基线的零点噪声）
- 控制台日志：`logs/real/bench/99f2a802…/transport.jsonl`、`logs/real/bench/297580c6…/transport.jsonl`
- 失败证据包：`evidence/p3b1/private/console_failure_20261116/summary.json`

**这不是空杯抓取结果**：两次会话都没有发送 PWM。原始数据保留用于失败复现和基线对照。

## 7. 下一步

1. 需要一次 **重烧授权**：把 `bd039a8…` 烧到 `/dev/cu.usbserial-A5069RR4`，PM15S 独立动力电源断开。
2. 烧录后只做无 PWM 验证：`GET_STATUS` → `BEGIN_BENCH(GRIPPER_ASSEMBLED)` → `BENCH_HOLD_MODE` → 多条 `HEARTBEAT` → `STATUS` → `DISARM`；确认所有应答 JSON 完整、request_id 匹配、无 NUL、无 `corrupt_response`。
3. 真实会话稳定后才通知用户重新运行 `pwm_console.py --target s3`。
4. 不启动 AUTO，不发送 PWM，不合并 PR。

## 8. 证据与边界

| 项 | 状态 |
|---|---|
| 两次超时根因 | **VERIFIED_REAL**（原始 RX + NUL 位置 + request_id/state 字段） |
| 固件修复 | **OFFLINE_VERIFIED**（编译 PASS + 主机定向测试） |
| 真实 S3 修复复测 | **NOT_TESTED（等待重烧授权）** |
| 失败 FSR 原始数据 | **已保存**（无 PWM，非空杯结果） |
| Dashboard LIVE 握手 | **仍未验证**；未提交的尝试性修改保存在 `evidence/p3b1/private/dashboard_handshake_unverified.patch`，不作为空杯前置条件 |
| PWM / 机械运动 / AUTO | **NOT_TESTED**（本轮明确禁止） |
