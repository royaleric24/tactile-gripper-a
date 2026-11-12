# Stage 0.9A：PWM 固件和 Python 控制器

日期：2026-11-11。**开发、离线测试及固件编译已完成；未上传、未开真实串口、未接线、未启用 GPIO PWM、无机械运动。** Stage 0.8 的真实通信结果不外推到本固件。新构建默认 DISARMED + UNCALIBRATED + hardware_enabled=false。

## 代码交付

- firmware/gripper_control/gripper_control.ino：LEDC 输出适配器、JSONL 命令、启动会话、独立超时、非阻塞有界接收与背压保护。
- firmware/gripper_control/SafetyCore.h：不依赖 Arduino 的共享安全逻辑，直接用于固件及本机测试，没有为测试另写一套状态机。
- config/gripper_control.json、scripts/generate_gripper_config.py、generated_config.h：配置源及生成头；安全脉宽上下界、首个目标、相邻步幅、累计变化量均为 null；生成头用 0 占位并由校准/使能双重门槛禁止 ARM。
- src/gripper_a/gripper_controller.py：保留旧 Gripper、FakeGripper、禁用的 SerialGripper；新增 GripperController.connect/get_status/arm/set_pulse_us/stop/disarm/heartbeat/close。默认 dry-run，真实连接需 hardware_permission=True 和明确端口；本阶段没有运行真实连接。
- serial_client.py：复用已有读写超时、request_id 匹配和 JSONL 日志，新增可配置的 ACK 接受类型；Stage 0.8 默认仍只接受原有响应。
- tests/test_gripper_controller.py、tests/native_control/：Python 控制器/Fake 集成测试、共享核心逻辑和实际固件入口的 native stub 测试。
- docs/GRIPPER_PROTOCOL.md：完整命令语义、失联行为、兼容性及当前限制。AGENTS、README、BLOCKERS、硬件清单均增量更新。

旧固件源码、构建和真实日志保留。本次新增日志/合成结果标 SIMULATED，没有新的 REAL_SERIAL 收发日志。

## 构建与验证

使用已安装 Arduino CLI 1.5.1、Arduino-ESP32 3.3.2、ArduinoJson 7.4.2、Xtensa GCC 14.2.0，FQBN esp32:esp32:nodemcu-32s。最终编译结果见 evidence/stage09a/compile.txt，版本、文件大小和 SHA-256 见 build_manifest.json；仅 compile，无 upload。

Python unittest 共 **28 项通过**（包含此前 19 项），覆盖默认 dry-run、硬件许可缺失、未标定拒绝、非法/超限/首目标/相邻目标/速率拒绝、Fake 集成、DISARM 后拒绝、重连不恢复，以及断连/新 boot_id 后 FAULT + UNKNOWN。evidence/stage09a/python_tests.txt 标 SIMULATED。

Native 共享核心测试通过：PWM 舍入、未标定锁定、ARM 不输出、首目标约束、速率/范围/步幅/累计变化量限制、通信超时、心跳不能延长输出租约、重放拒绝、输出 API 故障 UNKNOWN、STOP 不解除 FAULT、重新构造的启动默认状态。实际 .ino 的 native 入口测试通过：setup/loop 默认不调用 LEDC、PING/STATUS、ARM 锁定、坏 JSON/尾随垃圾/超长输入、启动逻辑。结果见 native_safety.txt、native_firmware.txt。

这些均在 Mac 执行，LEDC/时钟/串口用 stub 或 Fake，没有 ESP32 实机执行。本机测试不能证明 GPIO 波形、启动电气毛刺、舵机实际停止或夹持安全。

复现（项目根目录）：

```sh
.venv/bin/python scripts/generate_gripper_config.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
/usr/bin/clang++ -std=c++17 tests/native_control/test.cpp -o /tmp/tactile-control-test
/tmp/tactile-control-test
/usr/bin/clang++ -std=c++17 -Itests/native_control -I.tools/arduino-user/libraries/ArduinoJson/src tests/native_control/firmware_test.cpp -o /tmp/tactile-control-firmware-test
/tmp/tactile-control-firmware-test
```

板端编译命令及结果已保存在构建证据；不在此给出上传或实机运行指令。

## PWM 设计

GPIO23 为可配置候选，不代表接线已确认。50Hz、16bit，周期 20000μs；duty=round(pulse_us × 50 × 65536 / 1000000)，使用 64bit 中间量。1500μs 的纯计算结果为 4915 ticks；每 tick 约 0.30518μs。该示例不是自动中位或允许运动值，500–2500μs 没有被用作安全边界。

首次 SET 之前不调用 ledcAttach；ARM 本身无 PWM。首次目标必须等于另行核准的 initial_pulse_us，不能把它当成当前实际位置。检查 ledcAttach/ledcWrite/ledcDetach 返回值、配置频率和 duty 读回；API/寄存器成功只说明逻辑配置，物理波形必须用示波器/逻辑分析仪测量。

官方 API 依据：[Espressif LEDC 文档](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html)，实际编译采用本地 3.3.2 头文件/API，不套用 2.x 接口。

## 安全状态与失联

DISARMED → 显式 ARM → ARMED → 核准的首 SET → ACTIVE。所有运动需编译配置硬件使能、CONFIRMED 标定和有效边界；当前构建不能 ARM。运动命令带启动 boot_id、递增 sequence 和 request_id；旧会话/重放拒绝。Python 显式重连同步状态/序号，必要时先 DISARM，不自动恢复或重试目标。

设计值：100ms 最小命令间隔、1000ms 通信存活期限、2000ms 最大输出租约。心跳只维持存活，不延长输出租约；PING/STATUS 不刷新存活期限。累计绝对脉宽变化量和单步幅度独立限制。实际响应时限未测，这些值须在首次运动方案中确认。

异常、失联、期限到期或 API 故障进入 FAULT，尝试 duty=0 并 detach，不排队继续闭合。STOP 同样禁用，FAULT 中 STOP 不清故障；显式 DISARM 成功后才可再 ARM。无法可靠确认输出关闭时标 UNKNOWN，Python 通信错误亦标 UNKNOWN 并关闭连接。重启默认禁用、不居中、不恢复目标。

**STOP/停 PWM 可能失去保持力并导致掉杯子，不是机械保持、安全释放或硬件急停。** 当前选择禁用作为第一版有界测试策略，尚未现场验证适用性；人工切断电源、软件禁令、保持/释放、停 PWM 分别记录。CPU 卡死/驱动故障需硬件及看门狗策略另评估。

## 协议兼容与已知限制

保留 JSONL v1、115200 8N1、PING/PONG、GET_STATUS/STATUS、request_id；新增 ARM、DISARM、SET_PULSE_US、STOP、HEARTBEAT/ACK。新固件版本与 Stage 0.8 不同，旧严格版本客户端不能直接驱动新协议。没有远程标定或运行时解锁命令。

目标脉宽、命令角度、真实角度和真实开度不作线性对应。actual_angle_deg/actual_opening 为 null；状态为 PWM_COMMANDED_UNMEASURED 或 DISABLED_UNMEASURED，失败 UNKNOWN；不当作测得波形或到位证据。C 组真实帧尚未接入此脉宽控制器，原 closed_loop 仍为隔离的 FakeGripper 逻辑，不自动启用实机闭环。

## Stage 0.9B 首次运动前清单（未执行）

1. 核验 PM10D 原 PDF、正式引脚、输入信号电平及 GPIO23 适用性；用户提供参考参数不替代原件证据。
2. 核验已有独立 5V 方案的稳压、启动/堵转电流容量、保护与极性；公共 GND/信号兼容及无回灌风险。板载 3V3/GPIO 禁止供动力，板载 5V 未验证禁止直接供舵机。
3. 固定爪与舵机、排除夹伤区、提供负载支撑和可达人工断电手段；首次不夹杯子，不靠扫全行程找端点。
4. 制定并获准保守的标定/首目标方案，记录安全脉宽上下界、initial_pulse_us、相邻及累计幅度、速率与停止策略；未校准不能直接设 CONFIRMED。标定本身也需具体供电/接线/动作许可。
5. 先在无舵机负载条件下安排仪器验证 GPIO 波形及上电/复位/失联行为，不能以本机计算或寄存器替代。该 GPIO 输出测试也须另获许可。
6. 核准后的配置重新生成/测试/编译；分别取得固件上传许可与启用 GPIO/首次机械运动许可。Stage 0.8 的许可不延续到新固件。
7. 完成双端超时/停止现场验证后再联调 C 组真实 4×4 帧、保存配置/原始数据/命令/视频；本阶段真实运动和 Trial 数均为 0。

当前暂停于离线交付，等待用户确定下一阶段及授权，不自动执行以上清单。
