# 硬件联调前置条件与接口清单（软件 V1.0）

日期：2026-11-13。软件侧当前状态：**OFFLINE_FEATURE_COMPLETE**，真实传感器/真实自动控制 **BLOCKED_BY_HARDWARE / NOT_TESTED**。

## 1. 真实接入前必须满足

- [ ] 传感器采集固件与协议版本已由硬件组确认；共享契约仍为 `PROPOSED v0.1`。
- [ ] 实际扫描方式、6×6 单元数量、三颗 ADS1220 连接、SPI/复用结构有原理图/照片/说明。
- [ ] 扫描通道数 N 与矩阵单元数（目标 36）的关系明确；不得假定二者相等。
- [ ] 每个扫描通道的 ADC 物理输入、ADS1220/复用通道、矩阵位置映射明确。
- [ ] 采样率、整帧周期、抖动、切换/建立时间、丢帧定义明确。
- [ ] `boot_id`、`frame_seq` 起点/回绕/重启规则明确。
- [ ] MCU 时间戳单位、原点、是否含睡眠时间明确。
- [ ] 无效通道线值（null/占位）与部分有效帧策略明确。
- [ ] 传感器串口介质、波特率、端口、DTR/RTS 复位行为、boot wait 明确。
- [ ] 独立供电、电平/共地、限位、负载支撑、人工断电方式确认。
- [ ] PWM 方向、安全范围、机械停止/保持/释放行为经实测确认。
- [ ] 触觉标定方法、基线、阈值、材料差异有实测数据；不能用 ADC 推断摩擦力/重量/滑移。
- [ ] 真实窗口、操作员、停止方案和逐次授权流程确定。

## 2. 最小 HELLO 字段

```json
{"protocol_version":1,"type":"HELLO","device_id":"...","boot_id":"...",
 "firmware_version":"...","scan_mode":"...","sample_rate_hz":null,
 "channel_config":{"status":"PROPOSED","matrix_rows":null,"matrix_cols":null,
   "adc_count":null,"scan_mode":"UNKNOWN","channels":[
     {"channel_id":0,"adc_input":null,"ads1220_id":null,"mux_channel":null,
      "matrix_row":null,"matrix_col":null,"enabled":true,"unit":"ADC_COUNTS"}]}}
```

## 3. 最小 SAMPLE 字段

```json
{"protocol_version":1,"type":"SAMPLE","device_id":"...","boot_id":"...",
 "frame_seq":1,"mcu_time_us":1000,"channels":[812,806,null,799],
 "valid_mask":[true,true,false,true],"channel_ids":[0,1,2,3],"contact_score":null}
```

- `channels` 长度 = `channel_config.channels` 长度。
- 无效通道必须由 `valid_mask=false` 明确标出；软件不把占位值当测量值。
- `contact_score` 缺失时，AUTO 不得推断接触。
- 详见 [协议协作说明](PROTOCOL_COLLABORATION.md) 与 [INTERFACE_CONTRACT](INTERFACE_CONTRACT.md)。

## 4. 仍未确认的 C-01..C-18（摘要）

| 组 | 问题 |
|---|---|
| 物理/扫描 | C-01 通道/矩阵映射；C-02 扫描/复用；C-03 ADS1220 连接 |
| 时序 | C-04 采样率/整帧周期/抖动；C-17 传感器心跳/超时 |
| 数据质量 | C-05 有效性/部分有效帧；C-11 原始值单位/基线/标定 |
| 帧/时间 | C-06 序号回绕/重启；C-07 MCU 时间；C-18 boot_id |
| 传输/版本 | C-08 错误码/CRC/重试；C-09 版本兼容；C-10 传输介质/编码 |
| 主机 | C-12 控制命令/ACK/到位/STOP；C-13 HELLO 配置；C-14 无效通道线值；C-15 contact_score；C-16 传感器与 S3 是否同 MCU/串口 |

## 5. 真实接入顺序（需授权）

1. **只读**枚举/确认串口，不发送探测字节、不打开 PWM。
2. 只读传感器采样，核对 HELLO/SAMPLE、通道映射、时间戳、丢帧、重连。
3. 只读 S3 `GET_STATUS`，确认固件版本、DISARMED、FAULT/输出状态。
4. 经单独授权，建立 `BEGIN_BENCH` 与一次 `BENCH_HOLD`；记录 ACK、STOP、DISARM、超时差异。
5. 外部测量/观察位置与停止行为；STOP/保持/释放均标 NOT_TESTED 直到实测。
6. 完成触觉标定和真实安全范围后，才讨论 AUTO；AUTO 仍受协议、真实传感器、标定、授权门槛。

## 6. 软件当前可做的边界

- 已实现：传感器串口 transport（只读）、HELLO/SAMPLE 解析、重连、Dashboard 展示、Trial 记录、回放/对比、AUTO 规则离线框架。
- 未实现/不可用：真实传感器协议确认、真实 AUTO、真实 PWM 运动、真实闭环 Trial、视频编辑/流媒体。
- `BLOCKED_BY_HARDWARE`：真实扫描映射、采样性能、标定、机械安全范围与停止行为。
