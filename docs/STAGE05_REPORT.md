# Stage 0.5：ESP32 识别、工程规则与软件架构准备

日期：2026-11-11（Asia/Shanghai）；主机快照时间 14:37:41 +08:00。

结论：**未发现可归属于 ESP32 的 USB/串口设备；不能确认 macOS 已识别开发板，也不能据此断定开发板物理上未连接。** 工程规范与架构准备完成，未进入 Stage 1。

## 本轮已知信息及来源

用户提供：金属机械爪由三线舵机驱动；舵机参数 4–6V、180°；线色看起来黑/红/白；开发板标有 ESP-32，带 USB-C、EN、BOOT；MacBook Air 为 Apple Silicon；爪尚未与 ESP32 接线。C 组可能提供 16 通道触觉矩阵，尚未联调。

这些存入 [用户报告记录](../evidence/stage05_user_reported_hardware.json)，状态为 USER_REPORTED。本轮未实际看到新照片，不把文字描述当作已读铭牌或官方规格。品牌、精确板型、引脚、堵转电流、PWM 参数、机械安全行程及停止效果均 UNKNOWN。4–6V 未填入可执行配置；180° 不作为机械爪安全行程。

最终研究目标为触觉辅助水杯自适应抓取；当前优先级为真实触觉触发有限开合、停止及允许的释放，不承诺力控或液体场景安全。

## 只读设备识别结果

本轮 `sw_vers` / `uname -m` 确认为 macOS 27.0.1（26A434）/ arm64。Python 3.9.6、uv 等环境沿用 Stage 0 记录，本轮没有安装或更改环境。

| 本轮可见串口 | 与 Stage 0 比较 | 是否可认定 ESP32 |
|---|---|---|
| /dev/cu.Bluetooth-Incoming-Port | 保留 | 否，系统端口 |
| /dev/cu.debug-console | 保留 | 否，系统端口 |

对应 tty 节点也仅这两类。没有新增或消失的 cu 节点，没有实际检测到可列为 ESP32 候选的端口。

| USB 描述符名称 | VID:PID | 本轮观察 |
|---|---|---|
| USB2.0 Hub | 05e3:0608 | 与 Stage 0 相同 |
| VGN Mouse 2.4G Receiver | 3554:f503 | 与 Stage 0 相同；厂商字符串 Compx |
| USB Type-C Digital AV Adapter | 343c:0000 | 与 Stage 0 相同；厂商字符串 xxxxxxxx |

本轮使用 `system_profiler SPUSBHostDataType -detailLevel basic`、`ioreg -r -c IOUSBHostDevice -l -w 0`、`ioreg -r -c IOSerialBSDClient -l` 及 Python glob 枚举设备节点；未打开任何设备文件。上述名称是描述符，不足以确定板型或下载某种驱动。

[本轮证据](../evidence/stage05_host_enumeration.json) 保存时间、命令、退出码、输出和串口差异；比较基线是 12:37:18 的 [Stage 0 证据](../evidence/stage0_host_enumeration.json)。这只是两次历史快照比较，期间是否插拔 UNKNOWN，不是受控的连接前后实验。

官方建议通过前后枚举识别新增端口，并先识别板载桥接芯片再考虑其驱动。当前没有对应证据，不能猜 CP210x、CH34x、FTDI 或某个 ESP32 DevKit。[Espressif 串口连接说明](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/establish-serial-connection.html)

## 软件方案与边界

推荐 **uv 管理的 Python + pyserial，上位机有限状态机，Arduino-ESP32 官方稳定版固件，LEDC PWM，JSON Lines 消息**。对于单舵机与 48 小时交付，优先减少工程配置与联调层数；这是工程选择，不是实机性能结论。准确 SoC 确认后再固定稳定版本、板型与 API，不安装两套框架。ESP-IDF 保留为后续需要更细控制时的备选。

技术依据、官方链接、模块边界、双端超时/限幅/STOP 策略及八项后续验证方案见 [ARCHITECTURE.md](ARCHITECTURE.md)。JSON Lines 是拟议方案，不是 C 组已确认接口；相应状态已补充到 [SENSOR_CONTRACT.md](SENSOR_CONTRACT.md)。

所有实机控制参数在 [配置设计模板](../config/control.template.json) 中保持 null，硬件开关 false。没有参数加载器、固件或控制器实现，因此不宣称已有安全保护。启动不自动闭合、不居中、不扫动；STOP 不等于硬件急停，保持最后 PWM 不证明已停住，停 PWM 也可能掉落负载。

## 文件变更与保存策略

- 检查根目录原无 AGENTS.md，已创建 [AGENTS.md](../AGENTS.md)，未创建子目录规则。
- 更新 hardware_inventory.csv（58 条）、BLOCKERS.md；保留未知参数，区分 USER_REPORTED、OBSERVED 和 UNKNOWN。
- Stage 0 报告原文保留，仅追加 Stage 0.5 更新；原 Stage 0 JSON 不改动。初始文件 SHA-256 清单保存在 evidence/stage05_initial_manifest.json 供核对。
- 新增本报告、架构/八步验证计划、配置设计模板；README 与传感协议补充当前状态。
- 新增 firmware/、data/simulated/、logs/simulated/ 占位；原 simulation/ 及全部 Stage 0 占位保留，不迁移、不删除。

本轮不编写控制代码或测试实现，原因是板型、PWM 参数和传感语义未定；纯软件接口与边界已在架构文档中定义。后续可先实现纯逻辑测试，不需等待机械爪接线。

执行计数：主机只读检查已执行；文档/配置完整性检查另存 evidence/stage05_validation.json；串口打开 0，发送数据 0，固件写入 0，舵机运动 0，真实传感器联调 0，状态机模拟测试 0，真实闭环 Trial 0。文件完整性检查不算状态机测试或实机验证。

## 阻塞与唯一当前操作

进入无舵机的 Stage 1 通信准备前，仍缺精确开发板/SoC、USB 芯片或 USB 接口类型、实际设备映射、对应资料，以及用户对串口/必要固件写入的明确许可。运动还需舵机官方规格、独立电源容量、准确引脚、信号兼容性、限位、实际停止策略和现场安全确认，见 [BLOCKERS.md](../BLOCKERS.md)。

**现在只推进“独立开发板 USB 连接确认”这一步，由用户亲自完成。** USB 会给开发板供电；先确认板上没有舵机、外部电源或其他外接线，没有裸露短接，并确认 USB-C 为该板供电/数据接口且愿意仅给开发板 USB 供电，才用支持数据传输的线将仅开发板连接 Mac。此时不按 BOOT/EN、不启动串口监视器、不安装猜测的驱动。不能确认这些条件就保持现状并提供板照片，不试接。

用户确认并完成这一步后，助手再次只读枚举；预期出现一个新 USB 节点及可能的新 cu 端口，但端口名称无法预先保证。出现新节点仅说明枚举成功，不证明双向通信成功。若无新增：先记录用户是否实际连接；后续一次一个步骤检查线是否支持数据、USB 路径、设备描述符/芯片及官方驱动要求，绝不用上传固件或盲发数据排障。
