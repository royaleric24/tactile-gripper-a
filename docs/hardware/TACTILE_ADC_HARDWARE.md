# 旧 ESP32 + 3 × ADS1220 硬件与固件说明

- 目标板：旧 **NodeMCU ESP-32S V1.1**（ESP32-D0WDQ6，4 MB）
- 采集固件：`firmware/sensor/`，当前修正构建 `tactile-sense-0.1.3`（0.1.0/0.1.1 的 AVDD 参考映射有误）
- 不涉及 ESP32-S3、不涉及舵机/PWM/机械运动
- 真实硬件验证：见 [`STAGE_H1_REPORT.md`](STAGE_H1_REPORT.md)（PASSED / FAILED / NOT_TESTED 分项）

## 1. 引脚（已焊接，不修改接线）

| 功能 | ESP32 GPIO | 方向 | 说明 |
|---|---|---:|---|
| SCLK | 18 | 输出 | 三颗 ADC 共用；空闲低 |
| MOSI | 23 | 输出 | 三颗 ADC 共用 |
| ADC1 MISO | 35 | 输入 | 仅输入引脚；ADC1 独占（2026-11-13 实测确认） |
| ADC2 MISO | 26 | 输入 | ADC2 独占（2026-11-13 实测确认） |
| ADC3 MISO | 34 | 输入 | 仅输入引脚；ADC3 独占（2026-11-13 实测确认） |
| ADC1 CS | 21 | 输出 | 低有效 |
| ADC2 CS | 22 | 输出 | 低有效 |
| ADC3 CS | 5 | 输出 | 低有效；GPIO5 是 strapping 引脚 |

固件不依赖 DRDY，也不使用 ESP32 的 SPI 外设。三颗 ADC 的 MISO 独立，普通单 MISO SPI 外设无法同时服务三颗；因此使用 **bit-bang SPI**。

启动时先把 GPIO5 的输出去寄存器置高，再使能输出并拉高，避免 CS3 在上电阶段产生不必要的低电平；随后所有 CS 保持高。

## 2. 电气检查（上电前）

- ADS1220 模块 `AVDD`/`DVDD` 均为 3.3 V，`AVSS`/`DGND` 与 ESP32 GND 共地。
- 逻辑电平 3.3 V；ADS1220 的 DIN/SCLK/CS 是输入，DOUT 是输出，均与 ESP32 3.3 V GPIO 兼容。
- GPIO34/35 只能输入，正好用于 MISO；它们没有内部上拉，ADS1220 的 DOUT 是推挽输出。
- 不要给 ADS1220 模拟输入超过 AVDD 或低于 AVSS 的电压；内部 2.048 V 参考下，单端输入有效范围约为 0…2.048 V；超过时切换到 AVDD–AVSS 参考（单端约 0…AVDD）。
- 不使用 IDAC 激励电流；固件配置寄存器 IDAC=000，且配置生成器拒绝 `idac_enabled=true`。
- 只对旧 ESP32 烧录。ESP32-S3 使用独立固件，不得混烧。

## 3. SPI 时序

ADS1220 仅支持 **SPI Mode 1（CPOL=0, CPHA=1）**：

- SCLK 空闲低。
- ADS1220 在 SCLK **下降沿**锁存 DIN。
- ADS1220 在 SCLK **上升沿**移出 DOUT。
- 固件在 SCLK 低时改变 MOSI，拉高 SCLK，等待后采样 MISO，再拉低 SCLK。
- 半周期 1 µs（约 500 kHz），远低于 ADS1220 4 MHz 上限；转换等待占主导，SPI 不是帧率瓶颈。
- 每条命令用 CS 低开始、CS 高结束；命令之间保持高电平。

## 4. ADS1220 配置

正常采集配置（`buildNormalConfig`）：

| 寄存器 | 值 | 说明 |
|---|---:|---|
| Reg0 | `MUX<<4 \| 0x01` | MUX=1000..1011（AIN0..3 vs AVSS），Gain=1，PGA bypass |
| Reg1 | `0x80` | DR=100（330 SPS），Normal mode，Single-shot，TS=0，BCS=0 |
| Reg2 | `0x00` 或 `0xC0` | 内部 2.048 V（VREF=00）或 AVDD–AVSS（VREF=11）；`0x80` 是外部 REFP1/REFN1，不是 AVDD |
| Reg3 | `0x00` | IDAC 路由关闭，DRDYM=0，保留位 0 |

四个 MUX 步骤对应 Reg0 = `0x81`、`0x91`、`0xA1`、`0xB1`。

### 4.1 时序与旧数据防护

- 330 SPS 单次转换官方时间 `12562 × tCLK ≈ 3.067 ms`，加内部振荡器唤醒 ≤50 µs。
- 固件每次 START 后等待 **4500 µs** 再发 RDATA，超过官方时间 + 容差 + 裕量。
- 每次切换 MUX 后重新 WREG、START、等待、RDATA；不会复用上一通道结果。
- 没有 DRDY，因此用固定等待而不是“读到数据就算新”；等待时间可在 `config/sensor_esp32.json` 调整，但生成器拒绝低于官方时间 + 10% + 150 µs 的值。

### 4.2 三颗 ADC 重叠

每个 MUX 步骤：

1. 三颗 ADC 依次 `setMux` + `START`；
2. 统一等待 4500 µs；
3. 三颗依次 `RDATA`，记录各自通道时间。

四个步骤串行，因此三颗 ADC 的转换时间重叠，而不是“ADC1 扫完 4 路再 ADC2”。

### 4.3 寄存器验证与故障隔离

初始化/恢复时：

1. `RESET`，等待 1 ms；
2. 读回 4 个复位寄存器；
3. 写入配置 A（`81 80 00 00`）并读回；
4. 写入配置 B（`91 80 80 00`）并读回；
5. 写入正常配置并读回。

两组配置不同，且拒绝全 `0x00`/全 `0xFF` 的固定响应，用于排除 MISO 卡死/器件缺席造成的假通过。单颗 ADC 失败只把该 ADC 的 4 路置为 null，另外两颗继续；每 500 ms 重试初始化。运行中每 256 帧校验一次配置寄存器，发现 `CONFIG_LOST` 时重新初始化。

## 5. 参考与量程

| 模式 | VREF | 单端满量程 | 适用 |
|---|---|---|---|
| `INTERNAL_2V048` | 内部 2.048 V | 约 +2.048 V = +8388607 | 默认；低噪声、较低量程 |
| `AVDD_AVSS` | AVDD–AVSS | 约 +AVDD = +8388607 | 输入可能 >2.048 V 时 |

切换命令 `{"cmd":"SET_REF","value":"AVDD_AVSS"}`，固件写读回验证；失败会回滚并返回 ERROR。`AVDD_AVSS` 参考的绝对精度和噪声取决于板级 AVDD，不能把它当作已标定测量。

单端 AINx/AVSS 下，负的原始值通常意味着输入低于 AVSS、参考异常或接线问题；固件保留原始值并打 `NEGATIVE_SINGLE_ENDED` 标记，不伪造为零。

## 6. 诊断用内部通道

`DIAG` 不依赖外部传感器，使用 ADS1220 内部功能：

- **输入短接**：MUX=1110，两个输入短接到 `(AVDD+AVSS)/2`，差分应为 0；得到 offset 原始值。
- **AVDD/4 监测**：MUX=1101，结果约为 `(AVDD/4)/2.048 × 2^23`；固件换算 `AVDD_mV ≈ raw / 1024`。
- **内部温度**：TS=1，14-bit 左对齐；`T = (raw >> 10) × 0.03125 °C`。
- 三颗 ADC 的寄存器读取/两组配置写读回。

这些只能证明 ADC 内核、SPI 和配置在真实器件上工作，**不能**证明外部 12 路传感器接线、矩阵映射或接触响应。外部 12 路必须单独读取并由人工按压验证。

## 7. 构建与烧录

```bash
# 生成配置 + 编译（不访问串口）
.venv/bin/python scripts/build_sensor_firmware.py

# 身份确认 + 全片备份 + 只写应用分区（脚本在执行前强制校验）
.venv/bin/python scripts/flash_sensor_firmware.py --port /dev/cu.usbserial-XXXX
```

烧录脚本只接受旧 ESP32：先读 chip family/MAC，要求 `ESP32` 且 MAC 与 `config/board_esp32_tactile.json` 的 `02:00:00:00:00:01` 一致；否则拒绝。烧录前把当前 4 MB Flash 备份到 `evidence/sensor/`，不覆盖历史固件。应用写入地址 `0x10000`，不改 bootloader/分区表。

## 8. 数据与目录

- 真实运行数据：`data/real/tactile/<UTC 时间>_<端口>/`
  - `raw_frames.jsonl`：设备原始行
  - `samples.csv`：每帧一行，含 12 通道、valid、flags、设备/主机时间
  - `events.jsonl`：HELLO/STATUS/ERROR 及主机接收时间
  - `run.json`：设备身份、文件 SHA-256、帧率/丢帧/通道统计
- 诊断结果：`evidence/sensor/diagnostics_*.json`（不提交 Git）
- 不覆盖旧数据；大 CSV 不提交 Git。

## 9. 当前未验证/限制

- 12 路与 6×6 矩阵 36 单元的映射：UNKNOWN。
- 原始 counts 到电阻/力/压力/摩擦力：UNKNOWN，未标定。
- 传感器是否安装、外部 12 路实际接线与接触响应：以真实实验为准；没有做按压就写 NOT_TESTED。
- AVDD 实际电压、噪声、通道间串扰、温漂、长期稳定性：真实采集后报告。
- 480/921600 波特率在具体 CP210x 线上的长期误码率：以 60 秒实测为准。
