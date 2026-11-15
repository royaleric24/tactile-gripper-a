# Mac 采集工具（硬件组）

真实 12 通道 ADS1220 串口采集、校验、记录与实时监视。**不使用随机数或模拟数据冒充真实采样。**

## 1. 环境

```bash
cd /home/example/Developer/research/tactile-gripper-a-hw
UV_CACHE_DIR=$PWD/.cache/uv uv venv --python 3.9 .venv
UV_CACHE_DIR=$PWD/.cache/uv uv pip install --python .venv/bin/python pyserial==3.5
```

绘图可选（不安装也能用终端监视）：

```bash
UV_CACHE_DIR=$PWD/.cache/uv uv pip install --python .venv/bin/python matplotlib
```

## 2. 列出、识别、诊断

```bash
.venv/bin/python -m tools.tactile_acq list
.venv/bin/python -m tools.tactile_acq identify --port /dev/cu.usbserial-XXXX
.venv/bin/python -m tools.tactile_acq diag --port /dev/cu.usbserial-XXXX
```

- `list` 只枚举端口；`CANDIDATE=yes` 表示 USB 串口，不代表身份。
- `identify` 发送 `STATUS`（只读识别），要求 `firmware_version` 以 `tactile-sense-` 开头、12 通道，否则拒绝。
- `diag` 让固件读取三颗 ADC 配置、写入并读回两组不同配置、做内部短接/AVDD 监测/温度转换、读取 12 路，结果保存到 `evidence/sensor/diagnostics_*.json`。
- 端口选择：`--port` 省略时只在“恰好一个 USB 串口候选”时自动选择；有多个候选会报错并要求显式指定，避免把 S3 当成旧 ESP32。

## 3. 连续采集

```bash
# 60 秒，终端 12 路监视，自动保存
.venv/bin/python -m tools.tactile_acq run \
  --port /dev/cu.usbserial-XXXX \
  --duration 60 \
  --monitor text

# 实时曲线（需要 matplotlib/Tk）
.venv/bin/python -m tools.tactile_acq run \
  --port /dev/cu.usbserial-XXXX \
  --duration 60 \
  --monitor plot

# 指定输出目录；Ctrl+C 安全退出
.venv/bin/python -m tools.tactile_acq run \
  --port /dev/cu.usbserial-XXXX \
  --out data/real/tactile/press_test_01
```

- `--duration 0`（默认）表示一直采集到 Ctrl+C。
- `--monitor none|text|plot`；非 TTY 默认 none。
- `--baud` 默认读取 `config/sensor_esp32.json`（921600）。
- `--expect-device-id tactile-esp32-01` 可额外锁定设备。
- 程序不自动重连，不把不同会话的数据拼接；断线显示 `DISCONNECTED` 并以非零码退出。
- 结束时会发送 `STREAM false`（仅在已完成设备身份确认后），再关闭串口；文件已 flush + fsync。

## 4. 输出文件

每次运行创建 `data/real/tactile/<UTC 时间>_<端口>/`：

| 文件 | 内容 |
|---|---|
| `raw_frames.jsonl` | 设备原始 JSONL 行（含 SAMPLE/HELLO/STATUS/ERROR，原样） |
| `samples.csv` | 每个 SAMPLE 一行：`frame_seq`、设备 `timestamp_us`、Mac 接收 Unix ns/ISO/monotonic、`ch0..ch11`、`valid0..valid11`、`flag0..flag11`、参考、帧率、三颗 ADC 状态 |
| `events.jsonl` | HELLO/STATUS/ERROR 及 Mac 接收时间、原始消息 |
| `meta.json` | 设备身份、端口信息、运行配置、通道顺序 |
| `run.json` | 结束时间、设备身份、文件 SHA-256、完整统计 |

CSV 中无效通道：`chN` 为空、`validN=0`、`flagN` 含 `32`（NO_DATA）。不会填 0 冒充真实值。

## 5. 统计与复核

```bash
.venv/bin/python -m tools.tactile_acq analyze data/real/tactile/<run_dir>
# 或直接从 CSV 重算
.venv/bin/python -m tools.tactile_acq analyze data/real/tactile/<run_dir>/samples.csv
```

统计包括：

- 设备时间帧率、Mac 接收帧率、固件 `effective_frame_rate_hz` 均值/最小/最大；
- `frame_seq` 缺口（丢帧）、重复、乱序、`boot_id` 变化；
- Mac 接收超时次数、最大间隔；
- 每通道 valid/invalid、min/max/mean/std、unique、fixed、饱和、near-rail、负值、STUCK 标记；
- 三颗 ADC 最后状态与状态计数；
- 明确列出饱和通道、固定不变通道、含无效样本的通道。

固定不变（`fixed`）只表示该通道在本次运行中数值恒定，**不等于**传感器正常或接触为零；需要人工按压/释放验证。

## 6. 终端监视状态

| 状态 | 含义 |
|---|---|
| `STREAMING` | 正在接收有效 SAMPLE |
| `SATURATION` | 至少一个通道带 SAT/Near-rail 标记 |
| `CHANNEL_INVALID` | 至少一个通道 valid=false |
| `ADC_FAULT` | 至少一颗 ADC 状态非 OK |
| `TIMEOUT` | 超过阈值没有新 SAMPLE |
| `NO_DATA` | 连接后 2 秒内没有 SAMPLE |
| `DISCONNECTED` | 串口读错误/断开 |

## 7. 软件组接入

- 协议说明：[`docs/hardware/TACTILE_ADC_PROTOCOL.md`](../../docs/hardware/TACTILE_ADC_PROTOCOL.md)
- 独立解析示例：[`software_parser_example.py`](software_parser_example.py)
- 软件组现有 `src/tactile_gripper/protocol.py` 的 `parse_sample` 可直接消费本 SAMPLE：`channels`、`valid_mask`、`channel_ids`、`mcu_time_us` 均提供。
- 不修改软件组 `src/`、Dashboard 或 S3 控制固件；需要协议变更时先在 `docs/INTERFACE_CONTRACT.md` 登记。
