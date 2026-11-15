# Tactile Gripper 协作指令

目标是用触觉皮肤估计接触与滑移风险，逐步验证加水过程中杯子的保持与形变。验收需同时记录杯子、夹爪动作与触觉信号。当前验证范围见 README。

## 最近状态（P3-B1 真实 FSR 接管，2026-11-15）

已完成 `hw/p3b1-fsr-real` 上的真实 FSR_A 数据接管与探索性分析：固件 `tactile-fsr2-0.3.0`、
ADC4 AIN0/MUX8、5247 个有效 SAMPLE、61.74 Hz、帧序 1–5247 无缺帧、ADC4 全程 OK、无饱和。
操作者未按三段式计划，采集起点很可能是**第一处按压已在进行**（0–4.2 s 的 4.16M 不是已验证空载）；
约 4.6 s 首次持续下降 −470k、约 48.8 s 大幅下降 −1.72M、约 70 s 后回升，按“下降=释放/移动、
上升=第二处按压”读法与 `VOLTAGE_RISES_WITH_FORCE` 一致；事后 15:37Z 空载基线（中位 1.7k，
≈0）支持该读法，极性 **SUPPORTED（非单 trial）**。接触变化清晰，**FSR 初步响应验证成功**，不需重做手指三段式；
counts→牛顿/摩擦/滑移/杯重 **NOT_SUPPORTED**。详见
[P3-B1 分析](docs/P3B1_FSR_REAL_ANALYSIS.md) 与 [问题](docs/ISSUES.md)（I-207 起）。

事后 15:37Z 空载基线中位 1.7k counts（≈0）与 0–4.2 s 的 4.16M 一致，230/494 帧 flag 0x04
是零点噪声，不是通信故障。**S3 已于 2026-11-16 恢复**：真实端口 `/dev/cu.usbserial-A5069RR4`，
构建并上传 `gripper-control-s3-0.9b26.0`（460800、无全片擦除、每段 hash verified），
真实 STATUS 为 **DISARMED**、GPIO4、50 Hz、14-bit、`output_state=DISABLED_UNMEASURED`、
0 ERROR/0 FAULT/0 timeout；初始恢复 app SHA `d20782…`（历史 `04c77eed…`，同源同配置，见 I-216），
**当前运行是 TX 修复版 `bd039a8…`**。
2026-11-16 两次空杯 MANUAL 控制台均 `response_timeout`：最后命令分别是 HEARTBEAT seq30
（`e4fddfe2…`）与 BENCH_HOLD_MODE seq4（`4d0c5503…`）；两次都收到约 950 B 的正确 ACK，
但中间有 12/13 个 NUL，JSON 解析失败后主机 3 s 超时。根因为 `respond()` 的 900 B TX 阈值
小于实测 942–963 B 应答；已改为 `measureJson(d)+2` 精确预留 + 150 ms 有界等待 + 紧凑
`TX_BACKPRESSURE` ERROR。修复 app `bd039a8…`（317840 B）离线编译 PASS，380 tests OK；已 **460800 重烧**并通过真实
无 PWM 验证（64/64 应答匹配、64 条应答 0 NUL、5 次连续会话 + 20 次背靠背 HEARTBEAT 全 PASS，
最终 DISARMED/DISABLED_UNMEASURED）。两次失败会话均**未发 PWM、无 BENCH_ACTION、无机械运动**；
失败 FSR 原始数据已保存（17,392 SAMPLE，非空杯结果）。Dashboard LIVE 握手仍未修好，
未验证修改保存在 `evidence/p3b1/private/dashboard_handshake_unverified.patch`，未提交、未合并，
不再作为空杯前置条件。**下一步：修复版已重烧并验证 PASS；按用户指示暂不自行开始运动，
等待用户明确恢复后重跑 console。**

## 最近状态（P3-A V2 集成，2026-11-15）

在独立 `integrate/hybrid-demo-v2` 合入 main `633e570`、硬件 `0827536` 与软件 `2c5a996`。
P3-A 已按 [Issue #3](https://github.com/royaleric24/tactile-gripper-a/issues/3) 完成离线实现与验证，
集成 PR 由总负责人评审。PR #5 按总控复核更新当前目标：`FSR_ONLY`（1）与 `MATRIX_ELECTRODES_12`（12/13），唯一 FSR_A 为 ADC4 AIN0，MUX 8。
旧 2/14 通道供仿真和历史回放；`HYBRID_6X6_FSR2` 只用于标为 HISTORICAL 的旧记录。
Dashboard 的固件样例经过实际适配/记录链路。独立的「36 格仿真」只使用合成格值，无控制或记录入口。
看 [验收](docs/P3A_ACCEPTANCE.md)、[交接](docs/HANDOFF_CURRENT.md) 和 [问题](docs/ISSUES.md)。
真实操作仍暂停；`AUTO_REAL_ENABLED=False`。日志、真实原件和工具缓存只留本地。

## 软件组状态（P2-S 历史，2026-11-15）

`sw/fsr-live-v2` 已完成 FSR_ONLY / HYBRID_6X6_FSR2 离线适配、两路 FSR 相对接触评估、
矩阵/FSR 分流、双设备身份与 Trial/CSV/REPLAY 扩展。2026-11-15 追加
`MATRIX_ELECTRODES_12`（R1–R6 / C1–C6 各接 ADS1220 AIN）离线适配：只显示 12 路
原始 ADC，不合成 36 点压力热图；FSR_ONLY 与既有 Trial/CSV/REPLAY 保持。

2026-11-15 完成**发布前最终验收**：全套 **290 个离线测试通过**（1 项 PTY 交互测试因
本机沙箱无 pty 跳过，CI 上应运行）。Dashboard 重新实测截图（1440×900 / 1280×800 /
1920×1080，Live/Experiments/Analysis × HYBRID 与 12 电极），并补 1024×768 抽查，
见 [docs/screenshots/p2s-ui-audit/](docs/screenshots/p2s-ui-audit/README.md)。本轮修复
均为显示层：帧接收时间显示本机时钟（原先把主机单调时钟当秒数显示）、接触判断原因
与仿真事件说明中文化、条形图加 ADC 单位与读数、分析页侧栏/顶栏同步只读快照（原先
残留“离线/待机”占位）、热图色条与坐标标签分离。无协议、单位换算或控制权限变化。

真实 AUTO 仍硬关闭（`AUTO_REAL_ENABLED=False`），显式 commissioning 入口当前必定
拒绝。R/C→ADC/AIN 物理映射尚未现场确认；未打开真实串口、未烧录、未发 PWM、未做
机械动作；协议仍为 PROPOSED。详见 [P2-S 报告](docs/SOFTWARE_V2_P2S_REPORT.md)、
[进度](docs/PROGRESS.md)、[问题](docs/ISSUES.md)、[交接](docs/HANDOFF_CURRENT.md)。

## 所有权与入口

| 分支 | 维护范围 | 代码入口 |
|---|---|---|
| main | 总负责人管理稳定基线、跨组契约、集成和发布 | docs/INTERFACE_CONTRACT.md、config/、tests/ |
| feat/hardware-acquisition | 采集板、接线、ADC、设备协议、台架及原始设备日志 | firmware/、tools/tactile_acq/、硬件分支 docs/hardware/ |
| feat/dashboard-zh-v1 | 主机适配、控制状态机、中文界面、存储、回放与集成实现 | src/gripper_a/、软件分支 src/tactile_gripper/ |

目录随分支而异。scripts/ 与 config/ 按功能归属；修改前从调用入口核对消费者。firmware/AGENTS.md 和 src/AGENTS.md 分别细化设备端和主机端规则。

## 开发与集成

- 先用 git status -sb 和 git worktree list 核对分支与本地成果。一个任务一个分支；共享 Git 历史，各工作区独立暂存。提交显式列出本次文件。
- 按当前分支 pyproject.toml 使用 uv sync --locked。离线测试从仓库根运行：`PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests`。硬件工具测试单独发现，见 CONTRIBUTING.md。
- PR 写明基线、修改范围、可重复的命令、结果及未测条件。提交采用 type(scope): 摘要。协议、单位、板级配置、超时或控制权限有变化时，由两组检查生产者、消费者、旧帧和故障路径，总负责人合入 main。
- 模拟、回放、混合实验和真实 Trial 分开归档。真实实验保存 Trial ID、固件与配置版本、原始帧、动作与回复、时间戳、视频关联及失败原因；原件留在本地。对外提供经过审查的最小样例。
- 使用 PASS 标注已验证的具体行为并写明证据类型。其余按 IMPLEMENTED_UNVERIFIED、IN_PROGRESS、NOT_IMPLEMENTED、UNKNOWN 描述。没有独立标定时仅报告 ADC counts 或接触评分；没有实测反馈时角度和开度记为未知。
- 离线编译、模拟、代码修改及离线测试可连续执行。打开真实串口、采样、烧录、接线、上电、PWM 与机械动作需现场明确授权，限定设备、动作及会话。上传和运动分别授权。
- 保留已验固件、配置、实验原件与 Git 历史；稳定版本见 docs/ASSET_MANIFEST.md。实机默认 DISARMED，断连后重新授权；保留配置门控、停止、失联处理及分模式限位。禁止自动回中、扫描端点或重放旧运动。

## V2 增量规则（2026-11-14）

当前总体路线以 [docs/DEMO_PLAN_V2.md](docs/DEMO_PLAN_V2.md) 为准，接线以 [docs/WIRING_FREEZE_V2.md](docs/WIRING_FREEZE_V2.md) 为准。协议提案保持 PROPOSED，现有接口和历史记录原位保留。旧三工作区与公开仓库历史独立，禁止将旧提交直接推入公开仓库；日常协作从已发布组分支建立任务分支。

禁止 `reset --hard`、`clean -fd`、强制推送、重写历史或未经检查覆盖文件；备份失败、未提交成果覆盖风险或历史冲突时停止相关写入并集中报告。

## 设计优先级

1. FSR-only 串口采集 + 真 LIVE Dashboard。
2. 真实 S3 MANUAL PWM + 日志、断连行为。
3. FSR 实际闭环规则 + 加水 Trial。
4. 12 电极被动读取（辅助，12 个单端电压，不是 36 点矩阵；电极→ADC/AIN 映射 PENDING_REAL_WIRING）；更高级功能靠后。

## 实机已知观察

同一指定水杯：`1300 μs` 现场观察刚好夹住不显著形变，`1270 μs` 已有可见形变。前者只是起始参考，后者是风险观察点，不等于正式机械限幅。自动步幅、阈值、方向、功率与停止策略以现场复测为准，不凭空填写。

## 固定的 V2 硬件接口（用户确认，2026-11-14）

ADC1 = CS GPIO21 / MISO GPIO34；ADC2 = CS GPIO22 / MISO GPIO35；ADC3 = CS GPIO5 / MISO GPIO26。ADC4 计划 CS GPIO32 / MISO GPIO33；四 ADC 共用 SCLK GPIO18、MOSI GPIO23。**不得沿用旧硬件配置中的 MISO `[35,26,34]` 生成 V2 固件**。新方案的实机 SPI 验证尚未进行。接线唯一基准见 `docs/WIRING_FREEZE_V2.md`。

## 压敏布接线修正（2026-11-15，项目所有者确认）

- 真实压敏布是 **12 根电极**：R1–R6 各接自己的 ADS1220 AIN 并各有一颗 **10 kΩ 下拉到 GND**；C1–C6 各接自己的 ADS1220 AIN 并各有一颗 **1 kΩ 上拉到 3.3 V**。
- **没有 ESP32 GPIO 列激励、没有 HI_Z、没有 36 点扫描**。原 GPIO4/13/14/25/27/19 “逐列驱动 + 未选中列 HI_Z + 拼 36 点”方案已被 2026-11-15 修正取代（HISTORICAL），不得再用于施工、固件或演示。
- 12 个电极电压 = **12 个测量值，不是 36 个压力点**；真实电极图只用 12 路 ADC 条形图。36 格热力图仅在独立 SIMULATION 演示或 HISTORICAL 回放中出现。
- **电极 → ADC/AIN 映射 PENDING_REAL_WIRING**：必须由真实焊接/台架记录填写 `docs/WIRING_FREEZE_V2.md` §4.1 空白表；填表前不得写任何 ADC/AIN 编号或“示例映射”，不得假设行优先。
- 协议侧当前支持 `FSR_ONLY`（1 通道）及 `MATRIX_ELECTRODES_12`（12 电极，可选 FSR_A 合计 13 通道）；仅完成离线验证，现场映射保持 `validated=false`。
- 所有真实串口、烧录、采样、PWM 与 AUTO 工作**暂停**，等待项目所有者明确授权与真实接线记录。

## 每个开发进展的强制文档同步

每完成一个可辨识的工作进展（整阶段内也一样），不只更新代码：

1. 更新相应技术文件（接线、协议、配置、运行教程或测试记录），与实际变更保持一致。
2. **更新本文件 `AGENTS.md` 的“最近状态”**：本轮进展摘要、状态、指向进度台账的链接。若子目录有 `firmware/AGENTS.md` 或 `src/AGENTS.md`，仅在相应规则变化时同步改；不要删除旧子目录指令。
3. **更新 `docs/PROGRESS.md`**：日期、任务/分支、实际改动、验证命令/结果、真实或模拟、下一步。
4. **更新 `docs/ISSUES.md`**：新问题和阻碍、已有问题状态变化，标明负责人或待确认来源；不默默删除问题。
5. 若影响下一次会话或角色交接，**更新 `docs/HANDOFF_CURRENT.md`**：当前环境、已执行操作、分支/提交、待做任务、注意事项。

代码、测试与上述文档应在同一任务完成时共同交付；能提交时同次提交。离线代码工作不因频繁文档同步而被拆成逐条审批。若仅是讨论且尚未操作项目，就将状态写为 **PLANNED / NOT_EXECUTED**，不得填报已验证。

## 长上下文与跨对话交接

当 GPT / Codex / DSH 对话变长，开始出现重复信息、前后矛盾、遗漏分支状态或难以继续追踪当前进展时，主动提醒开启新对话。先更新/产出 `docs/HANDOFF_CURRENT.md`，提供可复制的新对话提示词，包括：目标、主要文档入口、已完成与待完成、文件位置、Git 状态、关键硬件映射、最近测试、未解决问题、下一项工作。不要自动假设新对话读取了老对话的上下文。

## 最近状态

- 2026-11-15：**接线修正（项目所有者确认）**。真实压敏布为 12 电极、全被动单端读取，原 GPIO 列激励 / HI_Z / 36 点扫描方案作废（HISTORICAL）；`HYBRID_6X6_FSR2` 撤回，新增 `MATRIX_ELECTRODES_12` 提案（12 逻辑通道，映射 PENDING_REAL_WIRING，validated=false）。`WIRING_FREEZE_V2.md`、`HARDWARE_DESIGN_V2.md`、`DEMO_PLAN_V2.md`、`PROTOCOL_V2_PROPOSAL.md` 与 `config/hybrid_sensor_v2.template.json` 已同步修正（文档层，无实机动作）。真实串口/烧录/采样/PWM/AUTO 全部暂停，等待明确授权与真实接线记录。详见 [进度](docs/PROGRESS.md)、[问题](docs/ISSUES.md) 与 [交接](docs/HANDOFF_CURRENT.md)。

- 2026-11-14：P0 完整归档与逐文件 SHA-256 核验通过；旧三工作区保持原状，硬件组 7 修改 + 7 未跟踪受到保护。P1 在公开 main `5ee92cd` 的独立工作区 `docs/demo-v2` 增量引入文档。静态检查通过（12 JSON、无新增断链），6 处历史缺失证据链接记为 I-010。ADC1–3 设计已确认，ADC4 待施工，协议仍 PROPOSED，V2 实机未验证。详见 [进度](docs/PROGRESS.md)、[问题](docs/ISSUES.md) 与 [交接](docs/HANDOFF_CURRENT.md)。本轮范围止于 P0/P1，无硬件动作、烧录或 AUTO。

- 2026-11-14 补充核验：硬件 14 个 WIP 文件已恢复到隔离目录并逐文件核对 SHA-256，符号链接目标与清单一致。接线文档的 Markdown 行尾空格在暂存检查中被发现，已去除；保留首个提交，使用追加提交修正。

## 硬件组离线记录（2026-11-15；历史分支上下文）


- 压敏布实为 **12 根独立电极**：R1–R6 各接 ADS1220 一个 AIN 并各用 10 kΩ 下拉 GND；C1–C6 各接
  一个 AIN 并各用 1 kΩ 上拉 3.3 V。**无 GPIO 列驱动、无 HI_Z、无 36 点扫描**；12 路电压不是
  36 个压力点。`COLUMN_SCAN_6X6` / `driveColumn()` / `parkColumns()` 与 HYBRID profile 已撤回，
  生成器拒绝 HYBRID、解析器报 `PROFILE_HISTORICAL`。
- 新 profile `MATRIX_ELECTRODES_12`（12 通道；+2 FSR = 14 通道）。真实 R/C→ADC/AIN 映射
  **仍缺失**：配置 `electrodes.map = []`，固件对 12 个通道输出 `null` + `NO_DATA`，不伪造。
- 证据：三 profile 离线编译 PASS（303819 / 312611 / 312659 B）、host 模拟 4 用例 PASS、
  fixtures 9 个重建、`test_fsr2_*` 49 用例 OK。**未接线、未烧录、未真实采样**。
- `docs/demo-v2`（PR #1）已在独立工作区同步修正（12 电极、无列驱动、映射 PENDING、HYBRID 历史）。
- 硬件操作全部暂停，等用户明确通知与现场映射表；进度/问题/交接见 `docs/PROGRESS.md`、
  `docs/ISSUES.md`（I-106 起）、`docs/HANDOFF_CURRENT.md`。

## 历史状态（V2 硬件 / FSR_ONLY，2026-11-14）

- 新分支 `hw/fsr-v2`（基线 `origin/feat/hardware-acquisition` @ b38e7bb），独立 worktree `~/Developer/research/tactile-gripper-v2-hw`；旧 `tactile-gripper-a-hw` 的 7 修改 + 7 未跟踪 WIP 已原样保护，未并入本分支。
- V2 引脚冻结：ADC1 21/34、ADC2 22/35、ADC3 5/26、**ADC4 32/33**，四颗共用 SCLK18/MOSI23；FSR_A/B = ADC4 AIN0/AIN1，各自 10 kΩ 下拉，节点不互连。历史 `miso=[35,26,34]` 只属 V1，V2 生成器拒绝 3 ADC 配置。
- 固件 `firmware/sensor_fsr2/` 自包含（driver/frame builder/sampler/生成头），不改动冻结的 `firmware/sensor/`。FSR 参考强制 `AVDD_AVSS`（内部 2.048 V 会削顶）。
- 当前证据等级：两 profile **离线编译 PASS**（FSR_ONLY 303471 B / HYBRID 312695 B）、host 模拟与帧检查 **PASS**；**未接线、未烧录、未真实采样**，因此真实硬件行为一律 `IMPLEMENTED_UNVERIFIED`。
- 接口以 `docs/hardware/FSR_ONLY_INTERFACE_V2.md` 为准（921600 8N1、null+valid 语义、实测行长度、验收清单）。软件组待办：`tools/tactile_acq/protocol.py` 需 profile 化（现硬编码 12 通道），波特率 115200 → 921600。
- 进度、问题、交接：`docs/PROGRESS.md`、`docs/ISSUES.md`（新增 I-012 起）、`docs/HANDOFF_CURRENT.md`。`docs/demo-v2`（PR #1）未合入，本分支只引用不复写其文件。
