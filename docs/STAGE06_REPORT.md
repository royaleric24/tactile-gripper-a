# Stage 0.6 ESP32 USB 识别与硬件资料更新

日期：2026-11-11（Asia/Shanghai）；枚举时间 14:59:31 +08:00。本轮只读，无串口打开、发送、复位、写固件或舵机运动。

## 枚举结果与证据边界

macOS 成功枚举了一个新增 USB 串口桥，作为此 ESP32 板的候选；尚未用受控插拔确认它与实物板的一一对应，更未验证 ESP32 固件通信。

| 项目 | 实际读取 |
|---|---|
| USB 描述符 | CP2102 USB to UART Bridge Controller |
| 厂商字符串 | Silicon Labs |
| VID:PID | 10C4:EA60 |
| USB 序列号 | EXAMPLE_ESP32（不假定全球唯一） |
| 位置 / 速率 | 0x01110000；12 Mb/s；位于 USB2.0 Hub 下 |
| 驱动 | AppleUSBSLCOM / com.apple.driverkit.AppleUSBSLCOM |
| 串口 | /dev/cu.usbserial-EXAMPLE_ESP32；对应 /dev/tty.usbserial-EXAMPLE_ESP32 |

IORegistry 树明确为 USB 桥 → USB interface → AppleUSBSLCOM → IOSerialBSDClient → 上述端口。因此端口映射有父子结构证据，不仅是名称猜测。桥接系列为 CP210x；具体芯片封装/型号仍 UNKNOWN，描述符自报 CP2102 不能单独证明真实硅片型号。Silicon Labs 资料说明多个型号共用 10C4:EA60：[官方 AN721](https://www.silabs.com/documents/public/application-notes/AN721.pdf)。

全部 cu 节点：Bluetooth-Incoming-Port、debug-console、usbserial-EXAMPLE_ESP32。相比 Stage 0.5 新增 usbserial-EXAMPLE_ESP32，无消失端口；USB 多出上述桥。历史基线存在，但没有记录用户在这两个快照之间的受控插拔，不能写成已完成对照验证。

原始命令、退出码与输出保存于 [stage06_host_enumeration.json](../evidence/stage06_host_enumeration.json)。采用 system_profiler SPUSBHostDataType、ioreg IOUSBHostDevice / IOSerialBSDClient 及 glob；没有打开串口或调用芯片探测程序。

## 硬件资料更新

用户转述板背面 NODEMCU ESP-32S V1.1，正面 ESP-32、EN/BOOT，引脚标识 P23/P22/P21/P19/P18/P5/P17/P16。具体 SoC、Flash 容量、板原理图和 GPIO 适用性未知，尚未选择舵机信号引脚。

舵机为用户转述的杭州众灵科技 PM10D，PWM 双轴位置控制，4–6V DC、10 kg·cm、180°，参考 50 Hz、500–2500 μs、中位 1500 μs；不支持实际角度回读、扭矩反馈或智能防堵转。来源是手册摘要转述，原始 PDF 未核验。电流、输入电平和机械安全行程 UNKNOWN；不将这些参考参数填入实际控制配置。用户报告舵机未接板。

## Arduino-ESP32 配置评估

推荐候选菜单 **NodeMCU-32S**，候选 FQBN `esp32:esp32:nodemcu-32s`。依据是用户提供的板丝印与 Espressif 官方 [boards.txt](https://raw.githubusercontent.com/espressif/arduino-esp32/master/boards.txt) 中 `nodemcu-32s.name=NodeMCU-32S`、`build.mcu=esp32`。这是候选匹配，不是已验证配置；不能把其默认 Flash 4MB 等设置当作实板测量。

本轮查阅的是 master 的定义，仅证明存在该板项，不作为稳定版本锁定。后续选兼容的官方稳定版，检查该版本板定义、模块完整标识/Flash 资料后再定配置。不因 USB 桥名称选择 S2/S3/C3 或 USB CDC 板型，不假定桥的 USB 速率是 UART 波特率。当前运行配置中的板型、串口和 PWM 参数继续为空；没有安装、编译或上传。

## 最小排查路径（备用，未执行）

此次已有 USB 节点和驱动端口，不存在已证实的枚举故障，不能编造“最可能故障原因”。当前只需确认物理板归属。若后续消失，按顺序一次查一项：已知支持数据的线 → Mac 端口 → 绕过集线器 → 重读 USB 描述符 → 若有 USB 但无串口，再核对具体桥芯片与官方驱动。没有 USB 节点时优先查连接路径，不能先归因驱动；不盲装驱动、不刷固件排障。

优先操作提议：用户确认舵机/外部电源隔离且允许仅开发板 USB 断电后，亲自只拔下这块开发板的 USB，再通知助手枚举，看 usbserial-EXAMPLE_ESP32 是否消失。此操作尚未执行；不要求现在接舵机，也不同时要求重新插回或按键。

## 后续供电与接线检查表（设计，全部待完成）

- [ ] 获取 PM10D 原 PDF 版本、适用型号，核对工作电压、启动/运行/堵转电流及输入信号电平；不能人为堵转测规格。
- [ ] 核对独立稳压电源的额定电压、电流余量、保护、极性、线径及连接器；资料未知不选电源、不接通。
- [ ] 核实三线正式引脚定义，不凭黑/红/白认定；按官方接线图设计信号参考地/共地，确认无 USB 回灌或电源互连风险。
- [ ] 核对开发板 V1.1 原理图、GPIO 电平/启动行为/复用限制；不根据 Pxx 丝印直接挑输出脚，不以 3V3 或板 5V 直接供舵机。
- [ ] 独立检查机械固定、安装零点、负载支撑和保守行程；禁止靠 500/2500 μs 或 180° 扫动探限位，1500 μs 也不默认安全。
- [ ] 确认上电/复位无自动 PWM，人工切断舵机电源方式可达；负载支撑防止断 PWM/断电掉落；软件 STOP 不等于急停。
- [ ] 完成双端超时/限幅方案，明确停止行为与独立角度测量方式；无反馈不填实际角度。
- [ ] 用户批准具体接线/供电/运动步骤后，由现场人员执行并记录；当前清单不构成授权。

## 更新与下一阶段条件

已增量更新根 AGENTS.md、hardware_inventory.csv、BLOCKERS.md；保留 Stage 0/0.5 原报告和原始证据。新增用户转述记录与本报告。控制模板保持禁用硬件、未知参数 null。

USB 枚举与驱动节点这一层已通过；可以继续无硬件软件准备。尚不能宣称 Stage 1 双向通信通过：实物映射、精确模块/配置、现有固件协议及开串口/写入许可仍需确认。舵机运动条件不具备，真实 Trial 数仍为 0。
