# 给硬件组 / 软件组 / 集成组的执行任务（一次性交付）

> 本轮仅 P0/P1；下列代码、硬件与联调任务供后续阶段使用，尚未启动。旧三个目录保留原状；实际后续任务应从已发布脱敏组分支另建工作区，避免在带 WIP 的硬件目录切分支。

> 这些是任务提示词模板，不自动执行真实硬件、Git push 或合并。先读取本地真实仓库状态；本包只反映此前公开远程版本，不能替代未提交文件。团队采用每组一个大阶段的工作方式，不在每个小文件暂停。

> **2026-11-15 修正**：真实压敏布为 **12 根电极被动读取**（R1–R6 各接 ADS1220 AIN + 各自 10 kΩ 下拉；C1–C6 各接 AIN + 各自 1 kΩ 上拉）。原“六列 GPIO 激励 / HI_Z / 36 点矩阵 / HYBRID_6X6_FSR2”任务作废（HISTORICAL），不要执行。所有真实串口、烧录、采样、PWM 与 AUTO 工作**暂停**，等待项目所有者明确授权与真实接线记录；电极 → ADC/AIN 映射 PENDING_REAL_WIRING（见 `docs/WIRING_FREEZE_V2.md` §4.1）。

## 硬件组：ADC4 + 两路 FSR + 12 电极（被动，无矩阵）

```text
历史保护目录：../tactile-gripper-a-hw（仅参考）；开发从公开 origin/feat/hardware-acquisition 新建 hw/* 任务分支与工作区
项目定位：兴趣科展 Demo，优先真实 FSR 反馈；不要重新设计已做好的 Dashboard，也不要做科研论文式流程。
先读取根 README、docs/WIRING_FREEZE_V2.md、docs/PROTOCOL_V2_PROPOSAL.md，并核验 git status、当前分支、worktree、现有未提交文件及历史采集原始数据；保护所有已有成果，不 reset/clean/覆盖历史真实日志。

整阶段连续完成：
1. 固定用户确认的 V2 映射：ADC1=CS21/MISO34、ADC2=CS22/MISO35、ADC3=CS5/MISO26；历史配置 `[35,26,34]` 仅用于旧记录。修改 V2 板级配置和生成固件时使用 `[34,35,26]`，实际烧录/上电后做 SPI 读写回验收。不再将该映射作为待用户回答的问题。
2. 将新 ADC4 设计为 CS GPIO32 / DOUT GPIO33，四颗共享 GPIO18 SCLK、GPIO23 MOSI。按“两片 FSR 独立 10kΩ 下拉”做固件 FSR_ONLY 的 HELLO/SAMPLE/STATUS 配置；FSR 在 ADC4 AIN0/1；不要使用图中的 FSR1 下拉误连。
3. 12 电极按被动单端读取实现：每根 R 电极各接自己的 ADS1220 AIN 并各有一颗 10 kΩ 下拉到 GND，每根 C 电极各接自己的 ADS1220 AIN 并各有一颗 1 kΩ 上拉到 3.3 V；**无 GPIO 列激励、无 HI_Z、无 36 点扫描**。输出 12 个电极逻辑通道（协议顺序 R1..R6 再接 C1..C6），不是 36 个点。电极 → ADC/AIN 映射 PENDING_REAL_WIRING，必须等真实焊接/台架记录填完再生成 `channel_config`；不得猜编号、不得假设行优先、不得复刻旧 row_gpio/列驱动配置。
4. 先完成固件构建、离线解析与测试，给出脱敏模拟 HELLO/SAMPLE fixtures、两种 profile 的清楚配置和设备问题定位日志。现场获得操作员对具体接线/烧录测试确认后再做真实 ADC4 与 FSR 测试，记录原始数据，不能将模拟测试写成真实通过。
5. **每完成一个有意义的进展，同步修改根 `AGENTS.md`（最近进展引用）、`docs/PROGRESS.md`（完成/测试/下一步）、`docs/ISSUES.md`（新增/解决问题）；若进度或决策变化也更新 `docs/HANDOFF_CURRENT.md` 和对应方案/接线/协议文件。** 简短交付：改动、固件、真实或模拟证据、问题、下一动作。一次大阶段输出，不分十几个审批节点。
```

## 软件组：V2 传感适配与 Dashboard LIVE

```text
历史保护目录：../tactile-gripper-a-sw（仅参考）；开发从公开 origin/feat/dashboard-zh-v1 新建 sw/* 任务分支与工作区
保持 Dashboard V1.0 NiceGUI 中文 UI、Trial、CSV、REPLAY、MANUAL、原控制器及全部现有数据。不扩展新页面、不做非必要 UI 美化。先核验 git status/worktree，避免覆盖本地未提交成果。

整阶段连续完成：
1. 阅读 docs/WIRING_FREEZE_V2.md 和 docs/PROTOCOL_V2_PROPOSAL.md，按 `FSR_ONLY`(2 通道) 与 `MATRIX_ELECTRODES_12`(12 逻辑通道，提案、validated=false、映射 PENDING) 兼容解析；`HYBRID_6X6_FSR2` 已撤回为 HISTORICAL，只保留历史回放识别，不得当当前 profile；不将历史“12 路 ADC 轮询”误判为 36 点矩阵。
2. 将两个 FSR 独立显示为电压/原始 ADC 与相对接触趋势，保留 valid、boot_id、seq、时间戳；12 电极渲染为电压列表/条（**不画 36 点热图、不按行列交点建模**），`mapping_status`/`validated` 原样透出，不能把无效电极当 0 或无接触。
3. 将 FSR-only 的真实帧用于可解释的相对接触评分与接触状态；AUTO 当前真实门控保持关闭，先完成离线测试与模拟，再提供有意开启真实联调的受控入口。必须区分传感器无效与未接触，不能因为坏帧继续夹紧。
4. 两路串口独立探测、跟踪，采集端旧固件可能为 921600 baud，别沿用 115200 静默失败。保存 FSR raw、电极 raw、PWM command/ACK、决策理由、Trial、REPLAY；无需改动已有存储格式，能兼容就增量扩展。
5. 每完成一项实际进展，同步更新根 `AGENTS.md`、`docs/PROGRESS.md`、`docs/ISSUES.md`、必要时 `docs/HANDOFF_CURRENT.md` 与接口文档；代码+测试+文档同次提交。未经现场许可不连接真实设备、不发 PWM；跨组接口有冲突集中列一次，不要碎片化等待答复。
```

## 集成组/负责人：并行开发成果汇总

```text
目标目录：保留原三个 worktree；在新 integrate/hybrid-demo-v2 集成分支合并，不直接覆盖 main。

核对三工作区 git status/log/worktree、所有 tracked/untracked/WIP 原始数据备份、分支差异后，再选择仅集成已发布脱敏历史的合并策略；不从旧仓库 merge/cherry-pick。先集成硬件的可解析真实 FSR 帧和软件 UI，跑离线测试；然后两个 USB 串口 LIVE+MANUAL；最后在实机允许后开启 FSR 规则 AUTO。
要保证固件、Mac 依赖、串口波特率、逻辑通道映射和试验记录一致。展示先选指定杯、1300µs 观察点，1270µs 已可见形变，不用旧值作自动限位。
一次输出：运行命令、可展示 Demo、测试证据、尚未验证的硬件项、最终 PR/分支建议；合并进展与遗留问题写入 `docs/PROGRESS.md`、`docs/ISSUES.md`、根 `AGENTS.md`、`docs/HANDOFF_CURRENT.md`；正式上传/合并前做文件公开审查。
```
