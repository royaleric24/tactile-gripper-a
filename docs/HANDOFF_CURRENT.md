# 新对话 / Agent 接续交接（2026-11-14）

## 项目与唯一入口

项目：`royaleric24/tactile-gripper-a`；科展式兴趣工程 Demo，非科研论文。**总体方案 `docs/DEMO_PLAN_V2.md`**；接线唯一基准 `docs/WIRING_FREEZE_V2.md`；接口提案 `docs/PROTOCOL_V2_PROPOSAL.md`；协作规则 `AGENTS.md`；实施状态 `docs/PROGRESS.md`；阻碍 `docs/ISSUES.md`。

## 必须沿用的硬件事实

用户已确认新图的 V2 接线：旧 ESP32 ADC1=CS GPIO21/MISO GPIO34，ADC2=CS GPIO22/MISO GPIO35，ADC3=CS GPIO5/MISO GPIO26；四 ADC 共用 SCLK GPIO18/MOSI GPIO23；新增 ADC4 **计划** CS GPIO32/MISO GPIO33，FSR1=A4 AIN0、FSR2=A4 AIN1，二者各自 10kΩ 独立下拉。矩阵六列计划 GPIO4/13/14/25/27/19 依次激励，六行分别经前三颗 ADC AIN0/1 读取，每行独立 10kΩ 下拉。旧硬件配置 `[35,26,34]` 只是历史，与用户确认的 V2 基准不同，迁移后实机 SPI 再验。

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

先评审文档 PR。后续硬件组从公开 origin/feat/hardware-acquisition 新建 hw/* 工作区，软件组从 origin/feat/dashboard-zh-v1 新建 sw/* 工作区，均先离线核对协议与 profile。硬件 7+7 WIP 继续保存在旧工作区与快照中，迁入时逐文件核对并脱敏。真实 FSR-only 帧与 LIVE/MANUAL 联调是后续阶段，不能以本轮文档完成视为授权。

## 每次推进和长对话规则

**任何实际开发进展**：同步 `AGENTS.md` 的最近状态、`docs/PROGRESS.md`、`docs/ISSUES.md`，变更接线/协议时同步相应文件；需要交接时同步本文件。出现长上下文、矛盾或状态难追踪，GPT/Agent 应主动提醒开新对话，先提供最新本文件内容和可复制的提示词。
