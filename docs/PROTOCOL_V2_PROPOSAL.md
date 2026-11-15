# 混合传感器软硬件协议 V2（增量兼容提案）

**本文保存设计提案。当前实现以 [V2 接口契约](INTERFACE_CONTRACT.md) 开头的 P3-A 表为准；真实 HELLO/SAMPLE 验收尚未执行。**

> **修正（2026-11-15，项目所有者确认）**：真实压敏布是 **12 根电极被动读取**（R1–R6 / C1–C6 各占一个 ADS1220 单端输入，无 GPIO 列激励、无 HI_Z、无 36 点扫描）。本提案据此新增 `MATRIX_ELECTRODES_12` 提案 profile，并把 `HYBRID_6X6_FSR2` 撤回为 HISTORICAL；物理电极 → ADC/AIN 映射 **PENDING_REAL_WIRING**，协议字段填 `null`/给状态值，不写示例编号。见 [WIRING_FREEZE_V2.md](WIRING_FREEZE_V2.md)。

> P3-A 已使用固件生成的现行 1/12/13 路及历史 2/14 路样例联调 Dashboard；本文件的 YAML 是设计示意，不能代替固件实际帧。

## 1. 目标与向后兼容

- 优先沿用当前传感器协议 `protocol_version=1`、每行 JSONL、`HELLO`/`SAMPLE`/`STATUS`/`ERROR`、`device_id`、`boot_id`、`frame_seq`、`mcu_time_us`、`channels`、`valid_mask`、`channel_config`，减少重写。
- 新增**可选、向后兼容**的字段 `sensor_profile`、`sensor_kind`、`fsr_layout`、`electrode_layout` 等；软件端根据真实 `channel_config` 渲染，不硬编码 2/12/14（历史文档中的 36/38 属已撤回的 HYBRID 语义，不得按它渲染）。
- 不能保证新旧版本兼容时，应显式升级协议号、加转换器与双向测试，而不是静默把旧数据当新数据。

## 2. 可交付的硬件 profile

| profile | 内容 | 状态 / 何时使用 |
|---|---|---|
| `FSR_ONLY` | FSR_A（ADC4 AIN0/MUX8）；旧 2 路仅离线兼容 | **当前唯一可用的推荐最短路径** |
| `MATRIX_ELECTRODES_12` | 12 个电极逻辑通道（R1..R6 后接 C1..C6）+ 可选 FSR_A 的 13 通道变体，旧 14 路仅离线兼容 | **PROPOSED**；面向真实布料的被动 12 电极读取，映射 PENDING，未验证 |
| `HYBRID_6X6_FSR2` | 36 个“扫描单元” + 2 FSR | **HISTORICAL / 已撤回**；依赖不存在的 GPIO 列激励，真实布料不可用，不得烧录 |

真实压敏布共 12 个被动单端测量值。P3-A 验证了 1/12/13 通道离线路径，兼容历史 2/14。独立 36 格仿真直接生成格值，现场优先验证 FSR_ONLY 的单 FSR_A。

### 2.1 `MATRIX_ELECTRODES_12` 提案细则

- `channel_config.matrix_rows = null`、`matrix_cols = null`（不存在行列交点语义）；`sensor_kind = ELECTRODE`。
- 12 个逻辑通道按**协议固定顺序** `channel_id 0..11`：`0..5 = R1..R6`，`6..11 = C1..C6`。**这是协议顺序，不是物理映射**；每根电极实际进哪颗 ADC 的哪个 AIN 由真实焊接记录填写，当前 `mapping_status: "PENDING_REAL_WIRING"`、`validated: false`。填表前对应通道的 `ads1220_id`/`adc_input` 为 `null`，不得猜测或按行优先假设。
- `electrode_layout` 对象：`{count: 12, rows: 6, columns: 6, row_bias: "PULLDOWN_10K_TO_GND", column_bias: "PULLUP_1K_TO_3V3", mapping_status: "PENDING_REAL_WIRING", gpio_excitation: false, validated: false, channels: [...]}`（字段名与取值已由硬件组固件实现固定：偏置字符串使用 `PULLDOWN_10K_TO_GND` / `PULLUP_1K_TO_3V3`；映射完整后 `mapping_status` 改为 `TABLE_PROVIDED`；`gpio_excitation` 恒为 false，明确不存在 GPIO 列驱动）。
- 电极通道**不得**带 `matrix_row`/`matrix_col`（与 FSR 一样为 `null`）；也不得命名为 `RrCc` 交点。
- `SAMPLE.channels` 与 `valid_mask` 长度为 12 或 13（历史 14），顺序与 HELLO 一致；坏点 `null` 且 `valid=false`，**不得用 0 代替无效值**。

## 3. 建议编码与 UI 消费规则

- `HELLO.channel_config.channels` 中每个逻辑值有唯一 `channel_id`、`sensor_kind`（`ELECTRODE` / `FSR`；`MATRIX_CELL` 仅属已撤回的 HYBRID）、`ads1220_id`、`adc_input`、有效标志；电极与 FSR 通道的 `matrix_row`、`matrix_col` 均为 `null`。
- `FSR_ONLY`：现行 `0=FSR_A`；历史双 FSR 才有 `1=FSR_B`，`matrix_rows/cols=null`，`sensor_kind=FSR`。
- `MATRIX_ELECTRODES_12`：见 §2.1；12 通道固定为 R1..R6 再接 C1..C6，`sensor_kind=ELECTRODE`，`matrix_rows/cols=null`，`electrode_layout.mapping_status="PENDING_REAL_WIRING"`，`validated=false`。这些编号是协议顺序，最终以 HELLO 报告的实际配置为准。
- `HYBRID_6X6_FSR2`：**HISTORICAL / 已撤回**，仅保留字段形状供历史回放识别；不得在真实布料上产生帧，也不得把其 36 个逻辑值展示为 36 个实测压力点。
- `SAMPLE.channels` 与 `valid_mask` 的长度必须与配置中通道数一致，坏点输出 `null` 且 `valid=false`；帧里不能把无效值替换成 0。
- 电极与 FSR 是不同时刻/不同通道的读取；保留 `mcu_time_us` 和可选每组采样时间，不能默认为所有通道严格同一时刻采集。
- 现有软件 `ChannelConfiguration.expected_channel_count` 是 `len(channels)`；12、13 及历史 14 项逻辑通道均保留。热力图从 `channel_id` 推导行列的旧逻辑**不适用于电极**（无行列交点），电极应渲染为电压列表/条；13 通道中电极图与 FSR_A 卡片分开显示。
- 现有 AUTO 要求 `contact_score` 且 `AUTO_REAL_ENABLED=False`。软件组应新增基于 FSR 质量/归一化的 `contact_score` 派生逻辑和独立 real-auto 联调门控；**不能因解析成功就直接开启 AUTO**。

## 4. 示例：结构示意（非设备实测 JSON，不直接向设备发送）

`MATRIX_ELECTRODES_12` 提案帧（12 逻辑通道；`ads1220_id`/`adc_input` 在映射表填全前保持 `null`，不得填示例编号）：

```yaml
HELLO:
  protocol_version: 1
  type: HELLO
  sensor_profile: MATRIX_ELECTRODES_12
  channel_config:
    matrix_rows: null
    matrix_cols: null
    adc_count: 4
    scan_mode: PASSIVE_12_ELECTRODE
    electrode_layout: {count: 12, rows: 6, columns: 6, row_bias: "PULLDOWN_10K_TO_GND", column_bias: "PULLUP_1K_TO_3V3", mapping_status: "PENDING_REAL_WIRING", gpio_excitation: false, validated: false}
    channels:
      - {channel_id: 0, sensor_kind: ELECTRODE, name: R1, matrix_row: null, matrix_col: null, ads1220_id: null, adc_input: null}
      # channel_id 1..11 = R2..R6、C1..C6，按同一形状生成；映射来自真实接线记录
SAMPLE:
  type: SAMPLE
  frame_seq: incrementing
  channels: 12 values in exact HELLO order
  valid_mask: 12 booleans
```

`FSR_ONLY` 当前帧的 `channels` 和 `valid_mask` 均为 1 项，`channel_id 0=FSR_A`，`sensor_kind=FSR`。HELLO、SAMPLE 与 STATUS 的布局须一致。完整真实样例必须由硬件组从本次固件生成并脱敏保存到 `tests/fixtures/`，不能从这段伪数据宣称已经联通。

## 5. 串口与实时控制最小要求

- 采集设备与 S3 控制设备走 Mac 的**两个独立串口**，分别握手、识别真实 board_id/firmware/version，不把一个端口当另一个端口。
- V2 采集固件与集成 Dashboard 默认统一为 `921600` 8N1，实际吞吐和 USB 桥留待现场验证。
- 设备接收端提供 `HELLO` 及足够的再次查询机制（如 `STATUS`），避免 Mac 错过上电 HELLO 后无法获得配置。
- 主机记录「设备采样时间」「Mac 收到帧时间」「Mac 发送 PWM」「S3 回复」；不要求一开始做复杂时钟同步，但需计算帧新鲜度并拒绝陈旧样本驱动动作。
- 无效 FSR、失联、帧长错、超时：不再自动夹紧，明确提示降级 MANUAL/FAULT；先保证不会因坏数据持续收紧。

## 6. 必要的集成测试

1. FSR-only HELLO + 2通道 SAMPLE：解析、展示、录制、CSV、REPLAY。
2. `MATRIX_ELECTRODES_12` HELLO + 12 通道 SAMPLE：电极按电压列表展示（不画 36 点热图）、`mapping_status=PENDING_REAL_WIRING` 与 `validated=false` 原样透出、坏点 `null`。
3. 历史 `HYBRID_6X6_FSR2` 帧：仅用于历史回放识别，软件必须拒绝把它当当前可用 profile（不发起真实采集、不渲染成 36 个实测点）。
4. 错波特率、缺失 `HELLO`、错位/短帧、`null`、ADC4 故障、重启、旧帧与串口掉线。
5. 真实控制从 `sensor_frame_seq → decision → PWM request_id → S3 ACK` 保留可追溯关系。

## 7. 冻结决策（硬件组和软件组只需确认一次）

`sensor_profile`、最终通道顺序、**12 电极 → ADC/AIN 物理映射（当前 PENDING_REAL_WIRING，须由焊接记录填写）**、FSR 极性/单位、ADC4 实物接线、真实波特率、最大帧长度、最大采样间隔、设备身份、何时生成 HELLO。**前三颗 MISO 的设计映射已由用户确认：ADC1→34、ADC2→35、ADC3→26；仍需固件迁移后的真实通信测试。**确定后更新唯一正式 `INTERFACE_CONTRACT.md`，停止维护两个相互冲突的规范。

## 8. V2 电气设计基准（施工未验证）

2026-11-15 修正后：压敏布为**纯被动 12 电极**——每个 R 电极独立接一颗 ADS1220 的 AIN 并各有一颗 10 kΩ 下拉到 GND；每个 C 电极独立接一颗 ADS1220 的 AIN 并各有一颗 1 kΩ 上拉到 3.3 V；**无 GPIO 列激励、无 HI_Z、无 36 点扫描**。唯一现行 FSR_A 为 ADC4 AIN0，设计为 10 kΩ 下拉，AIN1 上损坏 FSR_B 的物理隔离尚未确认。GPIO32=CS4、GPIO33=MISO4；电极 → ADC/AIN 的物理映射 **PENDING_REAL_WIRING**，详见 [WIRING_FREEZE_V2.md](WIRING_FREEZE_V2.md) §4.1。旧 ADC1–3 的 MISO **按用户确认的新图**：ADC1=GPIO34、ADC2=GPIO35、ADC3=GPIO26；旧硬件分支现存配置与此不同，必须迁移后再做真实 SPI 验证。原“六列 GPIO 激励 + 36 点矩阵”电气基准已被 2026-11-15 修正取代（HISTORICAL）。
