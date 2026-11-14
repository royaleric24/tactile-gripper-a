# 项目文档与文件整理清单（非破坏性）

## 第一轮：只补入口，不移动旧文件

- 当前对外导航：根 `README.md` → `DEMO_PLAN_V2.md`、`HARDWARE_DESIGN_V2.md`、`WIRING_FREEZE_V2.md`、`EXPERIMENTS_LITE_V2.md`、`AGENT_TASKS_V2.md`、`PROTOCOL_V2_PROPOSAL.md`、`INTEGRATION_WORKFLOW_V2.md`、`DEMO_RUNBOOK_V2.md`。
- 原始报告 `docs/STAGE*.md`、`docs/hardware/STAGE*.md`、`docs/HANDOFF.md`、`docs/ASSET_MANIFEST.md` 先留原位，避免破坏链接与追溯。
- 旧接口文件 `docs/INTERFACE_CONTRACT.md`、`docs/SENSOR_CONTRACT.md` 暂不覆盖；正式测试通过后将提案折叠进 `INTERFACE_CONTRACT.md`，在其他旧文件顶部标「历史/已替代」并链接新契约。
- 目前 `docs/SOFTWARE_RUNBOOK.md` 仍包含 `feat/software-v1` 和旧波特率 `115200` 描述。以后改为从当前 profile/配置读取真实值，并指向正确的软件分支。

## 第二轮：整合分支时整理代码

**目标结构（推荐，不要求一次性搬完）**：

```text
README.md
AGENTS.md
CONTRIBUTING.md
pyproject.toml / uv.lock
config/             # 不同硬件 profile、具体板型；敏感本地端口不入库
firmware/
  gripper_control/  # ESP32-S3
  sensor/           # 旧 ESP32 / ADS1220
src/
  gripper_a/        # 已有舵机协议/适配，迁移期间保留
  tactile_gripper/  # 主机服务、控制、UI、Trial
tests/
  fixtures/         # 脱敏真实 HELLO/SAMPLE + 合成故障数据
docs/
  DEMO_PLAN_V2.md
  HARDWARE_DESIGN_V2.md
  WIRING_FREEZE_V2.md
  EXPERIMENTS_LITE_V2.md
  INTERFACE_CONTRACT.md  # 真正冻结后才成为唯一协议
  INTEGRATION_WORKFLOW_V2.md
  DEMO_RUNBOOK_V2.md
  archive/           # 后续迁移历史报告
data/real/          # 本地实验原件，默认 Git 忽略
logs/               # 本地原始日志，默认 Git 忽略
videos/             # 本地现场视频，默认 Git 忽略
```

**不要把 `tactile-gripper-a-hw` 与 `tactile-gripper-a-sw` 直接移动到一个目录里当成两个子目录**；它们是分支工作区，应该通过 Git 集成到同一项目版本，才能共享模块与依赖。

## 第三轮：有稳定版本后再清理

- 检查 `README` 到子文档所有 Markdown 链接；历史代码引用、import、测试路径、配置字段和 Agent 指令；必要时保留兼容入口。
- 对 `data/real/`、固件备份、原始采样日志、视频建立本地资产清单和备份，不公开上传包含机器个人路径/串口身份信息的原件。
- 删除仅限确定冗余的临时构建产物；**不删除有证据价值的历史实验**。

## 目前值得直接修复的冲突

1. 软件旧 `sensor_serial.json` 的 115200 baud vs 硬件旧固件实际 921600 baud。
2. 旧 `docs/ARCHITECTURE.md` 将 Stage 0.5 原型放在当前说明下方，容易误读成仍待开发；建议后续把旧阶段段落移入归档而不是混在最新方案。
3. 原 12 ADC 通道轮询/单点实验与新的「6 行扫描 → 36 逻辑单元 + 2 FSR」是不同模式，必须分 `profile`；不能把历史 12 通道数据直接显示为 36 点热图。
4. `src/tactile_gripper/control/auto.py` 当前硬开关 `AUTO_REAL_ENABLED = False`；真正联调通过前保持禁用，联调时用显式启用条件替换，而不是全局无条件设 True。
5. 热图目前根据 `channel_id` 推导行列；如果以后调整通道排序，必须改成从 `channel_config` 提供的位置映射读取。

6. 用户已确认 ADC1–3 的 V2 MISO 为 `[34,35,26]`（顺序对应 ADC1、ADC2、ADC3）。旧硬件配置 `[35,26,34]` 作为历史保留，**新固件与单一板级配置必须改到当前用户确认值并实测 SPI**。旧矩阵行驱动 GPIO32 与 ADC4 CS4 冲突：V2 改成六列激励 GPIO4/13/14/25/27/19。
