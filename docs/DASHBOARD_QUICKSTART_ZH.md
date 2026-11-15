# Dashboard 中文使用指南（V2）

本指南与当前软件 UI 行为一致。真实硬件操作仍需单独授权；默认模式不会打开真实串口。

## 0. 双日志实时监控（P3-B，只读）

真实 FSR 与真实 PWM 同屏显示时，Dashboard **不打开任何串口**：`pwm_console` 独占 S3
串口并写 `transport.jsonl`，`capture_fsr_live.py` 独占 FSR 串口并写
`fsr/fsr_stream.jsonl`，Dashboard 只读这两个文件。

一个终端、一条命令（先确认两个端口）：

```bash
cd ~/Developer/research/tactile-gripper-v2-p3b-monitor
PYTHONPATH=src:. .venv/bin/python scripts/run_live_monitor.py
```

- 默认 PWM `/dev/cu.usbserial-A5069RR4`、FSR `/dev/cu.usbserial-0001`；不同时用
  `--pwm-port` / `--fsr-port` 指定。
- 会创建 `logs/real/sessions/session_<UTC>_<id>/`，后台启动 FSR 采集和 Dashboard，
  然后在当前终端进入 `pwm_console`；console 里照常输入 `1500`、`1040`、`stop`、`quit`。
- 退出 console 后自动结束 Trial，并打印 CSV 与 REPLAY 路径。
- 只观察、不控制：加 `--no-console`。
- **FSR 未就绪会直接终止**：HELLO 超时（默认 15 s）或采集进程退出时，启动器以退出码 3
  中止，不启动 Dashboard，也不进入 PWM Console；先看 `<session>/fsr_capture.log`。
  只有显式 `--no-fsr` 才允许只跟 console。
- 退出时先停 console/FSR，Dashboard 再读完最后 JSONL 并结束 Trial；终端会打印**本次**
  Trial 的 CSV/REPLAY（来自 `<session>/trial.json`），不会拿别的会话最新 CSV 顶替。
- **S3 心跳重试**：HEARTBEAT 与“尚无目标时的模式选择”允许一次有界重试（默认共 2 次、间隔 200 ms，
  可在 `config/gripper_s3.json` 的 `serial.heartbeat_retry_attempts` / `heartbeat_retry_delay_ms` 调整）；
  PWM/STOP/DISARM 不会自动重发。重试耗尽仍进入 FAULT/UNKNOWN 并关闭。
- **等待 PWM 日志**：Dashboard 先启动、console 后创建 `<session>/transport.jsonl` 时，页面显示“等待
  pwm_console 创建 transport.jsonl”，文件出现后自动接入；不会因此打开串口。
- **FSR 平滑**：FSR 区有“短窗平滑（仅显示）”开关（默认关）；原始曲线变淡、叠加 5 帧中值平滑；
  Trial / CSV / REPLAY 始终保存原始 counts。


- 不开 FSR：`--no-fsr`；不开 Trial 记录：`--no-record`。

页面上的只读 PWM 面板会显示：

- **当前目标**：只有 console 已 ACK 且仍有效时才显示 μs；STOP 后显示 `—` 与
  “输出已关闭（STOP ACK）”，不会把旧目标伪装成实时输出。
- **已发送 / 已 ACK / 失败 / 未确认**：分别标注；ACK 不是实测位置。
- **控制器状态 / 固件输出 / 最新应答 / 通信错误 / 日志新鲜度**：NUL、应答损坏、
  超时、STALE、OFFLINE 都会明确显示。
- **FSR 与 PWM 统一时间轴**：同一主机单调时钟；FSR 约 60 Hz，PWM 为命令写入时刻，
  不是硬件同步采样。
- **开始记录 Trial / 结束并导出 CSV**：同一 Trial 保存 FSR 帧、PWM 命令/ACK、
  操作事件与时间戳。

数据质量：FSR `0x04`（近零负计数/零点噪声）与 `0x20`（无效通道）会在 FSR 卡片下方提示；
负 counts 原样显示；曲线遇到无效帧留空隙；日志 3 s 不更新显示 STALE。

## 1. 启动

```bash
uv sync --locked

# 离线模式：S3 控制器显示离线，传感器等待数据，不会伪造数据
PYTHONPATH=src:. .venv/bin/python -m tactile_gripper.ui --no-browser --port 8080

# 固件 JSONL → Dashboard → 仿真 Trial / CSV / REPLAY
PYTHONPATH=src:. .venv/bin/python -m tactile_gripper.ui --no-browser --port 8080 \
  --firmware-fixture electrodes12-fsr1 --record-fixture --data-root /tmp/gripper-v2-demo
```

浏览器打开 `http://127.0.0.1:8080/`。页面：**实时监控**、**实验管理**、**分析与诊断**。

## 2. 实时监控

查看顶部四张状态卡：

- **控制器状态**：离线（OFFLINE）、已连接、控制会话已建立或故障锁存（FAULT）。
- **传感器通信**：等待数据、通信在线、采集已停止、陈旧帧、协议错误或离线。独立的“通道数据质量”显示有效数/总数和故障。
- **控制模式**：手动模式（MANUAL）、待机（STANDBY）、自动模式（AUTO）或故障锁存（FAULT）。
- **当前实验**：记录中（RECORDING）、正常完成（COMPLETED）等。

触觉分布显示 ADC 原始计数。无效通道会显示为空隙，不会当作零接触；未标定数据不解释为压力、摩擦力或杯子重量。仿真演示会明确显示 **仿真（SIMULATION）**，不会显示为真实设备（LIVE）。

固件样例可选 `fsr1`、`electrodes12`、`electrodes12-fsr1` 及相应故障场景。
电极条形图显示 R1–R6 / C1–C6 原始 ADC 计数，13 通道的 FSR_A 在独立卡片显示。空映射为
`PENDING_REAL_WIRING`，合成映射单独标注。双 FSR 的 2/14 通道样例和历史 Trial 仍可离线查看。
固件样例默认显示未标定；相对接触评分需要新鲜、有效的空载基线。[运行手册](SOFTWARE_RUNBOOK.md)

在 SIMULATION 的左侧导航点「36 格仿真」，可打开独立热力图。点击「下一仿真帧」更新合成格值。
控制、Trial 记录和真实传感器数据都不接入此页。历史矩阵 Trial 仍按 HISTORICAL 标记回放。

### 手动 PWM

1. 在 **手动 PWM 控制** 中拖动滑块或直接输入 μs 目标；这仅改变待提交值。
2. 点击 **提交 PWM（Apply）** 才向唯一控制接口提交一次目标。
3. 设备确认（ACK）只表示固件逻辑接受，**不是**实际机械位置。
4. **STOP** 关闭 PWM 输出，但不保证机械爪继续保持夹持，也不是独立硬件急停。

仿真演示：

1. 打开 **仿真演示（SIMULATION）**；
2. 点击 **连接仿真 S3**（只连接/查询状态）；
3. 点击 **建立手动会话**；
4. 再提交 PWM。

真实设备（LIVE）需要命令行显式授权并连接，UI 的“真实设备 · 通过命令行连接”不会被自动执行。

## 3. 实验管理

### 创建实验

填写：

- 实验名称、物体名称、杯子类型、材料、水量/质量（g）、操作人员；
- 抓取目标 / 实验条件、视频文件路径（可选）、备注。

点击 **创建实验**。**创建后不会自动开始记录**，需要再点击 **开始记录**；开始后系统保存触觉帧、控制事件和实验元数据。

### 记录中

- **开始记录**：开始写入 `frames.jsonl`、`events.jsonl` 和元数据。
- **添加事件标记**：选择标记/备注/异常，填写内容（例如“加水 100 g”），点击 **添加**。
- **正常结束**：保存为 `COMPLETED`。
- **中止实验**：弹出确认框，保存为 `ABORTED`；已有数据保留但不计为正常完成。
- **更新视频**：只关联已有视频文件路径，Dashboard 不会自动录像。
- **导出 CSV**：导出该实验的触觉帧 CSV。

目录：

- 仿真：`data/simulated/trials/<实验 ID>/`
- 真实：`data/real/trials/<实验 ID>/`

## 4. 分析与诊断

- 使用 **来源 / 实验状态 / 搜索** 筛选历史实验；
- 选择实验后点击 **加载实验**；
- **播放回放 / 上一帧 / 下一帧** 只改变界面帧索引，不触发真实 PWM；
- **触觉帧检查** 查看矩阵/通道；
- **触觉趋势** 选择通道；
- **PWM 变化曲线** 与控制事件对齐查看；
- **控制事件** 显示动作、阶段、PWM 目标、设备确认（ACK）、设备状态与说明；
- **故障与异常**、**实验事件日志** 查看异常和操作标记；
- **实验对比（可多选）** 选择两个以上实验后点击 **对比所选实验** 查看帧数、控制/ACK、丢帧、无效通道等摘要；
- **导出 CSV** 导出选中实验。

`INTERRUPTED` 表示软件未正常结束记录，数据保留但不视为正常完成；`ERROR` 表示写入失败；`DROPPED` 是丢帧，`INVALID` 是无效通道样本。

## 5. 真实设备与 AUTO 边界

- 真实设备（LIVE）和仿真（SIMULATION）严格隔离；回放（REPLAY）只读。
- 当前 **自动模式（AUTO）强制禁用**（`AUTO_REAL_ENABLED=False`），按钮不可用；等待真实传感器协议、PWM 方向/范围、触觉标定与实测验证。
- **STOP 不等于机械保持**，也不是独立硬件急停；释放/掉落行为未验证。
- 真实 PWM 运动、传感器连接、固件烧录和接线仍需逐次授权。

## 6. 视觉验收与截图

[P3-A 验收与截图](P3A_ACCEPTANCE.md)包含真正运行的 NiceGUI 页面、六种固件样例和只读 REPLAY。
本机复跑：`PYTHONPATH=src:. .venv/bin/python scripts/p3a_verify_dashboard.py --out evidence/p3-a/new-audit`。
需要 Node ≥22 与 Chrome（可用 `CHROME_PATH` 指定）。旧 [P2-S 视觉验收](screenshots/p2s-ui-audit/README.md)保留为历史记录。

## 7. 常见提示

| 提示 | 含义 |
|---|---|
| 等待传感器数据 | 没有收到真实/仿真触觉帧 |
| 传感器数据已过期 | 超过新鲜度窗口未收到新帧 |
| 控制会话未建立 | 只连接了设备，尚未 Begin manual session |
| 设备确认（ACK） | 固件接受命令；不是实际位置 |
| 时间（本机） | 表格/帧说明把存储的 UTC 时间转换为本机时间显示；数据文件仍是 UTC |
| 故障锁存（FAULT） | 需要排查并显式清除/重连，不能继续提交 |
| 实验异常中断（INTERRUPTED） | 软件未正常结束；数据保留，不标正常完成 |
| 写入错误（ERROR） | 帧/事件/锁写入失败；检查磁盘与事件日志 |

详细运行/数据/联调说明见 [软件运行手册](SOFTWARE_RUNBOOK.md)、[数据格式](DATA_FORMAT_V1.md)、[硬件联调清单](HARDWARE_INTEGRATION_CHECKLIST.md)。
