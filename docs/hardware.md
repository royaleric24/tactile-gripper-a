# 板卡与采集入口

> **2026-11-15 修正指针**：本页是硬件分支历史记录。真实压敏布为 12 电极被动读取（R1–R6 各接 AIN + 10 kΩ 下拉，C1–C6 各接 AIN + 1 kΩ 上拉），**无 GPIO 列激励、无 HI_Z、无 36 点扫描**；当前接线以 [WIRING_FREEZE_V2.md](WIRING_FREEZE_V2.md) 为准。

S3 控爪与旧 ESP32 采集使用独立固件和配置。控制侧核对 config/board_s3.json、config/gripper_s3.json 和固件哈希。S3 端控制输出与可见开合分别记录；设备 ACK 无角度反馈。

硬件分支的 config/sensor_esp32.json 定义 SCLK 18、MOSI 23 以及 ADC1/2/3 的 CS/MISO 对 21/35、22/26、5/34。firmware/sensor/ 依次配置输入、启动单次转换、读取有符号计数并附加有效位。每颗 AIN0–3 对应四个扫描通道。详见该分支 docs/hardware/STAGE_H1_REPORT.md 与 TACTILE_ADC_PROTOCOL.md。

firmware/sensor_diag_ain1/ 用于固定测点，firmware/sensor_matrix/ 曾用于待验证的行扫描（**HISTORICAL**，不适用于 V2 布料）。历史上 12 个 ADC 输入、36 个按压位置和 36 个独立电气读数曾须分别说明。单点接触结果记录在相应实验目录；正式控制前还需验证重复性、无效数据处理与控制侧门控。**2026-11-15 修正：真实布料是 12 根电极、12 个单端测量值，不是 36 个独立读数，也没有 36 点矩阵扫描；`sensor_matrix/` 行扫描原型属历史分支，不适用于 V2 布料。**
