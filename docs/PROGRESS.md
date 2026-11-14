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

## 下一步

1. 与硬件/集成组确认 `docs/SOFTWARE_V2_P2S_REPORT.md` 第 10 节接口问题。
2. PR #1 合并后对齐 V2 文档，避免本分支 PROGRESS/ISSUES/HANDOFF 与主线重复。
3. 获得现场授权后，先做只读双串口识别与 HELLO/STATUS，再做单步 PWM，不直接开 AUTO。
4. 标定 FSR 基线、极性和饱和，确认电压换算与矩阵方位后，才讨论真实 AUTO。
