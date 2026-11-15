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
