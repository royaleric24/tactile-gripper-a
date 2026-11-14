# 当前交接（P2-S 软件）

更新：2026-11-14
分支：`sw/fsr-live-v2`
基线：公开 `origin/feat/dashboard-zh-v1` `9997853`
协议：PROPOSED，未冻结、未真实联调

## 已完成

- `models.py` / `protocol.py`：`sensor_profile`、`sensor_kind`、FSR 电压基础、
  FSR_ONLY 2 通道与 HYBRID 6×6+2 的严格校验；HELLO 兼容顶层/内层 profile。
- `control/contact.py`：显式基线、相对评分、四态 + 无效/未标定滞回。
- `control/auto.py`：离线 `evaluate_contact()`；无效/过期/未完成命令不产生夹紧；
  真实 AUTO 硬关闭。
- `control/core.py`：基线采集/清除、设备身份、决策记录、AUTO 故障锁存、Trial 扩展、
  显式 denied commissioning 入口、profile 仿真。
- `ui/`：FSR 卡片/趋势、只含矩阵的热图、profile 选择、基线按钮、身份/波特率说明、
  查询按钮、真实 AUTO 拒绝入口。
- `experiments/store.py`：原始 SAMPLE、身份、评估、PWM 命令/ACK、CSV 追加列；
  `frames.jsonl` 可直接 REPLAY（自动补 HELLO）。
- `tests/test_v2_sensing.py` + `tests/fixtures/v2/`：27 个 P2-S 测试；全套 278 通过。
- `config/`：FSR_ONLY / HYBRID 仿真配置；`sensor_serial.json` 增加
  `queries_enabled=false`。

## 运行

```bash
cd tactile-gripper-v2-sw
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v

PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo \
  --demo-profile FSR_ONLY --data-root /tmp/gripper-fsr-demo --port 8080
```

详见 [SOFTWARE_V2_P2S_REPORT.md](SOFTWARE_V2_P2S_REPORT.md) 与
[SOFTWARE_RUNBOOK.md](SOFTWARE_RUNBOOK.md)。

## 未做/未验证

- 未打开任何真实串口、未烧录、未上电、未发 PWM、未做机械动作。
- 未验证 921600 链路、真实 HELLO/STATUS 回复、两台设备身份、FSR 电压/极性、
  矩阵物理方向/串扰、ACK 后实际夹持。
- 未实现真实 AUTO 闭环；`request_real_auto_commissioning()` 当前必拒绝。
- 未做 Dashboard 逐项视觉验收；未合并 PR #1 的 V2 文档。

## 下一步建议

1. 集成组先按报告第 10 节确认协议/硬件接口，不直接开 AUTO。
2. 现场只读识别双串口，确认 115200/921600 与 HELLO/STATUS，不接 PWM。
3. 用不会夹到杯子的空载/软对象确认 FSR 极性、基线与饱和。
4. 单步、限幅、有人值守地验证 PWM 方向与 1300/1270 μs 观察，仍保持 AUTO 关闭。
5. 协议冻结、标定和急停/失联策略签核后，才评审真实 AUTO 入口。

## 禁止事项

- 不得把本分支的仿真/离线决策当作真实闭环证据。
- 不得用仿真帧驱动真实 PWM。
- 不得在未授权时打开串口、烧录、上电或运动。
- 不得把 ACK 写成到位/夹持力；不得声称协议已冻结。
