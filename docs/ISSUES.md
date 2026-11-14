# 问题清单（硬件分支）

编号从 I-012 起。I-001..I-011 属于 `docs/demo-v2`（PR #1，未合入本分支），其中与本阶段直接相关的两条
在此按编号转述并保持原文语义，合并时再合并条目而不是重新编号。

## 转述（来自 docs/demo-v2，未合入）

- **I-003（OPEN）** ADC4 尚未接线。
- **I-006（OPEN）** 串口波特率不一致：固件 921600，软件旧模板 115200。

## 本分支新增

### I-012｜软件侧严格解析器仍硬编码 12 通道 / 3 ADC（OPEN，阻塞联调）

- 现象：`tools/tactile_acq/protocol.py` 的 `CHANNEL_COUNT = 12`、`ADC_COUNT = 3`，`parse_sample` /
  `parse_hello` 要求 12 通道与 3 个 `adc_status` 条目。FSR_ONLY 的 2 通道帧会被直接判错，
  HYBRID 的 38 通道帧同样被拒。
- 影响：软件组无法用现有解析器消费 V2 帧；目前只能参考 `tools/fsr2/protocol_v2.py`。
- 建议：按 `sensor_profile` 取通道数与 ADC 数量（FSR_ONLY 2/4、HYBRID 38/4、V1 12/3），
  保留旧路径；复用 `protocol_v2` 的 null/valid 语义。
- 负责人：软件组。

### I-013｜四颗 ADS1220 共用 bit-bang SCLK/MOSI 的真实时序未验证（OPEN）

- 现状：host 模拟按理想 SPI 行为建模，未建模 MISO 竞争、走线容性、器件间 CS 建立/保持差异。
- 风险：ADC1–3 与 ADC4 共用总线时，若 MISO 在 CS 拉高后仍被驱动，可能出现串扰读错。
- 需要：逻辑分析仪抓 SCLK/MOSI/各 CS/各 MISO，确认 CS 拉高到下一次传输之间的三态时间。
- 只读证据：离线编译与仿真不能替代。

### I-014｜FSR 分压取值与极性未标定（OPEN）

- 现状：10 kΩ 下拉、3.3 V 激励、`VOLTAGE_RISES_WITH_FORCE` 均为首轮设计值，尚未实测。
- 待做：空载/轻压/重压各记录 counts，换算 AVDD 实测值；必要时比较 4.7 kΩ / 10 kΩ / 47 kΩ。
- 约束：没有独立标定前只能报告 ADC counts，禁止换算成牛顿。

### I-015｜命令层仅编译通过，未逐命令验证（OPEN）

- 现状：`.ino` 的 ArduinoJson 命令解析编译通过，但 host 仿真不覆盖串口解析路径，
  也没有真实串口会话记录。
- 待做：实机按 `docs/hardware/FSR_ONLY_INTERFACE_V2.md` §11 第 6 步逐条执行 PING/STATUS/
  STREAM/STOP/RESET_ADC/VERIFY_CONFIG，并保存原始应答。

### I-016｜两套文档基线并行（OPEN，流程）

- `docs/demo-v2`（PR #1）含 V2 计划、接线冻结、协议提案、进度/问题/交接；本分支只新增硬件范围内的
  同名文件并引用其条目，未复制其内容。
- 合并 PR #1 时需要：以 demo-v2 的 I-001..I-011 为主干，把本文件 I-012 起并入；确认引脚、
  波特率、null 语义三处不产生分叉。
