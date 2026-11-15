# Tactile Gripper 协作指令

目标是用触觉皮肤估计接触与滑移风险，逐步验证加水过程中杯子的保持与形变。验收需同时记录杯子、夹爪动作与触觉信号。当前验证范围见 README。

## 所有权与入口

| 分支 | 维护范围 | 代码入口 |
|---|---|---|
| main | 总负责人管理稳定基线、跨组契约、集成和发布 | docs/INTERFACE_CONTRACT.md、config/、tests/ |
| feat/hardware-acquisition | 采集板、接线、ADC、设备协议、台架及原始设备日志 | firmware/、tools/tactile_acq/、硬件分支 docs/hardware/ |
| feat/dashboard-zh-v1 | 主机适配、控制状态机、中文界面、存储、回放与集成实现 | src/gripper_a/、软件分支 src/tactile_gripper/ |
| hw/fsr-v2 | V2 四 ADC：ADC4 双 FSR + 12 电极被动读数（FSR_ONLY / MATRIX_ELECTRODES_12）、离线测试、接口说明 | firmware/sensor_fsr2/、config/sensor_esp32_{fsr2,electrodes12,electrodes12_fsr2}.json、docs/hardware/FSR_ONLY_INTERFACE_V2.md |

目录随分支而异。scripts/ 与 config/ 按功能归属；修改前从调用入口核对消费者。firmware/AGENTS.md 和 src/AGENTS.md 分别细化设备端和主机端规则。

## 开发与集成

- 先用 git status -sb 和 git worktree list 核对分支与本地成果。一个任务一个分支；共享 Git 历史，各工作区独立暂存。提交显式列出本次文件。
- 按当前分支 pyproject.toml 使用 uv sync --locked。离线测试从仓库根运行：`PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests`。硬件工具测试单独发现，见 CONTRIBUTING.md。
- PR 写明基线、修改范围、可重复的命令、结果及未测条件。提交采用 type(scope): 摘要。协议、单位、板级配置、超时或控制权限有变化时，由两组检查生产者、消费者、旧帧和故障路径，总负责人合入 main。
- 模拟、回放、混合实验和真实 Trial 分开归档。真实实验保存 Trial ID、固件与配置版本、原始帧、动作与回复、时间戳、视频关联及失败原因；原件留在本地。对外提供经过审查的最小样例。
- 使用 PASS 标注已验证的具体行为并写明证据类型。其余按 IMPLEMENTED_UNVERIFIED、IN_PROGRESS、NOT_IMPLEMENTED、UNKNOWN 描述。没有独立标定时仅报告 ADC counts 或接触评分；没有实测反馈时角度和开度记为未知。
- 离线编译、模拟、代码修改及离线测试可连续执行。打开真实串口、采样、烧录、接线、上电、PWM 与机械动作需现场明确授权，限定设备、动作及会话。上传和运动分别授权。
- 保留已验固件、配置、实验原件与 Git 历史；稳定版本见 docs/ASSET_MANIFEST.md。实机默认 DISARMED，断连后重新授权；保留配置门控、停止、失联处理及分模式限位。禁止自动回中、扫描端点或重放旧运动。

## 最近状态（V2 硬件 / 12 电极修正，2026-11-15）

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
