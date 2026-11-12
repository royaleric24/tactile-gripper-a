# Stage 0.9B-1 最新真实结果

2026-11-11：已获本次明确授权，用户确认完全隔离。**正式锁定固件上传、真实串口拒绝及用户 EN 操作后的新启动锁定检查均通过，本阶段完成。** 下方“上传前审查”保留为历史记录，以本节与 real_summary.json 为当前结果。

## REAL_SERIAL

上传前全部源/配置/BIN SHA-256 匹配审查清单；esptool 实测 ESP32-D0WDQ6 revision v1.1、4MB、MAC 02:00:00:00:00:01，与历史设备相符。FQBN esp32:esp32:nodemcu-32s，端口 /dev/cu.usbserial-EXAMPLE_ESP32。身份读取仅加载 RAM stub/复位，不擦写 Flash。

一次上传成功，四段 Hash of data verified；仅写 bootloader 0x1000、partition 0x8000、boot_app0 0xe000、app 0x10000。EraseFlash=none，无整片擦除、无恢复重试。日志 evidence/stage09b1/upload_real.txt；设备身份/授权在 device_identity_real.txt、upload_authorization.json。

实际状态 gripper-control-0.9b1.0，DISARMED、UNCALIBRATED、hardware_enabled=false、motion_enabled=false、commanded_pulse_us=null、output_state=DISABLED_UNMEASURED。actual_angle_deg/actual_opening 均 null。

PING/PONG、GET_STATUS 与 request_id 匹配通过；ARM 与原样重复 ARM 均返回 UNCALIBRATED_OR_DISABLED；脉宽 0 和 4294967295 的 SET 均以 NOT_ARMED 拒绝；未知命令安全报错。非法 JSON、超长帧、缺失 ID 分别返回 INVALID_JSON、FRAME_TOO_LONG、INVALID_ID；半帧返回 PARTIAL_TIMEOUT。STOP/DISARM 返回 ACK，仍锁定。静默等待和主机响应超时/关闭/重连后保持禁用，没有自动 ARM。

日志 logs/real/stage09b1/locked_suite.jsonl 标 REAL_SERIAL，含 UTC/单调时间、TX/RX 原始十六进制和匹配回复；摘要 real_summary.json。客户端重连前后 boot_id 曾变化，说明连接可能复位设备，不能声称串口打开无复位影响；仍均回到默认锁定。

## SIMULATED / NOT_TESTED

本阶段此前 28 项 Python 和 native 测试为 SIMULATED。当前锁定态无法实机执行 ACTIVE/ARMED watchdog、已 ARM 后的幅度/速率分支，禁止为覆盖而解锁；这些仍只有模拟证据。重复 ARM 验证的是锁定拒绝，不是 request_id 去重实现。

GPIO23 波形、上电/复位毛刺均 NOT_TESTED。未改变锁定使能、未填安全边界、未连接舵机、未发出获准 PWM 使能，机械运动为 0。逻辑状态报告不能证明物理引脚无输出；不能把禁用 PWM 当成机械保持或安全释放。

## 后续门槛

Stage 0.9B-2 前仍需独立 5V 方案电流/保护/极性、信号电平与正式引脚/共地、GPIO23 适用性、固定和负载支撑、人工断电、核准标定方案与首脉宽；物理信号需适当仪器。原 PM10D 参考范围不能直接解锁。C 组真实触觉尚未联调。新固件/接线/PWM/机械动作均需下一阶段具体许可。

---

# Stage 0.9B-1 正式控制固件实机验证（上传前审查）

日期：2026-11-11。当前阶段：上传前准备；**尚未授权上传，正式控制固件未上传，实机应用测试 NOT_TESTED**。用户确认开发板仅连接 Mac USB，舵机/外部电源/其他电路完全隔离。

## 本轮设备与保存记录

只读系统枚举发现 /dev/cu.usbserial-EXAMPLE_ESP32、Silicon Labs 描述符 CP2102 USB to UART Bridge Controller、10C4:EA60、序列号 EXAMPLE_ESP32。当前位置 0x01120000（与此前位置不同，不能把位置当固定身份）；同一端口/描述符与既有归属证据相符，未重复执行受控插拔。lsof 无占用。

本次未打开串口重新探测芯片；目标 ESP32-D0WDQ6 / 4MB 来自 Stage 0.8 实测记录，与 NodeMCU-32S / esp32:esp32:nodemcu-32s 的已用配置匹配。获准上传时以 esptool 实际识别与日志复核，若不符则停止。

Stage 0.8 固件构建、两份原始 4MB 备份及真实日志全部保留；Stage 0.9A 证据也保留。preserved_manifest.json 保存本次审查前文件哈希；当前设备应用仍推定是 Stage 0.8，未查询验证，不冒充本轮实测。

## 代码审查

- setup 只初始化串口、配置结构和启动随机会话，不调用 GPIO 配置、ledcAttach、ledcWrite 或舵机驱动。全局输出适配器默认 attached=false。
- ARM 必须通过 Limits.valid：硬件使能、标定、上下界/首目标/步幅/累计幅度等全部有效。当前 false + UNCALIBRATED + 空边界拒绝 ARM，ARM 自身也不 attach LEDC。
- SET 在 DISARMED/FAULT 被拒绝，ACTIVE 输出还需会话/序号、边界、步幅、累计幅度及速率通过。没有修改配置/远程标定命令，因此当前 JSON 命令路径不能解锁校准。
- 额外加固：LEDC 适配器 set() 在实际 attach 前独立检查编译使能、标定及脉宽边界，避免只依赖调用方；GET_STATUS 增加 hardware_enabled 供实机核对。新版本 gripper-control-0.9b1.0，和旧构建不混用。
- STOP/DISARM 在未 attach 时直接返回，不为“停止”而启用 GPIO；若已 attach 则尝试 duty=0/detach。STOP 不清 FAULT；DISARM 关闭成功后可清除。失败记 UNKNOWN，不宣称机械安全保持。
- TX 背压可进入 FAULT，输出操作失败也锁定；UART 消失无法直接实时检测，依赖通信期限。不能把逻辑拒绝或未调用 API 当作已测到无启动毛刺。

结论：当前锁定配置下未发现通过命令到达 PWM 输出的路径；这是源代码审查与离线验证结论，不是物理波形验证或全系统无风险证明。

## 配置、构建与离线验证

配置源 config/gripper_control.json；生成脚本重新运行，并比较头文件与源值。硬件 false、标定 false；安全边界/初始值/步幅/累计幅度均空（头文件 0 占位）。没有填入手册 500–2500μs。

使用 Arduino CLI 1.5.1、Arduino-ESP32 3.3.2、ArduinoJson 7.4.2、Xtensa GCC 14.2.0。新构建目录 firmware/gripper_control/build_stage09b1；旧构建不覆盖。本次最终大小、版本、配置和 SHA-256 见 evidence/stage09b1/build_manifest.json，编译输出见 compile.txt。

28 项 Python SIMULATED 测试以及 native safety / firmware 测试结果分别保存本阶段证据目录。实际入口测试新增直接调用 LEDC 适配器 set(1500) 的旁路检查，默认配置返回拒绝且 stub LEDC 调用为 0；不是实机发出 1500μs。Native 测试只说明逻辑，不能证明物理 GPIO 无毛刺。

## 上传后方案（全部 NOT_TESTED，等待授权）

scripts/gripper_locked_test.py 只可在另获授权且固件上传成功后运行；先验证状态锁定，再发送 ARM/SET 的拒绝测试。日志标 REAL_SERIAL；离线结果标 SIMULATED；未执行标 NOT_TESTED。

| 项目 | 当前状态 / 证据边界 |
|---|---|
| 固件上传、真实启动与 PING/STATUS | NOT_TESTED |
| hardware_enabled=false、UNCALIBRATED 实机核对 | NOT_TESTED |
| ARM / SET 拒绝 | NOT_TESTED；不取消门槛测试可用运动路径 |
| 非法 JSON、缺 ID、未知、超长帧 | NOT_TESTED |
| 重复 ARM | NOT_TESTED；计划原样重复请求，均须拒绝。当前实现不缓存 request_id，不能声称所有重复请求都显式报重复错误 |
| 越界 SET | NOT_TESTED；锁定态应先以 NOT_ARMED 拒绝，不能声称实机独立覆盖已 ARM 后的数值限幅分支 |
| 半帧、主机无响应期限、静默/重连不自动 ARM | NOT_TESTED |
| ACTIVE/ARMED 的板端超时撤销输出 | 仅 SIMULATED；本阶段不能 ARM，因此不能实机覆盖该分支 |
| 重启后新 boot_id、DISARMED 和无恢复 | NOT_TESTED；上传后须分步让用户操作复位，不把开串口等同于重启证明 |
| GPIO23 物理波形/上电毛刺 | NOT_TESTED；未确认仪器，不宣称有/无物理意外输出 |

后续一次上传仅写必要引导、分区与应用扇区，EraseFlash=none，不使用 merged 全片镜像、不整片擦除。失败停止并报告，不自动试恢复。固件上传及写入校验期间不要求用户拔插。Stage 0.8 上传授权不覆盖本次上传。

## 首次机械运动前条件与下一步

Stage 0.9B-2 仍需 PM10D 原件规格、电流与信号电平、独立 5V 方案容量/保护、准确引脚/公共 GND、GPIO23 适用性、保守机构边界和核准首脉宽、固定/支撑、人工断电与停止策略。上电/复位波形需仪器验证；上传授权与 GPIO 输出、接线、运动授权分开。C 组数据联调另行开展。

当前需要用户的唯一下一步：审阅本次版本、配置、哈希与风险后，明确授权或拒绝上传锁定版 gripper-control-0.9b1.0 及之后的无运动串口测试。不要求连接舵机或开启 PWM。

## 上传前最终结论

最终编译成功：程序 293287 bytes、静态内存 21648 bytes。28 项 Python SIMULATED 测试通过，native 共享核心与实际入口测试通过；重复 ARM、缺失/空 ID、锁定态大脉宽拒绝及直接适配器旁路拒绝均在本机 stub 验证。新脚本已语法检查，尚未对设备运行。

应用 BIN SHA-256：94e4dbc1ec50f09a7474f072af77cb6629d3a2ebcdcec5b5744b80b5af52021a。其余源/配置/引导/分区文件哈希见 build_manifest.json。原 Stage 0.8/0.9A 构建 BIN 及旧证据核验未变。

尚未上传成功（未执行），尚无本版本 ESP32 运行状态、串口拒绝或重启结果；没有物理 PWM 测量，不能回答“没有意外物理输出”。当前允许结论为配置/源码门槛和离线测试通过。下一步仅请求本次锁定固件上传及无运动串口测试授权，不要求用户连接舵机。

## EN 操作后的最终验证（REAL_SERIAL）

用户确认“已短按并松开 EN 一次”。随后读取状态，boot_id 从 b7f924289ee48ba13decac6857a98f74 变为 680238ca3e68d0fda093f270be3020ac，fault_reason=BOOT、last_sequence=0，仍为 DISARMED、UNCALIBRATED、hardware_enabled=false、motion_enabled=false、commanded_pulse_us=null、DISABLED_UNMEASURED。证明新启动后锁定状态，不恢复 ARM/目标。

注意串口打开也可能造成复位，不能用该证据单独归因 EN 或排除额外复位；新启动与安全默认状态已验证。真实日志 logs/real/stage09b1/restart.jsonl，控制台 restart_real.txt，最终状态 status_after_restart.json，汇总 real_summary.json。完成后串口已关闭，lsof 无占用。

本阶段完成并暂停。物理 PWM 波形/启动毛刺、ACTIVE 看门狗实机分支、舵机/机械停止与保持仍未测；不得把本次结果作为首次机械运动许可。
