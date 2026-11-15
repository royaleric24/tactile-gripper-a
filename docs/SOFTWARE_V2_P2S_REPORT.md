# 软件 V2 · P2-S 传感适配与离线闭环报告

日期：2026-11-14
分支：`sw/fsr-live-v2`，基于公开 `origin/feat/dashboard-zh-v1`（`9997853`）
协议状态：**PROPOSED**。本报告不表示真实设备、串口、PWM 或机械动作已联调验证。

## 1. 结论

本阶段完成 Dashboard V2 传感适配、两路 FSR 显示与相对接触评估、矩阵/FSR 分流、
双设备身份/波特率/STATUS 查询入口、Trial/CSV/REPLAY 扩展，以及**不执行真实 PWM**
的离线滞回决策与拒绝路径测试。2026-11-15 追加 12 电极拓扑适配与三视口 Dashboard
视觉验收（见第 11 节）。

真实 AUTO 仍由 `AUTO_REAL_ENABLED=False` 硬关闭。新增的
`request_real_auto_commissioning()` 是显式、当前必定拒绝的现场入口，仅用于将来
协议、硬件、标定签核后接入，不是可用开关。仿真帧只生成 `SIMULATION` Trial 和
离线决策记录，不写真实 PWM。

## 2. 传感器配置与通道分流

`HELLO.channel_config` 是唯一识别依据，不按串口名、设备名或历史通道数推断矩阵。

| profile | 逻辑通道 | 约束 |
|---|---|---|
| `FSR_ONLY` | 2 个 FSR | 无矩阵维度；推荐 `0=FSR_A, 1=FSR_B` |
| `HYBRID_6X6_FSR2` | 38 | 36 个 `MATRIX_CELL` 覆盖 6×6 + 2 个 FSR；推荐 36/37 为 FSR |
| `MATRIX_ELECTRODES_12` | 12 | R1–R6 = ROW 0..5，C1–C6 = COLUMN 0..5；禁止 `matrix_row/col`；不生成 36 点 |
| `UNKNOWN` / 旧配置 | 按 `channel_config` 实际数量 | 不假定存在矩阵；仍可显示原始通道 |

每个 `ChannelConfig` 支持：

- `sensor_kind`: `MATRIX_CELL` / `FSR` / `MATRIX_ELECTRODE` / `UNKNOWN`
- `name`: 显示名，例如 `FSR_A`、`R1`、`C6`
- `matrix_row` / `matrix_col`: 零基矩阵位置；FSR 与电极禁止携带
- `electrode_axis` / `electrode_index`: 仅 `MATRIX_ELECTRODE` 使用；`ROW`/`COLUMN` 与
  零基逻辑序号，**不是** ADS1220 AIN 编号
- `adc_reference_uv` / `adc_gain` / `adc_bits`: 电压换算依据；缺失则不显示电压
- `unit`: 仍只允许 `ADC_COUNTS` / `UNKNOWN`，不引入未标定的力单位

矩阵热图只消费 `sensor_kind=MATRIX_CELL`（或具备矩阵位置的通道），位置使用
`matrix_row/matrix_col`，不再使用 `divmod(channel_id, cols)`。即使 FSR 的通道号
恰好落在 6×6 范围内，也不会进入热图。`MATRIX_ELECTRODES_12` 没有 36 个单元位置，
Live 与 Analysis 只画 12 路原始 ADC 条形图，并明确提示“36 点压力热图不可用”。

## 3. 两路 FSR 显示与相对接触评分

Dashboard 保留既有页面，在 Live 页增加 FSR 区：

- 每路显示名称、原始 ADC、有效/无效/饱和、相对变化
- 电压仅在 `adc_reference_uv`、`adc_gain`、`adc_bits` 全部存在时显示，并标注
  “按 HELLO 换算基准”；不默认 3.3 V 或 24-bit
- 无效通道显示 `—`，不作为 0 接触
- 时间趋势同时画原始 ADC（左轴）与相对接触评分（右轴）

相对评分使用**显式空载基线**：

```text
channel_score = clamp((raw - baseline_raw) / span, 0, 1)
score = min(两路 FSR channel_score)
span = 2**(adc_bits-1) * 0.05；缺少位数时使用 250000 counts 的保守占位
```

基线必须由操作者点击“采集空载基线”或显式调用
`ApplicationCore.capture_fsr_baseline()`；真实数据不会自动捏造基线。仿真首次有效帧
可自动采集，但标记 `SIMULATION_AUTO`，且只服务于仿真演示。设备重启会清除基线。

状态：

| 状态 | 含义 |
|---|---|
| `NO_CONTACT` | 低于 `no_contact=0.10` |
| `INSUFFICIENT` | 有接触但相对基线不足，尚未达到正常区 |
| `NORMAL` | 相对接触在正常区 |
| `TIGHT` | 达到 `tight=0.80`，应放松/停止加夹 |
| `INVALID` | 无帧、帧过期、帧无效、FSR 无效或饱和 |
| `UNCALIBRATED` | 尚无空载基线 |
| `NOT_APPLICABLE` | 配置无 FSR 通道 |

`insufficient=0.20` 目前只作为更严格的策略参考保留，不参与上述四态边界；实际
`INSUFFICIENT` 区间是 `0.10 ≤ score < 0.45`。这些阈值是**软件初始参数**，不是
杯子/夹爪的安全边界，也未做真实标定。1300 μs 只是指定杯子的人工观察起点，
1270 μs 已观察到形变；两者都不是自动限位。

## 4. 离线滞回决策（只记录，不执行）

`RuleBasedAutoPolicy.evaluate_contact()` 在以下条件下返回：

- 无帧：`WAIT`
- 非 `STREAMING`、过期、`INVALID`/`NOT_APPLICABLE`：`FAULT`
- 未标定：`WAIT`
- 有未完成 PWM 命令：`WAIT`，不重叠发令
- `NORMAL`：`WAIT`（保持）
- `TIGHT`：负向 `STEP`，受 `min_pwm_us` 限制
- `NO_CONTACT` / `INSUFFICIENT`：正向 `STEP`，受 `max_pwm_us`、步幅、速率和总变化限制

`ApplicationCore.evaluate_auto_contact()` 只写入 `AUTO_DECISION` 事件和
`last_auto_decision`，不调用 `request_pwm`。真实 `AUTO_REAL_ENABLED` 仍为 `False`；
`auto_available()` 无论数据如何都返回不可用原因。因此当前公开路径无法进入 AUTO；
`_latch_auto_sensor_fault()` 与 AUTO 评估中的故障锁存是为将来显式启用准备的安全
路径，离线测试只能验证策略返回 `FAULT`，不能据此声称真实 AUTO 已可运行。若传感器
失联、短帧、无效 ADC 或评估为无效/未标定，策略不会产生夹紧 STEP。

## 5. LIVE、双串口身份与恢复

- 传感器和夹爪各自保存身份：`device_id`、`boot_id`、固件版本、profile、通道数、
  端口与波特率。身份来自实际 HELLO/device status，不根据端口名猜测。
- 串口波特率由 `sensor_serial.json` 或 `--sensor-baud` 决定，默认仍是 115200；
  历史采集固件可能为 **921600**。配置不一致时表现为无 HELLO/乱码，不能解释为
  “无矩阵”或“无接触”。
- 传输层默认只读。`queries_enabled=false` 时查询被拒绝；只有显式开启并获现场授权
  后才允许发送一行 `{"type":"QUERY","query":"HELLO"}` 或
  `{"type":"QUERY","query":"STATUS"}`。查询不是运动命令，也不会自动重发。
- UI 的“查询状态”和断线重连只针对传感器读取路径；不会自动建立 S3 运动会话。
- 收到 `STATUS` 会更新状态与身份；设备重启会清除 FSR 基线和趋势。

## 6. Trial、CSV 与 REPLAY

`SENSOR_FRAME` 行新增（保持旧字段可读）：

- `raw`: 原始 SAMPLE wire（若设备提供）
- `sensor_identity`, `sensor_profile`
- `contact_assessment`: 状态、评分、质量、每路原始/电压/基线/相对变化
- `pwm_command_id`, `pwm_target_us`, `pwm_ack`
- 既有 `frame_seq`, `boot_id`, `mcu_time_us`, `host_received_ns`, 通道、掩码、contact_score

CSV 在旧列之后追加：

```text
device_id,sensor_profile,contact_state,contact_quality,pwm_command_id,pwm_target_us,pwm_ack
```

旧 Trial 仍可导出（缺失字段为空）。REPLAY 现在可直接读取 Trial 的
`frames.jsonl`：读取同目录 `metadata.json` 的 `sensor_config`，自动补 HELLO，
并把 `SENSOR_FRAME` 解包为 SAMPLE；也可使用 `TrialStore.export_replay_jsonl()` 生成
独立 wire 文件。REPLAY 不打开串口、不写真实目录。

## 7. 离线演示

```bash
cd tactile-gripper-v2-sw

# 默认矩阵仿真
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo --port 8080

# FSR_ONLY：两路 FSR，无矩阵热图
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo \
  --demo-profile FSR_ONLY --data-root /tmp/gripper-fsr-demo --port 8080

# HYBRID：36 矩阵 + 2 FSR
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo \
  --demo-profile HYBRID_6X6_FSR2 --data-root /tmp/gripper-hybrid-demo --port 8080

# 12 电极：12 路原始 ADC，无 36 点热图
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo \
  --demo-profile MATRIX_ELECTRODES_12 --data-root /tmp/gripper-electrode-demo --port 8080
```

页面：`/` Live、`/experiments` Trial、`/analysis` 分析。仿真开关、profile 选择、
基线按钮均只在对应来源可用；真实 AUTO 按钮保持禁用。

无真实串口/烧录/机械动作。

## 8. Fixtures

`tests/fixtures/v2/`：

- `fsr_only.jsonl`：FSR_ONLY HELLO + 3 帧，第 3 帧 FSR_B 无效
- `hybrid.jsonl`：HYBRID HELLO + 38 通道 SAMPLE
- `short_sample.jsonl`：短帧，预期被拒绝
- `README.md`：来源、用途、复现命令

fixtures 全部为合成数据，不含真实设备日志。

## 9. 测试证据

```bash
PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests -v
```

结果：**285 tests, OK**（2026-11-15，本地离线，Python 3.13.15；含 12 电极测试 7 个）。

覆盖重点：

- FSR_ONLY / HYBRID HELLO 与配置校验；FSR 不进矩阵热图
- 电压基础缺失时不换算；显式基础换算
- 基线、四态滞回、双 FSR 取较弱通道、饱和/无效/过期帧
- 未完成命令不重叠发令；无效数据不产生夹紧 STEP
- 真实 AUTO 仍不可用，显式 commissioning 入口被拒绝
- 短帧、无效 ADC、REPLAY、Trial 原始帧/身份/PWM/ACK/决策、CSV、直接 frames REPLAY
- 串口 921600 可配置、HELLO/STATUS 查询默认关闭、REPLAY 不误判旧帧过期
- 12 电极：配置/索引校验、禁止矩阵位置、条形图选择、HELLO 往返、仿真无接触评分、
  电极 Trial metadata 与 12 列 CSV

状态标注：

- **PASS（离线）**：上述单元/集成测试与三个 Dashboard 路由启动
- **IMPLEMENTED_UNVERIFIED**：真实 FSR 电压换算、双串口身份、921600 实际链路、
  STATUS 查询回复、矩阵扫描与热图映射
- **NOT_IMPLEMENTED**：真实 AUTO 闭环、真实 PWM 自适应、力/摩擦标定
- **UNKNOWN**：FSR 极性/饱和、ADC4 接线与基准、矩阵串扰/扫描率、ACK 后的实际夹持状态

## 10. 集成组需要确认的接口

1. HELLO 顶层 `sensor_profile` 与 `channel_config.sensor_profile` 的优先级/唯一来源；
   当前 channel_config 优先，两者都接受。
2. FSR 通道是否提供 `adc_reference_uv/gain/bits`，以及 ADS1220 单端/差分与有符号
   计数约定；当前按“显式基础 + 有符号满量程”换算，未确认前不应展示为真实电压。
3. FSR 通道顺序、`name`、极性、饱和定义；HYBRID 的 36/37 是否固定。
4. 采集固件实际波特率（115200 或 921600）、HELLO 发送时机、HELLO/STATUS 查询的
   请求/回复 wire 格式和超时；当前 `QUERY` 仅为提案。
5. 两台设备的身份字段是否稳定（S3 与采集板各自的 `device_id/boot_id`）。
6. 矩阵 `matrix_row/col` 与物理方位的对应、扫描率和串扰；热图只按配置映射，未验证
   物理方向。
7. PWM 方向/安全范围、ACK 语义与是否可提供独立位置/压力反馈；当前 ACK 不当作到位。
8. 真实 AUTO 的门控签核流程：协议冻结、硬件授权、标定确认、现场急停与失联策略。

在上述确认前，本分支不能宣称真实 FSR→PWM 闭环已完成。

## 11. 12 电极拓扑与 Dashboard 视觉验收（2026-11-15 追加）

### 11.1 接线事实与边界

用户确认：R1–R6 分别连接 ADS1220 AIN，各自经 10 kΩ 下拉到 GND；C1–C6 分别连接
ADS1220 AIN，各自经 1 kΩ 上拉到 3.3 V。这不是 GPIO 逐列激励方案。具体 R/C 到
ADS1220/AIN 的物理映射、扫描顺序、增益与基准尚未现场确认。

因此：

- 12 个电极测量值是 12 路单端原始 ADC，不是 36 个独立压力点；
- 不合成 `contact_score`、压力、牛顿或摩擦力；
- 不绘制 36 点热图，也不把 12 路值插值成 6×6；
- FSR_ONLY 两通道方案继续保留，互不影响。

### 11.2 实现

- `MATRIX_ELECTRODES_12` 严格校验 12 个通道、ROW/COLUMN 各 0..5、无矩阵位置；
- 仿真 transport 只产生 12 路带少量噪声的原始 ADC，并保留偶发无效通道；
- Live 用条形图显示 R1–R6/C1–C6，附琥珀色提示；接触指标为“未知”；
- Analysis 回放按 metadata 中的 `sensor_config` 选择条形图，并显示同一提示；
- 电极 Trial 的 `sensor_config` 保留 `electrode_axis/index`；CSV 仍按实际通道并集
  生成 `ch_0..ch_11`，不写 `ch_36`；
- `scripts/ui_screenshot_audit.mjs` 仅驱动本机 SIMULATION 页面截图，不接触硬件。

### 11.3 视觉验收

1440×900、1280×800、1920×1080 各截取 Live/Experiments/Analysis；修复前截图见
`docs/screenshots/p2s-ui-audit/before/`，修复后见 `after/`，12 电极见
`after-electrodes/`。对比与残留轻微不对称见同目录 `README.md`。

结果为 PASS（离线）：所有视口 `bodyScrollWidth == viewport`，console/page error 0；
顶部指标卡与主卡片等高；FSR 读数两列；表格不再溢出卡片。仍为仿真数据，真机视觉、
长时间运行和交互路径未验证。

### 11.4 仍需现场确认

1. R1–R6 / C1–C6 到 ADS1220 AIN 的逐路映射与板号；
2. ADS1220 单端/差分、增益、基准、数据速率与有符号计数约定；
3. 10 kΩ 下拉 / 1 kΩ 上拉下的实际电压范围、饱和与串扰；
4. 是否存在可验证的扫描/激励方案；没有之前不得输出 36 点压力图。
