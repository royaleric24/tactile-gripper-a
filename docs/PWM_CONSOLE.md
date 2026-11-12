> **Stage 0.9B-20C（历史）**：旧 ESP32 Bench 的手动范围与 Hold 规则。当前主控制器为 ESP32-S3（GPIO4/50Hz/14-bit，`gripper-control-s3-0.9b26.0`），用法见文末“Stage 0.9B-26 ESP32-S3 目标（当前）”；旧 ESP32 配置仅作回退。

# PM15S DETACHED_BENCH 手动控制台

本轮仅离线开发/测试/编译，未访问真实串口、未上传、未上电或试动。部署后用户在自己的Mac终端持续输入，不需要Codex逐条执行。

## 启动

在项目根目录运行，默认SIMULATED，不打开设备：

```sh
PYTHONPATH=src .venv/bin/python scripts/pwm_console.py
```

**当前旧固件不兼容Bench。先单独授权并部署已编译的新Bench固件，验证启动锁定后，才能用下面的真实命令。**

```sh
PYTHONPATH=src .venv/bin/python scripts/pwm_console.py \
  --real --port /dev/cu.usbserial-EXAMPLE_ESP32 --authorize-detached-bench
```

一次启动授权标志同时确认：PM15S完全脱离机械爪、固定牢靠、轴/舵盘自由无遮挡、独立电源/信号/共地核对、能够立即物理断电、无其他串口程序。仅用于独立无负载实验，不能用于完整机械爪。真实模式必须交互终端，拒绝管道/非TTY，避免此前EOF问题。连接核对Bench固件版本及锁定状态，启动BEGIN_BENCH但**不输出PWM**。

输入示例（每行由人独立输入，没有程序自动序列）：

```text
pwm> 1500
pwm> 1550
pwm> 1600
pwm> 1550
pwm> stop
pwm> quit
```

每条合法数字仅发送一次BENCH_PULSE（Hold 模式为 BENCH_HOLD），显示ACK并返回提示符，后台查询设备结束状态，不重试。首个目标由用户任意输入（500–2500），可能从未知当前位置明显定位。500–2500μs 是临时脱联动实验限制，不是机械爪标定区间；不按270°线性推算实际轴角。ACK和API成功不证明实际转动。

## 命令

- 数字：500–2500 整数，首个目标任意（500–2500），无相邻步幅限制；Pulse 单次≤500ms；越界本地拒绝而不发送，不自动修正到边界。命令间隔至少 100ms，过快会被 `rate_limit_no_queue` 拒绝。
- status：查询状态，不输出。
- stop：立即请求STOP、撤销Bench许可；不切断动力。之后数字拒绝，须显式begin才能重新人工开启，首目标重新任意（500–2500）。
- disarm：撤销许可；不切断动力。
- begin：仅在DISARMED且无故障条件下主动开启新的短期会话，没有定位输出；不自动调用。
- help：显示帮助。
- quit/EOF/Ctrl+C：请求DISARM并关闭串口、保存日志。通信失效时只能报告UNKNOWN，不能保证物理停止。

控制台不以sleep阻塞输出期间的终端输入，stop可在输出期间立即发起请求；上一输出结束前的其他数字会拒绝，不排队。串口请求仍有有界超时，因此软件STOP不保证瞬时响应，更不是硬件急停。异常时直接物理切断舵机电源。

## 设备端保护与协议

新版本gripper-control-bench-0.9b24.0，新命令BEGIN_BENCH（physical_condition=DETACHED_BENCH）及BENCH_PULSE。两者沿用JSONL、protocol_version=1、request_id、boot_id和递增sequence。BEGIN不输出；试动输出适配器独立验证Bench编译能力、许可和500–2500界限。原BEGIN_TRIAL/TRIAL_PULSE不放宽，正式ARM仍受hardware_enabled/UNCALIBRATED保护。

Bench设备端绝对窗口300000ms、失联5000ms、单脉冲500ms；手动目标无步幅限制，但100ms最小命令间隔、500–2500范围及绝对会话期限仍由设备强制。心跳仅保持通信，不续期窗口，不输出。Bench不继承旧Trial的80μs累计路径限制（否则连续人工往返不可用）。Bench专用能力默认false；新Bench构建trial_enabled=false，避免混淆两种能力。原Trial构建保持原限制。

串口异常/复位（boot_id变化）/FAULT/UNKNOWN/超时均退出，不重连不重放。过期需用户重新主动启动程序；不会为了继续输入自动续开。STOP/DISARM主动终止会话后可人工begin。故障须调查后另启，不自动恢复。

状态增加bench_capable、bench_active、bench_window_remaining_ms，旧trial_active在Bench中为false；motion_enabled仅表示当前临时许可，hardware_enabled仍false，calibrated_motion_enabled仍false。

## 硬件异常提示

此前“碰触后偶发转动”和静态万用表正常不证明电气链可靠。触碰导致变化应优先排查断电下的接插件/焊接/公共参考地，再核对供电动态压降和PM15S输入电平兼容；不得通过不断扩大脉宽掩盖故障。不得带电摸轴或晃线制造响应。不受控运动、异常振动、发热或供电不稳时，切断独立电源，使用stop/quit退出并保留日志，不自动重试。

## 日志与部署

每次运行自动保存logs/real/bench/<id>/transport.jsonl或logs/simulated/bench/<id>/transport.jsonl，包含UTC/单调时间、输入、请求/响应、会话/boot_id、状态、拒绝/故障、输出结束。模拟标SIMULATED、真实传输标REAL_SERIAL；实际角度/开度为空。不自动生成校准文件，不把终端ACK当人工运动观察。

最新诊断构建产物在 `evidence/stage09b24/build_bench/`（`gripper-control-bench-0.9b24.0`），SHA-256 见 `evidence/stage09b20c/binary_sha256.txt`；上传需单独授权。旧 `evidence/stage09b12/build_bench/` 仅作历史保留。

## Stage09B19 使用纠正（优先于旧候选说明）

0.9b20.0 固件（新范围）已编译待授权上传；主机 hold/pulse 入口已修复。退出旧 Console 后重新启动实际 scripts/pwm_console.py；输入 hold 选择模式（不输出），再手动输入任意目标（500–2500）才生成 BENCH_HOLD。此前 Pulse-only 文件虽可输入数字，却无法进入 Hold；本次使用不要只输入 1500 并等待 5 秒。详见 STAGE09B19_CONSOLE_FIX.md 与文末“Stage 0.9B-20C 使用说明”。真实模式仍须一次独立 Bench 实验授权及现场确认，本轮只有离线验证。

## Stage 0.9B-20C 使用说明（当前优先）

- 固件版本：`gripper-control-bench-0.9b24.0`（独立 Bench，默认锁定）。
- 手动范围：**500–2500μs**；首个目标任意；相邻目标无 50μs 步幅限制，输入什么合法脉宽就发送对应的目标脉宽，不做自动分段/渐变。
- 保留：Hold 固定 5 秒不续期、Pulse 单次≤500ms、**100ms 最小命令间隔**、5 分钟会话、5 秒通信超时、STOP/DISARM/FAULT 语义、GPIO23/50Hz。
- 诊断：失败时 ERROR 响应含 `output_api_stage`（`WRITE_FAIL`/`READ_MISMATCH`/`FREQ_MISMATCH`/`INVALID_DUTY`）、`output_expected_duty`/`output_actual_duty`、`output_expected_freq_hz`/`output_actual_freq_hz`。
- 本轮只编译与离线测试，未上传、未上电、未发 PWM。

## Stage 0.9B-24 交互式控制台（历史，旧 ESP32）

```sh
PYTHONPATH=src .venv/bin/python scripts/pwm_console.py \
  --real --port /dev/cu.usbserial-EXAMPLE_ESP32 --authorize
```

菜单：`1` 机械爪（GRIPPER_ASSEMBLED，连续保持，无 5 秒 Hold / 300 秒会话限制）；`2` 独立舵机（DETACHED_BENCH，500ms 脉冲）；`0` 退出。选择 1 后直接输入 500–2500 的整数目标，**无需 begin/hold**。`stop` 停止并回到菜单，`quit` 退出。心跳由非阻塞轮询约每 1 秒发送；串口断连或 5 秒通信超时会关闭 PWM。`DETACHED_BENCH` 仍保留 5 秒 Hold。

## Stage 0.9B-26 ESP32-S3 目标（当前）

S3 独立配置：`config/gripper_s3.json`，固件版本 `gripper-control-s3-0.9b26.0`，GPIO4、50Hz、14-bit LEDC、500–2500μs 手动 Bench 范围。旧 ESP32 仍使用 `config/gripper_bench.json`（GPIO23、16-bit、0.9b24.0），两个目标分别生成 `generated_config.h` / `generated_config_s3.h`，不共享构建目录。

主机不再把某个串口当作 S3 默认端口。先只读列出端口：

```sh
PYTHONPATH=src .venv/bin/python scripts/pwm_console.py --list-ports
```

显式选择 S3 目标和实际端口（示例端口来自 2026-11-12 实机枚举，不是默认值）：

```sh
PYTHONPATH=src .venv/bin/python scripts/pwm_console.py \
  --target s3 --real --port /dev/cu.usbserial-EXAMPLE_S3 --authorize
```

旧 ESP32 目标仍用 `--target esp32 --port /dev/cu.usbserial-EXAMPLE_ESP32`；不带 `--target` 时为向后兼容默认 `esp32`。握手按配置中的 `firmware_version` 精确匹配，S3 固件版本不同，混用会被拒绝。

S3 设备 STATUS 额外回报：`board_target`、`pwm_gpio`、`pwm_frequency_hz`、`pwm_resolution_bits`、`pwm_readback_settle_ms`、`pwm_first_readback_settle_ms`、`chip_model`、`flash_size_bytes`、`psram_size_bytes`。这些是设备回报，不替代实际波形或机械位置观察。

2026-11-12 已实机确认：ESP32-S3（QFN56 r0.2）、16MB Flash、8MB PSRAM、GPIO4/50Hz/14-bit 配置，启动 `DISARMED`、`DISABLED_UNMEASURED`、`bench_capable=true`。用户已亲自完成 S3 真实机械爪测试并报告开合 PASS；最新真实日志 `logs/real/bench/0e0571fd739d4f638541df1ccae5cc9b/transport.jsonl` 记录 1500→1300→1200→1160→1150→1500，0 ERROR/0 FAULT，最终 `DISARMED`。精确位置误差与长期稳定性 **UNKNOWN**；日志/ACK 不能替代实际机械位置观察。
