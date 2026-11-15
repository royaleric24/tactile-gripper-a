# V2 Dashboard 运行手册

日期：2026-11-15。适用于 P3-A 集成。真实硬件操作必须另行授权。

## 1. 环境

```bash
uv sync --locked
PYTHONPATH=src:. .venv/bin/python -V
```

要求 Python >= 3.11（NiceGUI 4）。依赖：NiceGUI 4、pySerial、Python 标准库 JSONL/CSV。

## 2. 启动 Dashboard

```bash
# 默认：SIMULATION 数据源，S3 OFFLINE，SENSOR WAITING，不发任何设备命令
PYTHONPATH=src:. .venv/bin/python -m tactile_gripper.ui --no-browser --port 8080

# 明确标注的模拟演示（合成传感器 + dry-run 控制器 + demo Trial）
PYTHONPATH=src:. .venv/bin/python -m tactile_gripper.ui --no-browser --demo --port 8080

# P3-A：使用固件 host 仿真输出，自动创建仿真 Trial、导出 CSV 和 REPLAY 文件
PYTHONPATH=src:. .venv/bin/python -m tactile_gripper.ui --no-browser \
  --firmware-fixture electrodes12-fsr1 --record-fixture --data-root /tmp/gripper-v2-demo --port 8080
```

`--demo-profile` 只影响合成帧；默认单 FSR 的 `FSR_ONLY`，另一选项为 `MATRIX_ELECTRODES_12`。
`--firmware-fixture` 直接使用固件帧构造器生成的 JSONL，仅可与 SIMULATION 同用。
当前场景为 `fsr1`、`electrodes12`、`electrodes12-fsr1`，故障场景为
`fsr1-adc4-fault`、`electrodes12-partial`、`electrodes12-fsr1-adc4-fault`。
历史双 FSR 场景 `fsr`、`electrodes12-fsr2` 及其故障版本可继续离线运行。
`--record-fixture` 在读完 HELLO 后开始记录，在文件结束后结束 Trial 并输出回放路径。

### 2.1 真实双日志只读监控（P3-B）

真实 FSR + 真实 PWM 时，Dashboard 不打开串口，只 tail 两个 JSONL：

| 写入者 | 文件 | 说明 |
|---|---|---|
| `scripts/pwm_console.py --real --log-dir <session>` | `<session>/transport.jsonl` | 唯一 PWM 写入者，既有事件格式 |
| `scripts/capture_fsr_live.py` | `<session>/fsr/fsr_stream.jsonl` | 唯一 FSR 串口读者，含 host UTC/monotonic |

一条命令完成（一个终端）：

```bash
PYTHONPATH=src:. .venv/bin/python scripts/run_live_monitor.py
```

它启动 FSR 采集 → 等 HELLO → 启动只读 Dashboard（`--follow-session` +
`--follow-record`）→ 在当前终端运行 console。

**启动门控（P3-B4）**：HELLO 超时（`--fsr-timeout`，默认 15 s）或 FSR 采集进程退出时，
启动器以 **退出码 3** 中止，不启动 Dashboard，也**不会启动 PWM Console**；`session.json`
记录 `aborted`。Dashboard 就绪后还会再检查一次 FSR 进程。会话中 FSR 退出只打印警告，
PWM Console 不会自动停止（由操作者 `stop`/`quit`）。`--no-fsr` 是显式跳过 FSR 的门控例外。

**S3 心跳重试（P3-B4）**：控制台对 `HEARTBEAT` 和“尚无 PWM 目标时的 `BENCH_HOLD_MODE`/
`BENCH_PULSE_MODE`”做有界重试：默认共 2 次（`config/gripper_s3.json` 的
`serial.heartbeat_retry_attempts`，1–3），间隔 200 ms（`serial.heartbeat_retry_delay_ms`，0–1000）。
长帧 NUL 损坏会快速失败（约 0.2 ms），首次失败保持端口打开后重试；**PWM/STOP/DISARM/BEGIN_BENCH
不会自动重发**。重试耗尽后控制器进入 FAULT/UNKNOWN 并关闭，不会无限期维持未知输出。
日志中会出现 `COMMAND_RETRY`。

**等待 PWM 日志**：Dashboard 先启动时，`--follow-session` 会等待预期的
`<session>/transport.jsonl`，页面显示“等待 pwm_console 创建 transport.jsonl”；console 创建后自动接入。
显式 `--follow-pwm-log` 仍要求文件存在。

**退出顺序**：console → FSR（SIGINT，采集写 summary）→ Dashboard。Dashboard 先 drain
尾部 JSONL，再结束 Trial 并导出 CSV/REPLAY；它运行在独立 session，终端 Ctrl+C 不会抢先
结束导出。结束时会打印 `<session>/trial.json` 记录的**本会话** Trial CSV/REPLAY，不会
使用全局最新 CSV。

常用选项：

```bash
--pwm-port /dev/cu.usbserial-A5069RR4   # S3
--fsr-port /dev/cu.usbserial-0001       # ESP32 FSR
--no-console                            # 只观察（Ctrl+C 结束）
--no-fsr                                # 只跟随 console
--no-record                             # 不自动建 Trial
--web-port 8080
```

也可以分开启动：

```bash
PYTHONPATH=src:. .venv/bin/python -m tactile_gripper.ui --source LIVE --follow-session \
  logs/real/sessions/<session> --follow-record --port 8080
PYTHONPATH=src:. .venv/bin/python -m tactile_gripper.ui --source LIVE --follow-pwm-log \
  <path>/transport.jsonl --follow-fsr-log <path>/fsr_stream.jsonl
```

`--follow-*` 要求 `--source LIVE`，但**不需要** `--hardware-permission`（不打开串口）；
与 `--connect/--connect-sensor/--sensor-port` 互斥。Dashboard 的 Apply/STOP 在
log-follow 下被拒绝，`core.request_pwm()/stop()` 返回 REJECTED。只读面板的
“已 ACK”只表示收到匹配应答，不是位置；STOP 后不显示旧目标；日志 3 s 不更新显示 STALE。

排障：

- 页面 FSR 一直“等待/离线”：看 `<session>/fsr_capture.log`；启动器会等 HELLO 12 s。
- 页面 PWM 一直“STALE”：console 是否仍在运行；`transport.jsonl` 是否被另一个
  `--log-dir` 覆盖（同一目录只允许一次）。
- `--follow-session` 找不到 FSR：期望 `<session>/fsr/fsr_stream.jsonl`；也可用
  `--follow-fsr-log` 显式指定。
- 端口被占用：Dashboard 报 permission/Resource busy；不要同时运行两个 console，
  也不要让 Dashboard 直连同一串口。

打开 `http://127.0.0.1:8080/`：

- `/` Live Monitor
- `/experiments`
- `/analysis`
- `/demo-6x6`（仅 SIMULATION，独立合成热力图）

默认只监听 `127.0.0.1`；投屏/局域网访问使用 `--host 0.0.0.0` 并自行评估网络暴露。

显示约定（2026-11-15 最终验收后）：界面里的时间列与帧说明显示**本机时间**（存储的
`*_utc` 字段仍是 UTC，未改数据格式）；接触指标是相对评分，不是压力/牛顿；12 电极
profile 只有 12 路原始 ADC，没有 36 点热图。

## 3. 无界面完整演示

```bash
PYTHONPATH=src:. .venv/bin/python scripts/run_simulation_demo.py --ticks 30 --interval 0.05
```

脚本会：连接 dry-run 控制器 → 建立 MANUAL 会话 → 连接合成传感器 → 创建 Trial → 记录帧/控制事件 → 结束 → 导出 CSV。只写 `data/simulated/trials/`，不打开串口。

## 4. 只读回放

```bash
PYTHONPATH=src:. .venv/bin/python -m tactile_gripper.ui \
  --source REPLAY --sensor-file "/tmp/gripper-v2-demo/data/simulated/trials/替换为实验ID/replay.jsonl" --port 8080
```

`REPLAY` 读取 `replay.jsonl` 或带同目录元数据的 `frames.jsonl`，自动开始读取；控制按钮禁用，不打开串口。分析页可加载 Trial 后逐帧查看和导出 CSV。

## 5. 真实 LIVE（本轮未执行，仅入口）

S3 + 传感器：

```bash
PYTHONPATH=src:. .venv/bin/python -m tactile_gripper.ui \
  --source LIVE --hardware-permission \
  --connect-port /dev/cu.usbserial-XXXX \
  --sensor-port /dev/cu.usbserial-YYYY \
  --sensor-config config/sensor_serial.json \
  --connect-sensor --connect --port 8080
```

仅传感器（不连接 S3）：

```bash
PYTHONPATH=src:. .venv/bin/python -m tactile_gripper.ui \
  --source LIVE --hardware-permission \
  --sensor-port /dev/cu.usbserial-YYYY --connect-sensor --port 8080
```

安全性：

- `--hardware-permission` 是真实连接的必要条件，不等于运动授权。
- `--connect` 才会打开 S3 串口并建立 BENCH 会话；`--connect-sensor` 才会打开传感器串口。
- 真实 PWM 运动、固件烧录、接线/上电仍须逐次具体授权。
- `STOP` 只发送已验证固件 STOP；不保证保持/释放，不是硬件急停。

## 6. 传感器串口配置

[config/sensor_serial.json](../config/sensor_serial.json)：

```json
{"sensor_serial": {"port": null, "baudrate": 921600, "bytesize": 8, "parity": "N",
  "stopbits": 1, "read_timeout_s": 0.1, "boot_wait_s": 0.0,
  "max_line_bytes": 8192, "reconnect_enabled": true,
  "reconnect_initial_s": 0.5, "reconnect_max_s": 10.0, "queries_enabled": true}}
```

- 端口默认 null。获现场连接授权后，明确选择传感器串口；S3 控制串口独立。
- V2 使用 921600 8N1；`--sensor-baud` 只在已确认设备配置不同的情况下覆盖。禁用 DTR/RTS，
  现场 USB 桥/波特率与启动时序尚未实测。
- 正常握手发送 `{"cmd":"HELLO"}`，验证同会话后发送带请求 ID 的 `STATUS` 查询，两者只读。
  `queries_enabled=false` 禁止写采集串口。打开和握手不启动采集；单独授权采集后才点击“开始采集”。
- 现行 LIVE 帧为 1/12/13 路，历史 2/14 可仿真或回放，缺失是 null / NO_DATA。显示 ADC counts；没有参考/增益/位数完整的
  实测基准就不显示电压。相对接触评分是归一化值，真实 AUTO 保持硬关闭。
- 状态、超时与 profile 约束见 [接口](INTERFACE_CONTRACT.md)；证据等级见 [P3-A 验收](P3A_ACCEPTANCE.md)。

## 7. 数据目录

- `data/simulated/trials/<ID>/`：模拟 Trial。
- `data/real/trials/<ID>/`：真实 Trial（需真实设备授权）。
- `logs/simulated/`、`logs/real/`：底层控制日志（既有实现位置）。
- `data/`、`logs/` 被 Git 忽略；不提交实验数据。

## 8. 测试

```bash
PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests -v
```

离线测试不依赖真实 ESP32/传感器。`NOT_TESTED` 项见 [V1 报告](SOFTWARE_V1_REPORT.md)。

P2-S 历史验收：`Ran 290 tests ... OK (skipped=1)`。跳过项
`test_pty_waits_for_explicit_input` 需要 pty，本地沙箱没有（`out of pty devices`），
CI/现场复核。截图审计脚本见 [screenshots/p2s-ui-audit/README.md](screenshots/p2s-ui-audit/README.md)。
