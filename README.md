# Tactile Gripper · 触觉闭环自适应机械爪

项目探索用压敏皮肤估计接触状态和滑移风险，最终让夹爪在杯中逐渐加水时调节夹持力度。现阶段可分别复现夹爪控制、触觉采集和软件模拟。

| 子系统 | 进度与证据 |
|---|---|
| ESP32-S3 夹爪控制 | PASS（历史通信记录及现场报告开合）。位置精度、长期稳定性 UNKNOWN。见 [S3 验收记录](docs/STAGE09B26_REPORT.md)。 |
| 旧 ESP32 + 3 颗 ADS1220 | PASS（硬件分支 H1 报告及本地原始帧）。60 秒采集 1579 帧，每路有效 1573 个值，当次输入悬空。 |
| 点接触检测、矩阵 | IN_PROGRESS。固定 AIN1 诊断与 12 路扫描各有独立流程；6×6 主动扫描原型的实机验收为 IMPLEMENTED_UNVERIFIED。 |
| Python 服务与中文 Dashboard | 软件分支实现设备适配、模拟 AUTO、Trial、回放与对比，离线测试覆盖。真实采集端与软件端联合验收 UNKNOWN。 |
| 加水自适应演示 | UNKNOWN。缺少贯穿触觉输入、动作、载荷变化和杯体观察的真实闭环证据。 |

## 快速开始

从当前分支根目录执行。main 和硬件分支依赖 Python ≥3.9 与 pyserial；软件分支依赖 Python ≥3.11、NiceGUI 与 pyserial。依赖版本由各自的 uv.lock 固定。

```sh
uv sync --locked
PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests
```

在软件分支运行离线界面，打开终端显示的本机地址：

```sh
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo --port 8080
```

SIMULATION 生成合成数据。LIVE 需要明确选择来源、设备及现场许可。操作方式见软件分支 docs/SOFTWARE_RUNBOOK.md；机械爪台架入口见 [PWM Console](docs/PWM_CONSOLE.md)。

## 分支与下一步

main 保留控制基线；feat/hardware-acquisition 提供采集固件与诊断；feat/dashboard-zh-v1 提供主机服务。feat/software-v1 是中文界面之前的本地祖先分支。下一步先用同版本握手与原始帧验证两端兼容，再开展受控夹持 Trial，记录滑落和形变。

参见 [系统架构](docs/ARCHITECTURE.md)、[硬件](docs/hardware.md)、[软件](docs/software.md)、[接口契约](docs/INTERFACE_CONTRACT.md) 和 [贡献流程](CONTRIBUTING.md)。

## 软件分支运行资料

[中文 Dashboard 指南](docs/DASHBOARD_QUICKSTART_ZH.md) · [软件运行手册](docs/SOFTWARE_RUNBOOK.md) · [Trial 格式](docs/DATA_FORMAT_V1.md) · [联调清单](docs/HARDWARE_INTEGRATION_CHECKLIST.md) · [协议讨论](docs/PROTOCOL_COLLABORATION.md) · [V1 交付记录](docs/SOFTWARE_V1_REPORT.md)

无界面模拟：`PYTHONPATH=src .venv/bin/python scripts/run_simulation_demo.py --ticks 30 --interval 0.05`。LIVE 入口需显式来源与硬件许可；真实 AUTO 保持禁用。
