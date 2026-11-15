# 当前交接｜P3-B1 真实 FSR 接管（2026-11-15）

- **工作区/分支**：`~/Developer/research/tactile-gripper-v2-p3b1`，`hw/p3b1-fsr-real`，
  基线 `af1758e`（main 已合入 PR #5）。`git status -sb` 仅 `.venv` 为未跟踪符号链接。
- **已完成的真实采集**：`tactile-fsr2-0.3.0` / `FSR_ONLY` / ADC4 AIN0 MUX8，CP2102 921600 8N1，
  约 85.0 s、5247 SAMPLE、61.74 Hz、帧序 1–5247 无缺帧、ADC4 全程 OK、无饱和。
  原始 JSONL/CSV 与旧分析在 `evidence/p3b1/private/real_20261115_2314/`（`evidence/` 已 gitignore，未提交）。
- **分析结论**：操作者没有按三段式计划；4.6 s 首次持续下降 −470k counts、48.8 s 大幅下降 −1.72M、
  70 s 后方差下降并缓慢回升；85 s 内未回到初始基线。接触变化清晰，**FSR 初步响应验证成功**，
  不需要重做手指三段式。详见 [P3-B1 分析](P3B1_FSR_REAL_ANALYSIS.md) 与
  [曲线图](screenshots/p3b1/fsr_a_real_curve_v2.png)。
- **关键未决**：两个主要变化都是 counts 下降，与 `VOLTAGE_RISES_WITH_FORCE` 相反；
  极性 **UNVERIFIED**。Dashboard 接触评分只认上升，空杯实验必须用“空载→夹持→释放”重新确认符号。
  counts→牛顿/摩擦/滑移/杯重 **NOT_SUPPORTED**。
- **当前硬件阻塞**：Mac 只枚举到旧 ESP32 CP2102 `/dev/cu.usbserial-0001`；S3 的 FT232R 串口
  **未出现**（I-210）。本会话沙箱无 PTY，`pwm_console.py --real` 不能由代理直接运行（I-211）。
  下一步需要用户连接 S3 USB/舵机电源并核对共地、机械状态，然后在自己的 Terminal 运行 console。
- **空杯实验预案（尚未授权）**：PWM **1300–1500 μs、50 μs 步进、1300 为下限，不进 1270**；
  先无杯 1500→1450→1400→1350→1500 验证方向，再空杯 1500→1450→1400→1350→1300，
  首次接触即停，保持并观察，释放回 1500；2 次（最多 3 次）抓取/释放。
  `AUTO_REAL_ENABLED=False`；FSR 只记录，不闭环。
- **数据分工**：用户 terminal 的 `pwm_console.py --target s3` 独占 S3 串口并写
  `logs/real/bench/<id>/transport.jsonl`；本进程用独立采集脚本独占 FSR 串口写
  `evidence/p3b1/private/cup_*`。两个进程不得打开同一设备。
- **未执行**：未发 PWM、未做机械动作、未重烧 S3、未做 AUTO、未做加水。
- **下一步顺序**：S3 端口出现 → 只读 STATUS 核对 0.9b26.0/board_target/pwm_gpio=4/50 Hz/14-bit/
  DISARMED → 用户一次授权 → 无杯方向 → 空杯抓取 → Dashboard LIVE FSR 曲线 → 保存/分析/文档/
  commit/push/PR（不合并）。

# 当前交接｜P3-A V2 离线集成（2026-11-15）

集成分支 `integrate/hybrid-demo-v2`；独立目录同级 `tactile-gripper-v2-integration`。
已核对 GitHub 基线：main `633e570623d90777aa204142c269ebe69eb59ac2`、
硬件 `08275363736aace39ca893b4fb64660df95a7b8b`、
软件 `2c5a996aacc86d9e100018ce3c4cb8fa77b16aee`。
增量以首轮 P3-A 提交 `7e6c425` 为起点，在同一 [PR #5](https://github.com/royaleric24/tactile-gripper-a/pull/5) 待审。
当前 FSR_A 接 ADC4 AIN0/MUX8，FSR_B 已损坏。现行固件 `fsr1`、`electrodes12_fsr1` 对应 1/13 通道，
`electrodes12` 仍为 12 通道。旧双 FSR 构建只作离线兼容；「36 格仿真」入口为 `/demo-6x6`。[接线确认](https://github.com/royaleric24/tactile-gripper-a/pull/5#issuecomment-6895547216)

旧工作区、WIP 与原始记录未改动。工作区采用锁定依赖，测试 Python 3.13，CI Python 3.11。

接手先查 [验收报告](P3A_ACCEPTANCE.md)、[中文启动指南](DASHBOARD_QUICKSTART_ZH.md)、
[现行接口](INTERFACE_CONTRACT.md)、[问题台账](ISSUES.md)。完整本地日志、浏览器审计、仿真 CSV/JSONL
增量证据保留在集成工作区 `evidence/p3-a-followup/`，首轮证据仍在 `evidence/p3-a/`；公开分支只保留审查后的证据摘要和截图。

**下一步：总负责人审阅集成 PR → main，P3-A 执行人不合并。**
真实串口、烧录、真实采样、上电、PWM、真实 AUTO 全部未执行且保持暂停。
P3-B 要求项目所有者单独授权。现场先核对 AIN1 上的损坏器件是否已电气隔离、3.3 V 与 10 kΩ 分压，再核对 R/C→ADC/AIN 接线表。
`AUTO_REAL_ENABLED=False`；保留原工作区和物理记录。

## P0/P1 文档组交接快照（历史）

## 项目与唯一入口

项目：`royaleric24/tactile-gripper-a`；科展式兴趣工程 Demo，非科研论文。**总体方案 `docs/DEMO_PLAN_V2.md`**；接线唯一基准 `docs/WIRING_FREEZE_V2.md`；接口提案 `docs/PROTOCOL_V2_PROPOSAL.md`；协作规则 `AGENTS.md`；实施状态 `docs/PROGRESS.md`；阻碍 `docs/ISSUES.md`。

## 必须沿用的硬件事实

用户已确认新图的 V2 ADC 接线：旧 ESP32 ADC1=CS GPIO21/MISO GPIO34，ADC2=CS GPIO22/MISO GPIO35，ADC3=CS GPIO5/MISO GPIO26；四 ADC 共用 SCLK GPIO18/MOSI GPIO23；新增 ADC4 **计划** CS GPIO32/MISO GPIO33，FSR1=A4 AIN0、FSR2=A4 AIN1，二者各自 10kΩ 独立下拉。

**2026-11-15 修正（项目所有者确认）**：真实压敏布是 **12 根电极**，不是 6×6 扫描矩阵。R1–R6 每根接自己的 ADS1220 AIN 并各有一颗 10 kΩ 下拉到 GND；C1–C6 每根接自己的 ADS1220 AIN 并各有一颗 1 kΩ 上拉到 3.3 V。**没有 GPIO 列激励、没有 HI_Z、没有 36 点扫描**；原 GPIO4/13/14/25/27/19 列驱动方案已作废（HISTORICAL）。12 个电极电压 = 12 个测量值，不是 36 个压力点。**电极 → ADC/AIN 映射 PENDING_REAL_WIRING**，须等真实焊接/台架记录填写 `WIRING_FREEZE_V2.md` §4.1；填表前不得猜测或写示例编号。`HYBRID_6X6_FSR2` 已撤回；`MATRIX_ELECTRODES_12` 是 PROPOSED（validated=false），`FSR_ONLY` 仍是当前唯一可用 profile。

另有 ESP32-S3 + PM15S 真 PWM 控制；指定水杯下 1300μs 观察到刚夹住未显著变形，1270μs 观察到轻度形变，这两个值不是正式限位。Mac Python / NiceGUI 中文 Dashboard V1.0 离线开发基本完成，尚无真实 AUTO 集成。

## Git / 工作目录（本次已核实）

| 目录名（同级） | 分支 | HEAD | 状态 |
|---|---|---|---|
| tactile-gripper-a | main | 22bb3604187113114ab4c3824c5a3b0a2cf06e48 | 干净 |
| tactile-gripper-a-hw | feat/hardware-acquisition | 48272022b0a449e8165a88622e12fb58edbf6296 | 7 修改 + 7 未跟踪，未暂存 |
| tactile-gripper-a-sw | feat/dashboard-zh-v1 | 8461e39f25278a17e3f629cf8f3459d114a99044 | 干净 |

上述三目录共享旧 Git 历史，无 origin。公开脱敏历史独立；本次另建 tactile-gripper-v2-docs，从已在线核实的公开 main `5ee92cd5a599bef497566638c7754e40a2edac4a` 创建 `docs/demo-v2`。不要从旧三目录推送、merge 或 cherry-pick 到公开仓库。

## 这一轮完成/未完成

- P0：完整工程归档、Git 状态与差异快照、逐文件 SHA-256 校验及备份后源文件复核通过，原目录保持原状。恢复时先解压到隔离路径，再处理 .git/worktrees 中原路径，禁止覆盖现有工作区。
- P1：核对实际 ZIP，增量引入 V2 docs/config，合并 README/AGENTS、更新进度与问题，保留旧接口和报告。检查结果见 [LOCAL_INTEGRATION_V2.md](LOCAL_INTEGRATION_V2.md)。静态检查通过，6 处继承的缺失证据链接见 I-010。具体提交及 PR 结果由 Git 与本地保护目录报告记录。
- 私有证据位置：与三个旧目录同级的 tactile-gripper-v2-protection-20261114；包含 original-workspaces.tar.gz、manifest.json、SHA256SUMS、VERIFIED.json、差异与恢复说明。私有归档、设备日志不入库。
- 未执行 P2/P3、设备枚举/串口连接、采样、烧录、上电、PWM、AUTO 或真实加水验证。

## 下一任务

先评审文档 PR。后续硬件组从公开 origin/feat/hardware-acquisition 新建 hw/* 工作区，软件组从 origin/feat/dashboard-zh-v1 新建 sw/* 工作区，均先离线核对协议与 profile。硬件 7+7 WIP 继续保存在旧工作区与快照中，迁入时逐文件核对并脱敏。真实 FSR-only 帧与 LIVE/MANUAL 联调是后续阶段，不能以本轮文档完成视为授权。**2026-11-15 起所有真实串口、烧录、采样、PWM 与 AUTO 工作额外暂停，等待项目所有者明确授权，并等待真实接线记录填入电极映射表（ISSUES I-012）。**

## 每次推进和长对话规则

**任何实际开发进展**：同步 `AGENTS.md` 的最近状态、`docs/PROGRESS.md`、`docs/ISSUES.md`，变更接线/协议时同步相应文件；需要交接时同步本文件。出现长上下文、矛盾或状态难追踪，GPT/Agent 应主动提醒开新对话，先提供最新本文件内容和可复制的提示词。

- 2026-11-14 补充核验：硬件 14 个 WIP 文件已恢复到隔离目录并逐文件核对 SHA-256，符号链接目标与清单一致。接线文档的 Markdown 行尾空格在暂存检查中被发现，已去除；保留首个提交，使用追加提交修正。
- 2026-11-15：压敏布接线修正为 12 电极被动读取（无 GPIO 列激励/HI_Z/36 点扫描）。文档层同步：`WIRING_FREEZE_V2.md`（修正横幅、§4.1 空映射表、§5 焊接清单、§4.2 记录废止方案）、`HARDWARE_DESIGN_V2.md`、`DEMO_PLAN_V2.md`、`PROTOCOL_V2_PROPOSAL.md`（新增 `MATRIX_ELECTRODES_12`，`HYBRID_6X6_FSR2` 标 HISTORICAL）、`config/hybrid_sensor_v2.template.json`（改为 12 电极空映射模板、选中 FSR_ONLY）、根 `AGENTS.md`、`PROGRESS.md`、`ISSUES.md`（I-012…I-015）。未执行任何实机动作，未提交。

## 硬件组交接快照

基线 `origin/feat/hardware-acquisition` @ b38e7bb。上一提交：V2 四 ADC + 双 FSR（2026-11-14）。
本次为增量修正提交，不重写历史。

## 一句话状态

压敏布实为 **12 根独立电极**（R×10 kΩ 下拉 GND、C×1 kΩ 上拉 3.3 V，各自接 ADS1220 AIN），
原 6×6 列扫描/36 点方案已撤回。固件改为 `FSR_ONLY` + `MATRIX_ELECTRODES_12`（12 或 14 逻辑
通道），**三个 profile 离线编译 PASS、host 模拟与 fixtures PASS**；真实接线/烧录/采样**未开始**
（用户明确暂停）。真实 R/C→ADC/AIN 映射仍缺失，固件对未映射通道输出 `null` + `NO_DATA`。

## 目录

| 路径 | 内容 |
|---|---|
| `firmware/sensor_fsr2/` | 自包含 sketch：`sensor_fsr2.ino`、`ads1220_multi.*`、`frame_builder_fsr2.*`、`sampler_fsr2.*`、`fsr2.*`、三个生成的 `fsr2_config*.h` |
| `config/sensor_esp32_fsr2.json` | FSR_ONLY（2 通道，ADC4） |
| `config/sensor_esp32_electrodes12.json` | 12 电极（ADC1–3，映射 MISSING） |
| `config/sensor_esp32_electrodes12_fsr2.json` | 12 电极 + 2 FSR（14 通道，映射 MISSING） |
| `scripts/generate_sensor_fsr2_config.py` | JSON → 头文件；拒绝 HYBRID；未映射 sentinel；映射唯一性校验 |
| `scripts/build_sensor_fsr2_firmware.py` | `--profile fsr\|electrodes12\|electrodes12_fsr2` |
| `scripts/run_fsr2_host_tests.py` | 4 个 host 用例（含未映射与合成映射） |
| `scripts/check_fsr2_frames.py` | 帧往返 + 重建 9 个 fixtures |
| `tools/fsr2_sim/` | 四器件 SPI/ADS1220 模拟 + `electrode_test_profile.h`（合成映射，仅测试） |
| `tools/fsr2/protocol_v2.py` | 软件组参考严格解析器（`PROFILE_HISTORICAL`、mapping 校验） |
| `tests/fixtures/fsr2/` | FSR + 电极（未映射/合成映射）样例，全部来自 host 模拟 |
| `tests/test_fsr2_config.py`、`tests/test_fsr2_protocol.py` | 49 条离线单测 |
| `docs/hardware/FSR_ONLY_INTERFACE_V2.md` | 串口接口、电极语义、行长、验收清单、**电极映射核对表** |

`firmware/sensor/`（V1，3 ADC）与 `firmware/sensor_matrix/`（历史扫描原型）保持冻结，未改动。

## 复现（离线，不接线）

```bash
python3 scripts/run_fsr2_host_tests.py
python3 scripts/check_fsr2_frames.py
PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests -p "test_fsr2_*.py"
ARDUINO_CLI="<arduino-cli>" python3 scripts/build_sensor_fsr2_firmware.py --profile fsr \
  --build-dir "$PWD/evidence/fsr2/build_fsr"
ARDUINO_CLI="<arduino-cli>" python3 scripts/build_sensor_fsr2_firmware.py --profile electrodes12 \
  --build-dir "$PWD/evidence/fsr2/build_electrodes12"
ARDUINO_CLI="<arduino-cli>" python3 scripts/build_sensor_fsr2_firmware.py --profile electrodes12_fsr2 \
  --build-dir "$PWD/evidence/fsr2/build_electrodes12_fsr2"
```

## 下一步（等待用户明确通知）

1. 现场按接口文档 §11 断电核对焊接（R×10 kΩ→GND、C×1 kΩ→3.3 V、无 GPIO 列线）。
2. 填写 §12 电极映射表 → 改配置 `electrodes.map` 与 `mapping_status` → 重新生成头文件。
3. 授权后烧录 14 通道 profile，先看 HELLO（`mapping_status = TABLE_PROVIDED`）再开流。
4. 软件组：`tools/tactile_acq/protocol.py` profile 化（I-101）、波特率 921600（I-006）、
   删除缓存的 hybrid fixtures（I-109）。

## 不要做

- 不要为 HYBRID_6X6_FSR2 生成固件或烧录旧 38 通道镜像（生成器会拒绝，别绕过）。
- 不要把 12 电极渲染成 6×6 热图或写成 36 个压力点。
- 不要用合成映射（`SIM_SYNTHETIC_MAPPING`）当真实接线。
- 不要把 host 模拟写成硬件实测；真实采样前所有固件行为保持 IMPLEMENTED_UNVERIFIED。
- 未授权时不要打开串口、烧录、上电或驱动机械。

## 软件组记录（P2-S 历史快照）


更新：2026-11-15
分支：`sw/fsr-live-v2`
基线：公开 `origin/feat/dashboard-zh-v1` `9997853`
协议：PROPOSED，未冻结、未真实联调

## 已完成

- `models.py` / `protocol.py`：`sensor_profile`、`sensor_kind`、FSR 电压基础、
  FSR_ONLY 2 通道与 HYBRID 6×6+2 的严格校验；HELLO 兼容顶层/内层 profile。
- `MATRIX_ELECTRODES_12`：12 个 `MATRIX_ELECTRODE` 通道（R1–R6 = ROW 0..5，
  C1–C6 = COLUMN 0..5）；禁止 `matrix_row/col`，`matrix_cells` 返回 None；
  `electrode_axis/electrode_index` 只表达逻辑序号，不表达 ADC/AIN 物理映射。
- `devices/sensor.py`：该 profile 的仿真只产生 12 路原始 ADC，不合成 contact_score，
  不推算 36 点；`demo_config_for_profile()` 增加 12 电极配置。
- `control/contact.py`：显式基线、相对评分、四态 + 无效/未标定滞回（FSR 方案保留）。
- `control/auto.py`：离线 `evaluate_contact()`；无效/过期/未完成命令不产生夹紧；
  真实 AUTO 硬关闭。
- `control/core.py`：基线采集/清除、设备身份、决策记录、AUTO 故障锁存、Trial 扩展、
  显式 denied commissioning 入口、profile 仿真。
- `ui/`：FSR 卡片/趋势、只含矩阵的热图、profile 选择（含 12 电极）、基线按钮、
  身份/波特率说明、查询按钮、真实 AUTO 拒绝入口；12 电极显示 R1–R6/C1–C6 条形图，
  并明确提示 36 点热图不可用。
- `ui/theme.py`：指标卡/主卡片等高、FSR 读数两列、表格换行/内部滚动、代码块换行；
  仅做最小布局修正，未重设计页面。
- `experiments/store.py`：原始 SAMPLE、身份、评估、PWM 命令/ACK、CSV 追加列；
  `frames.jsonl` 可直接 REPLAY（自动补 HELLO）；电极配置随 metadata 保存。
- `tests/test_v2_sensing.py` + `tests/fixtures/v2/`：34 个 P2-S 测试（含 7 个电极测试）；
  最终验收后全套 290 个离线测试通过（1 项 PTY 测试在本地沙箱跳过）。
- `config/`：FSR_ONLY / HYBRID / 12 电极仿真配置；`sensor_serial.json` 保持
  `queries_enabled=false`。
- `docs/screenshots/p2s-ui-audit/`：1440×900、1280×800、1920×1080 的
  Live/Experiments/Analysis 修复前后截图、12 电极截图、布局度量与对比说明。
- `scripts/ui_screenshot_audit.mjs`：可重复的无头 Chrome 截图/度量脚本（仅本地
  SIMULATION 页面，不碰硬件）。沙箱内需 `CHROME_NO_SANDBOX=1`；脚本在 CDP WebSocket
  打不开时会报错退出，不会静默产出零截图。

## 运行

```bash
cd tactile-gripper-v2-sw
PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests -v

PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo \
  --demo-profile FSR_ONLY --data-root /tmp/gripper-fsr-demo --port 8080

# 12 电极离线视图（只有 12 路原始 ADC，没有 36 点热图）
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo \
  --demo-profile MATRIX_ELECTRODES_12 --data-root /tmp/gripper-electrode-demo --port 8080
```

截图验收见 [docs/screenshots/p2s-ui-audit/README.md](screenshots/p2s-ui-audit/README.md)
（脚本用法与 `CHROME_NO_SANDBOX=1` 说明也在该文件）。
协议与 UI 细节见 [SOFTWARE_V2_P2S_REPORT.md](SOFTWARE_V2_P2S_REPORT.md) 与
[SOFTWARE_RUNBOOK.md](SOFTWARE_RUNBOOK.md)。

## 2026-11-15 最终验收（发布前，离线）

验收前 HEAD `884a8c41bc204d4e9c958c3b7c3821f8130103e7`，基线
`origin/feat/dashboard-zh-v1` `9997853`（祖先关系成立）。本轮只做验收、显示层修复、
文档与发布，未进入新开发阶段。

- 测试：`PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests` →
  **290 tests, OK (skipped=1)**。新增 5 项显示层测试（条形图单位/读数、时间标签、
  接触原因翻译、动态事件说明）。
- Dashboard：重新实测 3 视口 × 3 页面 × 2 profile（HYBRID、12 电极）+ 1024×768 抽查，
  18 个页面 console/page error 为 0，无页面级横向滚动；产物在
  `docs/screenshots/p2s-ui-audit/{after,after-electrodes,narrow-1024}/`。
- 显示层修复：帧接收时间改本机时钟；接触原因与仿真事件说明中文化；条形图轴名
  “ADC 计数”+柱顶读数+刻度取整；分析页侧栏/顶栏同步只读快照；热图色条与轴标签分离；
  FSR 趋势去掉与图例重复的轴名。
- 未改：协议、单位换算、AUTO 门控、Trial/CSV/REPLAY 格式、硬件组固件。
- 发布：推送 `origin/sw/fsr-live-v2`（`7a1bf07`），PR
  [#4](https://github.com/royaleric24/tactile-gripper-a/pull/4) → `feat/dashboard-zh-v1`；
  GitHub Actions `Offline tests` 两个 run 均 PASS；**未合并**，等待总控审核。
- 未做：真实串口、真实 FSR/电极读数、PWM、机械动作、真实 AUTO；PTY 交互测试本地跳过。

## 未做/未验证

- 未打开任何真实串口、未烧录、未上电、未发 PWM、未做机械动作。
- 未验证 921600 链路、真实 HELLO/STATUS 回复、两台设备身份、FSR 电压/极性、
  矩阵物理方向/串扰、ACK 后实际夹持。
- 未确认 R1–R6 / C1–C6 到 ADS1220 AIN 的物理映射、扫描顺序、基准与增益；
  12 个电极测量值不能推出 36 个独立压力点。
- 未实现真实 AUTO 闭环；`request_real_auto_commissioning()` 当前必拒绝。
- Dashboard 视觉验收只覆盖仿真数据与本地浏览器；真实设备错误提示、长时间运行和
  交互路径需现场走查。
- 未合并 PR #1 的 V2 文档。
- 未做真实设备视觉走查；本轮验收全部为 SIMULATION 离线数据。
- PTY 交互测试在本地沙箱被 skip（无 pty 设备），本地未证明该路径。

## 下一步建议

1. 现场只读确认 R/C→ADS1220 AIN 映射、通道/增益/基准与扫描时序；确认前不启用
   真实电极采样，也不把 12 路值解释为压力图。
2. 集成组先按报告第 10 节确认协议/硬件接口，不直接开 AUTO。
3. 现场只读识别双串口，确认 115200/921600 与 HELLO/STATUS，不接 PWM。
4. 用不会夹到杯子的空载/软对象确认 FSR 极性、基线与饱和。
5. 单步、限幅、有人值守地验证 PWM 方向与 1300/1270 μs 观察，仍保持 AUTO 关闭。
6. 协议冻结、标定和急停/失联策略签核后，才评审真实 AUTO 入口。

## 禁止事项

- 不得把本分支的仿真/离线决策当作真实闭环证据。
- 不得用仿真帧驱动真实 PWM。
- 不得在未授权时打开串口、烧录、上电或运动。
- 不得把 ACK 写成到位/夹持力；不得声称协议已冻结。
- 不得把 12 路 R/C 电极 ADC 当作 36 点压力分布或已标定触觉图。
