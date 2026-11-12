# Stage 0 硬件盘点与安全检查报告

检查日期：2026-11-11（Asia/Shanghai）。详细采集时间见证据 JSON 的 `checked_at`。

**结论：主机只读盘点和基础文档已完成；机械爪未识别，连接未验证，现场安全未确认。Stage 0 的硬件确认仍待补充，不进入 Stage 1，不允许运动。**

## 1. 已确认的环境与可见设备

| 项目 | 实际观察 |
|---|---|
| 项目路径 | /home/example/Developer/research/tactile-gripper-a |
| 初始项目 | 空目录；无代码、配置、说明书、照片或 AGENTS.md；未初始化 Git |
| 系统 | macOS 27.0.1，build 26A434，arm64 |
| Python | 3.9.6；shell 路径 /usr/bin/python3；实际 executable /Library/Developer/CommandLineTools/usr/bin/python3 |
| 虚拟环境 | 当前 Python 未在虚拟环境中；本轮未创建虚拟环境 |
| pyserial | 当前解释器未找到 serial 模块；系统枚举已足够，未安装 |
| 开发工具 | Git 2.55.0，uv 0.12.10 可用；pip3 路径 /usr/bin/pip3，未用于安装 |
| /dev/cu.* | /dev/cu.Bluetooth-Incoming-Port；/dev/cu.debug-console |
| /dev/tty.* | /dev/tty.Bluetooth-Incoming-Port；/dev/tty.debug-console |

USB 系统描述符中可见的外设（名称仅是设备报告的字符串，不是机械爪身份鉴定）：

| 名称 | VID:PID | 结论 |
|---|---|---|
| USB2.0 Hub | 05e3:0608 | USB 集线器，无法据此识别机械爪 |
| VGN Mouse 2.4G Receiver | 3554:f503 | 名称为鼠标接收器；厂商字符串 Compx |
| USB Type-C Digital AV Adapter | 343c:0000 | 名称为影音转接器；厂商字符串 xxxxxxxx，不作为可信品牌 |

另见两个内置 USB 3.1 总线条目。系统端口和上述外设均未被认定为机械爪端点；未向任何设备打开通信连接。

串口是操作系统提供的通信入口；看见端口不等于连接机械爪成功。当前没有已确认的外接机械爪串口，但这也不能证明设备物理上未连接，其他接口、线缆、驱动或供电状态仍未知。

## 2. 检查方法与可核查证据

只读取系统信息、设备节点名称及注册表缓存；未打开串口、发送控制字节、调用 SDK、联网扫描设备或触碰电源与接线。

- `sw_vers`、`uname -m`、Python 标准库检查及开发工具版本查询。
- `system_profiler SPUSBDataType -detailLevel basic` 返回码 0，但无输出，不能当作“无 USB 设备”的结论。
- `system_profiler -listDataTypes` 列出了 `SPUSBHostDataType`；改用 `system_profiler SPUSBHostDataType -detailLevel basic` 后获得上述 USB 列表。
- `ioreg -p IOUSB -l -w 0` 和 `ioreg -r -c IOSerialBSDClient -l` 补充注册表信息。
- [evidence/stage0_host_enumeration.json](../evidence/stage0_host_enumeration.json) 保存时间、关键环境信息、各命令退出码及输出。证据范围只覆盖本次快照。

没有修改系统 Python、安装依赖、初始化 Git、加载新驱动或探测未知协议。未检测网络/Bluetooth 外部设备，因尚无接口线索，也未进行主动发现。

## 3. 硬件未知项

机械爪品牌/型号、驱动器/控制板、固件、通信接口/协议/参数、供电电压/电流/极性、控制方式、角度/开度单位与映射、反馈能力、停止方式、安全行程、限位及过载保护全部为 **UNKNOWN**。

原因：没有资料和照片，现有 USB/串口信息无法对应机械爪。详见 [hardware_inventory.csv](../hardware_inventory.csv) 与 [BLOCKERS.md](../BLOCKERS.md)。尚无精确型号，因此没有选用或套用任何厂家 API/协议；型号明确后须查找对应型号的官方资料，记录版本和适用范围。

## 4. 初步风险识别（未完成现场验收）

以下是本项目需要核查的潜在风险，不是已观察到的缺陷，也不是设备已经具有保护功能的证明。

| 风险 | 当前未知 | 任何运动前必须核实 |
|---|---|---|
| 夹伤/卷入 | 夹爪行程、速度、夹力、连杆暴露情况 | 手与工具不进入运动区，人员远离；安全范围、停止机制和现场看护已确认 |
| 电气损伤/短路 | 额定电压、电流、极性、引脚、线缆状态 | 官方额定值与电源/接线一致，由具备能力的现场人员核对；本轮不接线、不上电 |
| 设备或物体掉落 | 安装固定、负载、失电后是否松开 | 固定与支撑条件；停止、释放、断电分别会发生什么，不默认释放最安全 |
| 意外启动/失控 | 上电动作、限位、失联/程序崩溃/复位行为 | 对应协议与故障策略、可达的现场停止方式；未经明确授权不得试验 |
| 触觉误判导致继续夹紧 | 数据时效、坏通道、材料与阈值 | 数据约定和异常处理明确；无效数据不应成为继续闭合的依据 |

限位是运动范围的边界；“软件不再发送命令”并不证明设备停止。软件停止命令、硬件急停、释放和断电的效果必须分别核实，不能混为一谈。

运动门槛：型号、官方协议、供电、限位、停止/故障行为及现场安全全部确认，并且用户明确同意具体操作。本轮未满足门槛，实际操作保持禁止。

## 5. 本轮交付与测试状态

已创建 README.md、hardware_inventory.csv、BLOCKERS.md、docs/SENSOR_CONTRACT.md、docs/STAGE0_REPORT.md，并保存主机枚举证据。

预留 src/gripper_a/、tests/、config/ 以及真实/模拟数据与日志、真实视频目录，仅有占位文件，没有控制器或可运行运动入口。

主机只读检查：已执行。机械爪通信测试：未执行。安全停止验证：未执行。运动测试：未执行。真实触觉采集：未执行。真实闭环 Trial：0。软件模拟：0。文件结构校验仅用于确认交付内容，不计入任何实机或模拟测试结果。

## 6. 所需资料与唯一下一步

后续识别所需资料清单（无需现在同时完成）：机械爪全貌及铭牌、控制板标签/丝印、接口标签与当前线缆全貌、电源输出标签、对应说明书/官方产品链接、现场固定与负载情况。照片只拍安全可见部分，不拆卸、不伸入夹爪、不改变接线或供电。

**现在只做一步：提供一张能读清机械爪品牌和型号铭牌的照片。** 保持设备现状，在安全距离拍摄；若铭牌不可安全接近，不移动设备，改用已有照片或采购型号截图。

预期结果：读出品牌与完整型号，把 B01 从 UNKNOWN 更新为有证据的身份，再查对应官方文档；这仍不构成运动授权。

如果失败：文字模糊可在安全位置调整对焦/拍摄角度；铭牌缺失或不可见时，提供已有包装标签、采购记录或说明书封面。不得通过试接电源或发送开合命令来识别型号。

## 7. Stage 0.5 追加记录（2026-11-11）

以上为 Stage 0 历史快照，保留原文，不代表当前资料仍为空。当前阶段详见 [STAGE05_REPORT.md](STAGE05_REPORT.md)。

用户新增信息：金属机械爪由三线舵机驱动；标称 4–6V、180° 尚待官方资料核实，线色不能确定引脚；板面标有 ESP-32、USB-C、EN/BOOT，准确型号与引脚未知；爪尚未接 ESP32。上述均为 USER_REPORTED，不是实测或已读铭牌。

本轮再次只读枚举，仍仅见 Bluetooth-Incoming-Port 和 debug-console；与 Stage 0 相比无新增/消失 cu 端口。USB 外设名称及 VID/PID 无变化，未建立 ESP32 映射，也未观察受控插拔。新证据单独保存于 evidence/stage05_host_enumeration.json；原 Stage 0 JSON 保持不变。

已新增根目录 AGENTS.md、软件架构/验证计划及禁用硬件的配置设计模板；新增模拟目录采用 simulated，Stage 0 simulation 目录原样保留。没有串口通信、固件写入、舵机运动、模拟状态机测试或真实 Trial。
