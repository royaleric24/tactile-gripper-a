# 问题与阻塞台账（持续更新）

## P3-A 当前状态（2026-11-15；下方组内条目保留历史上下文）

| 编号 | 状态 | 变更 / 后续 |
|---|---|---|
| I-006 / I-101 | OFFLINE_VERIFIED | Dashboard 使用 921600 8N1、V2 参考解析器；旧三 ADC 工具保留原协议。实际 Mac UART 尚待 P3-B。 |
| I-015 / I-105 | RESOLVED | GitHub PR #4 已合入软件组分支；两组及 main 文档基线已保留在集成提交中。 |
| I-104 | PARTIAL | HELLO/STATUS 及主机命令字节、超时经离线验证，实际板端收发仍未实测。 |
| I-106 / I-107 | OPEN | 电极物理映射仍 PENDING_REAL_WIRING；未映射通道 null/NO_DATA。硬件组与项目所有者待现场核对。 |
| I-109 | OFFLINE_VERIFIED | 现行采集/演示拒绝 HYBRID；历史样例仅供带标识的回放。 |
| I-201 | RESOLVED | 零等待串口轮询原来不读，分片不保留；修复后用固件原帧分片通过假串口。 |
| I-202 | RESOLVED | 浏览器点“加载实验”触发 NiceGUI 容器刷新错误，已改为刷新试次视图，复测加载、步进、CSV。 |
| I-204 | OFFLINE_VERIFIED | 所有者确认 FSR_A 为 ADC4 AIN0。1/13 通道固件、单 FSR 评分/AUTO、Trial 与回放通过离线验证；2/14 留作离线兼容。 |
| I-205 | OPEN | FSR_B 已损坏。AIN1 是否已电气隔离、AVDD 实际参考值、分压、FSR_A 阈值与滑移代理等待总控/现场组核对。 |
| I-206 | OFFLINE_VERIFIED | 36 格仅在独立 SIMULATION 演示和历史矩阵回放中显示，现行采集保留 12 电极原始 ADC 条形图。 |
| I-203 | OPEN | P3-B 需核对实际波特率、包吞吐、真实时间基准、FSR 极性与阈值、滑移代理、杯体机械风险。负责人：总负责人 / 现场硬件与软件组。 |

> 状态为 OPEN / WAITING / RESOLVED / ACCEPTED_LIMITATION。解决后留历史记录，不直接删掉。每个开发进展后检查是否需要更新。

| ID | 问题 | 状态 | 当前判断与下一步 |
|---|---|---|---|
| I-001 | 旧 ADC1–3 MISO 映射文档写错 | **RESOLVED（设计）** | 用户确认 `ADC1=CS21/MISO34`、`ADC2=CS22/MISO35`、`ADC3=CS5/MISO26`。本文档与 V2 模板已修正；旧固件的 `[35,26,34]` 需在实际 V2 开发时迁移并用 SPI 读回验证。 |
| I-002 | FSR 两路独立分压的焊接与响应 | OPEN | 正式施工时确保 AIN0/AIN1 各自 10kΩ 下拉到 GND、测量节点不短接；暂未进行 V2 实物采样。 |
| I-003 | 新 ADC4（CS32/MISO33）尚未接入 | OPEN | 硬件组在后续阶段实施，核验 3.3V/共地、CS、SPI 读回和两路 FSR。 |
| I-004 | 6×6 扫描方案已作废（2026-11-15 修正） | **RESOLVED（前提作废，非完成）** | 项目所有者确认真实压敏布为 12 电极被动读取：无 GPIO 列激励、无 HI_Z、无 36 点扫描。原“六列 GPIO 激励 + GPIO19 给 C6”的设想与真实硬件不符，已从当前设计移除（HISTORICAL）。`HYBRID_6X6_FSR2` 随之撤回，见 I-014。 |
| I-005 | 软硬件分支未集成 | OPEN | 2026-11-14 P0 保护完成；本轮只落地文档。后续仅在公开脱敏历史的集成分支合并组成果。负责人：集成组。 |
| I-006 | 串口波特率/协议两组旧配置不一致 | OPEN | 采集历史固件用 921600；软件模板 115200；真实联调时识别设备并统一。 |
| I-007 | 真实 AUTO、加水实验未完成 | OPEN | 优先 FSR-only 真采集 + S3 MANUAL，再做规则闭环；实验次数按时间弹性调整。 |

| I-008 | 旧三 worktree 与公开仓库历史独立 | ACCEPTED_LIMITATION | 已核实、完整备份；文档改用公开 main 独立 clone。禁止将旧提交直接导入公开仓库。后续文件级迁移由集成组单独核验。 |
| I-009 | V2 协议及施工尚未验证 | WAITING | 设计映射已确认；ADC4、FSR、12 电极、波特率与真实帧由后续硬件/软件组联合核实。P0/P1 不启动 P2/P3。 |

| I-010 | 历史报告 6 处本地证据链接缺失 | ACCEPTED_LIMITATION | Markdown 检查确认均继承自公开 main，涉及 STAGE0/05/06/09B26 报告中的本地证据或原始日志；公开库未包含原件。保留历史正文、不上传原始日志。负责人：文档集成组。 |

| I-011 | 交接包接线文档行尾空格 | RESOLVED | 暂存检查发现 Markdown 双空格换行；已改成普通换行，追加提交修正，不重写历史。 |

| I-012 | 12 电极 → ADC/AIN 物理映射缺失（2026-11-15） | **OPEN** | 真实布料每根 R/C 电极进哪颗 ADC（ADC1/2/3）的哪个 AIN 尚不知道，必须由真实焊接/台架记录填写 `docs/WIRING_FREEZE_V2.md` §4.1 空白表；填表前不得写任何 ADC/AIN 编号、不得假设行优先、不得给“示例映射”。`MATRIX_ELECTRODES_12` 因此保持 `mapping_status: "PENDING_REAL_WIRING"`、`validated: false`。负责人：硬件组（施工后）。 |

| I-013 | 12 电极不能代表 36 个压力点 | ACCEPTED_LIMITATION | 12 个电极电压是 12 个单端测量值，不是 36 个独立压力点；无行列交点语义，空间分辨率受限。任何热图、Demo 文案与验收标准都不得宣称 36 点或“矩阵已验证”。后果：演示只能用电压趋势/粗接触区域，不能用 6×6 热图证明定位精度。 |

| I-014 | `HYBRID_6X6_FSR2` 不得用于真实布料 | **OPEN** | 该 profile 依赖不存在的 GPIO 列激励，真实布料不可用；已撤回为 HISTORICAL（仅保留历史回放识别）。软件组需拒绝将其作为当前 profile、不据此发起真实采集、不把 36 逻辑值渲染为实测点。负责人：软件组。 |

| I-015 | P2-S 软件提交 `8d4d7d8` 尚未推送/评审 | **OPEN** | 见 PR #2 评论提及的软件提交；本仓库文档 PR #1 不含该提交。需确认其基线、是否已在公开仓库可见、是否需要评审后合入。负责人：软件组 / 总负责人。 |

## 更新规则

新问题添加 ID、复现条件、影响、临时方案和负责人（如果明确）；现有问题的状态变化说明证据与日期。仅讨论未施工时，不能把实际电气验收标 PASS。

## 硬件组问题记录（保留原编号）

### I-101｜软件侧严格解析器仍硬编码 12 通道 / 3 ADC（OPEN，阻塞联调）

- 现象：`tools/tactile_acq/protocol.py` 的 `CHANNEL_COUNT = 12`、`ADC_COUNT = 3`，`parse_sample` /
  `parse_hello` 要求 12 通道与 3 个 `adc_status` 条目。FSR_ONLY 的 2 通道帧会被直接判错，
  HYBRID 的 38 通道帧同样被拒。
- 影响：软件组无法用现有解析器消费 V2 帧；目前只能参考 `tools/fsr2/protocol_v2.py`。
- 建议：按 `sensor_profile` 取通道数与 ADC 数量（FSR_ONLY 2/4、HYBRID 38/4、V1 12/3），
  保留旧路径；复用 `protocol_v2` 的 null/valid 语义。
- 负责人：软件组。

### I-102｜四颗 ADS1220 共用 bit-bang SCLK/MOSI 的真实时序未验证（OPEN）

- 现状：host 模拟按理想 SPI 行为建模，未建模 MISO 竞争、走线容性、器件间 CS 建立/保持差异。
- 风险：ADC1–3 与 ADC4 共用总线时，若 MISO 在 CS 拉高后仍被驱动，可能出现串扰读错。
- 需要：逻辑分析仪抓 SCLK/MOSI/各 CS/各 MISO，确认 CS 拉高到下一次传输之间的三态时间。
- 只读证据：离线编译与仿真不能替代。

### I-103｜FSR 分压取值与极性未标定（OPEN）

- 现状：10 kΩ 下拉、3.3 V 激励、`VOLTAGE_RISES_WITH_FORCE` 均为首轮设计值，尚未实测。
- 待做：空载/轻压/重压各记录 counts，换算 AVDD 实测值；必要时比较 4.7 kΩ / 10 kΩ / 47 kΩ。
- 约束：没有独立标定前只能报告 ADC counts，禁止换算成牛顿。

### I-104｜命令层仅编译通过，未逐命令验证（OPEN）

- 现状：`.ino` 的 ArduinoJson 命令解析编译通过，但 host 仿真不覆盖串口解析路径，
  也没有真实串口会话记录。
- 待做：实机按 `docs/hardware/FSR_ONLY_INTERFACE_V2.md` §11 第 6 步逐条执行 PING/STATUS/
  STREAM/STOP/RESET_ADC/VERIFY_CONFIG，并保存原始应答。

### I-105｜两套文档基线并行（OPEN，流程）

- `docs/demo-v2`（PR #1）含 V2 计划、接线冻结、协议提案、进度/问题/交接；本分支只新增硬件范围内的
  同名文件并引用其条目，未复制其内容。
- 合并 PR #1 时需要：以 demo-v2 的 I-001..I-011 为主干，把本文件 I-101 起并入；确认引脚、
  波特率、null 语义三处不产生分叉。

### I-106｜压敏布接线由"6 列 GPIO 扫描"更正为"12 电极被动读数"（OPEN，现场复核）

- 事实：R1–R6 各接一个 ADS1220 AIN + 各自 10 kΩ 下拉 GND；C1–C6 各接一个 AIN + 各自 1 kΩ 上拉
  3.3 V；无 GPIO 列驱动、无 HI_Z、无 36 点扫描。
- 已做：固件/配置/解析器/文档全部改为 `MATRIX_ELECTRODES_12`，删除 GPIO 列激励代码。
- 待做：现场按接口文档 §11/§12 核对焊接，填写电极映射表；确认 12 根电极的偏置电阻实际装配。

### I-107｜R/C → ADC/AIN 映射缺失（OPEN，阻塞电极读数）

- 现状：配置 `electrodes.map = []`、`mapping_status = PENDING_REAL_WIRING`；12 个通道在 SAMPLE
  中固定为 `null` + `NO_DATA`。
- 影响：无法判断 12 路电极电压，也无法做任何空间/位置相关分析。
- 下一步：按 `docs/hardware/FSR_ONLY_INTERFACE_V2.md` §12 填表 → 填 `map` → 改
  `mapping_status = TABLE_PROVIDED` → 重新生成头文件并编译。禁止猜测或按行优先"示例"填充。

### I-108｜12 路电极电压不能代表 36 个压力点（ACCEPTED_LIMITATION）

- 12 根电极是 12 个电位节点，不是 36 个独立测量单元。界面/分析/报告都不得把 12 通道渲染成
  6×6 热图或宣称 36 点已测；`matrix_rows/cols` 恒为 `null`，解析器拒绝旧的 38 通道 HYBRID 帧。

### I-109｜HYBRID_6X6_FSR2 已封存（OPEN，流程）

- 旧 profile/配置/头文件/fixtures 已从本分支删除（仍可在 git 历史 2026-11-14 提交中查看）。
- 生成器对 `HYBRID_6X6_FSR2` 报错；参考解析器报 `PROFILE_HISTORICAL`；软件若仍缓存旧 fixture，
  升级时必须删除，不能把 36 通道帧当当前数据。

### I-110｜合成电极映射只用于测试（OPEN，流程）

- `tools/fsr2_sim/electrode_test_profile.h` 的 `SIM_SYNTHETIC_MAPPING` 与对应 fixture 仅用于验证
  "映射齐全时读数正确"的代码路径。它不是真实接线，不得作为配置模板或验收证据。

### I-111｜命令层仍仅编译验证（继承 I-104）

- 12 电极 profile 的 `.ino` 命令面与之前相同（PING/HELLO/STATUS/STREAM/STOP/RESET_ADC/
  VERIFY_CONFIG），仍未逐命令实测；实机验收步骤见接口文档 §11。

## 软件组记录（P2-S 历史快照）


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
