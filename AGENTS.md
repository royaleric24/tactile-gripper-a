# Tactile Gripper 协作指令

目标是用触觉皮肤估计接触与滑移风险，逐步验证加水过程中杯子的保持与形变。验收需同时记录杯子、夹爪动作与触觉信号。当前验证范围见 README。

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
4. 6×6 真实矩阵辅助热图；更高级功能靠后。

## 实机已知观察

同一指定水杯：`1300 μs` 现场观察刚好夹住不显著形变，`1270 μs` 已有可见形变。前者只是起始参考，后者是风险观察点，不等于正式机械限幅。自动步幅、阈值、方向、功率与停止策略以现场复测为准，不凭空填写。

## 固定的 V2 硬件接口（用户确认，2026-11-14）

ADC1 = CS GPIO21 / MISO GPIO34；ADC2 = CS GPIO22 / MISO GPIO35；ADC3 = CS GPIO5 / MISO GPIO26。ADC4 计划 CS GPIO32 / MISO GPIO33；四 ADC 共用 SCLK GPIO18、MOSI GPIO23。**不得沿用旧硬件配置中的 MISO `[35,26,34]` 生成 V2 固件**。新方案的实机 SPI 验证尚未进行。接线唯一基准见 `docs/WIRING_FREEZE_V2.md`。

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

- 2026-11-14：P0 完整归档与逐文件 SHA-256 核验通过；旧三工作区保持原状，硬件组 7 修改 + 7 未跟踪受到保护。P1 在公开 main `5ee92cd` 的独立工作区 `docs/demo-v2` 增量引入文档。静态检查通过（12 JSON、无新增断链），6 处历史缺失证据链接记为 I-010。ADC1–3 设计已确认，ADC4 待施工，协议仍 PROPOSED，V2 实机未验证。详见 [进度](docs/PROGRESS.md)、[问题](docs/ISSUES.md) 与 [交接](docs/HANDOFF_CURRENT.md)。本轮范围止于 P0/P1，无硬件动作、烧录或 AUTO。
