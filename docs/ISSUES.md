# P2-S 已知问题与集成阻塞

更新：2026-11-15。协议仍为 **PROPOSED**；以下不是已冻结契约。

## 阻塞真实闭环的接口问题

1. **波特率不一致**：历史采集固件可能 921600，软件默认 115200。当前可由配置/
   `--sensor-baud` 指定，但实际设备值未确认。错误波特率会表现为无 HELLO/乱码，
   不能推断为无矩阵或无接触。
2. **HELLO/STATUS 查询未冻结**：当前接受顶层或 `channel_config.sensor_profile`，
   channel_config 优先；查询发送 `{"type":"QUERY","query":"HELLO"}` 或
   `{"type":"QUERY","query":"STATUS"}`，回复格式与超时未与硬件组确认。查询默认关闭。
3. **FSR 电压换算依据**：只有显式 `adc_reference_uv/adc_gain/adc_bits` 才显示电压。
   ADS1220 单端/差分、有符号计数、实际基准与增益未确认；未确认前不能把换算值当
   真实电压或力。
4. **FSR 极性与饱和**：按下通常使电压升高，但实际极性、饱和阈值、通道顺序
   （FSR_A/B）需硬件确认。当前只报告相对评分。
5. **矩阵映射/扫描**：`matrix_row/col` 到物理方位的对应、6×6 扫描率与串扰未验证；
   热图只按 HELLO 元数据绘制，不代表已标定触觉图。
6. **双设备身份**：S3 与采集板的 `device_id/boot_id/firmware_version` 是否稳定、
   何时发送 HELLO 未联合确认；当前分别记录，不能证明“同一 Trial 的两台设备”已
   经硬件同步。
7. **ACK 语义**：ACK 只表示命令回复，不是位置/夹持力/到位反馈。Trial 分开保存
   `pwm_command_id`、目标、ACK；`actual_pwm_us` 保持未知。
8. **真实 AUTO 签核**：`AUTO_REAL_ENABLED=False`， commissioning 入口当前必拒绝。
   需要协议冻结、硬件授权、FSR 标定、PWM 方向/范围、急停/失联策略与现场证据。
9. **12 电极 R/C→ADC/AIN 映射未确认**：用户确认 R1–R6 各经 10 kΩ 下拉到 GND、
   C1–C6 各经 1 kΩ 上拉到 3.3 V 并分别接 ADS1220 AIN，但未给出哪一路接哪个
   AIN/ADS1220/mux。当前 `MATRIX_ELECTRODES_12` 的 `adc_input`、`ads1220_id`、
   `mux_channel` 全部为 null，`electrode_index` 只是逻辑序号，不能当物理通道。
10. **12 电极 ≠ 36 压力点**：R/C 单端测量不是逐列激励的互电容/电阻矩阵，不能由
    12 路值推算 36 个独立压力点。软件只显示 12 路原始 ADC；热图、压力、接触评分
    均不可用，除非硬件组给出经过验证的扫描与标定方案。

## 当前实现的限制

- 阈值（0.10/0.20/0.45/0.80）是软件初始值，不是杯子/夹爪安全边界；1300 μs 与
  1270 μs 只是人工观察，不是自动限位。
- 相对评分依赖空载基线；杯子/夹爪重新装夹或设备重启后必须重采。真实数据不会
  自动采集基线。
- 仿真首次有效帧自动采集基线，标记 `SIMULATION_AUTO`；该路径不得用于真实 PWM。
- Trial 原始 SAMPLE 依赖设备/适配器提供 `raw`；旧 Trial 无 raw 时 REPLAY 用已验证
  字段重建，不能恢复未落盘的原始字节。
- `frames.jsonl` 直接 REPLAY 依赖同目录 `metadata.json` 的 `sensor_config`；手工
  移动文件会失去自动 HELLO。
- Dashboard 已完成 1440×900、1280×800、1920×1080 的 Live/Experiments/Analysis
  离线截图验收（`docs/screenshots/p2s-ui-audit/`），但仍是仿真数据；真实设备错误
  提示、长时间运行和交互路径需现场走查。
- 视觉验收保留的轻微不对称：Live 底部事件/记录卡高度由内容决定；分析页 7 列
  “控制事件”表在 ≤1440 px 使用卡片内横向滚动；实验历史表在 1280 px 内部滚动
  约 72 px。均不溢出卡片，未为此重排页面。

## 非目标

- 不新增页面、不重做 UI、不引入未标定的牛顿/摩擦系数。
- 不自动回中、扫描端点、重放旧运动，不自动开真实 AUTO。

## 2026-11-15 最终验收：已解决

以下问题在本轮验收中确认、修复并有测试或截图证据（均在离线环境）：

| # | 问题（修复前） | 处理 | 证据 |
|---|---|---|---|
| R1 | Live 帧说明把主机单调时钟当秒数显示（如 `3345443.070s`），像是已经录了 38 天 | 改为 `接收于 HH:MM:SS（本机时间）`，取自 `host_received_utc` | 新 `after/live-*.png` |
| R2 | 接触判断原因整段英文（`relative contact above tight threshold; do not keep tightening`） | `contact_reason_label()` 翻译固定原因，动态原因保留数字 | `tests/test_text_zh.py::ContactReasonTests` |
| R3 | 事件说明漏译带 profile 的形式 `SIMULATION sensor connected (HYBRID_6X6_FSR2); ...` | `event_detail_label()` 前缀规则 | `DynamicEventDetailTests` |
| R4 | 三个页面各复制 `_clock()`，把 UTC 时间戳当本机时间显示且互不一致 | 统一 `theme.clock_label()`，表头写明“时间（本机）” | `DashboardDisplayTests` + 截图 |
| R5 | 分析页侧栏残留占位“离线（OFFLINE）/等待数据”，顶栏“待机”，与同进程其他页面矛盾 | 用只读 `core.snapshot()` 同步侧栏与顶栏，不新增写路径 | 新 `after/analysis-*.png` |
| R6 | 12 电极条形图无单位/读数，Y 轴出现 `2,134.55` 这类小数刻度 | 轴名“ADC 计数”、柱顶读数、刻度取整 | `DashboardDisplayTests::test_bar_chart_shows_units_and_electrode_counts` |
| R7 | 热图色条压在 C 轴标签行；FSR 趋势图轴名与图例重叠 | 热图 `grid.bottom` 加大；删除与图例重复的轴名 | 新整页截图 |
| R8 | 无头 Chrome 启动失败时审计脚本静默退出 0、不产图（会伪造“截图通过”） | `connect()` 对 close/timeout 拒绝；提供 `CHROME_NO_SANDBOX=1` | 复现后修复，重跑 18+3 张截图 |
| R9 | `docs/screenshots/p2s-ui-audit/before/audit.json` 含 9 处本机绝对路径 | 改为仓库相对路径 | `git grep /Users/` 为空 |
| R10 | 工作区遗留 0 字节未跟踪文件 `Ran` | 确认无引用后删除 | 见 PROGRESS 本轮记录 |

## 2026-11-15 最终验收：仍开放（交 P3-A / P3-B）

1. **P3-A 协议**：`QUERY` 请求/回复 wire 格式、超时、HELLO 发送时机仍未冻结；
   第 1 节的第 2、4、5 项仍是集成前的硬阻塞。
2. **P3-A 通道映射**：R1–R6 / C1–C6 → ADS1220 AIN 的物理映射、单端/差分、增益、
   基准、扫描顺序仍未知。软件中 `adc_input/ads1220_id/mux_channel` 保持 null。
3. **P3-A 命名冲突**：矩阵热图行/列用 0 基索引（`R0…R5` / `C0…C5`），电极用 1 基
   逻辑名（`R1…R6` / `C1…C6`）。两者同屏出现时容易误读为同一组通道；需在接口契约里
   统一命名或加前缀（例如 `M-R0` 与 `E-R1`）。本轮未改，避免影响既有 Trial 字段。
4. **P3-A 数据契约**：`sensor_profile` 只用顶层还是 `channel_config` 内层，是否允许
   两者不一致；当前 channel_config 优先且都接受，硬件组未确认。
5. **P3-A/P3-B 视觉**：本轮只做桌面 1024–1920 px。真实设备错误提示、长时间运行、
   断连/重连交互仍未现场走查；1024 px 下四张指标卡会整行堆叠（无溢出，但纵向变长）。
6. **P3-B 标定**：FSR 极性/饱和/基线、阈值（0.10/0.20/0.45/0.80）与 1300/1270 μs
   观察值都不是标定结果；真实 AUTO 仍需现场证据与签核。
7. **CI 覆盖**：本机沙箱无 pty，`test_pty_waits_for_explicit_input` 被跳过；PTY 交互
   路径在本地未验证，只能依赖 CI/现场复核。
