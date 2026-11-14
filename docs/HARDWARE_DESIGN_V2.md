# 混合传感硬件设计 V2（总览）

**状态：方案确定，物理接线待核对。** 正式的引脚、独立分压电路、6×6 行列接线和施工核对项见 **[WIRING_FREEZE_V2.md](WIRING_FREEZE_V2.md)**。不要使用以前 `config/sensor_matrix.json` 的 `row_gpio=[4,13,14,25,27,32]` 给 V2 新硬件烧录，它和 ADC4 CS32 冲突，而且扫描方向不同。

## 1. V2 最终功能架构

```text
MacBook · Python · 中文 Dashboard
  ├─ USB → 旧 ESP32 ── SPI18/23 ── ADC1+ADC2+ADC3 → 矩阵六个行测量节点
  │                  ├─ 6 列 GPIO 依次激励 → 单侧 6×6 压敏布
  │                  └─────────── ADC4 AIN0/AIN1 → 另一侧 FSR1/FSR2
  └─ USB → ESP32-S3 → PWM → PM15S（单独舵机电源）
```

- FSR1/FSR2 两组独立分压，3.3 V → FSR → AIN 节点 → 各自 10kΩ → GND。作为接触强弱的主要反馈；不直接声称精确压力或摩擦力。
- 6×6 一侧依次驱动 C1…C6，R1…R6 各有独立 10kΩ 下拉并连接 ADC1–3 的六个 AIN。得到按 R1C1…R6C6 的 36 点相对响应；高阻未选列不能彻底消除串扰。
- ADC4 CS→GPIO32、DOUT→GPIO33，SCLK→GPIO18、DIN→GPIO23；前三颗 MISO 按用户确认的新版接线：ADC1/CS21/MISO34、ADC2/CS22/MISO35、ADC3/CS5/MISO26；旧固件配置须迁移并验证。
- 矩阵 C1..C6 驱动 GPIO 提议：4、13、14、25、27、19。GPIO32 专属 ADC4 CS。所有 ADC 与传感器使用旧 ESP 的 3.3V/GND，确保供电实测稳定；舵机单独供电。

## 2. 采集与执行优先级

**首要交付**：ADC4 两路 FSR 真实实时值 → Mac Dashboard LIVE → S3 PWM MANUAL → FSR 规则式 AUTO → 加水 Demo。矩阵属于辅助功能，若真实行列扫描出现鬼影、漂移或焊接困难，直接关闭矩阵保留 FSR-only。

软件存储以 `FSR_ONLY` 和 `HYBRID_6X6_FSR2` 两个 profile 区分；历史 12 通道单端采集、36 点扫描、38 逻辑值是三种不同语义，不能混用。完整接口见 [PROTOCOL_V2_PROPOSAL.md](PROTOCOL_V2_PROPOSAL.md)。

## 3. 最小实机确认

1. 以用户确认的 ADC1~3 CS/MISO 对应关系实施 V2 配置，并在本次实机验收时进行 SPI 读回测试；检查两片 FSR 各自独立分压，不让下拉电阻跨接两路。
2. 四 ADC 3.3V、地、CS 上拉、去耦和 ADC4 寄存器读回。
3. 只测试 FSR1、FSR2 的未按/轻按/夹杯/释放，保存原始值。
4. 三 ADC 矩阵逐列扫描单点与串扰验证，失败不阻断演示。
5. 两块 ESP USB 接 Mac，S3 单独操作舵机，最后才由 Python 连接并进入 AUTO。

## 4. 外部原始资料

- TI ADS1220：<https://www.ti.com/lit/ds/symlink/ads1220.pdf>
- ESP-IDF ESP32 GPIO：<https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/gpio.html>
