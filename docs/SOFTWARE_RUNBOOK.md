# 软件 V1.0 运行手册

日期：2026-11-13。适用于软件分支 `feat/software-v1`。真实硬件操作必须另行授权。

## 1. 环境

```bash
cd /home/example/Developer/research/tactile-gripper-a-sw
UV_CACHE_DIR=/tmp/uv-cache uv sync --locked
PYTHONPATH=src .venv/bin/python -V
```

要求 Python >= 3.11（NiceGUI 4）。依赖：NiceGUI 4、pySerial、Python 标准库 JSONL/CSV。

## 2. 启动 Dashboard

```bash
# 默认：SIMULATION 数据源，S3 OFFLINE，SENSOR WAITING，不发任何设备命令
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --port 8080

# 明确标注的模拟演示（合成传感器 + dry-run 控制器 + demo Trial）
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo --port 8080
```

打开 `http://127.0.0.1:8080/`：

- `/` Live Monitor
- `/experiments`
- `/analysis`

默认只监听 `127.0.0.1`；投屏/局域网访问使用 `--host 0.0.0.0` 并自行评估网络暴露。

## 3. 无界面完整演示

```bash
PYTHONPATH=src .venv/bin/python scripts/run_simulation_demo.py --ticks 30 --interval 0.05
```

脚本会：连接 dry-run 控制器 → 建立 MANUAL 会话 → 连接合成传感器 → 创建 Trial → 记录帧/控制事件 → 结束 → 导出 CSV。只写 `data/simulated/trials/`，不打开串口。

## 4. 只读回放

```bash
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui \
  --source REPLAY --sensor-file data/simulated/trials/<TRIAL_ID>/frames.jsonl --port 8080
```

`REPLAY` 页面没有 Apply/STOP，不创建真实串口，不写 `data/real/`。

## 5. 真实 LIVE（本轮未执行，仅入口）

S3 + 传感器：

```bash
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui \
  --source LIVE --hardware-permission \
  --connect-port /dev/cu.usbserial-XXXX \
  --sensor-port /dev/cu.usbserial-YYYY \
  --sensor-config config/sensor_serial.json \
  --connect-sensor --connect --port 8080
```

仅传感器（不连接 S3）：

```bash
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui \
  --source LIVE --hardware-permission \
  --sensor-port /dev/cu.usbserial-YYYY --connect-sensor --port 8080
```

安全性：

- `--hardware-permission` 是真实连接的必要条件，不等于运动授权。
- `--connect` 才会打开 S3 串口并建立 BENCH 会话；`--connect-sensor` 才会打开传感器串口。
- 真实 PWM 运动、固件烧录、接线/上电仍须逐次具体授权。
- `STOP` 只发送已验证固件 STOP；不保证保持/释放，不是硬件急停。

## 6. 传感器串口配置

[config/sensor_serial.json](../config/sensor_serial.json)：

```json
{"sensor_serial": {"port": null, "baudrate": 115200, "bytesize": 8, "parity": "N",
  "stopbits": 1, "read_timeout_s": 0.1, "boot_wait_s": 0.0,
  "max_line_bytes": 16384, "reconnect_enabled": true,
  "reconnect_initial_s": 0.5, "reconnect_max_s": 10.0}}
```

- 端口默认 null；只有 `--sensor-port` 或 UI Connect sensor 才会打开。
- 传输层只读，不提供 write 方法。
- DTR/RTS 在打开前置 false，避免非预期复位；真实板是否需要 boot wait 由硬件组确认。
- 协议仍为 `PROPOSED v0.1`，不得据此声称硬件已实现。

## 7. 数据目录

- `data/simulated/trials/<ID>/`：模拟 Trial。
- `data/real/trials/<ID>/`：真实 Trial（需真实设备授权）。
- `logs/simulated/`、`logs/real/`：底层控制日志（既有实现位置）。
- `data/`、`logs/` 被 Git 忽略；不提交实验数据。

## 8. 测试

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

离线测试不依赖真实 ESP32/传感器。`NOT_TESTED` 项见 [V1 报告](SOFTWARE_V1_REPORT.md)。
