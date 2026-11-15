# 混合传感硬件设计 V2（总览）

**状态：方案确定，物理接线待核对。** 正式的引脚、独立分压电路、12 电极接线和施工核对项见 **[WIRING_FREEZE_V2.md](WIRING_FREEZE_V2.md)**。不要使用以前 `config/sensor_matrix.json` 的 `row_gpio=[4,13,14,25,27,32]` 给 V2 新硬件烧录，它和 ADC4 CS32 冲突，而且扫描方向不同。

> **修正（2026-11-15，项目所有者确认）**：真实压敏布是 **12 根电极**（R1–R6 / C1–C6），全部被动接入 ADS1220 单端输入；原“ESP32 六列 GPIO 依次激励 + 未选中列 HI_Z + 拼 36 点矩阵”的设计**已被 2026-11-15 修正取代（HISTORICAL）**，不再是 V2 当前设计。R/C → ADC/AIN 的具体映射 **PENDING_REAL_WIRING**，待真实焊接/台架记录填写，文档不写任何示例编号。

## 1. V2 最终功能架构

```text
MacBook · Python · 中文 Dashboard
  ├─ USB → 旧 ESP32 ── SPI18/23 ── ADC1+ADC2+ADC3 → 12 电极被动单端读取
  │                                                 （R1–R6 / C1–C6 各占一个 AIN，映射 PENDING）
  │                  └─────────── ADC4 AIN0/AIN1 → 独立 FSR1/FSR2 分压
  └─ USB → ESP32-S3 → PWM → PM15S（单独舵机电源）
```

- FSR1/FSR2 两组独立分压，3.3 V → FSR → AIN 节点 → 各自 10kΩ → GND。作为接触强弱的主要反馈；不直接声称精确压力或摩擦力。
- 压敏布为**纯被动 12 电极**：每个 R 电极独立接一颗 ADS1220 的 AIN，并各有一颗 10 kΩ 下拉到 GND；每个 C 电极独立接一颗 ADS1220 的 AIN，并各有一颗 1 kΩ 上拉到 3.3 V。**没有 GPIO 列驱动，没有 HI_Z 切换，没有逐列扫描**；12 个电极电压是 12 个测量值，**不是 36 个独立压力点**。电极到 ADC/AIN 的对应关系见 [WIRING_FREEZE_V2.md](WIRING_FREEZE_V2.md) §4.1，未填表前按 PENDING 处理。
- ADC4 CS→GPIO32、DOUT→GPIO33，SCLK→GPIO18、DIN→GPIO23；前三颗 MISO 按用户确认的新版接线：ADC1/CS21/MISO34、ADC2/CS22/MISO35、ADC3/CS5/MISO26；旧固件配置须迁移并验证。
- **不再有矩阵列驱动 GPIO**；4、13、14、25、27、19 不用于 C1..C6 驱动。所有 ADC 与传感器使用旧 ESP 的 3.3V/GND，确保供电实测稳定；舵机单独供电。
- 通道容量：4 颗 ADS1220 共 16 个单端输入，12 电极 + ADC4 两路 FSR = 14 个逻辑通道，若真实映射不冲突则放得下；**14 通道合并是未来变体，当前仍先走 FSR_ONLY（2 通道）**。这只是容量核算，不是已接线事实。

## 2. 采集与执行优先级

**首要交付**：ADC4 两路 FSR 真实实时值 → Mac Dashboard LIVE → S3 PWM MANUAL → FSR 规则式 AUTO → 加水 Demo。12 电极属于辅助功能：当前只做“12 路电压是否稳定可读”的验证，若读数漂移、焊接困难或无法对应实物，直接保留 FSR-only，不把电极说成矩阵或压力点。

软件存储以 `FSR_ONLY` 为当前 profile；`MATRIX_ELECTRODES_12` 是面向真实布料的**提案**（12 逻辑通道，映射 PENDING，validated=false）；`HYBRID_6X6_FSR2` 已撤回为 HISTORICAL，只保留历史记录，不得在真实布料上使用。历史 12 通道单端采集、36 点扫描、38 逻辑值是三种不同语义，不能混用。完整接口见 [PROTOCOL_V2_PROPOSAL.md](PROTOCOL_V2_PROPOSAL.md)。

## 3. 最小实机确认

1. 以用户确认的 ADC1~3 CS/MISO 对应关系实施 V2 配置，并在本次实机验收时进行 SPI 读回测试；检查两片 FSR 各自独立分压，不让下拉电阻跨接两路。
2. 四 ADC 3.3V、地、CS 上拉、去耦和 ADC4 寄存器读回。
3. 只测试 FSR1、FSR2 的未按/轻按/夹杯/释放，保存原始值。
4. 12 电极被动读取验证：逐根确认 R 有 10 kΩ 下拉、C 有 1 kΩ 上拉、无 GPIO 列驱动线；读数只作相对趋势与通道稳定性检查，**不做 36 点热图，不宣称矩阵可用**；失败不阻断演示。电极 → ADC/AIN 映射须先由 §4.1 记录填全（当前 PENDING_REAL_WIRING）。
5. 两块 ESP USB 接 Mac，S3 单独操作舵机，最后才由 Python 连接并进入 AUTO。

## 4. 外部原始资料

- TI ADS1220：<https://www.ti.com/lit/ds/symlink/ads1220.pdf>
- ESP-IDF ESP32 GPIO：<https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/gpio.html>
