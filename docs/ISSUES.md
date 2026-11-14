# P2-S 已知问题与集成阻塞

更新：2026-11-14。协议仍为 **PROPOSED**；以下不是已冻结契约。

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
- Dashboard 只做了路由/服务启动验证，未做逐像素/交互视觉验收；真实设备错误提示
  需现场走查。

## 非目标

- 不新增页面、不重做 UI、不引入未标定的牛顿/摩擦系数。
- 不自动回中、扫描端点、重放旧运动，不自动开真实 AUTO。
