# P3-B1｜测试 A：无舵机负载的 S3 PWM + UART 隔离（2026-11-16）

状态：**PASS（VERIFIED_REAL）**。在 PM15S 5V 关闭、舵机信号线断开、保持现有修复固件的条件下，
GPIO4 输出 1500/1450 μs PWM，同时完成无 PWM 基线与 120 次 PWM 期间 HEARTBEAT。
**未重烧、未改 PWM 范围、未自动重试、未修改 Dashboard/FSR。**

## 1. 前置条件（操作者确认）

- PM15S 独立 5V 电源：**关闭**。
- 舵机信号线：**已从 S3 GPIO4 断开**，避免反向供电。
- S3 固件：`gripper-control-s3-0.9b26.0` / `bd039a8…`（TX 背压修复版），**不重烧**。
- 端口：`/dev/cu.usbserial-A5069RR4`。
- 测试期间无 Dashboard、无 FSR 采集、无其他串口进程。

## 2. 测试序列

1. `GET_STATUS`（初始，应 DISARMED）
2. `BEGIN_BENCH`（GRIPPER_ASSEMBLED）
3. `BENCH_HOLD_MODE`
4. **无 PWM 基线**：20× `HEARTBEAT`
5. `STATUS`
6. `BENCH_HOLD 1500`
7. **1500 期间**：60× `HEARTBEAT`
8. `BENCH_HOLD 1450`
9. **1450 期间**：60× `HEARTBEAT`
10. `STATUS`
11. `DISARM`

## 3. 结果

| 项 | 值 |
|---|---|
| 命令 / 应答 / 匹配 | **151 / 151 / 151** |
| 应答行数 | 151 |
| 应答 NUL 总数 | **0** |
| `corrupt_response` | **0** |
| `COMMUNICATION_ERROR` | **0** |
| `FAULT` | **0** |
| PWM 命令 | 仅 **1500、1450** 各一次 |
| PWM 期间 HEARTBEAT | **120**（1500 段 60 + 1450 段 60） |
| 无 PWM 基线 HEARTBEAT | 20 |
| HEARTBEAT 响应时延 | min 99.52 / median 100.14 / max 101.64 ms |
| BENCH_HOLD 响应时延 | 1500: 127.67 ms；1450: 127.57 ms |
| boot_id | `818fa796cec656fcf625036177475071`（全程未变） |
| 最终状态 | **DISARMED** / `DISABLED_UNMEASURED` / `commanded_pulse_us=null` |
| 启动 banner | 9 条，全部 `boot_or_invalid_json`，0 NUL |

关键点：**151/151 匹配、0 NUL、0 超时、0 FAULT**；1500/1450 的 ACK 均为
`ACTIVE` / `TARGET_COMMANDED` / `PWM_COMMANDED_UNMEASURED`，`commanded_pulse_us` 分别为
1500/1450，且无 `output_api_stage`/写失败/频率失败。GPIO4 的 PWM 输出在舵机完全隔离时
不会破坏 S3 的 JSON 应答。

## 4. 能下的结论与不能下的结论

### 可以确认（VERIFIED_REAL）

- 在舵机电气隔离、GPIO4 仍输出 1500/1450 PWM 的条件下，S3 固件/Serial/UART 路径
  151/151 应答匹配、0 NUL、0 超时、0 FAULT。
- 因此，**“GPIO4 输出 PWM”本身**（在无舵机负载/无反向供电条件下）**不足以**造成此前的
  NUL/超时；S3 的串口写入与 UART 缓冲在该条件下工作正常。
- 测试结束 DISARM 成功，输出禁用状态确认。

### 不能确认（NOT_TESTED）

- 不能据此证明真实 PWM 故障是舵机电流/地弹/EMI；本测试只排除了“纯 GPIO4 PWM + S3 串口”
  这一项。
- 不能说明 1450 后舵机停止是机械限位还是供电/连接问题；本测试中舵机信号线断开，无机械运动。
- 不能证明有舵机动力、无杯状态下也一定复现或消失。

## 5. 对真实 PWM 故障的含义

真实 PWM 故障（1500/1450，舵机动力接通）与测试 A 的差异只剩：

1. 舵机 5V 接通、信号线接通、舵机可能转动/堵转；
2. 舵机电流、地弹、电源线/信号线耦合；
3. 机械负载/限位/杯体接触。

因此下一步应做 **有舵机动力、无杯、机械空载** 的对照（Phase B），而不是继续改固件。

## 6. 下一次最小验证方案（Phase B，当前不执行）

**条件**：PM15S 5V 接通、信号线接回、**不夹杯、机械空载、无堵转**；操作者可立即断电。

**步骤**：

1. 只读 `GET_STATUS`，确认 DISARMED；
2. `BEGIN_BENCH` → `BENCH_HOLD_MODE`；
3. 20× 无 PWM `HEARTBEAT` 基线；
4. `BENCH_HOLD 1500` → 60× `HEARTBEAT`；观察舵机是否运动/到位；
5. `BENCH_HOLD 1450` → 60× `HEARTBEAT`；观察是否运动、停止位置是否可重复；
6. `STATUS` → `DISARM`。

**同时记录**：

- 舵机 5V 在 1500/1450/停止时的电压（万用表或示波器）；
- S3 GND 与舵机 5V GND 的电位差；
- 停止位置的可重复性（空载多次 1500→1450）；
- 所有 TX/RX、NUL、匹配、时延、最终状态。

**判读**：

- 若 Phase B 干净 → 真实故障与**机械负载/堵转/杯体接触**相关，下一步才做有杯轻夹；
- 若 Phase B 出现 NUL → 舵机通电/电流/地/EMI 相关，先修供电/共地/线束，不继续夹杯；
- 若 1450 停止位置不可重复 → 先查连杆/舵机连接，不先改固件。

**约束**：不自动重试 PWM、不扩大超时、不改 PWM 范围、不重烧固件；Phase B 需单独授权。

## 7. 证据

- 原始日志：`evidence/p3b1/private/test_a_no_servo_20261115T173722Z/transport.jsonl`
  SHA-256 `ff7e0c3f59beebf54c08d9abb23db0393b97d191f1368665c161bbe24e3258a5`
- 分析摘要：`evidence/p3b1/private/test_a_no_servo_20261115T173722Z/test_a_analysis.json`
- 脚本输出：`test_a_summary.json` / `test_a_stdout.log`
- 本轮未修改固件、Dashboard、FSR 或 PWM 范围；未进行 Phase B。
