# 主机服务与 Dashboard

- 基线 src/gripper_a/ 保留串口握手、模拟控制与台架调用。软件分支 src/tactile_gripper/devices/ 封装 sensor、sensor_serial 与 gripper；UI 通过 control/ 调用适配层。保留既有控制台调用和配置。
- 软件分支 Python ≥3.11，uv sync --locked，入口为 PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui。默认离线；--demo 使用合成帧，--firmware-fixture 使用固件主机仿真输出。当前 V2 仅使用 FSR_ONLY 与 MATRIX_ELECTRODES_12；历史矩阵只读回放。界面中文为主，保留 PWM、ACK、AUTO、LIVE 和来源标签。
- 加入新帧先检查协议版本、设备与启动身份、通道配置、有效位、帧序和时间。无效值保留掩码；遇到过期、失联或会话变化停止产生新的夹紧命令。不要将 ACK 写成到位反馈。
- experiments/store.py 维护 Trial 元数据、帧和事件。保持中断恢复、时间顺序、来源标签和旧记录可读。回放不得打开设备；以 SIMULATION 生成的 Trial 仅写入相应模拟目录。
- control/core.py 和 control/auto.py 的状态转换、人工/自动许可和超时策略须有离线拒绝路径测试。真实 AUTO 的开放需现场证据。LIVE 启动参数与设备授权见软件运行手册。
- 修改协议或回放格式时分别覆盖旧帧、坏帧、部分无效、断流与重启；在 PR 中关联硬件端版本。运行根目录 tests/；页面测试需要本机 loopback 端口。
