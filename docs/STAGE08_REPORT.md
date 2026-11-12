# Stage 0.8 真实双向串口通信验证

日期：2026-11-11。**真实 Mac Python ↔ ESP32 双向通信与 USB 拔下后的设备缺失错误处理均已通过，本阶段完成。**测试对象仅开发板，不接舵机或外部电源。

## 授权与上传前核验

用户明确确认 USB-only 完全隔离并授权上传已编译 serial-test-0.8.0、执行无运动串口测试，禁止整片擦除与失败自动恢复。再次核对板型、候选端口、全部固件哈希与两份原始 Flash 备份；lsof 无占用。记录见 evidence/stage08/upload_preflight.json。

芯片为 esptool 实测 ESP32-D0WDQ6 revision v1.1、4MB Flash。两次完整 4MB 备份均保留：bootloader/分区表、ota_0/ota_1 和 at_customize 一致，117 字节差异限于 NVS 的 0x13000 扇区，可能来自旧应用复位后的持久化更新（推断）。两份哈希见 backup_manifest.json。备份未做恢复试验、不包含 eFuse，不宣称完整恢复已验证。

## 实际环境与构建

- Arduino CLI 1.5.1（复用 Arduino IDE 内置程序）；官方 Arduino-ESP32 3.3.2、ArduinoJson 7.4.2；编译器 xtensa GCC 14.2.0。
- FQBN esp32:esp32:nodemcu-32s；串口 /dev/cu.usbserial-EXAMPLE_ESP32，CP210x 桥；115200 8N1。
- Python 3.9.6 + uv 项目虚拟环境，pyserial 3.5。
- 固件 serial-test-0.8.0，板端编译通过；程序存储 287267 bytes、全局变量 21296 bytes，应用 bin 文件 287408 bytes。构建/依赖/二进制哈希见 compile.txt、build_manifest.json。
- 首轮 GitHub 下载慢，改用 Espressif 官方国内镜像并校验原官方 SHA-256，全部工具位于项目 .tools，无不必要全局安装。

## 真实写入结果

一次上传成功，EraseFlash=none；使用离散文件而非 4MB merged 镜像。仅写入 bootloader 0x1000（23664 bytes）、分区表 0x8000（3072）、boot_app0 0xe000（8192）和应用 0x10000（287408）。四段均 Hash of data verified；正常硬复位后进入应用。相关扇区发生必要擦写，未 erase-all，未自动重试或进行恢复。完整命令和输出见 evidence/stage08/upload_real.txt。

## 真实通信结果

PING→PONG、GET_STATUS、request_id 匹配全部通过；状态 SERIAL_ONLY_NO_MOTION、固件版本 serial-test-0.8.0、motion_enabled=false，并返回实际 uptime_ms、芯片及 Flash 大小。

非法 JSON→INVALID_JSON，未知命令→UNKNOWN_COMMAND，513 字节超长帧→FRAME_TOO_LONG，错误帧后 PING 恢复正常。无法提取 ID 的坏帧回复 request_id=null；正常命令使用随机唯一 ID 核对。客户端按应用协议版本、固件版本、request_id 匹配，不把启动输出当响应。

半帧输入超过固件 1000ms 闲置限制后返回 INCOMPLETE_FRAME_TIMEOUT；随后 PING 成功。主机故意不发送完整请求，等待约 3 秒后触发 response_timeout 并关闭端口，再显式重新连接 PING 成功。实际耗时见 real_test_summary.json。该主机超时是有意构造的无响应情形，不是设备故障或 USB 热拔插。

真实收发日志：logs/real/stage08/roundtrip.jsonl、timeouts.jsonl，标签 REAL_SERIAL，含 UTC/单调时间、TX/RX 十六进制、request_id 与异常。控制台输出在 evidence/stage08/roundtrip_real.txt、timeouts_real.txt。日志可能含启动信息，匹配结果单独记录。

## USB 断连测试

写入/校验全部结束，两个测试进程均退出，所有测试串口已关闭；lsof 再次无占用，记录 before_disconnect.json。用户随后确认“拔了”；重新枚举确认 USB CP210x 桥与 /dev/cu.usbserial-EXAMPLE_ESP32 均消失。客户端尝试连接缺失端口，捕获 Errno 2（No such file or directory）并记录 CONNECT_ERROR 和 ABSENT_DEVICE_ERROR_HANDLED，程序正常退出。原始证据见 disconnected_enumeration.json、disconnected_real.txt，真实日志见 logs/real/stage08/disconnected.jsonl。当前开发板保持 USB 拔下状态。不声称进行传输中的断连测试；这一场景目前仅有 SIMULATED 单元测试覆盖。

## 软件与离线结果

新增 serial_client.py、serial_test 固件、serial_roundtrip.py、serial_timeout_test.py、serial_disconnect_check.py，serial_test.json 配置和由其生成的 serial_config.h；复用已有 FakeGripper/控制器并保持真实爪入口禁用。协议见 SERIAL_TEST_PROTOCOL.md。

19 项 Python 单元测试、8 个 native 固件解析用例均通过，结果分别为 simulated_tests.txt 和 simulated_firmware_parser.txt。均为 SIMULATED，不计真实通信、舵机试验或闭环 Trial。

## 下一阶段条件与阻塞

真实串口命令通道已建立。本阶段真实双向通信、异常帧、超时及设备缺失检查已完成。Stage 0.9 开始前须明确范围；当前板已拔下，如需实机工作须由用户重新连接并复核通信。未来控制协议须另行设计、测试并授权写入。

舵机运动仍被独立供电缺失、启动/堵转电流、信号电平、正式引脚与公共 GND、安全机械行程、限位和人工停止/负载支撑阻塞。C 组真实 4×4 数据仍未联调，PM10D 原 PDF 未独立核验，无位置反馈，不得把目标当实测。串口成功不等于机械爪控制成功。

本阶段舵机接线、PWM 输出、机械运动和真实闭环 Trial 均为 0。用户授权限于本次无运动通信，不扩展为后续运动许可。
