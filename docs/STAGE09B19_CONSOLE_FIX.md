# Stage 0.9B-19：Hold控制台入口修复

日期：2026-11-12（Asia/Shanghai）。本轮只修改Python入口及主机测试、文档，没有打开真实串口、修改/编译/上传固件、上电或输出真实PWM。

## 漂移定位

项目不是Git仓库；无法确定具体操作者、编辑工具或覆盖操作。修复前控制台SHA256=53ec0475816b0906792406644cb5610e721c7af70f7d2bdbea72f62dc59348b0，与Stage09B16记录的漂移哈希完全一致；Stage15审查哈希为a643afc3abb5c070d80e691fe632fb5280c1884fa0fb063b42fd542801dc6c12。因此可以确认：缺失至少从Stage16预检已存在，漂移内容为Pulse-only命令入口，而不是本轮才出现。Stage15只有审查哈希和测试证据，不虚称存在可逐字恢复的完整原始快照。

修复前运行真实scripts/pwm_console.py的原PTY测试，hold输入被Rejected: unknown_command，测试失败；证据evidence/stage09b19/before_tests.txt。当前文件副本pwm_console.before.py和最小差异console.diff已保存。

## 最小修复

仅scripts/pwm_console.py：

- help增加hold/pulse，启动文字区分Pulse500ms和Hold固定5秒。
- 两个命令共用现有BenchController.select_mode()，选择模式不输出。
- 数字仍调用同一g.pulse()，由已验证控制器按模式选择BENCH_HOLD或BENCH_PULSE，未复制第二套解析或协议逻辑。
- 增加Hold到期撤销提示；已活动会话的begin只提示不续期，避免误重开。
- 保留TTY、参数、STOP/DISARM/退出、日志及其他现有格式，不覆盖整个文件。

固件、生成头、config/gripper_bench.json及BenchController哈希逐项与修改前一致，证据unchanged_verified.json。实际范围1400–1600、step50、首目标1500、固定5秒窗口及故障保护没有变化。

## 端到端证明（SIMULATED）

直接启动实际脚本，通过PTY输入，不用另一个命令解析器替代。新增/加强tests/test_pwm_console.py，核对脚本自动生成的JSONL请求记录：

- 输入hold后BENCH_HOLD_MODE，无目标请求；1500、1550、重复1550分别生成一次BENCH_HOLD，检查protocol_version/request_id/boot_id/sequence。
- 显式pulse生成BENCH_PULSE_MODE，1500生成BENCH_PULSE。
- Hold更新/同值不续期，超时后数字拒绝，显式begin后可新会话。
- STOP/DISARM撤销，非法首目标/范围/步进拒绝，不出现额外目标。
- 实际入口注入模拟FAULT/通信异常，退出关闭且只失败一次，无自动重试。
- Ctrl+C及原Pulse回归保留。

97项Python测试全部通过：evidence/stage09b19/python_tests.txt。e2e_protocol_evidence.json保存模拟请求及对应日志路径。这里证明的是实际入口在FakeGripper路径生成正确协议请求，未向真实ESP32发送。相同目标不重复LEDC初始化仍由未变的已部署固件实现；本轮未重新跑native或物理波形测试，Stage15原native验证作为历史依据保留。

## 正确使用

兼容已部署gripper-control-bench-0.9b15.0，无需刷写。今后在已获独立Bench实验启动许可并确认脱联动、固定自由轴、可靠接线/供电/共地、可立即断电且无其他串口程序后，从项目根目录启动：

```sh
PYTHONPATH=src .venv/bin/python scripts/pwm_console.py \
  --real --port /dev/cu.usbserial-EXAMPLE_ESP32 --authorize-detached-bench
```

先quit旧Console，重新启动修复后的程序。启动自动BEGIN_BENCH但不输出，默认Pulse。输入hold，见Mode selected；输入1500启动5秒Hold；5秒内可输入1550或相同目标，步进不超过50，命令间隔至少100ms。status可查看设备hold_mode/hold_remaining_ms。Hold到期后必须手动begin、hold、1500再开始，不自动续期。stop/disarm/quit保留，STOP不是动力断电。

如只验证界面可不带任何参数启动，始终SIMULATED。本轮没有运行真实实验，至此停止。
