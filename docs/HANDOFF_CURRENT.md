# 当前交接（P2-S 软件）

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
- 发布：推送 `origin/sw/fsr-live-v2`，PR 指向 `feat/dashboard-zh-v1`，**未合并**。
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
