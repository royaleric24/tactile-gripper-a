# P3-B4 真实会话故障分析（S3 ACK NUL 损坏 + FSR 波动）

日期：2026-11-16（Asia/Shanghai）
分支：`sw/p3b-live-monitor`
会话：
- `logs/real/sessions/session_20261116T032219_0fce`
- `logs/real/sessions/session_20261116T032328_a804`
状态：**OFFLINE_ANALYZED**；未打开真实串口、未发 PWM、未烧录。

## 1. 结论摘要

1. 两次 `response_timeout` 的直接原因都是 **S3 的 ACK 在传输中被 0x00 字节替换了字段中间的一段**，JSON 解析失败，
   主机按设计拒绝该应答；不是主机 JSON 解析器误判，也不是设备完全失联。
2. NUL 是**替换**字节而不是简单插入：去掉 NUL 后 JSON 可以解析，但字段名已被破坏
   （0fce：`pwm_first_readback_settle_ms` → `pwm_firettle_ms`；a804：`commanded_pulse_us` → `commanded_puss`）。
   因此**不能**用“剥掉 NUL 再解析”来恢复；必须拒绝并重试。
3. 串口发送缓冲耗尽、主机读取过慢、设备重启/失联都**缺乏证据**：
   - 固件已有 `measureJson(d)+2` + 150 ms 有界等待的 TX 背压保护；两次都没有 `TX_BACKPRESSURE` ERROR；
   - 950 B 应答在 2048 B TX 缓冲内，`serializeJson` 直接流式写串口，不是“先写 950 B 缓冲再清空”；
   - 应答的 `request_id` 完整、`boot_id` 未变、无 FAULT、无重启；设备确实回应了；
   - 主机 115200 逐字节读取，950 B 约 82 ms，远小于 3 s 超时。
4. 与供电/干扰一致的模式（**LEADING_HYPOTHESIS，未证实**）：NUL 是连续 4/13 个 0x00，像短暂的 UART break/地弹；
   两次会话都有舵机供电/连接；Test A（舵机 5V 关、信号线断开）151/151、0 NUL；但 0fce **没有任何 PWM 命令**
   也发生了损坏，所以共同因素更可能是“舵机通电/共地/线束”，而不是“PWM 输出本身”。精确原因 UNKNOWN。
5. 0fce 发生在 `BENCH_HOLD_MODE`（尚无 PWM）；a804 发生在 1500 保持期间的心跳。两次主机都按设计关闭并标记
   `output_state=UNKNOWN`，没有假装知道输出状态。
6. 最小修复（主机侧，不烧录）：
   - HEARTBEAT 与“尚无目标时的 BENCH_HOLD_MODE/BENCH_PULSE_MODE”允许 **有界重试**（默认共 2 次，最多 3 次）；
   - 首次遇到长帧 JSON 损坏时 **快速失败**（约 0.2 ms），不再等 3 s 超时；保持端口打开后重试；
   - **PWM / STOP / DISARM / BEGIN_BENCH 绝不自动重发**；重试耗尽后仍进入 FAULT/UNKNOWN 并关闭端口；
   - 未修改固件，也不需要重烧。缩短 HEARTBEAT ACK 的评估见 §5。
7. 另一处联调缺陷：Dashboard 原先在 `transport.jsonl` 尚未创建时启动，导致两个会话的 PWM 面板都显示
   `PWM 日志: None`，整段 PWM/ACK 没有进入 Trial。已改为等待预期路径并在文件出现后接入（见 §4）。
8. FSR：数据 100% valid、约 61.7 Hz、0/1 丢帧、ADC4 全程 OK；0fce 的大幅变化与“按压/释放”平台一致，
   a804 的高频波动显著高于历史 FSR-only 采集，但不能仅凭 counts 区分机械接触不稳定与电气噪声；力/牛顿/
   摩擦力/杯重 **NOT_SUPPORTED**。

## 2. S3 会话证据

### 2.1 session_20261116T032219_0fce

| 项 | 值 |
|---|---|
| 端口/连接 | `/dev/cu.usbserial-A5069RR4`；打开时 ESP-ROM `rst:0x1 (POWERON)`；boot 等待 2 s |
| boot_id | `b73a811490fbbb9943d83c784c56bcd7`（会话内未变） |
| 命令数/匹配 | 4 COMMAND；3 MATCHED（GET_STATUS×2、BEGIN_BENCH）；BENCH_HOLD_MODE 未匹配 |
| 最后命令 | `BENCH_HOLD_MODE` seq 4，request_id `e8529db8de034d3fa81f63bd63a67938` |
| 发送/应答 | 19:23:09.733586Z / 19:23:09.833430Z（约 100 ms 后） |
| ACK 长度 | **953 B**（同类干净 ACK 952 B） |
| NUL | **13 个，offset 192–204 连续**；`raw` 总长 953，去 NUL 后 940 |
| 被破坏字段 | `pwm_first_readback_settle_ms` → `pwm_firettle_ms`（去 NUL 后 JSON 可解析但字段名错误） |
| 主机处理 | `IGNORED corrupt_response`（length 953, nul_count 13），继续读到 3 s 超时 |
| 超时 | 19:23:12.741123Z `response_timeout`；随后 CLOSED，`output_state=UNKNOWN` |
| PWM | **本会话没有任何 BENCH_HOLD/BENCH_PULSE**；最后 ACK 的 `output_state=DISABLED_UNMEASURED` |
| 设备状态 | 最后有效 ACK：ARMED / BENCH_HOLD_SELECTED / bench_active=true；无 FAULT，boot_id 未变 |

### 2.2 session_20261116T032328_a804

| 项 | 值 |
|---|---|
| 端口/连接 | 同上；打开时 POWERON 复位 |
| boot_id | `3c4f978e4eab1f3529d23c76269209b9`（会话内未变） |
| 命令数/匹配 | 13 COMMAND；12 MATCHED；最后 HEARTBEAT 未匹配 |
| PWM 时间线 | `BENCH_HOLD 1500` seq 8 发送 19:23:44.365556Z，ACK 19:23:44.492522Z（ACTIVE / PWM_COMMANDED_UNMEASURED / 1500） |
| 最后接受心跳 | seq 12 发送 19:23:48.625303Z，ACK 19:23:48.725067Z（ACTIVE / 1500） |
| 最后命令 | `HEARTBEAT` seq 13，request_id `7d9de5bc3eeb4b7a97fcc57ac0de8805` |
| 发送/应答 | 19:23:49.773177Z / 19:23:49.872857Z（约 100 ms 后） |
| ACK 长度 | **957 B**（同一 1500 ACTIVE 的干净 ACK 也为 957 B） |
| NUL | **4 个，offset 897,899,900,901**；去 NUL 后 953 B |
| 被破坏字段 | `commanded_pulse_us` → `commanded_puss`（去 NUL 后 JSON 可解析，但目标字段丢失） |
| 主机处理 | `IGNORED corrupt_response`（length 957, nul_count 4），3 s 后超时 |
| 超时 | 19:23:52.777115Z；CLOSED / `output_state=UNKNOWN` |
| 与 PWM 关系 | 损坏发生在 1500 命令后 **5.38 s**；最后确认 ACTIVE 的心跳在损坏前 **1.15 s**（距 PWM 4.23 s） |
| 输出保护 | 设备 `bench_comm_timeout_ms=5000`；最后一次被接受心跳 48.725 + 5 s ≈ 53.725Z 才由固件超时关闭。主机 52.778Z 已关闭且无法确认，故主机侧 UNKNOWN 是正确状态 |

### 2.3 逐项区分

- **JSON 损坏**：确认。ACK 是完整帧、request_id 正确、长度接近干净 ACK；坏在中间一段 0x00。
- **主机解析**：正确。`json.loads` 拒绝含 NUL 的 JSON；`IGNORED corrupt_response` 记录 length/nul_count；
  如果强行去 NUL，0fce/a804 都会得到“可解析但字段名错误”的对象，不能用于安全判断。
- **串口发送缓冲**：证据不支持。固件 `respond()` 先 `measureJson(d)+2` + `waitForTxSpace`，950 B < 1800/2048；
  未出现 `TX_BACKPRESSURE`；损坏是字段中间的短 NUL 串，不是尾部截断或整段清零。
- **主机读取/缓冲**：证据不支持。逐字节读取，950 B ≈ 82 ms，远小于 3 s；NUL 是实际收到的字节。
- **供电/干扰**：与观察一致但不能证实。NUL 连续且长度 4/13，像 break/地弹；两次都有舵机供电，
  Test A 舵机 5V 关/信号断开时 151/151、0 NUL；但 0fce 没有 PWM 命令，不能把“PWM 输出”当必要条件。
  需要 5V/地电位/电流/示波器或“舵机通电但无 PWM”的对照。
- **真实设备失联/重启**：证据不支持。boot_id 稳定、无 FAULT、无 ESP-ROM 二次重启、ACK 含正确 request_id；
  设备是“回应了但字节损坏”。

## 3. FSR_A 数据分析

数据源：`fsr/fsr_stream.jsonl` 的 SAMPLE（channel 0）。ADC4 全程 `OK`；ADC1–3 为 `NO_RESPONSE`（FSR_ONLY 未接，属预期）。
两会话均无 invalid 帧、无饱和 flag（无 0x01/0x02），flag `0x04` 只出现在近零/负值附近。

| 指标 | 0fce | a804 |
|---|---|---|
| SAMPLE / 有效率 | 3080 / 3080（100%） | 1247 / 1247（100%） |
| 采样率 | 61.74 Hz | 61.69 Hz |
| 帧序 | 1–3080，0 丢帧 | 1–1248，1 丢帧（缺 1 帧） |
| 采样跨度 | 49.87 s | 20.20 s |
| min / max | −188,890 / 6,230,947 | −20,559 / 4,754,595 |
| median | 4,957 | 1,117,686 |
| P5 / P95 | −7,205 / 5,561,476 | 50,557 / 4,000,021 |
| flag 0x04 | 983（31.9%，集中在近零段） | 12（1.0%） |
| 1 s 窗 range 中位 / P90 / max | 20,754 / 3,113,718 / 5,786,750 | 1,731,356 / 2,590,781 / 3,023,046 |
| 跳变 >100k / >500k / >1M / >2M | 610 / 116 / 12 / 2 | 707 / 162 / 28 / 1 |
| 残差 std（5 点中值滤波后） | 111,167 | 239,297 |
| lag-1 自相关 | 0.995 | 0.959 |

对照（历史 FSR-only 采集，**不是同一机械/供电条件**）：old_cup 1 s range 中位 142,472、残差 std 23,310；
old_real 1 s range 中位 202,268、残差 std 84,339。a804 的高频波动约为历史 FSR-only 的 2.8×（残差）
和 8.5×（1 s range）；0fce 的残差接近 old_real，但存在多段大幅接触/释放平台。

时间行为：

- 0fce（t 为 SAMPLE 起点后秒）：0–21 s 近零（约 ±20k）；22–25 s 约 5.2–5.6M；26 s 回落近零；27–30 s 约 2.5M；
  31 s 回落；32–35 s 约 2.2M；36–38 s 约 5.5–5.9M；39–49 s 回落近零。1 s 中位数呈**持续数秒的平台**，
  更像按压/释放/接触状态变化，而不是逐帧随机电气噪声。
- a804：0.7M 起，逐步升到 2–4M；1 s 中位从 0.67M 升到 4.06M（t=18），逐秒 range 常为 1.3–3.0M。
  高频波动在第一条 S3 命令之前（t=0–4）就存在，在 PWM 1500（t≈16）前后没有阶跃式变化；
  损坏心跳（t≈21.3）和超时（t≈24.2）附近有大幅跳变（49.39/50.59–50.67/52.39），但更早也有同类跳变。

与 S3 命令/通信故障的相关性：

- 0fce 的接触平台（t=22–39）**早于**任何 S3 命令（t≈47–50）；S3 失败时 FSR 已回到近零，末段 1 s 中位约 1–3k，
  没有与 BENCH_HOLD_MODE 损坏或超时同步的大跳变。
- a804 的高频波动贯穿整个采集，S3 命令之前已存在；PWM 1500 前后 1 s 中位 2.78M → 2.66M，无明确阶跃；
  损坏/超时附近有跳变但与其它时段同类，不能建立唯一相关。
- 因此**没有证据**把 FSR 大幅波动归因于 S3 命令、PWM 输出或串口通信故障；时间相关性不足以定因。

能否区分正常接触变化与电气噪声：

- 可区分“慢变成分”：1 s 中位数的多秒平台与按压/释放过程一致，可作为**相对接触变化**的显示；
- 不可区分“快变成分”：16 ms 内 1–2.9M counts 的跳变、a804 的 1 s range 1.7M，既可能是手指接触不稳定/机械振动，
  也可能是高阻节点的电气噪声；没有独立力/位移参考，标 **UNKNOWN**；
- 不能从 ADC counts 推断牛顿、摩擦力、滑移或杯重；FSR 只提供 counts 与相对变化。

## 4. 已实施的最小修复

### 4.1 S3 ACK 重试（主机侧，不烧录）

- `SerialClient.exchange(..., close_on_error=False, fail_fast_on_corrupt=True)`：
  - 长帧（`{"protocol_version"` 开头、>128 B）JSON 失败时立即抛 `corrupt_response`，不再等 3 s；
  - 首次失败不关闭端口，保留重试机会。
- `GripperController._send()`：
  - 仅 `HEARTBEAT` 与“尚无目标时的 `BENCH_HOLD_MODE`/`BENCH_PULSE_MODE`”可重试；
  - 默认共 2 次（`serial.heartbeat_retry_attempts`，1–3），间隔 200 ms（`heartbeat_retry_delay_ms`，0–1000）；
  - 每次重试生成新 `request_id`/sequence，日志写 `COMMAND_RETRY`；
  - **PWM/STOP/DISARM/BEGIN_BENCH 不重试**；重试耗尽后仍 `FAULT / output_state=UNKNOWN / close()`。
- 为什么允许 mode 重试：`BENCH_HOLD_MODE` 在 `state=ARMED && !hasTarget` 时是幂等的（不输出 PWM），
  可以救回 0fce 的“模式 ACK 损坏”；有目标后不再重试。
- 真实损坏字节验证：用两会话的原始 corrupt ACK 喂 `SerialClient`，均 **0.2 ms** 抛 `corrupt_response`、
  端口未关闭、NUL 计数 13/4 记录正确；随后可由上层重试。

### 4.2 Dashboard 接入晚创建的 PWM 日志

原缺陷：启动器先启动 Dashboard，`pwm_console` 后创建 `transport.jsonl`；`--follow-session` 启动时只发现 FSR，
于是两个会话的 `dashboard.log` 都是 `PWM 日志: None`，PWM/ACK 没有进入 Trial。

修复：

- `--follow-session` 始终把 `<session>/transport.jsonl` 作为**预期**路径；
- `LogFollowGripper(require_existing=False)` 在文件缺失时进入 `LOG_WAITING`，文件出现后由 tail 自动接入；
- 页面显示“等待 pwm_console 创建 transport.jsonl”，不会打开串口；
- 显式 `--follow-pwm-log` 仍要求文件存在（避免拼写错误静默等待）；
- 新增端到端测试：先只放 FSR，启动 `--follow-record`，再创建 `transport.jsonl`，确认 Trial 事件出现 `SET_PWM 1500`。

### 4.3 FSR 显示平滑（不覆盖原始值）

- 新增 `moving_median(values, window)`；Live 页 FSR 区增加“短窗平滑（仅显示）”开关（默认关闭）。
- 打开后：原始曲线变细/半透明，叠加 5 帧中值平滑曲线；统一时间轴同样显示 raw + smoothed。
- **Trial / CSV / REPLAY 始终保存原始 counts**；平滑只作用于 ECharts option，不改 `fsr_history`/`fsr_timeline` 数据。
- 文案明确“只影响显示、不覆盖历史数据”。

## 5. 是否需要缩短 HEARTBEAT ACK / 重烧

- 评估：HEARTBEAT ACK 约 957 B。缩短到只含 `type/request_id/state/output_state/commanded_pulse_us/fault_reason/bench_active`
  约可降到 200–300 B，理论上把暴露窗口从 ~83 ms 降到 ~25 ms；但：
  - 损坏不是长度阈值现象：942–963 B 的 ACK 多次干净，953/957 B 各损坏一次；4/13 个 NUL 位于任意 offset；
  - 固件 TX 背压保护已存在且无 `TX_BACKPRESSURE`，证据不支持“缓冲耗尽”；
  - 改响应 schema 需要重烧和兼容性验证，不能解决 break/地弹本身，只是降低概率。
- 结论：**本轮不改固件、不重烧**。先用主机侧重试 + 现场 5V/地/电流/线束测量验证；
  若链路稳定后仍反复出现 NUL，再考虑离线实现紧凑 HEARTBEAT ACK（保留旧字段兼容）并单独授权烧录。

## 6. 测试

```bash
PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests
# Ran 435 tests — OK (skipped=1)
```

新增覆盖：

- `tests/test_serial_client.py`：retryable timeout 不关端口；corrupt 长帧快速失败且不关端口。
- `tests/test_gripper_controller.py`：HEARTBEAT 一次重试恢复；两次失败后有界关闭/FAULT；
  PWM 不重试；mode 在无目标时可重试、有目标时不重试；用真实 NUL 替换模式构造的 ACK 恢复。
- `tests/test_log_follow.py`：晚创建 `transport.jsonl` 的 `require_existing=False` 接入；core 端到端记录 SET_PWM。
- `tests/test_dashboard.py`：Dashboard 先启动、后创建 PWM 日志的端到端 SET_PWM 事件。
- FSR 平滑：`moving_median` 保留长度/None；raw 序列不被替换；timeline raw+smooth+PWM。

真实会话 UI 抽样：以 a804 会话启动只读 Dashboard，PWM 面板显示 1500 ACK、最后心跳未确认、NUL 4/应答损坏 1/超时 1，
FSR 1247 帧、61.8 Hz、1/1 有效；Chrome 无头截图 `cards=10 errors=0`，无 Traceback。

## 7. 剩余假设 / 下一次真实测试

**已确认**：主机侧 ACK 因字节被 0x00 替换而解析失败；超时是等待未损坏匹配 ACK 的结果。
**未确认（UNKNOWN）**：0x00 替换的物理机制（UART break/地弹/供电/线束/EMI/CP2102）。
**未确认（UNKNOWN）**：a804 FSR 高频波动的机械 vs 电气来源；不能从 counts 推断力。

下一次真实测试（需现场授权；不自动重发 PWM）：

```bash
cd ~/Developer/research/tactile-gripper-v2-p3b-monitor
PYTHONPATH=src:. .venv/bin/python scripts/run_live_monitor.py
```

建议顺序：

1. **舵机通电但无 PWM** 的会话：只 BEGIN_BENCH + BENCH_HOLD_MODE + 心跳 ≥ 60 s，观察 NUL 是否复现；
2. 1500-only + 心跳 ≥ 60 s；观察 `COMMAND_RETRY` 是否出现、是否恢复；
3. 若稳定，再 1500 → 1040 + FSR 同步；每次记录 `transport.jsonl`、FSR、dashboard/Trial；
4. 同步测量舵机 5V/地电位/电流与线束，必要时示波器看 S3 TX/地弹；链路稳定前不夹杯、不自动重试 PWM。

**不需要重烧固件**：本轮修复均在主机侧（`serial_client.py`、`gripper_controller.py`、Dashboard/launcher）；
固件源码与二进制未改。`AUTO_REAL_ENABLED=False` 未改。
