# A 组触觉机械爪项目交接

更新时间：2026-11-12（Stage 0.9B-26 验收后）。工作目录 /home/example/Developer/research/tactile-gripper-a。新对话先读根 AGENTS.md、本文件、docs/STAGE09B26_REPORT.md、BLOCKERS.md；不要重新初始化或覆盖历史证据。

## Stage 0.9B-26 当前基线（优先，2026-11-12）

- **主控制器：ESP32-S3**（YD-ESP32-23 2022-V1.3 / S3-N16R8），GPIO4、50 Hz、14-bit LEDC，固件 `gripper-control-s3-0.9b26.0`，串口 `/dev/cu.usbserial-EXAMPLE_S3`。后续开发以 S3 为主。
- **回退控制器：旧 ESP32**（NodeMCU ESP-32S V1.1），GPIO23、50 Hz、16-bit，稳定固件 `gripper-control-bench-0.9b24.0`；BIN SHA-256 `bd02b1d22165afda4bf6ab5e39907693e238d3c017145368b3a7e0aa9ffb98e1`。旧固件、配置、源码、构建产物和历史日志全部保留，不覆盖、不重烧。
- **验收结果**：固件上传 PASS；通信 PASS；用户报告真实机械爪开合 PASS（用户观察，非 Agent 观察）；精确位置误差 **UNKNOWN**；长期稳定性 **UNKNOWN**。
- **真实日志**：`logs/real/bench/0e0571fd739d4f638541df1ccae5cc9b/transport.jsonl`（REAL_SERIAL，0.9b26.0，0 ERROR/0 FAULT，最终 `DISARMED`）。日志只证明命令/ACK/状态时间线，不证明实际机械位置。
- 本验收步骤未重新烧录固件、未重复舵机测试。完整记录见 `docs/STAGE09B26_REPORT.md`、`evidence/stage09b26/summary.json`、`evidence/stage09b26/real_acceptance.json`。
- 下一阶段 4×4 触觉接入尚未开始；GPIO/ADC 映射、供电/电平/共地、UART/USB 资源与 C 组 16 通道协议均为待确认项。

> 以下 Stage 0.9B-1 至 Stage 0.9B-24 段落保留为历史记录，用于追溯当时的授权、证据和限制；当前状态以上方 Stage 0.9B-26 为准。

## 当前状态与权限

**历史记录（Stage 0.9B-1）：** 正式锁定固件已上传，真实无运动串口验证通过；用户确认 EN 操作后的新启动/默认锁定检查也已通过，本阶段完成并暂停；以 evidence/stage09b1/real_summary.json 为最终状态源。用户确认旧 ESP32 仅 USB 连 Mac，舵机/独立电源/其他外部电路完全隔离。本次授权只限 gripper-control-0.9b1.0 上传及无运动测试。后续新固件、接线、使能 GPIO/PWM、机械运动或标定均须新具体许可。

**历史记录：** 当时没有真实舵机运动或闭环 Trial，未测物理 PWM 或启动毛刺。当前 S3 已完成用户报告的真实机械开合验收（见上节），但精确位置误差、长期稳定性以及触觉闭环仍未验证；`hardware_enabled=false + UNCALIBRATED` 的设备端安全门槛仍适用于正式 ARM 路径。

## 硬件与来源（当前）

- Mac：macOS 27.0.1 / Apple Silicon；Python 3.9.6 + uv，项目 .venv。
- **主控制器**：YD-ESP32-23 2022-V1.3 / S3-N16R8；实测 ESP32-S3 (QFN56) r0.2、16 MB Flash、8 MB PSRAM、MAC `02:00:00:00:00:03`；USB 桥 FT232R，端口 `/dev/cu.usbserial-EXAMPLE_S3`（COM USB-C）。
- **回退控制器**：NodeMCU ESP-32S V1.1（丝印），ESP32-D0WDQ6 r1.1、4 MB Flash、MAC `02:00:00:00:00:01`；旧端口 `/dev/cu.usbserial-EXAMPLE_ESP32`。旧板仅作回退，不主动重烧。
- **舵机**：杭州众灵 PM15S，单轴，标称 15 kg·cm、270°；用户资料 5–8.4 V、50 Hz、500–2500 μs 参考、中位 1500 μs（USER_REPORTED，原件未独立核验）；无角度/扭矩反馈，信号电平兼容性 UNKNOWN。
- **舵机供电**：外部 5.3 V/2 A 标称，实际负载电压、启动/堵转电流余量与保护 UNKNOWN；GND 与 S3 共地（用户接线，USER_REPORTED）。不得用 S3 3V3 或板载 5V 给舵机供电。
- **当前 PWM**：S3 GPIO4、50 Hz、14-bit；旧回退 GPIO23、50 Hz、16-bit。GPIO4 为舵机专用，触觉接入不得复用。
- C 组拟提供 4×4 真实矩阵（16 通道 row-major），接口类型、GPIO/ADC 映射、质量/单位/时钟、供电与电平均未联调，见 `docs/SENSOR_CONTRACT.md`。

## 当前固件、配置和工具

- **S3 主控制器固件**：`gripper-control-s3-0.9b26.0`；配置 `config/gripper_s3.json`，生成头 `firmware/gripper_control/generated_config_s3.h`；构建目标 `config/board_s3.json`，FQBN `esp32:esp32:esp32s3` + 16 MB Flash / OPI PSRAM / 3 MB APP 分区。BIN `evidence/stage09b26/build_s3/gripper_control.ino.bin`，SHA-256 `04c77eed02c1d300f1d6aede842069489295f9fab4638ad2612acecb519c9348`。
- **旧 ESP32 回退固件**：`gripper-control-bench-0.9b24.0`；配置 `config/gripper_bench.json`，GPIO23/50 Hz/16-bit；旧 BIN `evidence/stage09b24/build_bench/gripper_control.ino.bin`，SHA-256 `bd02b1d22165afda4bf6ab5e39907693e238d3c017145368b3a7e0aa9ffb98e1`，保留不覆盖。
- **工具链**：Arduino-ESP32 3.3.2、ArduinoJson 7.4.2、GCC 14.2.0、arduino-cli 1.5.1；CLI 来自 `/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli`，配置 `.tools/arduino-cli.yaml`；Python 3.9.6 + uv，pyserial==3.5。
- **控制台**：`scripts/pwm_console.py --target s3 --real --port /dev/cu.usbserial-EXAMPLE_S3 --authorize`；端口必须显式提供，不写死。
- **历史说明**：下方 Stage 0.9B-1 的“板载 0.9b1.0 / GPIO23 / 16-bit”段落是历史快照，不代表当前主控制器。

## 真实与模拟证据

**Stage 0.9B-26 REAL_SERIAL（当前）**：S3 `gripper-control-s3-0.9b26.0` 真实日志 `logs/real/bench/0e0571fd739d4f638541df1ccae5cc9b/transport.jsonl`；端口 `/dev/cu.usbserial-EXAMPLE_S3`；0 ERROR、0 FAULT，最终 `DISARMED`；用户报告真实机械开合 PASS。日志不证明机械位置；精确位置误差/长期稳定性 UNKNOWN。摘要见 `evidence/stage09b26/real_acceptance.json`。

**历史 REAL_SERIAL**：Stage 0.8 serial-test 固件完成 PING/STATUS/错误帧/超时/设备缺失错误；Stage 0.9B-1 正式固件一次上传、四段哈希校验，EraseFlash=none，真实 PING/STATUS、request_id、ARM/SET/重复 ARM 拒绝、非法 JSON/缺 ID/超长/半帧、静默/超时/重连锁定通过。真实状态 DISARMED、UNCALIBRATED、hardware_enabled=false、motion_enabled=false、脉宽/实际角度/开度 null、DISABLED_UNMEASURED。未知命令在锁定态先 NOT_ARMED 拒绝，不外推为已 ARM 分支测试。

- logs/real/stage09b1/locked_suite.jsonl：完整时间、原始 TX/RX、回复；后续重启结果也在该目录。
- evidence/stage09b1/device_identity_real.txt、upload_real.txt、locked_suite_real.txt、status_before_restart.json、real_summary.json。
- SIMULATED：28 项 Python 测试与共享 C++ SafetyCore/实际 .ino 本机 stub；evidence/stage09b1/python_tests.txt、native_safety.txt、native_firmware.txt。
- 历史 0.9B-1 NOT_TESTED：真实 ACTIVE/ARMED 的看门狗、步幅/速率分支（不能为覆盖而取消锁定）；物理 PWM/毛刺；机械运动、保持/释放、真实触觉闭环。当前 S3 已由用户完成真实机械开合验收；波形/毛刺、精确位置与长期稳定性仍 UNKNOWN。

原厂旧 Flash 两份完整4MB备份在 evidence/stage08/flash_backup_original.bin / flash_backup_verify.bin，哈希与分区/117 字节 NVS 差异见 backup_manifest.json。应用/引导区一致，恢复过程未验证；备份不含 eFuse。serial-test-0.8.0 源码、构建及所有旧真实日志保留，不删除。不要整片擦除，不用 merged 4MB BIN 代替必要扇区上传，不自动进行恢复重试。

## 软件入口与复现

- src/gripper_a/gripper_controller.py：GripperController 默认 dry-run；真实硬件许可开关与配置门槛独立。旧 FakeGripper/SerialGripper 接口保留。
- serial_client.py：显式端口、版本/ID 匹配、超时关闭、JSONL 日志；打开串口可能通过 RTS/DTR/驱动造成复位，不保证无影响。
- scripts/gripper_locked_test.py：仅获授权后可对锁定固件运行；不是自动执行入口；复位验证模式比较 boot_id 并检查锁定。
- closed_loop.py：仍是 FakeGripper 模拟单位状态机，尚未绑定真实脉宽控制。
- config/simulated.json 与测试合成边界不是真实安全限位。模拟日志严格 SIMULATED，与 REAL_SERIAL 隔离。

离线测试：项目根目录 `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`。编译记录在 evidence/stage09b1/compile.txt；本文件不提供可直接触发上传或 GPIO 的命令。

## 下一阶段与安全阻塞（当前）

Stage 0.9B-26 已完成 S3 机械爪验收，下一阶段是 4×4 触觉传感器接入评估，但**尚未开始任何接线或代码开发**。仅输出待确认项：

1. C 组传感器的接口类型（16 路 ADC / 行列扫描 / 外部 ADC / 多路复用器）、采样率、分辨率、数据格式与时钟。
2. GPIO/ADC 映射：GPIO4 已固定给舵机 PWM，禁止复用；USB/UART、Flash/PSRAM、strapping 引脚需按 YD-ESP32-23 原理图核对，当前无原理图。
3. S3 内部 ADC1/ADC2 可用性、Wi-Fi 互斥、校准与输入范围。
4. 传感器 UART 与现有控制台 COM USB 的串口资源、波特率、缓冲和心跳带宽是否冲突。
5. 传感器供电电压/电流、3V3 余量、独立电源、共地、电平转换与过压保护。
6. 16 通道 row-major 仍是约定；C 组是否实际提供 16 通道、坏通道/质量标记/单位/阈值均未联调。
7. 触觉超时、STOP/释放策略、与 50 Hz PWM 的实时性和安全联动未定义。

历史段落中的 500–2500 μs/180°/10 kg·cm/PM10D 等说法已过时或不适用于当前 PM15S；不得把 PWM 目标当实际角度，也不得把 15 kg·cm 标称值当连续安全夹持力。

## 最终交接状态

EN 操作后新 boot_id=680238ca3e68d0fda093f270be3020ac，状态 DISARMED / UNCALIBRATED / hardware_enabled=false / motion_enabled=false，脉宽、实际角度及开度均 null。restart.jsonl 与 status_after_restart.json 保存证据。打开串口可能附带复位，不能单独判定复位来源；新启动默认锁定已确认。最终串口关闭、无占用，ESP32 保持 USB-only，无舵机/外部电源。Stage 0.9B-1 完成，不自动进入下一阶段。

## Stage 0.9B-2 当前交接优先记录

本轮已完成硬件/供电/固件离线安全审查及C1/C2测量方案，见 STAGE09B2_PREFLIGHT.md；没有重复 Stage 0.9B-1 实测，也未开串口或改变控制代码/配置。当前仍运行锁定 gripper-control-0.9b1.0，硬件false、UNCALIBRATED。

官方GPIO23复位表输出不使能，不等于主动低或无瞬态。找到Ai-Thinker参考P23映射，但USB-C实物定位、PM10D原始电气资料、独立5V USB供电链规格和仪器仍缺。UNKNOWN锁存/attach瞬态/主机本地拒绝等活动输出问题仅记录建议，未经批准不修改固件。Git当前不是仓库，不初始化。

C1（舵机隔离、当前固件被动观察）与C2（另获准专用固定PWM测量）分开，当前均NOT_TESTED；首次运动还需供电、信号、机械标定及人工断电/支撑。下一步只收集可用仪器型号/探头资料，无硬件操作授权。既有上传/测试许可不复用。

## Fast Track 最新交接（优先于上方测量硬门槛）

用户取消仪器作为首次功能试动硬门槛，并授权修改代码/离线测试/编译，未授权上传/接线/供电/PWM/运动。当前设备仍为旧锁定0.9b1.0，未触碰。候选试动构建 gripper-control-trial-0.9b2.0 在既有状态机中新增BEGIN_TRIAL/TRIAL_PULSE，正式ARM仍锁定；范围1460–1540、步幅20、累计80、单脉冲500ms、会话30s、失联5s，必须人工确认条件且逐次触发。正式硬件使能false和UNCALIBRATED不改成已标定；临时许可单独表示。

关闭UNKNOWN锁存和主机本地拒绝后的STOP已实现并离线验证。attach瞬态仍未物理测量，不把观察运动作为波形证据。config/gripper_trial.json是试动能力配置；config/gripper_control.json仍锁定（源码版本0.9b2.0，未上传），默认头最终恢复锁定；试动编译头快照/哈希在 evidence/fast_track/。候选试动BIN在 firmware/gripper_control/build_trial/，不自动上传。

下一步仅按 docs/FAST_TRACK_TRIAL.md 逐项完成最低硬件资料确认与分项授权，先无负载脱联动Test1，再另行批准Test2复装/局部范围。日志空模板 config/first_motion_record.template.json，NOT_EXECUTED。实际位置、供电容量和信号兼容尚未确认，不猜线色/电流。

## Stage 0.9B-3 最新交接（当前板状态）

已获明确上传/无运动授权及三项隔离确认；当前板载 gripper-control-trial-0.9b2.0，试动能力trial_capable=true，默认DISARMED/UNCALIBRATED/hardware_enabled=false/motion_enabled=false/trial_active=false/目标null。PING/STATUS、预先证明安全的拒绝请求、工具复位后新boot_id锁定均REAL_SERIAL通过，串口已关闭。完整报告 STAGE09B3_REPORT.md，最终状态 evidence/stage09b3/status_final.json，日志 logs/real/stage09b3/。

供电接线由他人完成，本轮不再审查；用户确认电源物理断开、PWM信号未接、爪不受上传影响。尚无有效Trial、PWM或运动，当前上传许可不包括后续接线/上电/试动。下一轮需用户断电确认脱联动、固定清场，另行批准恢复信号/上电/具体Test1动作。候选范围/期限保留，不擅自扩大。

## Stage 0.9B-4 当前优先路线

用户补充：完整机械爪基本完全闭合，机械联动不便拆卸；不强制拆卸，不以仪器为首次功能试动门槛。本轮仅审查和文档调整，没有硬件操作。当前板仍是 gripper-control-trial-0.9b2.0；代码/配置不变，现有LOCAL_RANGE_CONFIRMED可用于经审核的完整机构目标，不需要重传。

但未知当前轴位、方向及限位映射，1500μs可能进一步闭合/撞限位/堵转。500ms限制输出时间，不限制实际位移；命令首值比较锚点不是测得当前位置。当前没有任何已审核安全首目标，禁止BEGIN/TRIAL_PULSE、接线或上电。旧1500→1520→1500和脱联动Test1不适用当前路线；以 FAST_TRACK_TRIAL.md 顶部0.9B-4方案为准。

UNKNOWN在实际输出适配器RAM内锁存，复位会清除，不能以重启当作故障消除；没有自动输出1500/扫描路径。STOP/断PWM不是断独立舵机电源。

最短下一步：向装配者索取本套未改变装配的已知安全张开脉宽/旧程序或控制记录及方向/限位说明，配合当前位置/可见干涉检查。仅照片或“基本闭合”不足以定首值；无对应证据时，现有无拆卸/无反馈约束下不能给出可保证低风险的首定位命令。后续具体接线/上电/单次定位仍须分别授权。

## 交互式标定工具最新交接

已开发 scripts/calibrate_gripper.py 与 src/gripper_a/calibration.py，复用LimitedTrialController/SerialClient/FakeGripper，默认SIMULATED；未开真实串口或运动，无需修改/重传固件。使用说明 docs/CALIBRATION_TOOL.md，空参考模板 config/calibration_reference.template.json（无默认脉宽、不能直接作为参考）。

56项Python离线测试通过（新增20项），模拟终端启动/状态/退出通过，evidence/calibration_tool/保存证据。工具分UNREFERENCED/REFERENCE_CONFIRMED/LOCAL_CALIBRATING/LOCAL_RANGE_COMPLETE/FAULT；未参考禁运动，逐次EXECUTE和观察，所有安全记录来自人工确认，不把目标当位置反馈。候选范围有内缩余量且不自动改固件，后续动作/FAULT使其标过期待复核。

当前实际机构基本闭合、首次安全参考仍缺。工具不能填补脉宽—位置未知；真实模式需独立连接/运动授权、现场条件和真实参考证据。同安装记录不可与其他安装混用，异常/会话到期不自动续开。此轮只软件开发，用户未授权上电/试动。

## 2026-11-11 串口连接超时已修复

SerialClient连接后统一等待2秒，修复标定工具立即GET_STATUS撞上ESP32启动的问题；无运动权限的真实CLI退出不再隐式发送DISARM。65项离线测试通过，3次真实独立连接/7次PING或GET_STATUS通过（其中两次完整CLI status/quit），串口已关闭。设备仍gripper-control-trial-0.9b2.0、DISARMED/UNCALIBRATED、hardware_enabled=false、motion_enabled=false、trial_active=false、目标null。未修改/上传固件，未执行PWM或机械动作。详见docs/SERIAL_CONNECTION_FIX.md及evidence/serial_connection_fix/20261111T132827Z/；真实日志logs/real/serial_connection_fix/。初始安全参考仍缺，不能直接开始运动。

## Stage 0.9B-6 首次独立舵机试动失败（2026-11-11）

用户确认舵机完全脱联动、轴自由、固定、接线供电核对及可立即断电，明确授权并确认上电。仅执行一次1500μs：BEGIN_TRIAL(LINKAGE_DETACHED, low=high=initial=1500)获ACK；TRIAL_PULSE返回OUTPUT_API_FAILURE，设备FAULT/OUTPUT_UNKNOWN，motion_enabled=false、trial_active=false。无重试，串口已关闭。用户随后确认独立舵机电源已断开；实际运动观察未知，不能称试动成功。日志logs/real/stage09b6/20261111T133343Z/。

只读源码定位到明确缺陷：LedcOutput::set在ledcAttach后、首次非零ledcWrite前调用ledcReadFreq；本地Arduino-ESP32 3.3.2 esp32-hal-ledc.c的ledcReadFreq在ledcRead(pin)==0时直接返回0。attach初始duty为0，因此当前频率检查会将正常零占空比初始化误判失败。实际ERROR未区分attach/频率/write等分支，不能仅靠该错误排除其他故障，但此顺序缺陷足以阻塞首输出。

未修改控制代码或固件，未重新打开串口。建议下一任务离线修正读回顺序并增加遵循真实API零duty行为的回归测试；保留频率/占空比校验、错误off及UNKNOWN锁存，不直接删除保护。新固件上传和再次单次试动需分别授权，不能复用本次已消耗的单次运动许可。

## Stage 0.9B-6 LEDC最小修复候选已离线通过

修复gripper_control.ino：初始化以ledcAttach返回值和核心定时器配置为依据；ledcReadFreq仅在获准目标非零duty写入/读回成功后作为附加检查，不发初始化探测PWM。所有授权/限幅/时限/UNKNOWN机制保留。65项Python、5个native测试通过；Arduino CLI 1.5.1 + ESP32核心3.3.2两种配置实际编译成功，证据evidence/ledc_frequency_fix/，报告docs/STAGE09B6_LEDC_FIX.md。源码与二进制SHA已保存，生成头恢复原锁定配置。未上传、未开串口，板上仍旧固件；候选版本字符串未变，审核必须核对本次哈希。可进入上传审核，上传与再次单次试动分别授权；当前舵机动力保持断开。

## Stage 0.9B-7 上传后中间交接

用户确认动力物理断开、无人触轴、无其他程序后，已授权上传LEDC修复试动产物；芯片MAC匹配，写入哈希校验通过，无整片擦除。版本仍gripper-control-trial-0.9b2.0，部署应用SHA-256=5d3fc7050343f9950f354743f26ddf63a6f0138fd6b033cd1b6607706ffdbaf8。上传后GET_STATUS/PING通过且完全锁定，串口关闭。已请求用户短按EN，尚待其确认后查询；不要重复上传。报告docs/STAGE09B7_REPORT.md；真实日志logs/real/stage09b7/。未发运动命令，未验证真实PWM修复，动力须保持断开。

### Stage 0.9B-7 已完成并暂停

用户已确认短按EN。重连后GET_STATUS/PING均通过，boot_id已变，仍DISARMED/UNCALIBRATED、hardware_enabled=false、motion_enabled=false、trial_active=false、目标null、DISABLED_UNMEASURED。串口关闭且无占用。注意打开串口也可能复位，因此不把新boot_id唯一归因于EN，不声称连续测得重启瞬态。两轮实际仅发送2次GET_STATUS+2次PING；证据evidence/stage09b7/result.json和logs/real/stage09b7/。不再重复上传。仅具备下一次独立舵机单次试动准备条件，仍须新的现场确认及上电/一次具体PWM授权；本阶段未验证PWM物理效果。

## Stage 0.9B-8 单次输出API通过，等待观察

用户重新确认现场、明确授权并上电后，仅一次LINKAGE_DETACHED、范围1500–1500、TRIAL_PULSE(1500)。ACK/ACTIVE/PWM_COMMANDED_UNMEASURED，随后TRIAL_PULSE_ENDED/DISABLED_UNMEASURED；DISARM并查询恢复完全锁定，串口关闭。旧OUTPUT_API_FAILURE本次未出现；物理波形NOT_MEASURED，用户是否看到运动/异常仍PENDING，不能称机械运动成功。日志logs/real/stage09b8/20261111T135113Z/，报告docs/STAGE09B8_REPORT.md。未发1520、不重试。单次许可已使用，停止等待观察及下一授权；不将独立轴参考当机械爪标定。

### Stage 0.9B-8 观察补充

用户报告“没有转动，没有异响等”。本次结论仅为单次目标获ACK、API读回通过、自动结束并DISARM；未证实舵机运动。不能默认已位于1500位置或信号/供电正常；下一步先确认动力断开，再规划最小排查/另获准差分目标，不自动试1520。

## Stage 0.9B-9 仅首条已执行

同会话两次人工授权实验仅完成1500μs ACK及TRIAL_PULSE_ENDED，实际用户观察待反馈。执行器非交互stdin收到EOF，保守DISARM关闭，1520未发、未重试；不能称固件超时或第二次成功。最终锁定，详见docs/STAGE09B9_REPORT.md和logs/real/stage09b9/20261111T135827Z/。后续须先离线验证持续交互输入，再另行明确授权新会话；不自动补发/重复首条。

### Stage09B9 用户反馈及离线修复

用户报告首条“什么动静都没有”，已确认断电。输入通道修复候选在evidence/stage09b9/two_step_runner_pty_candidate.py，必须以PTY运行，非TTY在串口打开前拒绝；原实际执行脚本保留。新增2项纯软件PTY握手/EOF防护测试，全部67项Python测试通过。没有真实重试，没有完整两步实测；窗口保持30秒，迟到确认不得补发。当前等待新授权，不自动运行候选脚本。

### Stage09B9 新授权同会话1500→1520完成API验证

日志logs/real/stage09b9/20261111T140223Z/。PTY等待成功；首条1500结束后用户明确“无转动，无异常，继续1520”，原会话剩余约2.3秒时1520仅发送一次，ACK且随后TRIAL_PULSE_ENDED；最终DISARMED/UNCALIBRATED、motion_enabled=false、trial_active=false、目标null，串口已关闭。没有重开或第三条目标。1520实际运动/异常观察仍待用户反馈，不能称真实运动成功；等待反馈和断电确认，不自动继续。

## Stage 0.9B-10 当前舵机纠正为PM15S

用户最新报告PM15S、270°、5–8.4V、15KG、参考50Hz/500–2500μs/1500中位，无角反馈；输入逻辑阈值未知。电源标称5.3V/2A，非实测。此前PM10D称呼系误认；原始记录保留，不视为当前型号证明。实际代码没有180°线性映射：1500/1520分别4915/4981ticks（16bit/50Hz），同GPIO23 attach/write/off，未发现新增明确软件缺陷，API不能证明舵机端波形/电平。1500无运动无异常，1520最终观察仍待反馈。型号纠正不改变运动配置或授权。报告docs/STAGE09B10_PM15S_REVIEW.md；下一步先断电状态拍清铭牌/全接线/P23与电源标签，核对引脚/公共地，再另行规划实物电气测量。不在本轮上电或试动。

## Stage09B11 共地修正后独立1500试动

用户报告已可靠补齐共地并确认现场、上电无异常。本次仅1500μs（50Hz、500ms设备上限），ACK/API通过、TRIAL_PULSE_ENDED，DISARM后完全锁定，串口已关闭。保留全部保护，无上传/修改/重试/1520。日志logs/real/stage09b11/20261111T142359Z/；报告docs/STAGE09B11_REPORT.md。PM15S实际运动及异常观察待用户报告，物理PWM未测，不自动继续。

### Stage09B11 用户确认无动静且已断电

补共地后的1500请求API通过，但用户反馈没有任何动静；动力已物理断开。实际运动未证实，不重复同一目标，不擅自扩大范围/延长时间。下一项为断电实物接线核对，继而有依据地规划电气测量或适配测试器对照；无新的运动授权执行。

## Stage 0.9B-12 手动Bench控制台候选就绪（未部署）

新增scripts/pwm_console.py、src/gripper_a/bench.py、config/gripper_bench.json；固件增加独立BEGIN_BENCH/BENCH_PULSE及输出门。版本gripper-control-bench-0.9b12.0，1400–1600/step50/首1500/单次500ms/5分钟绝对窗/5秒失联，不自动续期或输出。原Trial限制保留，Bench专用模式不继承total80路径限制。默认SIMULATED；真实模式一次启动授权后用户逐次输入数字，不需Codex逐条批准。

85项Python、7个native通过，control/trial/bench在核心3.3.2下全部实际编译成功。源码/产物/配置快照evidence/stage09b12/；报告docs/STAGE09B12_REPORT.md，操作说明docs/PWM_CONSOLE.md。生成头恢复默认锁定；板仍旧Trial修复版，不兼容Bench，不要跳过上传阶段直接开真实控制台。本轮无串口/上传/PWM/接线。下一步新的单独部署授权，动力断开时审核哈希及写入/复位锁定，再一次Bench实验启动授权。偶发触碰运动仍是待排查硬件问题，ACK不证明实际运动。

## Stage09B13 Bench已部署并通过锁定验证

已授权上传gripper-control-bench-0.9b12.0；应用SHA256=a47093afe77d84ff61036f76b64e853a2f4a471836788cfa6fed9c7bbd0cfc56。身份/备份/审查哈希及写入校验通过，无整片擦除。上传后和用户EN后重连PING/GET_STATUS通过，最终DISARMED/UNCALIBRATED、hardware_enabled=false、motion_enabled=false、bench_capable=true、bench_active=false、窗口0、目标null。串口关闭，无Bench/PWM命令或真实试动。证据evidence/stage09b13/和logs/real/stage09b13/；报告docs/STAGE09B13_REPORT.md。旧“Bench未部署”段落为历史。真实Console现在协议兼容，但须新的一次实验启动许可及现场确认，本轮不自动启动。硬件偶发触碰运动/电平/供电问题未被锁定串口测试消除。

## Stage09B15 有限Hold候选（未部署）

用户报告独立PM15S已有真实可见转动，但500ms脉冲后回退/抖动；不把此当角度/可靠性验证。新候选gripper-control-bench-0.9b15.0新增显式hold/pulse选择、BENCH_HOLD目标、设备5秒绝对Hold期限。首次人工1500启动计时；同值/目标更新/心跳不续期、持续ACTIVE不重attach；到期off、撤销Bench至DISARMED，须人工begin/hold/首1500。原Pulse500ms、范围1400–1600/step50、默认锁定和故障保护保留。板仍bench-0.9b12.0，不直接启动新真实控制台。详见docs/STAGE09B15_HOLD.md、evidence/stage09b15/。本轮无上传/串口/PWM；下一步单独授权部署，再独立实验许可。

Stage09B15最终离线验证：93项Python、8个native、三种核心3.3.2配置编译均通过，配置/源码/二进制哈希保存在evidence/stage09b15/。未部署。

## Stage09B16 Hold固件已部署并暂停

gripper-control-bench-0.9b15.0已授权上传、写入校验通过，应用SHA256=d20f9eca0024648583e161c406c4e341e1b14b04a7906e7c97526215ee405aa3。上传后/EN后重连锁定验证及最终DISARM通过，串口关闭。最终DISARMED/UNCALIBRATED、motion_enabled=false、bench_active=false、hold_mode=false、目标null。无Bench或PWM启动。本轮唯一哈希漂移为主机scripts/pwm_console.py，已保留未运行，固件/配置/产物匹配；不能声称主机漂移版本已重新测试。报告docs/STAGE09B16_REPORT.md，日志logs/real/stage09b16/。下一步另授权独立Hold实验，软件固件条件具备，需核对实际CLI版本及现场。

## Stage09B19 主机Hold入口已修复

scripts/pwm_console.py原漂移文件与Stage16记录哈希一致；缺少hold/pulse分支已最小修复，保留格式和其他有效代码。具体覆盖来源无Git证据无法确定。97项Python通过，实际入口PTY测试核对BENCH_HOLD_MODE、BENCH_HOLD(1500/1550/同值)、Pulse、STOP/DISARM、超时、异常关闭，全部SIMULATED。固件/配置/BenchController未变、未开串口，兼容已部署0.9b15.0，无需上传。报告docs/STAGE09B19_CONSOLE_FIX.md；证据evidence/stage09b19/。退出旧Console后重新启动新入口，默认Pulse，人工hold再1500才会实际进入Hold；真实实验仍需独立授权及现场确认，本轮停止。
