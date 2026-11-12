# Stage 0.7 报告

## 受控 USB 归属验证：通过

用户先确认开发板无外部电路/舵机/外部电源、无固件写入，并分步亲自拔下和重插。同一开发板 USB 桥与串口的变化如下：

| 阶段 | USB 桥 | 串口 |
|---|---|---|
| 基线 | 10C4:EA60，描述符 CP2102，序列号 EXAMPLE_ESP32 | /dev/cu.usbserial-EXAMPLE_ESP32 存在 |
| 用户确认拔下后 | 该桥消失 | 该端口消失 |
| 用户确认重插后 | 相同 VID/PID、序列号、0x01110000 位置恢复 | 同名端口恢复 |

可确认当前端口属于用户操作的 NodeMCU ESP-32S V1.1。CP2102 是描述符名称，精确硅片型号仍未经独立核实。没有打开串口或验证双向通信，不代表 ESP32 运行的固件正确。

原始快照与确认分别保存在 evidence/stage07/01_baseline.json、02_unplugged.json、03_replugged.json，均含时间、命令、输出与退出码。Stage 0–0.6 原始证据未覆盖。

## 软件交付与测试

- src/gripper_a/gripper_controller.py：协议式硬件抽象、FakeGripper；真实 SerialGripper 明确拒绝构造。
- src/gripper_a/closed_loop.py：只接受 FakeGripper 和 SIMULATED 配置，有限步进、限幅、累计限制、间隔限制、接触停止、异常锁定及单独释放授权。
- src/gripper_a/sensor.py：完整 JSONL 单行校验、16 通道、有限值、有效性/质量校验；保守策略待 C 组确认。
- tests/test_offline.py：12 项 unittest 全部通过；结果 evidence/stage07/simulated_unittest.txt。所有测试及合成帧为 SIMULATED；没有真实 Trial。
- config/simulated.json：纯模拟参数与任意目标单位，不是角度、开度或 PWM；config/control.template.json 保持硬件禁用、实机参数 null。
- pyproject.toml、uv.lock、.venv：uv 创建本地环境并离线锁定，无第三方依赖安装，不改系统 Python。
- docs/FIRMWARE_PROTOCOL_DRAFT.md：串口接口、固件协议、双端超时及四类停止行为设计；没有固件实现/上传。
- docs/POWER_CHECKLIST.md：最小物料与待确认规格；AGENTS.md、SENSOR_CONTRACT.md、BLOCKERS.md 和 hardware_inventory.csv 增量更新。

复现：`PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`（项目根目录）。测试覆盖启动无动作、接触停止与释放授权、超时锁定、坏帧、重复帧、累计限幅、手动停止、速率限制、时钟倒退、JSONL 校验、禁用真实入口、停止语义区分。

局限：当前逻辑无真实 ACK/固件执行器、无流式拆包、未解决跨时钟延迟旧帧检测；Fake 是逻辑替身，没有机械动力学、夹持力或真实停止验证。日志为内存结构，Fake executed=false；实际角度为 None。下一步可继续离线完成流式缓冲、协议 ID/ACK、独立板端超时模型与持久化日志测试。不可直接用于真实闭环。

## 供电阻塞与运动门槛

尚无独立合规舵机电源；启动/堵转电流、电平兼容、正式引脚/共地方案、实际机械行程、人工停止与支撑均需核实。板载 GPIO/3V3 不可供动力，5V 未经验证禁止供舵机；10 kg·cm 不视作连续安全扭矩。参考 1500 μs 不作为自动回中命令。

禁止进一步闭合、软件保持/释放、停 PWM 和人工切断舵机电源是四种不同操作；均不能凭软件记录宣称物体已安全保持/释放。没有独立供电和人工停止手段不得运动。后续还需原 PDF 核验、双端保护实现与测试、C 组接口联调和具体固件写入/运动授权。

本轮真实串口打开 0、控制命令发送 0、固件写入 0、舵机接线 0、机械运动 0、真实 Trial 0。用户仅操作独立开发板 USB。软件测试通过不解除供电或实机安全阻塞。
