# Tactile Gripper 协作指令

目标是用触觉皮肤估计接触与滑移风险，逐步验证加水过程中杯子的保持与形变。验收需同时记录杯子、夹爪动作与触觉信号。当前验证范围见 README。

## 最近状态（P2-S 软件，2026-11-15）

`sw/fsr-live-v2` 已完成 FSR_ONLY / HYBRID_6X6_FSR2 离线适配、两路 FSR 相对接触评估、
矩阵/FSR 分流、双设备身份与 Trial/CSV/REPLAY 扩展。2026-11-15 追加
`MATRIX_ELECTRODES_12`（R1–R6 / C1–C6 各接 ADS1220 AIN）离线适配：只显示 12 路
原始 ADC，不合成 36 点压力热图；FSR_ONLY 与既有 Trial/CSV/REPLAY 保持。全套
**285 个离线测试通过**。Dashboard 已在 1440×900、1280×800、1920×1080 完成
Live/Experiments/Analysis 截图验收，见
[docs/screenshots/p2s-ui-audit/](docs/screenshots/p2s-ui-audit/README.md)。

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
