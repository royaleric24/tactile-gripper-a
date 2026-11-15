# 问题清单（硬件分支）

编号从 I-101 起。I-001..I-011 属于 `docs/demo-v2`（PR #1，未合入本分支），其中与本阶段直接相关的两条
在此按编号转述并保持原文语义，合并时再合并条目而不是重新编号。

## 转述（来自 docs/demo-v2，未合入）

- **I-003（OPEN）** ADC4 尚未接线。
- **I-006（OPEN）** 串口波特率不一致：固件 921600，软件旧模板 115200。

## 本分支新增

### I-101｜软件侧严格解析器仍硬编码 12 通道 / 3 ADC（OPEN，阻塞联调）

- 现象：`tools/tactile_acq/protocol.py` 的 `CHANNEL_COUNT = 12`、`ADC_COUNT = 3`，`parse_sample` /
  `parse_hello` 要求 12 通道与 3 个 `adc_status` 条目。FSR_ONLY 的 2 通道帧会被直接判错，
  HYBRID 的 38 通道帧同样被拒。
- 影响：软件组无法用现有解析器消费 V2 帧；目前只能参考 `tools/fsr2/protocol_v2.py`。
- 建议：按 `sensor_profile` 取通道数与 ADC 数量（FSR_ONLY 2/4、HYBRID 38/4、V1 12/3），
  保留旧路径；复用 `protocol_v2` 的 null/valid 语义。
- 负责人：软件组。

### I-102｜四颗 ADS1220 共用 bit-bang SCLK/MOSI 的真实时序未验证（OPEN）

- 现状：host 模拟按理想 SPI 行为建模，未建模 MISO 竞争、走线容性、器件间 CS 建立/保持差异。
- 风险：ADC1–3 与 ADC4 共用总线时，若 MISO 在 CS 拉高后仍被驱动，可能出现串扰读错。
- 需要：逻辑分析仪抓 SCLK/MOSI/各 CS/各 MISO，确认 CS 拉高到下一次传输之间的三态时间。
- 只读证据：离线编译与仿真不能替代。

### I-103｜FSR 分压取值与极性未标定（OPEN）

- 现状：10 kΩ 下拉、3.3 V 激励、`VOLTAGE_RISES_WITH_FORCE` 均为首轮设计值，尚未实测。
- 待做：空载/轻压/重压各记录 counts，换算 AVDD 实测值；必要时比较 4.7 kΩ / 10 kΩ / 47 kΩ。
- 约束：没有独立标定前只能报告 ADC counts，禁止换算成牛顿。

### I-104｜命令层仅编译通过，未逐命令验证（OPEN）

- 现状：`.ino` 的 ArduinoJson 命令解析编译通过，但 host 仿真不覆盖串口解析路径，
  也没有真实串口会话记录。
- 待做：实机按 `docs/hardware/FSR_ONLY_INTERFACE_V2.md` §11 第 6 步逐条执行 PING/STATUS/
  STREAM/STOP/RESET_ADC/VERIFY_CONFIG，并保存原始应答。

### I-105｜两套文档基线并行（OPEN，流程）

- `docs/demo-v2`（PR #1）含 V2 计划、接线冻结、协议提案、进度/问题/交接；本分支只新增硬件范围内的
  同名文件并引用其条目，未复制其内容。
- 合并 PR #1 时需要：以 demo-v2 的 I-001..I-011 为主干，把本文件 I-101 起并入；确认引脚、
  波特率、null 语义三处不产生分叉。

### I-106｜压敏布接线由"6 列 GPIO 扫描"更正为"12 电极被动读数"（OPEN，现场复核）

- 事实：R1–R6 各接一个 ADS1220 AIN + 各自 10 kΩ 下拉 GND；C1–C6 各接一个 AIN + 各自 1 kΩ 上拉
  3.3 V；无 GPIO 列驱动、无 HI_Z、无 36 点扫描。
- 已做：固件/配置/解析器/文档全部改为 `MATRIX_ELECTRODES_12`，删除 GPIO 列激励代码。
- 待做：现场按接口文档 §11/§12 核对焊接，填写电极映射表；确认 12 根电极的偏置电阻实际装配。

### I-107｜R/C → ADC/AIN 映射缺失（OPEN，阻塞电极读数）

- 现状：配置 `electrodes.map = []`、`mapping_status = PENDING_REAL_WIRING`；12 个通道在 SAMPLE
  中固定为 `null` + `NO_DATA`。
- 影响：无法判断 12 路电极电压，也无法做任何空间/位置相关分析。
- 下一步：按 `docs/hardware/FSR_ONLY_INTERFACE_V2.md` §12 填表 → 填 `map` → 改
  `mapping_status = TABLE_PROVIDED` → 重新生成头文件并编译。禁止猜测或按行优先"示例"填充。

### I-108｜12 路电极电压不能代表 36 个压力点（ACCEPTED_LIMITATION）

- 12 根电极是 12 个电位节点，不是 36 个独立测量单元。界面/分析/报告都不得把 12 通道渲染成
  6×6 热图或宣称 36 点已测；`matrix_rows/cols` 恒为 `null`，解析器拒绝旧的 38 通道 HYBRID 帧。

### I-109｜HYBRID_6X6_FSR2 已封存（OPEN，流程）

- 旧 profile/配置/头文件/fixtures 已从本分支删除（仍可在 git 历史 2026-11-14 提交中查看）。
- 生成器对 `HYBRID_6X6_FSR2` 报错；参考解析器报 `PROFILE_HISTORICAL`；软件若仍缓存旧 fixture，
  升级时必须删除，不能把 36 通道帧当当前数据。

### I-110｜合成电极映射只用于测试（OPEN，流程）

- `tools/fsr2_sim/electrode_test_profile.h` 的 `SIM_SYNTHETIC_MAPPING` 与对应 fixture 仅用于验证
  "映射齐全时读数正确"的代码路径。它不是真实接线，不得作为配置模板或验收证据。

### I-111｜命令层仍仅编译验证（继承 I-104）

- 12 电极 profile 的 `.ino` 命令面与之前相同（PING/HELLO/STATUS/STREAM/STOP/RESET_ADC/
  VERIFY_CONFIG），仍未逐命令实测；实机验收步骤见接口文档 §11。
