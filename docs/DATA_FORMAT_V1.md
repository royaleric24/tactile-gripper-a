# V1 Trial 数据格式

> P3-A：文档中的 Trial 容器仍适用。V2 的 `raw` 保留固件 SAMPLE 原文对象（含 uint32 μs 时间、
> `channel_flags` 和 ADC 状态），CSV 无效 `ch_N` 留空并保留 `valid_N=false`。
> REPLAY 导出附带从元数据生成的主机布局头；不把旧 36/38 通道记录解释为 V2 新采集。


日期：2026-11-13。当前写入 `schema_version=3`。无数据库服务器，全部为本地 JSON/JSONL/CSV。

现行单 FSR Trial 记录 `parameters.sensor.fsr_layout` 中的 FSR_A 通道 ID、ADC ID 和 AIN，
并在 `parameters.sensor_config` 保留完整布局。CSV 按原通道编号输出：1 通道仅 `ch_0`；
13 通道的 `ch_12` 为 FSR_A，12 根待映射电极的值留空。历史 2/14 通道继续按各自的布局读取。

## 1. 目录

| 来源 | 目录 | 写入 |
|---|---|---|
| SIMULATION | `data/simulated/trials/<TRIAL_ID>/` | 允许 |
| LIVE | `data/real/trials/<TRIAL_ID>/` | 允许（需真实授权） |
| REPLAY | 无 | 只读 |

Trial ID 形如 `T-YYYYmmdd-HHMMSS-<8 hex>`，创建时会检查目录唯一性。

## 2. 文件

```text
metadata.json      TrialMetadata
recording.json     录制锁（仅 RECORDING 时存在）
events.jsonl       CONTROL_EVENT / TRIAL_EVENT
frames.jsonl       SENSOR_FRAME
frames.csv         动态通道 CSV
```

`recording.json` 包含 `trial_id`、`pid`、`host`、`started_at`、`heartbeat_utc`、`heartbeat_ns`、`source`。用于判断进程异常结束；不参与回放控制。

## 3. metadata.json 主要字段

- `trial_id`, `name`, `source`, `mode`, `status`
- `created_at`, `started_at`, `ended_at`
- `schema_version`（新文件 3；缺失时按 1 读取）
- `software_version`、`protocol_version`
- `git_commit`（创建时 HEAD；不可用为 UNKNOWN）
- `write_error`、`video_path`、`operator`、`tags`
- `conditions`：人工录入，例如 `object`、`cup_type`、`material`、`water_mass_g`、`grasp_target`
- `parameters`：固件版本、PWM 范围、完整 `gripper_config`、`sensor_config`、环境信息
  （`sensor_config` 是 HELLO `channel_config` 的副本；`MATRIX_ELECTRODES_12` 时
  channels 含 `electrode_axis/electrode_index` 且不含 `matrix_row/col`）
- `counts`：frames/events/invalid/dropped/restarts 等
- `files`

`water_mass_g` 是操作员录入的质量/水量（克），不是从触觉推算出的夹持力。

## 4. 事件

`events.jsonl` 每行：

- `record_type="CONTROL_EVENT"`：控制命令、stage、ACK、serial_write_ok、actual_pwm_us、firmware_state、response、command_id。
- `record_type="TRIAL_EVENT"`：`TRIAL_START`、`TRIAL_STOP`、`TRIAL_INTERRUPTED`、`MARKER`、`NOTE`、`ANOMALY` 等。

`actual_pwm_us` 始终为 null；ACK 不是位置反馈。

## 5. 帧

`frames.jsonl` 每行包含：

`frame_seq`、`boot_id`、`mcu_time_us`、`host_received_ns`、`host_received_utc`、`source`、`channels`、`valid_mask`、`channel_ids`、`matrix_rows/cols`、`channel_count`、`valid_count`、`contact_score`、`schema_version`、`trial_id`。

12 电极 Trial 仍只有 12 个通道（`channel_ids` 0..11），`contact_score` 为 null；
不保存 36 点插值或压力推算。通道名称与逻辑轴/序号来自 metadata 的 `sensor_config`。

无效通道保持 null 或占位值 + `valid_mask=false`，不会当零接触。

## 6. 状态与恢复

| status | 含义 | complete |
|---|---|---|
| CREATED | 未开始 | 否 |
| RECORDING | 录制中 | 否 |
| COMPLETED | 正常 Stop | 是 |
| ABORTED | 操作员 Abort / shutdown | 否 |
| INTERRUPTED | 进程异常结束或锁缺失，已恢复 | 否 |
| ERROR | 帧/事件/锁写入失败 | 否 |

恢复时保留原 frames/events，追加 `TRIAL_INTERRUPTED`，设置 ended_at，重算 counts 并导出 CSV；不会标为 COMPLETED。

## 7. JSONL 尾行

写入总是以换行结束。读取时若最后一行没有换行且不是完整 JSON，会忽略该尾行并在 `read_errors`/`truncated_tail` 中报告；之前完整行保留。

## 8. CSV

`frames.csv` 保持动态列：

```text
frame_seq, boot_id, mcu_time_us, host_received_ns, host_received_utc,
source, contact_score, channel_count, valid_count,
ch_<id>, valid_<id>, ...
```

列不固定为 12/16/36，按该 Trial 实际通道并集生成。CSV 在停止/恢复/手动导出时生成。

## 9. 兼容性

- v1（无 schema_version）→ 读为 schema 1。
- v2 → 读为 2。
- v3 增加 video_path/operator/tags；旧字段不删除。
- 旧 Trial 可直接 `TrialStore.load()`；不需要数据库迁移。
- 不把未知字段静默写入控制逻辑；只保留显示/检索。

## 10. 完整性

Analysis 页面与 `trial_integrity()` 统计：无效通道样本、含无效通道的帧、丢帧、重复帧、重启、控制事件/ACK、故障、read errors、write error、截断尾行、录制锁、完成/中断状态。
