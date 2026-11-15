# Tactile Gripper · 触觉闭环自适应机械爪

## V2 当前路线（2026-11-15 接线修正）

当前总体方案以 [DEMO_PLAN_V2](docs/DEMO_PLAN_V2.md) 为唯一入口：科展 Demo 优先真实抓杯与 FSR→PWM 反馈，12 电极被动读取作为辅助（**不是 6×6 矩阵；2026-11-15 项目所有者确认**，见接线基准）。

- [V2 接线基准](docs/WIRING_FREEZE_V2.md)：ADC1 CS21/MISO34、ADC2 CS22/MISO35、ADC3 CS5/MISO26 已获用户确认；ADC4 CS32/MISO33 待施工。压敏布为 12 电极被动读取（R1–R6 各接 AIN + 10 kΩ 下拉、C1–C6 各接 AIN + 1 kΩ 上拉），**无 GPIO 列激励/HI_Z/36 点扫描**；电极 → ADC/AIN 映射 PENDING_REAL_WIRING（§4.1 空表待填）。
- [V2 接口契约](docs/INTERFACE_CONTRACT.md)（OFFLINE_VERIFIED：2/12/14 通道；真实映射待核对）、[硬件总览](docs/HARDWARE_DESIGN_V2.md)、[配置模板](config/hybrid_sensor_v2.template.json)（AUTO 关闭、端口和阈值留空、电极映射为空列表）。
- [进度](docs/PROGRESS.md)、[问题](docs/ISSUES.md)、[当前交接](docs/HANDOFF_CURRENT.md)、[本地保护与文档检查](docs/LOCAL_INTEGRATION_V2.md)。
- [并行任务模板](docs/AGENT_TASKS_V2.md)、[集成流程](docs/INTEGRATION_WORKFLOW_V2.md)、[轻量实验](docs/EXPERIMENTS_LITE_V2.md)、[演示流程](docs/DEMO_RUNBOOK_V2.md)、[文档整理](docs/DOC_CLEANUP_V2.md)。

P3-A 已离线跑通固件 JSONL → Dashboard → Trial / CSV / REPLAY。查看 [验收与截图](docs/P3A_ACCEPTANCE.md)。

> 设备身份与个人路径已脱敏；连接硬件前请阅读 [公开副本说明](docs/PUBLICATION.md)。

项目探索用压敏皮肤估计接触状态和滑移风险，最终让夹爪在杯中逐渐加水时调节夹持力度。现阶段可分别复现夹爪控制、触觉采集和软件模拟。

| 子系统 | 进度与证据 |
|---|---|
| ESP32-S3 夹爪控制 | PASS（历史通信记录及现场报告开合）。位置精度、长期稳定性 UNKNOWN。见 [S3 验收记录](docs/STAGE09B26_REPORT.md)。 |
| 旧 ESP32 + 3 颗 ADS1220 | PASS（硬件分支 H1 报告及本地原始帧）。60 秒采集 1579 帧，每路有效 1573 个值，当次输入悬空。 |
| 点接触检测、12 电极 | IN_PROGRESS。固定 AIN1 诊断与 12 路单端采集各有独立流程；**12 电极 ≠ 36 压力点**，6×6 主动扫描方案已随 2026-11-15 接线修正作废（HISTORICAL），电极映射 PENDING_REAL_WIRING。 |
| Python 服务与中文 Dashboard | OFFLINE_VERIFIED：固件 host 仿真驱动 2/12/14 通道，支持数据质量、Trial、CSV、回放和离线 AUTO。真实操作留待 P3-B。 |
| 加水自适应演示 | UNKNOWN。缺少贯穿触觉输入、动作、载荷变化和杯体观察的真实闭环证据。 |

## 快速开始

从仓库根目录执行。V2 Dashboard 依赖 Python ≥3.11，依赖版本由 uv.lock 固定。

```sh
uv sync --locked
PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests
```

运行固件样例驱动的离线界面，打开终端显示的本机地址：

```sh
PYTHONPATH=src:. .venv/bin/python -m tactile_gripper.ui --no-browser --port 8080 \
  --firmware-fixture electrodes12-fsr2 --record-fixture --data-root /tmp/gripper-v2-demo
```

SIMULATION 生成合成数据。LIVE 需要明确选择来源、设备及现场许可。操作方式见软件分支 docs/SOFTWARE_RUNBOOK.md；机械爪台架入口见 [PWM Console](docs/PWM_CONSOLE.md)。

## 分支与下一步

P3-A 的合并来源为 main、feat/hardware-acquisition 与 feat/dashboard-zh-v1。集成结果交总负责人评审。P3-B 授权后再做真实接线核对、采集和标定。

参见 [系统架构](docs/ARCHITECTURE.md)、[硬件](docs/hardware.md)、[软件](docs/software.md)、[接口契约](docs/INTERFACE_CONTRACT.md) 和 [贡献流程](CONTRIBUTING.md)。

## 软件分支运行资料

[中文 Dashboard 指南](docs/DASHBOARD_QUICKSTART_ZH.md) · [软件运行手册](docs/SOFTWARE_RUNBOOK.md) · [Trial 格式](docs/DATA_FORMAT_V1.md) · [联调清单](docs/HARDWARE_INTEGRATION_CHECKLIST.md) · [协议讨论](docs/PROTOCOL_COLLABORATION.md) · [V1 交付记录](docs/SOFTWARE_V1_REPORT.md)

无界面模拟：`PYTHONPATH=src .venv/bin/python scripts/run_simulation_demo.py --ticks 30 --interval 0.05`。LIVE 入口需显式来源与硬件许可；真实 AUTO 保持禁用。
