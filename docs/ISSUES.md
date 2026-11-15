# P2-S 已知问题与集成阻塞

更新：2026-11-15。协议仍为 **PROPOSED**；以下不是已冻结契约。

## 阻塞真实闭环的接口问题

1. **波特率不一致**：历史采集固件可能 921600，软件默认 115200。当前可由配置/
   `--sensor-baud` 指定，但实际设备值未确认。错误波特率会表现为无 HELLO/乱码，
   不能推断为无矩阵或无接触。
2. **HELLO/STATUS 查询未冻结**：当前接受顶层或 `channel_config.sensor_profile`，
   channel_config 优先；查询发送 `{"type":"QUERY","query":"HELLO"}` 或
   `{"type":"QUERY","query":"STATUS"}`，回复格式与超时未与硬件组确认。查询默认关闭。
3. **FSR 电压换算依据**：只有显式 `adc_reference_uv/adc_gain/adc_bits` 才显示电压。
   ADS1220 单端/差分、有符号计数、实际基准与增益未确认；未确认前不能把换算值当
   真实电压或力。
4. **FSR 极性与饱和**：按下通常使电压升高，但实际极性、饱和阈值、通道顺序
   （FSR_A/B）需硬件确认。当前只报告相对评分。
5. **矩阵映射/扫描**：`matrix_row/col` 到物理方位的对应、6×6 扫描率与串扰未验证；
   热图只按 HELLO 元数据绘制，不代表已标定触觉图。
6. **双设备身份**：S3 与采集板的 `device_id/boot_id/firmware_version` 是否稳定、
   何时发送 HELLO 未联合确认；当前分别记录，不能证明“同一 Trial 的两台设备”已
   经硬件同步。
7. **ACK 语义**：ACK 只表示命令回复，不是位置/夹持力/到位反馈。Trial 分开保存
   `pwm_command_id`、目标、ACK；`actual_pwm_us` 保持未知。
8. **真实 AUTO 签核**：`AUTO_REAL_ENABLED=False`， commissioning 入口当前必拒绝。
   需要协议冻结、硬件授权、FSR 标定、PWM 方向/范围、急停/失联策略与现场证据。
9. **12 电极 R/C→ADC/AIN 映射未确认**：用户确认 R1–R6 各经 10 kΩ 下拉到 GND、
   C1–C6 各经 1 kΩ 上拉到 3.3 V 并分别接 ADS1220 AIN，但未给出哪一路接哪个
   AIN/ADS1220/mux。当前 `MATRIX_ELECTRODES_12` 的 `adc_input`、`ads1220_id`、
   `mux_channel` 全部为 null，`electrode_index` 只是逻辑序号，不能当物理通道。
10. **12 电极 ≠ 36 压力点**：R/C 单端测量不是逐列激励的互电容/电阻矩阵，不能由
    12 路值推算 36 个独立压力点。软件只显示 12 路原始 ADC；热图、压力、接触评分
    均不可用，除非硬件组给出经过验证的扫描与标定方案。

## 当前实现的限制

- 阈值（0.10/0.20/0.45/0.80）是软件初始值，不是杯子/夹爪安全边界；1300 μs 与
  1270 μs 只是人工观察，不是自动限位。
- 相对评分依赖空载基线；杯子/夹爪重新装夹或设备重启后必须重采。真实数据不会
  自动采集基线。
- 仿真首次有效帧自动采集基线，标记 `SIMULATION_AUTO`；该路径不得用于真实 PWM。
- Trial 原始 SAMPLE 依赖设备/适配器提供 `raw`；旧 Trial 无 raw 时 REPLAY 用已验证
  字段重建，不能恢复未落盘的原始字节。
- `frames.jsonl` 直接 REPLAY 依赖同目录 `metadata.json` 的 `sensor_config`；手工
  移动文件会失去自动 HELLO。
- Dashboard 已完成 1440×900、1280×800、1920×1080 的 Live/Experiments/Analysis
  离线截图验收（`docs/screenshots/p2s-ui-audit/`），但仍是仿真数据；真实设备错误
  提示、长时间运行和交互路径需现场走查。
- 视觉验收保留的轻微不对称：Live 底部事件/记录卡高度由内容决定；分析页 7 列
  “控制事件”表在 ≤1440 px 使用卡片内横向滚动；实验历史表在 1280 px 内部滚动
  约 72 px。均不溢出卡片，未为此重排页面。

## 非目标

- 不新增页面、不重做 UI、不引入未标定的牛顿/摩擦系数。
- 不自动回中、扫描端点、重放旧运动，不自动开真实 AUTO。
