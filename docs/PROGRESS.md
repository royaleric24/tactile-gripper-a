# P2-S 软件进度

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
