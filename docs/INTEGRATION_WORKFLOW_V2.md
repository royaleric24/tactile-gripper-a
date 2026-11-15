# Git / Worktree 集成与团队协作 V2

**目标**：在最少 Git 操作下，把硬件组和软件组整合进一个能运行的主线，并允许组员继续并行工作。**本文件不执行上传、合并、重置或删除。**

## 1. 已知远程事实（2026-11-14 查阅）

仓库：`royaleric24/tactile-gripper-a`（公开）。已存在：`main@5ee92cd`、`feat/hardware-acquisition@b38e7bb`、`feat/dashboard-zh-v1@9997853`。远程分支不能反映三个 Mac 工作目录的未提交文件。

## 1a. 本次本地核实（2026-11-14）

旧三目录已实查为共享 worktree，但没有 origin；其 main=`22bb360`、硬件=`4827202`、软件=`8461e39`，与已发布脱敏历史独立。硬件组有 7 修改 + 7 未跟踪，原件未变动。完整归档、SHA-256 清单与恢复说明保存在工程之外的本地私有保护目录。

本次从在线核实的公开 main `5ee92cd5a599bef497566638c7754e40a2edac4a` 新 clone 建立 `docs/demo-v2`；不要把旧仓库添加公开 origin 后直接推送，也不要从旧历史 merge/cherry-pick。未来如需迁入本地改动，应逐文件脱敏、检查目标版本并验证。

## 2. 整理前保护原始目录与内容

原始目录：`tactile-gripper-a`、`tactile-gripper-a-hw`、`tactile-gripper-a-sw`。**先保存现状，不要以远程版本强行覆盖本地。**

在每个目录分别运行并保存结果：

```bash
pwd
git rev-parse --show-toplevel
git rev-parse --git-common-dir
git status --short --untracked-files=all
git branch --show-current
git log -1 --oneline
git remote -v
```

然后在共享仓库任一工作区运行 `git worktree list --porcelain`；如果三个目录不共享 git-common-dir，先按独立仓库迁移评估，**不要假设已是 Worktree**。

先做至少两份快照（包含非 Git 跟踪文件、真实实验日志及固件）：一份只读目录备份，另一份 `git status` / 文件 SHA-256 / 清单。尤其保留此前报告过的硬件组 **7 个已修改 + 7 个未跟踪文件**（这是历史线索，具体以当前检查为准）。**未经检查禁止** `git clean -fd`、`git reset --hard`、强制推送、覆盖 `uv.lock` 或移动真实日志。

## 3. 推荐 Git 分支结构

- `main`：稳定、可重现的集成 Demo；所有组员通过 PR 合入。
- `feat/hardware-acquisition`：现有硬件成果的基线，继续在 `hw/*` 子分支开发新 ADC4/FSR/12 电极（被动读取，无矩阵；2026-11-15 修正）。
- `feat/dashboard-zh-v1`：现有软件成果的基线，继续在 `sw/*` 子分支开发适配器与 AUTO。
- `integrate/hybrid-demo-v2`：从 main 创建的**临时集成分支**，分阶段引入双方代码；联调跑通后经 PR 合入 main。不要直接用一个分支覆盖另一分支。
- `docs/demo-v2`：可选独立文档 PR，避免与实时硬件修改互相阻断。

推荐先审查分支差异和同名文件：`pyproject.toml`、`uv.lock`、`docs/INTERFACE_CONTRACT.md`、`README.md`、`config/`、`scripts/`、`tests/`。硬件带入 `firmware/sensor`、采集工具和硬件配置；软件带入 `src/tactile_gripper`、UI、存储与测试；共享文件按功能逐项解决冲突。

## 4. 最小 PR 规范

每个 PR 回答五件事即可：**改了什么、为什么、测试命令及结果、是否接触真实硬件、哪些尚未验证**。API/协议/引脚变更 @硬件组+软件组评审；纯 UI 文案、离线工具可由本组负责人完成，不要求总负责人逐文件审批。

- 一次提交可以包含一个完整阶段（功能 + 测试 + 简短文档），不需要拆成十几个微阶段。
- 硬件组负责 `firmware/sensor*`、板卡映射、设备原始日志；软件组负责 `src/tactile_gripper`、Dashboard、记录/回放、主机 AUTO；共享接口文档由双方确认后由集成负责人维护。
- 所有离线代码写作、构建、测试可由 Agent 在对应工作区连续执行。真实上电、接线改动、烧录和机械动作应由现场操作员确认本次板卡及测试动作；**不要求每个离线子步骤都停下来等批准**。
- `README.md` 是导航入口；**`docs/DEMO_PLAN_V2.md` 是唯一总体方案文档**；`docs/WIRING_FREEZE_V2.md` 是当前接线基准；`docs/INTERFACE_CONTRACT.md` 在协议经双方真实验证冻结后才成为执行契约；旧 Stage 报告保留为历史证据。
- 每次实际进度推进，交付代码与测试的同时更新 `AGENTS.md`、`docs/PROGRESS.md`、`docs/ISSUES.md`；对话交接时同步 `docs/HANDOFF_CURRENT.md`。

## 5. 推荐集成顺序

1. 本地保护/确认 Git 共享关系；保留现有未提交工作和 WIP 快照，后续单独评审迁入公开历史的文件差异，但不公开原始私密路径与设备日志。
2. 本文档在 `docs/demo-v2` 提交 PR；不要让文档变更阻断硬件组并行采集。
3. 主线创建 `integrate/hybrid-demo-v2`；先导入硬件采集模块和模拟/真实传感器协议 fixtures，再导入软件服务/UI。也可按依赖使用已发布脱敏历史中的 `cherry-pick`/selective merge，保留来源 SHA；不引入旧本地历史。
4. 统一 Python 版本、依赖与入口；软件需要的 Python ≥3.11 应作为优先兼容目标，确认本地 `uv` 环境后再更新锁文件。
5. 离线测试 + 模拟 demo + 两路真实串口 + MANUAL 夹杯 + AUTO。只有真实联调通过才把 main 标为 DEMO_READY。
6. 按成员分工拆小 PR；总负责人只处理关键接口、集成冲突和发布。

## 6. 文档整理规则

**先建立索引、再归档、最后清理。** 目前远程 `docs/` 内大量 STAGE 报告引用其他文档/配置，立即移动可能破坏相对链接。短期允许保留老位置，新增当前方案文档；之后再批量迁入 `docs/archive/2026-11/`，同时检查全部 Markdown 相对链接与代码引用。不能删除真实证据。

## 7. V2 接线变更的跨组交付

硬件组只需一次提交包含 `docs/WIRING_FREEZE_V2.md` 核线结果（含 §4.1 电极映射表）、板级配置、真实 HELLO/SAMPLE（脱敏）、固件与少量测试；软件组按 `FSR_ONLY`（当前可用）与 `MATRIX_ELECTRODES_12`（12 电极提案，映射 PENDING、validated=false）更新解析和 UI；`HYBRID_6X6_FSR2` 已撤回为 HISTORICAL，不作当前 profile。**不要把旧 `ROW_SCAN_6X6`/列激励配置或 HYBRID 当作当前固件**（真实布料无 GPIO 列驱动，见 `WIRING_FREEZE_V2.md` 2026-11-15 修正）；同时不在未确认硬件前把 `AUTO_REAL_ENABLED` 直接设成 True。
