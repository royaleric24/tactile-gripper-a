# P3-B 双日志实时监控（真实 FSR_A + 真实 PWM，只读）

日期：2026-11-16（Asia/Shanghai）
分支：`sw/p3b-live-monitor`
基线：`622ef97`（`hw/p3b1-fsr-real` 已核实 HEAD）
状态：**OFFLINE_VERIFIED**；真实串口/真实 PWM **NOT_TESTED（未在本次执行）**

## 1. 目标与结论先行

在不碰硬件、不产生第二个 PWM 写入者的前提下，让中文 Dashboard 同屏显示：

- 真实 FSR_A 原始 ADC（来自真实采集程序写入的 JSONL）；
- pwm_console 真实 PWM 命令与 ACK 状态（来自真实 `transport.jsonl`）；
- 两者在同一 Trial 下保存、导出 CSV、回放。

实现方式：Dashboard **只读跟随两个日志文件**，不打开任何串口。PWM 仍只由
`scripts/pwm_console.py --real` 写入；FSR 仍只由采集程序打开。

真实硬件联调未执行，等待现场授权。`AUTO_REAL_ENABLED=False` 未改。

## 2. 数据流

```text
ESP32 (FSR, /dev/cu.usbserial-0001)          ESP32-S3 (PWM, /dev/cu.usbserial-A5069RR4)
        │ 独占串口                                     │ 独占串口
        ▼                                              ▼
scripts/capture_fsr_live.py                    scripts/pwm_console.py --real
  fsr/fsr_stream.jsonl                            transport.jsonl
  （host UTC + host_monotonic_ns + raw/message）   （既有 JsonlLog 事件流）
        │                                              │
        └──────────────┬───────────────────────────────┘
                       ▼  只读 tail（不打开串口）
        tactile_gripper.ui --source LIVE --follow-session <dir>
          LogFollowSensorAdapter → 既有严格 V2 解析/校验 → TactileFrame
          LogFollowGripper       → 命令/ACK 状态机 + 只读拒绝
                       │
                       ▼
         同一 Trial：frames.jsonl / events.jsonl / frames.csv / replay.jsonl
```

约束：

- `LogFollowGripper.execute()` 永远抛 `ControlDenied`；Dashboard 的 Apply/STOP 在
  log-follow 下被禁用，`core.request_pwm()`/`core.stop()` 返回 REJECTED 并留事件。
- Dashboard 不导入 pyserial，不打开 `/dev/cu.*`；`tests/test_dashboard.py` 的静态检查
  覆盖这一点。
- 打开网页不会发送任何 PWM；页面只读日志。

## 3. 会话目录与启动

```text
logs/real/sessions/session_<UTC>_<id>/
  session.json            # 端口、URL、写入者、开始/结束时间
  transport.jsonl         # pwm_console（既有格式）
  fsr/fsr_stream.jsonl    # 新采集脚本（既有 P3-B1 capture 格式）
  fsr/fsr_stream.summary.json
  fsr_capture.log
  dashboard.log
```

一条命令（一个终端）：

```bash
PYTHONPATH=src:. .venv/bin/python scripts/run_live_monitor.py
```

它依次：启动 FSR 采集 → 等 HELLO → 启动只读 Dashboard → 在当前终端运行
`pwm_console --real --log-dir <session>`。console 退出后自动收尾、结束 Trial、
打印 CSV 路径。只观察不控制：

```bash
PYTHONPATH=src:. .venv/bin/python scripts/run_live_monitor.py --no-console
```

## 4. PWM 状态语义（不伪造）

| 状态 | 触发 | UI |
|---|---|---|
| `NO_PWM` | 日志中没有 PWM/STOP 命令 | 目标 `—`，灰色 |
| `SENT_UNACKED` | 有 `COMMAND`，3 s 内无匹配应答 | 显示目标，橙色“已发送 · 等待 ACK” |
| `ACKED` | 同一 `request_id` 的 `MATCHED` ACK + `output_state=PWM_COMMANDED_UNMEASURED` | 绿色“已 ACK”；**仍不是实测位置** |
| `TIMEOUT` | `COMMUNICATION_ERROR` 含 timeout | 橙色“未确认（ACK 超时）” |
| `UNCONFIRMED` | `IGNORED corrupt_response` 且随后无 ACK | 橙色“未确认（应答损坏）” |
| `FAILED` | 设备 `ERROR` 或异常 | 红色“失败” |
| `ACK_STALE` | ACK 后日志超过 3 s 未更新 | 不显示为当前输出 |
| `OUTPUT_OFF` | STOP/DISARM 已 ACK | `—`，“输出已关闭（STOP ACK）” |
| `STOP_UNCONFIRMED` | STOP/DISARM 未 ACK | `—`，“STOP 未确认” |
| `OFFLINE` | `CLOSED`/`CONTROLLER_CLOSED` | 显示最后 `output_state`，明确“不是当前机械状态” |

“已发送”只代表日志有 `COMMAND`（`TX` 在写串口前记录，不作为送达证据）；“已 ACK”只代表
收到匹配 `request_id` 的应答。`actual_pwm_us` 永远为 `None`。

每次 console 会话（含日志轮转/重连后的新 `CONNECTED`）会重置目标与表格，避免把上一会话
的 ACK 目标当作当前输出。

## 5. 时间对齐与精度

- 两条流都记录 `host_time_utc` + `host_monotonic_ns`（同一台 Mac、同一次开机）。
- 统一时间轴用记录里的 `host_monotonic_ns` 求差，不重新打时间；绝对时间显示各记录 UUID。
- 精度限制：FSR 约 60 Hz（16 ms/帧）；PWM 是命令写入时刻；JSONL `flush()` 落盘为毫秒级。
  两者不是硬件同步采样，**不能据此计算亚毫秒级延迟**。
- 帧的 `pwm_target_us` 用帧时间戳回溯“该时刻仍在生效的命令”（STOP 之后为 None），不是
  记录时恰好最新的目标。

## 6. FSR 数据质量

- 只显示 ADC counts 与相对变化；不换算牛顿/摩擦力/杯重。
- `channel_flags`：`0x04 NEGATIVE_SINGLE_ENDED` 显示为“近零负计数/零点噪声”；`0x20 NO_DATA`
  显示为无效通道。负 counts 原样显示，不截断成 0。
- 无效帧在曲线中为空隙（`connectNulls=false`），不是零。
- 行级容错：半行 JSON 保留到下一次补全；超长行丢弃并计数；文件截断/轮转从新文件重读并
  计数；NUL/坏 JSON 计入 `bad_lines`/NUL 统计，不终止数据流。
- 大文件后加入时，从文件头 1 MB 提取 HELLO（通道配置），再从最近 4 MB 窗口读取帧，避免
  缺少 `channel_config` 或从头重放数十分钟。
- 日志 3 s 不更新 → 传感器 `STALE`，PWM 卡片同步显示“STALE”，曲线末端标注不是实时数据；
  console `CLOSED` → 控制器 `OFFLINE`。

## 7. 启动后非预期闭合：离线审计

对象：最新真实会话 `logs/real/bench/d499e6405e264e20a5f92e7acf20bca8/transport.jsonl`
（2026-11-15 18:18:05Z–18:19:06Z，298 行，操作序列与用户描述一致：
1500/1300/1100/1000/900/1200/1050/1040/STOP/DISARM）。

事实：

1. `CONNECTED` 18:18:05.622Z；`STARTUP_WAIT` 2 s；`STARTUP_READY` 18:18:07.626Z。
2. 第一条 RX 是 ESP-ROM：`rst:0x1 (POWERON)`、`boot:0x8`。同一时刻首个 `GET_STATUS`
   应答的 `uptime_ms=1920`（18:18:07.72Z），即 **S3 在 18:18:05.8 左右启动**，与打开
   串口几乎同一时刻。`serial_client.py` 的注释也记录了“打开 CP210x 可能复位 ESP32，
   即使 DTR/RTS 已释放”。因此“打开 console 触发 S3 复位”有日志证据。
3. 在用户第一次输入 1500 之前（18:18:07–18:18:24，约 17 s），日志只有
   `GET_STATUS`、`BEGIN_BENCH`、`BENCH_HOLD_MODE`、3 次 `HEARTBEAT`；**没有任何
   `BENCH_HOLD`/`BENCH_PULSE` 命令**。首个 PWM 是 18:18:24.017Z 的 1500。
4. 53/53 COMMAND 全部 MATCHED；本会话 0 NUL、0 corrupt_response、0 timeout、0 FAULT；
   最终 `DISARMED / DISABLED_UNMEASURED / commanded_pulse_us=null`。
5. 代码审计：`GripperController.connect()` 只发 `GET_STATUS`；`begin()`/
   `select_mode()` 只发 `BEGIN_BENCH`/`BENCH_HOLD_MODE`；`close(disarm=True)` 只发
   `DISARM`；Dashboard 自动 PWM 仅存在于 `--demo`（SIMULATION dry-run，且被
   `_demo_setup` 的 source 检查拦截）；`run_simulation_demo.py` 同为 SIMULATION。
   没有“重连自动恢复旧目标”的路径；`target/last_pulse` 在 connect/stop/disarm/close 清空。

结论（按证据强度）：

- **可以排除**（本会话）：主机/console/Dashboard 在闭合前下发了 PWM 命令。
- **观察到的**：console 打开串口时 S3 复位；复位后 PWM 外设未驱动。
- **未验证的机制（LEADING_HYPOTHESIS，不是根因）**：S3 复位/未授权期间舵机失去 50 Hz
  信号或被断电，机械爪在弹簧/残余位置下闭合；舵机 5 V/共地/线束/EMI、上电毛刺、机械
  失持均不能排除。
- 本阶段不通过真实机械动作复现，也不新增自动开爪/自恢复/端点扫描。

## 8. 测试

```bash
PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests     # 全套
PYTHONPATH=src:. .venv/bin/python -m unittest tests.test_log_follow   # 新增 27 项
```

新增覆盖：正常会话、ACK-less、STOP 未确认、重复应答、心跳不产生 PWM 事件、陈旧 ACK、
轮转/重连、半行、截断、超长行、NUL、缺 HELLO、mid-file attach、0x04/负 counts、CSV/回放、
Dashboard 启动（真实 HTTP 200，无 Traceback）。

离线验证（不提交真实数据）：用 P3-B1 私有真实日志跑适配器，`d499e640` 解析出
8 条 PWM 事件（1500…1040）全部 ACK、0 NUL、最终 `OUTPUT_OFF`；旧 FSR capture 解析出
1,719 帧、末帧 −996 counts、flag `0x04`，与原始记录一致。

## 9. 明确未做

- 未打开真实串口、未发 PWM、未烧录、未做机械动作、未启用 AUTO。
- 未在真实硬件上验证 FSR 与 PWM 的同会话时间对齐（只验证了格式与主机时钟来源）。
- 未验证 log-follow 下的真实 Trial 长时间写入（仅离线合成/私有日志回放）。
- 未把 ACK 当成位置/夹持力；未把 counts 换算成力。
