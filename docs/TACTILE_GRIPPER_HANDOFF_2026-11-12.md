# 真实触觉闭环机械爪项目交接（2026-11-12）

## 0. 当前基线（Stage 0.9B-26 验收后，优先）

- **主控制器：ESP32-S3**（YD-ESP32-23 2022-V1.3 / S3-N16R8），GPIO4、50 Hz、14-bit LEDC，固件 `gripper-control-s3-0.9b26.0`，串口 `/dev/cu.usbserial-EXAMPLE_S3`。
- **回退控制器：旧 ESP32**（NodeMCU ESP-32S V1.1），GPIO23、50 Hz、16-bit，稳定固件 `gripper-control-bench-0.9b24.0`；旧 BIN `bd02b1d2...`、配置、源码、构建产物和历史日志保留，不覆盖、不重烧。
- **验收**：固件上传 PASS；通信 PASS；用户报告真实机械爪开合 PASS（用户观察）；精确位置误差 UNKNOWN；长期稳定性 UNKNOWN。
- **真实日志**：`logs/real/bench/0e0571fd739d4f638541df1ccae5cc9b/transport.jsonl`（0.9b26.0，0 ERROR/0 FAULT，最终 DISARMED）。日志不证明机械位置。
- 未重新烧录、未重复舵机测试。完整记录见 `docs/STAGE09B26_REPORT.md`、`evidence/stage09b26/real_acceptance.json`。

## 1. 项目目标

项目根目录（用户 Mac）：`/home/example/Developer/research/tactile-gripper-a`。

短期目标：让 ESP32 控制 PWM 舵机可靠张开/闭合机械爪，接入已验证可采集信号的 4×4 触觉阵列，按照触觉反馈调节开合，完成至少 5 次有完整触觉、命令、设备状态和视频记录的真实闭环 Trial。

长期目标：夹持杯子，在持续加水的重量变化过程中依据触觉反馈调节夹持状态，在尽量避免掉落的同时限制杯体形变。长期目标尚未实现。不能将触觉电阻直接等同摩擦力，或将 PWM 目标等同实测夹持力。

## 2. 用户偏好与工作原则

- 用户是机器人控制初学者；希望简明、分阶段、尽快进行真实实验，不要反复重跑已通过的测试或让智能体逐条发送 PWM。
- 开发、代码审查和离线测试交给 DeepSeek Harness（取代已耗尽额度的 Codex）。
- 可以在终端手动输入 PWM 数值，自主实验，但命令必须来自已授权、可监控的设备端控制路径；发生异常应能物理切断舵机电源。
- 工程事实与模型推断必须区分；不能将 ACK / API success 当成 GPIO 真实波形或实际舵机角度的证明。
- 对上传、固件修改、接线、上电和真实运动分别获得明确授权；避免因默认权限而执行未批准动作。
- 避免没有必要的重复文档审查；遇到明确的代码缺陷先做最小改动和针对性测试。

## 3. 已确认硬件

- **S3 主控制器**：YD-ESP32-23 2022-V1.3 / S3-N16R8；ESP32-S3 (QFN56) r0.2、16 MB Flash、8 MB PSRAM、MAC `02:00:00:00:00:03`；FT232R，COM USB-C 端口 `/dev/cu.usbserial-EXAMPLE_S3`。
- **旧 ESP32 回退**：NodeMCU ESP-32S V1.1，ESP32-D0WDQ6，4 MB Flash，CP210x 系列，端口 `/dev/cu.usbserial-EXAMPLE_ESP32`；仅作回退，不主动重烧。
- **PWM**：S3 GPIO4 / 50 Hz / 14-bit（当前）；旧 ESP32 GPIO23 / 50 Hz / 16-bit（回退）。GPIO4 为舵机专用，触觉接入禁止复用。
- **舵机**：杭州众灵 PM15S（曾误认为 PM10D），单轴，15 kg·cm、标称 270°；用户资料 5–8.4 V、50 Hz、500–2500 μs 参考、中位 1500 μs；无实际角度/扭矩反馈，控制电平兼容性未确认。
- **独立电源**：三星 EP-TA10CBC，标称 5.3 V/2 A，实际负载电压和瞬时供电能力未验证；与 S3 共地（USER_REPORTED）。
- 白色 PWM、红色 V+、黑色 GND（线色依据用户资料；实物线序需以接头确认）。
- **机械状态**：机械爪已完成 S3 真实开合测试，用户报告与旧 ESP32 基本一致；精确位置误差和长期稳定性仍 UNKNOWN。不得把 500–2500 μs 当作机械安全行程。
- 用户无示波器或逻辑分析仪，有万用表。

## 4. 软件项目与关键文件

- `AGENTS.md`：Agent 工程约束。
- `BLOCKERS.md`、`docs/HANDOFF.md`：进展与未解决项。
- `docs/GRIPPER_PROTOCOL.md`、`docs/FAST_TRACK_TRIAL.md`、`docs/PWM_CONSOLE.md`。
- `docs/STAGE09B26_REPORT.md`、`evidence/stage09b26/summary.json`、`evidence/stage09b26/real_acceptance.json`：当前 S3 迁移与验收证据。
- `config/gripper_s3.json`、`config/board_s3.json`：S3 主控制器运行与构建配置；`config/board_esp32.json`：旧板回退配置。
- `docs/STAGE09B15_HOLD.md`、`docs/STAGE09B16_REPORT.md`、`docs/STAGE09B19_CONSOLE_FIX.md`：历史证据。
- `firmware/gripper_control/gripper_control.ino`、`SafetyCore.h`。
- `src/gripper_a/gripper_controller.py`、`src/gripper_a/bench.py`、`src/gripper_a/serial_client.py`。
- `scripts/pwm_console.py`、`scripts/calibrate_gripper.py`。
- 实机日志：`logs/real/bench/`，其他阶段证据位于 `evidence/`、`docs/`。
- 项目之前曾被查出主目录并非 Git 仓库；目前 Git 状态请重新核验，不能假定有提交历史或直接创建 worktree。

## 5. 历史阶段汇总

- Stage 0–0.8：设备识别、串口协议、PING/PONG、GET_STATUS、假机械爪和传感器协议；实机通信 PASS。
- Stage 0.9A–0.9B1：安全状态机、PWM 固件、锁定版本上传，重启后 DISARMED+UNCALIBRATED。
- Stage 0.9B6–7：Arduino-ESP32 3.3.2 `ledcReadFreq()` 在 duty=0 返回0造成错误频率检查；将检查移到获准正常写入之后；回归与编译通过；已上传。
- Stage 0.9B8–11：真实 1500/1520μs PWM 请求多次 ACK，初期没有观察到转动；发现可能缺公共地，用户补线；后续观察到偶发转动。
- Stage 0.9B12–13：开发人工输入数字的常驻 Bench Console，固件部署。
- Stage 0.9B15–16：有限 Hold 模式：Hold 5s绝对窗口，设备端超时；新固件 `gripper-control-bench-0.9b15.0` 已上传并通过重启锁定测试。应用 SHA-256 `d20f9eca0024648583e161c406c4e341e1b14b04a7906e7c97526215ee405aa3`。
- Stage 0.9B18–19：发现主机控制台发生文件漂移，旧版本缺 `hold` 入口，真实执行的仍是 500ms Pulse；恢复 Hold 分支并通过 97 项 Python 回归以及伪终端协议测试。真实固件无须再上传。
- Stage 0.9B24：机械爪连续保持模式（GRIPPER_ASSEMBLED），无固定 5 秒 Hold 期限；旧 ESP32 部署 `gripper-control-bench-0.9b24.0`。
- Stage 0.9B25–26：ESP32-S3 迁移；GPIO4/50Hz/14-bit，固件 `gripper-control-s3-0.9b26.0` 上传并 verify；用户报告真实机械开合 PASS。旧 ESP32 保留为回退。

## 6. 当前控制台与机械爪行为

- **现行 S3 固件**：`gripper-control-s3-0.9b26.0`（默认 DISARMED，不自动 ARM，不自动 PWM）。
- 启动命令：
  ```bash
  cd /home/example/Developer/research/tactile-gripper-a
  PYTHONPATH=src .venv/bin/python scripts/pwm_console.py \
    --target s3 --real --port /dev/cu.usbserial-EXAMPLE_S3 --authorize
  ```
- 菜单：`1` 机械爪（GRIPPER_ASSEMBLED，连续保持，无 5 秒 Hold / 300 秒会话限制）；`2` 独立舵机（DETACHED_BENCH，500ms 脉冲）；`0` 退出。
- 选择 1 后直接输入 500–2500 的整数目标；无 50μs 步幅限制；100ms 最小命令间隔；5 秒通信超时；`stop` 停止、`quit` 退出。STOP/DISARM 不切断独立舵机电源。
- **旧 ESP32 回退命令**：`--target esp32 --port /dev/cu.usbserial-EXAMPLE_ESP32`，固件 `gripper-control-bench-0.9b24.0`，GPIO23/16-bit。仅在 S3 回归时使用，不主动重烧。

## 7. 当前验收状态与历史异常

- **当前验收**：S3 上传 PASS、通信 PASS、用户报告真实机械开合 PASS；最新真实日志 `logs/real/bench/0e0571fd739d4f638541df1ccae5cc9b/transport.jsonl` 记录 1500→1300→1200→1160→1150→1500，0 ERROR/0 FAULT，最终 DISARMED。
- **UNKNOWN**：精确位置误差、长期稳定性、实际 PWM 波形/毛刺、堵转/温升与长期重复性。日志不证明机械位置；机械 PASS 来自用户观察。
- **历史异常**：下方 Pulse/Hold 阶段的“偶发转动、触碰线缆后变化、Hold 回退”是旧 ESP32 调试期记录，不是 S3 当前验收结论；不得用扩大脉宽掩盖电气问题。
- 不能将 API ACK 或状态 ACTIVE 当作真实物理波形测量；不能推断“停止 PWM 必然返回中位”。

## 8. 下一阶段：4×4 触觉接入待确认（未开发）

1. 传感器接口类型：16 路 ADC、行列扫描、外部 ADC 或多路复用器；采样率、分辨率、数据格式、时钟。
2. GPIO/ADC 映射：GPIO4 固定给舵机 PWM，禁止复用；USB/UART、Flash/PSRAM、strapping 引脚需按 S3 与 YD-ESP32-23 原理图核对（当前无原理图）。
3. S3 内部 ADC1/ADC2 可用性、Wi-Fi 互斥、校准与输入范围（0–3.3V）。
4. 传感器 UART 与现有控制台 COM USB 的串口资源、波特率、缓冲、心跳/命令带宽是否冲突。
5. 传感器供电/电流、3V3 稳压余量、独立电源、共地、电平转换与过压保护。
6. C 组 16 通道 row-major 是否实际提供、坏通道/质量标记/单位/阈值/超时/STOP/释放策略，均未联调。

## 9. DeepSeek Harness 接手方式（官方 Web UI）

在 Mac 终端：
```bash
cd /home/example/Developer/research/tactile-gripper-a
node -v
npx @deepseek-ai/dsh web
```
官方 Web UI 通常位于 `http://127.0.0.1:3080`。在 UI 选择此现有项目为 Workspace；Settings → Models 配置 DeepSeek 模型/账号或 API Key；新建会话并发送下述接手提示词。最新 DSH 发布可能要求 Node.js ≥24.9，请以当前发布的版本要求为准。此步骤不需要重新初始化 Python 项目，也不要把 DeepSeek Harness 源码克隆进此机械爪项目。

## 10. DeepSeek Harness 首条任务（只读审计）

你现在是本地机械爪项目的接手工程师，工作目录 `/home/example/Developer/research/tactile-gripper-a`。先读取 `AGENTS.md`、`BLOCKERS.md`、`docs/HANDOFF.md`、`docs/STAGE09B15_HOLD.md`、`docs/STAGE09B16_REPORT.md`、`docs/STAGE09B19_CONSOLE_FIX.md`、`docs/PWM_CONSOLE.md`，再检查 `scripts/pwm_console.py`、`src/gripper_a/bench.py`、固件源码及最新 `logs/real/bench/` 日志。核实实际 Git 状态（历史可能没有 .git），保护所有原始证据、既有修改及环境。你必须区分上一个Codex的报告与自己真正读取到的磁盘证据，不得假装已执行测试。本轮只允许只读分析：不修改文件、不运行项目脚本、不触碰串口、不上传固件、不打开电源、不发送 PWM。整理：当前固件与主机代码版本是否匹配；此前的Hold是否确实发送 `BENCH_HOLD_MODE`/`BENCH_HOLD`；Hold期间是否可从日志证明ACTIVE；现有日志与硬件异常各支持什么结论；提出一个最小下一步实验（如必要的日志增强或安全电气测量）。最后用中文输出一个不超过2页的接手报告，列出PASS/UNKNOWN/BLOCKED及下一次明确授权事项，等待用户许可。
