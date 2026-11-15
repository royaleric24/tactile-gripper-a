# 项目进度记录（持续更新）

> 当前唯一总体路线：`docs/DEMO_PLAN_V2.md`；硬件接线：`docs/WIRING_FREEZE_V2.md`。只记实际完成内容，计划不冒充完成。每项进展结束同步此文件、根 `AGENTS.md` 和问题台账。

## 2026-11-15｜压敏布接线修正 / 文档同步｜docs/demo-v2

- **来源**：项目所有者在 2026-11-15 确认真实压敏布接线：12 根电极（R1–R6 各接 ADS1220 AIN + 各自 10 kΩ 下拉到 GND；C1–C6 各接 ADS1220 AIN + 各自 1 kΩ 上拉到 3.3 V），**无 GPIO 列激励、无 HI_Z、无 36 点扫描**。
- **改动（文档层，OFFLINE）**：`docs/WIRING_FREEZE_V2.md` 增加修正横幅与焊接检查清单，§4 改为 12 电极被动读取、§4.1 留空映射表（PENDING_REAL_WIRING）、§4.2 记录已废止方案；`docs/HARDWARE_DESIGN_V2.md`、`docs/DEMO_PLAN_V2.md` 删除列驱动/36 点承诺；`docs/PROTOCOL_V2_PROPOSAL.md` 新增 `MATRIX_ELECTRODES_12` 提案、`HYBRID_6X6_FSR2` 标记 HISTORICAL；`config/hybrid_sensor_v2.template.json` 改为 12 电极模板（空映射、FSR_ONLY 选中、不写 ADC/AIN 编号）；同步根 `AGENTS.md`、`docs/PROGRESS.md`、`docs/ISSUES.md`、`docs/HANDOFF_CURRENT.md` 及残留引用页。
- **测试命令与结果**：仅离线文档/JSON 检查（JSON 解析、全文 grep 检索“GPIO 列激励 / HI_Z / 36 点”）；**未运行**固件、串口、烧录、采样、PWM 或 AUTO。
- **状态**：所有真实设备相关动作暂停，等待项目所有者明确授权与真实接线记录（映射填表）。`MATRIX_ELECTRODES_12` 为 PROPOSED（validated=false）；`FSR_ONLY` 仍是当前唯一可用 profile。
- **关联问题**：I-004 改记“前提作废”；新增 I-012（映射缺失）、I-013（12 电极≠36 压力点）、I-014（HYBRID 禁用）、I-015（软件提交 8d4d7d8 未推送/评审）；I-009 状态不变，措辞更新。
- **下一步**：等真实焊接/台架记录填 `WIRING_FREEZE_V2.md` §4.1；填全并复核后再讨论生成固件 `channel_config`；在此之前不做任何实机采集或烧录。

## 2026-11-14｜P0 工程保护 / P1 文档落地｜docs/demo-v2

- **P0 OFFLINE_VERIFIED**：检查三目录 Git/HEAD/worktree、暂存/未暂存/未跟踪/忽略文件；实际共享旧 Git 仓库，main 与软件目录干净，硬件 7 修改 + 7 未跟踪。完整快照覆盖 47,302 个普通文件、8,556,395,224 字节；归档逐文件 SHA-256 与备份后原文件复核通过。数据目录候选 707 个文件、183,684,501 字节（含模拟/回放，未逐条判为实测）。原目录未写入。
- **P1**：从在线核实的公开 main `5ee92cd5a599bef497566638c7754e40a2edac4a` 创建独立 clone 和 `docs/demo-v2`。对照 ZIP 17 个文件，增量引入 docs 与 JSON；合并 README 导航及 AGENTS 规则，保留既有接口主体、历史报告、子目录指令、代码与锁文件。包内 REVIEW_FIRST/NEW_CHAT_PROMPT 留在私有来源快照。
- **检查**：检查方法与结果见 [LOCAL_INTEGRATION_V2.md](LOCAL_INTEGRATION_V2.md)。仅离线文件检查；未运行新硬件、固件烧录、串口、PWM 或 AUTO。
- **问题**：I-008 旧/公开历史隔离；I-009 协议与施工状态保持待验证；I-010 记录继承的 6 个历史缺失证据链接。I-001 设计映射维持 RESOLVED，实机验证不随文档导入升级。
- **下一步**：文档提交/PR 评审后，两组从公开组分支另建工作区开展离线任务；现场动作依后续明确授权。本次提交 SHA 由 Git 与私有交付报告记录，避免自引用。

## 2026-11-14｜交接包编制历史（导入前，仅文档副本）

- **任务**：对齐旧 ESP32 四 ADC 的引脚关系，落实文档协作与长上下文交接规则。
- **用户确认**：ADC1 `CS21/MISO34`，ADC2 `CS22/MISO35`，ADC3 `CS5/MISO26`。ADC4 `CS32/MISO33` 是后续新设计。
- **完成**：仅修改本次交付的离线文档副本、更新 JSON 配置模板、补充协作规则与交接模板。未进入本地三个工作目录，未执行真实硬件测试、Git 合并、GitHub push、Codex/DSH 操作。
- **文档核验**：对输出 JSON 解析、目标链接与旧 MISO 误标做静态检查。此项不等于固件编译或实机验证。
- **实际工程状态**：硬件分支与软件分支原有成果分别存在；V2 四 ADC/FSR 还未集成，Dashboard V1.0 仍是离线功能完成、真实 AUTO 未联调。
- **下一步**：在新对话先审查本地三个目录的实际 Git/worktree 与未提交文件；安全引入文档，再分配硬件组（ADC4/FSR）和软件组（协议/界面）的并行开发。

## 后续每次记录模板

### YYYY-MM-DD｜任务 / 阶段 / 分支

- 执行者与工作目录：
- 改动文件及功能：
- 测试命令与结果（OFFLINE / REAL / NOT_TESTED）：
- 证据/运行输出位置：
- 已解决问题与关联 Issues：
- 当前 Git SHA / 未提交文件状态：
- 下一项行动及依赖：

- 2026-11-14 补充核验：硬件 14 个 WIP 文件已恢复到隔离目录并逐文件核对 SHA-256，符号链接目标与清单一致。接线文档的 Markdown 行尾空格在暂存检查中被发现，已去除；保留首个提交，使用追加提交修正。

## 硬件组证据记录

## 2026-11-15｜压敏布 12 电极接线修正（离线）｜hw/fsr-v2

- **触发**：用户更正实物接线——R1–R6 各接一个 ADS1220 AIN 并各用 10 kΩ 下拉 GND；C1–C6 各接
  一个 AIN 并各用 1 kΩ 上拉 3.3 V。**不存在 GPIO 列驱动 / HI_Z / 36 点扫描**。
- **撤回**：`HYBRID_6X6_FSR2`（38 通道、36 扫描单元）标记为历史性实验实现；`COLUMN_SCAN_6X6`、
  `driveColumn()`、`parkColumns()`、GPIO 列激励代码与配置已从本分支删除；生成器对 HYBRID 直接
  报错，参考解析器报 `PROFILE_HISTORICAL`。
- **新增**：`MATRIX_ELECTRODES_12` profile（12 逻辑通道；+2 FSR = 14），R/C 各自独立单端读数，
  `electrode_layout` 描述 6 行 + 6 列、偏置方式与映射状态。真实 R/C→ADC/AIN 映射**仍缺失**，
  配置 `electrodes.map` 为空、`mapping_status = PENDING_REAL_WIRING`，生成头对 12 个通道使用
  0xFF sentinel，固件输出 `null` + `NO_DATA`，不伪造数值。
- **固件**：`firmware/sensor_fsr2/` 的驱动、帧构造器、采样器、sketch 与三个 profile 头文件同步
  更新；FSR_ONLY 采集路径保持不变并通过同一套回归测试。
- **离线证据**：
  - host 模拟 4 个用例 PASS（driver / FSR_ONLY / 14 通道未映射 / 12 通道合成映射）
  - `scripts/check_fsr2_frames.py` PASS，重建 9 个 fixtures（删除 3 个 hybrid fixtures）
  - `tests/test_fsr2_*.py` 49 用例 OK；仓库全量 python 套件 190 用例 OK
  - 三 profile 离线编译 PASS：FSR_ONLY 303819 B、12 电极 312611 B、12 电极 + FSR 312659 B
- **状态**：接线、烧录、上电、串口、采样、PWM、AUTO **全部暂停**，等待用户明确通知与现场映射表。
- **关联问题**：I-106（接线修正待现场复核）、I-107（R/C→ADC/AIN 映射缺失）、I-108（12 电极
  ≠ 36 压力点）、I-109（HYBRID 已封存）、I-110（合成映射样本仅供测试）。

## 2026-11-14｜V2 四 ADC + 双 FSR（FSR_ONLY 优先）

| 项 | 状态 | 证据类型 |
|---|---|---|
| V2 引脚与 profile 配置（`config/sensor_esp32_fsr2*.json`） | IMPLEMENTED | 生成器校验 + 单测 |
| 第四颗 ADS1220 driver（`ads1220_multi.*`，无 V1 配置依赖） | IMPLEMENTED_UNVERIFIED | host 模拟 31 条断言 |
| 帧构造器 / 采样器 / 命令层（`frame_builder_fsr2.*`、`sampler_fsr2.*`、`sensor_fsr2.ino`） | IMPLEMENTED_UNVERIFIED | host 模拟 + 离线编译 |
| FSR_ONLY 固件离线编译 | **PASS（离线编译）** | `evidence/fsr2/build_sensor_fsr2/` |
| HYBRID_6X6_FSR2 固件离线编译 | **PASS（离线编译）** | `evidence/fsr2/build_sensor_fsr2_hybrid/` |
| host 模拟（driver + sampler + hybrid sampler） | **PASS（host 仿真，非硬件）** | `evidence/fsr2/host_tests/` |
| 帧往返检查与 fixtures 生成 | **PASS（host 仿真，非硬件）** | `evidence/fsr2/frames/`、`tests/fixtures/fsr2/` |
| 参考解析器 `tools/fsr2/protocol_v2.py` | IMPLEMENTED | 18 条协议单测 |
| 真实接线 / 烧录 / 采样 | **NOT_STARTED（未授权）** | — |

### 历史复现命令（含已撤回的 HYBRID，不可用于当前 V2）

```bash
python3 scripts/generate_sensor_fsr2_config.py                      # FSR_ONLY 头文件
python3 scripts/generate_sensor_fsr2_config.py \
  --config config/sensor_esp32_fsr2_hybrid.json \
  --output firmware/sensor_fsr2/fsr2_config_hybrid.h
python3 scripts/run_fsr2_host_tests.py                              # g++ host 模拟
python3 scripts/check_fsr2_frames.py                                # 帧检查 + 重建 fixtures
ARDUINO_CLI="/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli" \
  python3 scripts/build_sensor_fsr2_firmware.py --build-dir "$PWD/evidence/fsr2/build_sensor_fsr2"
ARDUINO_CLI="..." \
  python3 scripts/build_sensor_fsr2_firmware.py --profile hybrid \
  --build-dir "$PWD/evidence/fsr2/build_sensor_fsr2_hybrid"
PYTHONPATH=src:. python3 -m unittest discover -s tests -p "test_fsr2_*.py"
```

`--build-dir` 必须是绝对路径（脚本用 `Path.relative_to` 记录证据路径）。

### 构建体积（离线编译结果）

| profile | program | 全局变量 |
|---|---:|---:|
| FSR_ONLY | 303471 B (23%) | 32872 B (10%) |
| HYBRID_6X6_FSR2 | 312695 B (23%) | 32872 B (10%) |

fqbn `esp32:esp32:nodemcu-32s`，arduino-cli 1.5.1，Arduino-ESP32 core 3.3.2。

### 实测行长度（帧构造器真实输出，非估算）

HELLO FSR_ONLY 1650 B；SAMPLE FSR_ONLY 931 B（ADC4 掉线 964 B）；
HELLO HYBRID 6554 B；SAMPLE HYBRID 2311 B。发送缓冲 8192 B。

### 下一步（需要现场授权）

接线核对 → 烧录 → 921600 打开串口收 HELLO → 空载基线 → 单路按压 → ADC4 断线/恢复语义。
逐条动作见 `docs/hardware/FSR_ONLY_INTERFACE_V2.md` §11。做完后把原始帧与 AVDD 实测值补到本文件，
并用真实样例替换/补充 `tests/fixtures/fsr2/`（现有一律来自 host 模拟）。

## 软件组记录（P2-S 历史快照）


更新：2026-11-14
分支：`sw/fsr-live-v2`（基于公开 `feat/dashboard-zh-v1` `9997853`）

> 本文件是任务分支的 P2-S 进度。V2 文档 PR #1（`docs/demo-v2` → main）尚未合并，
> 因此没有复制/覆盖 `docs/demo-v2` 的原始文档；PR #1 合并后再统一对齐路径与内容。

## 状态总览

| 条目 | 状态 | 证据/说明 |
|---|---|---|
| FSR_ONLY 2 通道 + HYBRID 38 逻辑通道 | PASS（离线） | HELLO/config 校验与 fixtures；不按设备猜矩阵 |
| 两路 FSR 原始 ADC/电压/相对变化/有效/趋势 | PASS（离线） | 单测 + 三个 Dashboard 路由启动；未做真实视觉走查 |
| 矩阵热图只消费 MATRIX_CELL，按 row/col | PASS（离线） | FSR 36/37 排除测试 |
| 显式空载基线 + 相对接触评分 | PASS（离线） | 无自动伪造真实基线；设备重启清基线 |
| 四态 + 无效/未标定滞回 | PASS（离线） | 边界、饱和、双 FSR 较弱通道测试 |
| 未完成命令/无效帧/过期帧不夹紧 | PASS（离线） | 策略返回 WAIT/FAULT，不调用 PWM |
| 真实 AUTO 关闭 + 显式未来入口 | PASS（离线） | `AUTO_REAL_ENABLED=False`；commissioning 必定拒绝 |
| 双设备身份/波特率/STATUS 查询 | IMPLEMENTED_UNVERIFIED | 921600 可配置；查询默认关闭；无真实串口 |
| Trial 原始帧/身份/命令/ACK/决策/CSV | PASS（离线） | 写入与导出测试；旧字段兼容 |
| Trial frames 直接 REPLAY | PASS（离线） | 自动补 HELLO 并解包 SENSOR_FRAME |
| Dashboard 三路由启动 | PASS（离线） | 当前测试套件覆盖 |
| 真实 FSR 电压/矩阵方向/串口链路 | UNKNOWN | 需硬件组确认基准、接线、扫描与方向 |
| 真实闭环 Demo | NOT_IMPLEMENTED | 未连接真实串口/烧录/动作 |

## 验证命令

```bash
PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests -v
# 278 tests, OK
```

离线演示：

```bash
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo \
  --demo-profile FSR_ONLY --data-root /tmp/gripper-fsr-demo --port 8080
```

## 2026-11-15 · 12 电极适配与 Dashboard 视觉验收

用户确认的最新接线：R1–R6 分别接 ADS1220 AIN，各自 10 kΩ 下拉到 GND；
C1–C6 分别接 ADS1220 AIN，各自 1 kΩ 上拉到 3.3 V。这不是 GPIO 逐列激励，
R/C 到具体 ADC/AIN 的物理映射仍待现场确认，12 个电极不能冒充 36 个压力点。

| 条目 | 状态 | 证据/说明 |
|---|---|---|
| `MATRIX_ELECTRODES_12` 配置与校验 | PASS（离线） | 12 个 `MATRIX_ELECTRODE`；row/column 索引各覆盖 0..5；禁止矩阵位置 |
| 12 路原始 ADC 仿真与图表 | PASS（离线） | 条形图 R1–R6/C1–C6；`heatmap_options` 对电极配置返回空图 |
| 不合成 36 点热图/接触评分 | PASS（离线） | 仿真不产生 contact_score；Live/Analysis 显示“36 点热图不可用” |
| FSR_ONLY / HYBRID / Trial / CSV / REPLAY | PASS（离线） | 既有 278 个测试保持通过，新增 7 个电极测试 |
| Dashboard 三视口 × 三页面视觉验收 | PASS（离线） | `docs/screenshots/p2s-ui-audit/`；console/page error 0 |
| R/C→ADC/AIN 物理映射 | UNKNOWN | 需硬件组现场确认 |
| 真实电极测量、串口、PWM、机械动作 | NOT_IMPLEMENTED | 本阶段未连接任何硬件 |

验证命令与结果（2026-11-15）：

```bash
PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests
# Ran 285 tests ... OK
```

UI 验收命令与截图脚本见
[docs/screenshots/p2s-ui-audit/README.md](screenshots/p2s-ui-audit/README.md) 与
`scripts/ui_screenshot_audit.mjs`。

## 2026-11-15 · P2-S 发布前最终验收（离线）

用户要求做发布前最终验收：核实工作区、重跑测试、实测 Dashboard、修复明显问题、
补文档、提交并推送软件分支、创建 PR（不合并）。本轮未进入新开发阶段，未接硬件。

### 验收环境

| 项 | 值 |
|---|---|
| 工作区 | `tactile-gripper-v2-sw`（本机 checkout，路径按机器而异） |
| 分支 | `sw/fsr-live-v2` |
| 验收前 HEAD | `884a8c41bc204d4e9c958c3b7c3821f8130103e7` |
| 公开基线 | `origin/feat/dashboard-zh-v1` = `999785308e0fb38659a90302a3388d82cdd0b424` |
| 祖先关系 | `git merge-base origin/feat/dashboard-zh-v1 HEAD` == `9997853`（成立） |
| Python | 3.13.15（`.venv`，`nicegui==4.0.0`） |
| 数据来源 | `SIMULATION` only（`--demo`），未打开任何串口 |

### 测试（本轮实际执行）

```bash
# 在仓库根目录执行
PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests
# Ran 290 tests ... OK (skipped=1)
git diff --check    # 无输出
```

- 290 通过 / 0 失败（Python 3.13.15）。此前交接记录的 285 项已复核：确实为 285，
  本轮新增 5 项显示层测试（`DashboardDisplayTests` 2 项、`ContactReasonTests` 2 项、
  `DynamicEventDetailTests` 1 项）。
- 1 项跳过：`test_trial_interactive_input.InteractiveInputTests.test_pty_waits_for_explicit_input`
  —— 本机沙箱无 pty（`out of pty devices`）。GitHub Actions 的 ubuntu 环境应可运行；
  本地无法证明。
- 工作区无 `tools/` 目录，CI 中 `for suite in tools/*/tests` 循环为空转。

### Dashboard 实测（重新运行，不只依赖旧截图）

```bash
# 终端 1 / 2：两个离线仿真 Dashboard（各自独立 data-root）
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo \
  --demo-profile HYBRID_6X6_FSR2 --data-root /tmp/gripper-ui-audit --port 8095
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo \
  --demo-profile MATRIX_ELECTRODES_12 --data-root /tmp/gripper-electrode-audit --port 8096

# 终端 3：真实无头 Chrome 截图 + 布局度量
CHROME_NO_SANDBOX=1 AUDIT_BASE=http://127.0.0.1:8095 OUT_DIR=/tmp/audit-final/after \
  LABEL=after node scripts/ui_screenshot_audit.mjs
CHROME_NO_SANDBOX=1 AUDIT_BASE=http://127.0.0.1:8096 OUT_DIR=/tmp/audit-final/after-electrodes \
  LABEL=after-electrodes node scripts/ui_screenshot_audit.mjs
CHROME_NO_SANDBOX=1 AUDIT_BASE=http://127.0.0.1:8095 OUT_DIR=/tmp/audit-final/narrow \
  LABEL=narrow VIEWPORTS=1024x768 node scripts/ui_screenshot_audit.mjs
```

结果：3 视口 × 3 页面 × 2 profile = 18 张视口截图 + 18 张整页审计图 + 1024×768 抽查
3 张；18 个页面 console/page error 均为 0；任何视口下 `body.scrollWidth` 都等于视口
宽度（无页面级横向滚动）。截图与度量见
[docs/screenshots/p2s-ui-audit/](screenshots/p2s-ui-audit/README.md)。

### 本轮修复（均为显示层，无协议/控制变化）

| 问题 | 证据 | 修复 |
|---|---|---|
| 帧时间显示 `3345443.070s`（主机单调时钟当秒数） | 旧 `after/live-*.png` | 帧说明改为 `接收于 HH:MM:SS（本机时间）`，取自 `host_received_utc` |
| 接触判断原因整段英文 | 旧 Live 截图 | `text_zh.contact_reason_label()` 翻译固定原因，动态原因保留数字 |
| 事件说明漏译 `SIMULATION sensor connected (PROFILE); ...` | 旧整页截图 | `event_detail_label()` 增加该前缀规则 |
| 三个页面各自复制 `_clock()`，把 UTC 当本机时间显示 | `live/experiments/analysis` | `theme.clock_label()` 统一转本机时间；表头改“时间（本机）” |
| 分析页侧栏残留“离线（OFFLINE）”“等待数据”、顶栏“待机” | 旧 `after/analysis-*.png` | 用只读 `core.snapshot()` 同步侧栏与顶栏（不新增写路径） |
| 12 电极条形图无单位、无读数、Y 轴出现 `2,134.55` 这类小数刻度 | 旧 `after-electrodes/live-*.png` | Y 轴名“ADC 计数”、柱顶读数（≤14 通道）、刻度取整 |
| 热图色条压在 C 轴标签行 | 旧截图 | 热图 `grid.bottom` 44→58，色条单独一行 |
| FSR 趋势图左侧轴名 `ADC` 与图例重叠 | 旧 `after/analysis-*.png` | 去掉与图例重复的轴名 |
| 无头 Chrome 在沙箱内启动失败时脚本静默退出 0、不产图（假 PASS） | 复现：WS 未 open 时 Promise 不落地 | `connect()` 增加 close/timeout 拒绝；新增 `CHROME_NO_SANDBOX=1` 开关 |
| `before/audit.json` 内含本机绝对路径 | `git grep /Users/` | 9 处改为仓库相对路径 |

未改：协议字段、单位换算、AUTO 门控、Trial/CSV/REPLAY 格式、硬件组固件代码。

### 发布状态

| 项 | 值 |
|---|---|
| 目标分支 | `feat/dashboard-zh-v1`（公开软件历史祖先，已确认） |
| 远程分支 | `origin/sw/fsr-live-v2`（本轮新建） |
| PR | [#4](https://github.com/royaleric24/tactile-gripper-a/pull/4) → `feat/dashboard-zh-v1`；本轮**不合并** |
| CI | GitHub Actions `Offline tests`：push 与 pull_request 两个 run 均 **PASS**（2026-11-15） |

### 状态标注

- OFFLINE_VERIFIED：上述 290 项测试、三视口截图与布局度量、AUTO 硬关闭、坏帧/
  失联不产生新的 PWM 目标。
- VERIFIED_REAL：**无**（本轮未接任何真实设备）。
- NOT_TESTED：真实串口、真实 FSR/电极读数、PWM 与机械动作、真实 AUTO。

## 下一步

1. 现场确认 R/C→ADS1220 AIN 的物理映射、ADS1220 通道/增益/基准与扫描顺序，
   再决定是否启用真实电极采样。
2. 与硬件/集成组确认 `docs/SOFTWARE_V2_P2S_REPORT.md` 第 10 节接口问题。
3. PR #1 合并后对齐 V2 文档，避免本分支 PROGRESS/ISSUES/HANDOFF 与主线重复。
4. 获得现场授权后，先做只读双串口识别与 HELLO/STATUS，再做单步 PWM，不直接开 AUTO。
5. 标定 FSR 基线、极性和饱和，确认电压换算与矩阵方位后，才讨论真实 AUTO。

## 发布记录

- 2026-11-15：`sw/fsr-live-v2` 推送至 `origin/sw/fsr-live-v2`
  （`7a1bf07ca62fe6cc27864d716a85b4f16799f5f3`）。
- 2026-11-15：创建 PR
  [#4](https://github.com/royaleric24/tactile-gripper-a/pull/4)
  → `feat/dashboard-zh-v1`（91 个文件、+9593/−127、3 个 commit、`MERGEABLE`）。
  GitHub Actions `Offline tests`：push run 19s PASS，pull_request run 22s PASS。
- **未合并**，也未操作 `integrate/hybrid-demo-v2` 或启动 P3-A；等待总控审核。
