# 混合传感器软硬件协议 V2（增量兼容提案）

**状态：PROPOSED。双方确认并通过真实 HELLO/SAMPLE 测试后再取代现有 `docs/INTERFACE_CONTRACT.md`。不要未经联调就假设已冻结。**

> 包内对现有软件模型、热图和 AUTO 开关的描述指软件组分支，并非 main 已含这些模块；本轮未运行 V2 解析或控制测试。

## 1. 目标与向后兼容

- 优先沿用当前传感器协议 `protocol_version=1`、每行 JSONL、`HELLO`/`SAMPLE`/`STATUS`/`ERROR`、`device_id`、`boot_id`、`frame_seq`、`mcu_time_us`、`channels`、`valid_mask`、`channel_config`，减少重写。
- 新增**可选、向后兼容**的字段 `sensor_profile`、`sensor_kind`、`fsr_layout` 等；软件端根据真实 `channel_config` 渲染，不硬编码 12/36/38。
- 不能保证新旧版本兼容时，应显式升级协议号、加转换器与双向测试，而不是静默把旧数据当新数据。

## 2. 两种可交付的硬件 profile

| profile | 内容 | 何时使用 |
|---|---|---|
| `FSR_ONLY` | 2 个 FSR 通道；未装或暂不用矩阵 | **首个真实闭环的推荐最短路径** |
| `HYBRID_6X6_FSR2` | 36 个真实扫描单元 + 2 FSR，理论上 38 个逻辑测量值 | 行列扫描完成实测、36 点映射有效之后 |

**物理 ADC 输入数、矩阵单元数、逻辑采样值个数不是同一个量。** 对于 HYBRID，ADC1-3 只用 6 路行 AIN，但随着 6 列轮流选通，输出 36 个逻辑位置测量；ADC4 输出 2 个 FSR 值。

## 3. 建议编码与 UI 消费规则

- `HELLO.channel_config.channels` 中每个逻辑值有唯一 `channel_id`、`sensor_kind`（`MATRIX_CELL` / `FSR`）、`ads1220_id`、`adc_input`、有效标志；矩阵通道额外有零起始 `matrix_row`、`matrix_col`；FSR 的这两个字段均为 `null`。
- `FSR_ONLY`：推荐通道 `0=FSR_A`、`1=FSR_B`，`matrix_rows/cols=null`。
- `HYBRID_6X6_FSR2`：推荐 `0..35` 按 R1C1 到 R6C6 行优先排序，`36=FSR_A`、`37=FSR_B`，`matrix_rows=6`、`matrix_cols=6`。这些编号是**提案**，最终以 HELLO 报告的实际映射为准。
- `SAMPLE.channels` 与 `valid_mask` 的长度必须与配置中通道数一致，坏点输出 `null` 且 `valid=false`；帧里不能把无效值替换成 0。
- FSR 与矩阵扫描先后不同；保留 `mcu_time_us` 和可选每组/每点采样时间，不能默认为 38 项严格同一时刻采集。
- 现有软件 `ChannelConfiguration.expected_channel_count` 是 `len(channels)`；38 项逻辑通道模型可表达。但现有热力图从 `channel_id` 推导行列，暂只适合 0..35 为矩阵的布局；**未来重排通道或采用非连续 ID 时须改热图使用 `matrix_row/col` 元数据**。
- 现有 AUTO 要求 `contact_score` 且 `AUTO_REAL_ENABLED=False`。软件组应新增基于 FSR 质量/归一化的 `contact_score` 派生逻辑和独立 real-auto 联调门控；**不能因解析成功就直接开启 AUTO**。

## 4. 示例：结构示意（非设备实测 JSON，不直接向设备发送）

```yaml
HELLO:
  protocol_version: 1
  type: HELLO
  sensor_profile: HYBRID_6X6_FSR2
  channel_config:
    matrix_rows: 6
    matrix_cols: 6
    adc_count: 4
    scan_mode: COLUMN_SCAN_6X6_PLUS_FSR2
    channels:
      - {channel_id: 0, sensor_kind: MATRIX_CELL, matrix_row: 0, matrix_col: 0, ads1220_id: 1, adc_input: 0}
      # 其余矩阵点 1..35 必须按真实行列生成、逐一映射
      - {channel_id: 36, sensor_kind: FSR, name: FSR_A, matrix_row: null, matrix_col: null, ads1220_id: 4, adc_input: 0}
      - {channel_id: 37, sensor_kind: FSR, name: FSR_B, matrix_row: null, matrix_col: null, ads1220_id: 4, adc_input: 1}
SAMPLE:
  type: SAMPLE
  frame_seq: incrementing
  channels: 38 values in exact HELLO order
  valid_mask: 38 booleans
```

完整真实样例必须由硬件组从本次固件生成并脱敏保存到 `tests/fixtures/`，不能从这段伪数据宣称已经联通。

## 5. 串口与实时控制最小要求

- 采集设备与 S3 控制设备走 Mac 的**两个独立串口**，分别握手、识别真实 board_id/firmware/version，不把一个端口当另一个端口。
- 旧 ESP32 固件历史使用 `921600` baud，而软件旧模板使用 `115200` baud。优先更新软件运行时配置与测试为设备实际值，再考虑统一固件；不要两个组各改一半。
- 设备接收端提供 `HELLO` 及足够的再次查询机制（如 `STATUS`），避免 Mac 错过上电 HELLO 后无法获得配置。
- 主机记录「设备采样时间」「Mac 收到帧时间」「Mac 发送 PWM」「S3 回复」；不要求一开始做复杂时钟同步，但需计算帧新鲜度并拒绝陈旧样本驱动动作。
- 无效 FSR、失联、帧长错、超时：不再自动夹紧，明确提示降级 MANUAL/FAULT；先保证不会因坏数据持续收紧。

## 6. 必要的集成测试

1. FSR-only HELLO + 2通道 SAMPLE：解析、展示、录制、CSV、REPLAY。
2. HYBRID HELLO + 38通道 SAMPLE：热图只绘 36 个矩阵点，FSR_A/B 独立显示。
3. 错波特率、缺失 `HELLO`、错位/短帧、`null`、ADC4 故障、重启、旧帧与串口掉线。
4. 真实控制从 `sensor_frame_seq → decision → PWM request_id → S3 ACK` 保留可追溯关系。

## 7. 冻结决策（硬件组和软件组只需确认一次）

`sensor_profile`、最终通道顺序、FSR 极性/单位、ADC4 实物接线、真实波特率、最大帧长度、最大采样间隔、设备身份、何时生成 HELLO。**前三颗 MISO 的设计映射已由用户确认：ADC1→34、ADC2→35、ADC3→26；仍需固件迁移后的真实通信测试。**确定后更新唯一正式 `INTERFACE_CONTRACT.md`，停止维护两个相互冲突的规范。

## 8. V2 电气设计基准（施工未验证）

本版选定六列 GPIO 逐列激励、六行各自 10kΩ 下拉并由 ADC1–3 AIN0/1 测量。FSR1/FSR2 为 ADC4 AIN0/AIN1，各自 10kΩ 下拉，**两路分压节点不互连**。GPIO32=CS4、GPIO33=MISO4，原矩阵的 GPIO32 行驱动不再使用。物理映射详见 [WIRING_FREEZE_V2.md](WIRING_FREEZE_V2.md)；旧 ADC1–3 的 MISO **按用户确认的新图**：ADC1=GPIO34、ADC2=GPIO35、ADC3=GPIO26；旧硬件分支现存配置与此不同，必须迁移后再做真实 SPI 验证。
