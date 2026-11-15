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

## 下一步

1. 现场确认 R/C→ADS1220 AIN 的物理映射、ADS1220 通道/增益/基准与扫描顺序，
   再决定是否启用真实电极采样。
2. 与硬件/集成组确认 `docs/SOFTWARE_V2_P2S_REPORT.md` 第 10 节接口问题。
3. PR #1 合并后对齐 V2 文档，避免本分支 PROGRESS/ISSUES/HANDOFF 与主线重复。
4. 获得现场授权后，先做只读双串口识别与 HELLO/STATUS，再做单步 PWM，不直接开 AUTO。
5. 标定 FSR 基线、极性和饱和，确认电压换算与矩阵方位后，才讨论真实 AUTO。
