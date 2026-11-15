# 设备端

- ESP32-S3 控制 PM15S（型号由现场报告），当前配置 GPIO4、50 Hz、14-bit LEDC；旧 ESP32 的 GPIO23 控爪方案仅供回退。采集板上 GPIO23 用作 MOSI。先核对板型、用途、FQBN 和独立配置，两个角色不能同时复用该脚。
- 控制固件在 gripper_control/，串口测试在 serial_test/。从仓库根运行 `.venv/bin/python scripts/build_firmware.py s3` 仅构建。Arduino-ESP32 3.3.2 的 LEDC API 与板级配置配套；保留独立构建目录和 SHA-256。更新生成头文件须核对来源配置。
- V2 变体是 sensor_fsr2/ + config/sensor_esp32_{fsr1,electrodes12,electrodes12_fsr1}.json：四颗 ADS1220，FSR_A 为 ADC4 AIN0/MUX8，参考 AVDD_AVSS。历史双 FSR 构建由原 fsr2/electrodes12_fsr2 JSON 保留；12 电极是 R×10 kΩ 下拉 / C×1 kΩ 上拉的被动节点，**不得**再引入 GPIO 列驱动或 HI_Z 扫描，也不得把 12 路写成 36 点。它自带 driver、帧构造器与生成的 fsr2_config*.h，**不得**反向 include sensor/generated_config.h（会把 V1 的 3 ADC 引脚串进来）。构建：`python3 scripts/build_sensor_fsr2_firmware.py --profile fsr1（或 electrodes12 / electrodes12_fsr1；历史构建 fsr / electrodes12_fsr2） --build-dir <绝对路径>`，只编译不烧录。接口见 docs/hardware/FSR_ONLY_INTERFACE_V2.md。
- 历史 V1 sensor/ 与 config/sensor_esp32.json 描述 3×4 单次转换。ADC1/2/3 的 CS 分别为 21/22/5，MISO 为 35/26/34，SCLK 为 18。经寄存器回读确认的映射见 docs/hardware/STAGE_H1_REPORT.md。记录参考源、MUX、通道顺序、符号扩展、有效位及错误状态。
- sensor_diag_ain1/ 是固定输入诊断，sensor_matrix/ 是独立行扫描原型（**历史分支产物**：2026-11-15 修正后真实布料为 12 电极被动读取，无 GPIO 列激励、无 36 点扫描，sensor_matrix 不适用于 V2 布料；见 docs/WIRING_FREEZE_V2.md）。每个变体分别记录构建、上传及实际运行版本。主机驱动离线验证入口为 scripts/run_host_tests.py；它会写 evidence/sensor/host_test/，需要保留既有记录时在临时源码副本运行。
- 输出字段变更同时核对 frame_builder.cpp、主机解析器和旧固件样例。变更记录需包含板卡配置、固件版本/哈希、采样时钟、原始 JSONL、异常帧及复现条件。公开样例先剥离设备唯一标识。
- 保留独立供电、人工断电、支撑和限位检查。按装配区分 detached bench、trial、mechanical 模式；历史脉宽范围只适用于对应模式与设备。STOP/失联撤销输出许可，不能保证持物或切断动力。设备端执行超时、会话和动作边界检查。
