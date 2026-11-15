> 2026-11-15：压敏布实为 12 根被动电极（R×10 kΩ→GND，C×1 kΩ→3.3 V），无 GPIO 列驱动/6×6 扫描。见 docs/hardware/FSR_ONLY_INTERFACE_V2.md。

# 板卡与采集入口

S3 控爪与旧 ESP32 采集使用独立固件和配置。控制侧核对 config/board_s3.json、config/gripper_s3.json 和固件哈希。S3 端控制输出与可见开合分别记录；设备 ACK 无角度反馈。

硬件分支的 config/sensor_esp32.json 定义 SCLK 18、MOSI 23 以及 ADC1/2/3 的 CS/MISO 对 21/35、22/26、5/34。firmware/sensor/ 依次配置输入、启动单次转换、读取有符号计数并附加有效位。每颗 AIN0–3 对应四个扫描通道。详见该分支 docs/hardware/STAGE_H1_REPORT.md 与 TACTILE_ADC_PROTOCOL.md。

firmware/sensor_diag_ain1/ 用于固定测点，firmware/sensor_matrix/ 用于待验证的行扫描。12 个 ADC 输入、36 个按压位置和 36 个独立电气读数须分别说明。单点接触结果记录在相应实验目录；正式控制前还需验证重复性、无效数据处理与控制侧门控。
