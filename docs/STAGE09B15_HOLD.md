# Stage 0.9B-15：有限Hold候选

本轮仅代码、离线测试与实际编译。没有打开真实串口、上电、上传或PWM操作。用户报告已观察到独立PM15S转动及短暂回退，属USER_REPORTED，不当作实际角度测量。持续PWM是否解决回退仍NOT_TESTED，接触/供电/信号兼容问题不能仅据本功能排除。

## 行为

新版本gripper-control-bench-0.9b15.0。一次Bench启动授权后，默认Pulse；hold/pulse只能在全新Bench且尚未输出任何目标时选择，不产生PWM。首次数字仍必须1500，范围1400–1600、相邻≤50μs、最小命令间隔100ms、5分钟Bench和5秒通信超时保留。

Hold：首次人工目标成功输出时启动设备端5秒绝对计时。后续合法数字更新目标，但不重置holdStart；同值也不续期，不重复attach LEDC。不同于Pulse，保持ACTIVE期间允许合法目标更新。已有LEDC输出直接写新duty/读回，不先关闭或重新初始化。心跳仅维持通信，不延长Hold或Bench窗口。

5秒到期写零/detach、撤销Bench许可，DISARMED、BENCH_HOLD_TIMEOUT、目标null；不会回到临时ARMED等待下一条。后续数字拒绝，用户必须显式begin；默认回Pulse，若要新Hold须再次hold，再手动1500。停止/异常更早发生则提前结束。期限从命令处理时计，不承诺精确物理输出持续5秒；周期任务/串口发送可能有调度延迟，未实测波形。

Pulse模式原样保留，每次最多500ms，到期off后仍临时ARMED，下一条必须等其结束；不改旧Trial。Hold模式禁止完整机械爪/负载实验。

## 交互

真实使用前须另行授权部署新固件，板上仍旧bench-0.9b12.0，当前不能直接用新控制台真实启动。部署后：

```sh
PYTHONPATH=src .venv/bin/python scripts/pwm_console.py \
  --real --port /dev/cu.usbserial-EXAMPLE_ESP32 --authorize-detached-bench
```

```text
pwm> begin
pwm> hold
pwm> 1500
pwm> 1550
pwm> 1600
pwm> stop
pwm> quit
```

启动本身已经BEGIN_BENCH且不输出，因此首个begin若会话已开只提示“不续期”，不重建。hold选择模式，第一条1500才启动5秒计时。5秒内来不及输入全部目标是正常情况；程序不自动补发、排队或续期。看到超时提示后须重新begin/hold，不能直接输入1550恢复。

STOP在输入循环中直接发请求，没有sleep阻挡；串口请求仍存在有界等待，并非硬件急停。DISARM/FAULT/Bench过期/失联也关闭PWM。持续PWM只是持续发送位置目标，不等于实际位置反馈、机械保持能力证明或物理断电。异常运动/振动/发热/不稳定时立即物理切断独立电源；舵机必须固定，不能手持观察。

## 协议和文件

新增BENCH_HOLD_MODE、BENCH_PULSE_MODE（只选择模式），以及BENCH_HOLD目标命令；沿用request_id、boot_id、sequence。新状态hold_capable、hold_mode、hold_remaining_ms。硬件门控复用独立Bench许可，Hold能力单独编译开关，默认false。模式选择无GPIO/LEDC调用。未经授权、首目标/范围/速率不符、故障锁存等仍阻止输出。

修改SafetyCore.h、gripper_control.ino、generate_gripper_config.py、config/gripper_bench.json、src/gripper_a/bench.py、scripts/pwm_console.py；新增native hold_test.cpp、Python test_hold.py及控制台Hold集成测试。修正控制台残留“1000..2000”帮助文字为实际1400..1600，未扩大控制边界。

## 证据

证据evidence/stage09b15/：最终Python结果python_tests_final.txt、8个native测试运行/编译日志、control/trial/bench三份Arduino编译日志、配置快照和sha256.json。构建使用Arduino CLI1.5.1、核心3.3.2、esp32:esp32:nodemcu-32s；保留旧构建和部署证据，生成头恢复默认锁定配置。

覆盖Hold选择无输出、首次目标、同值/更新不重复attach、更新/心跳不续期、5秒结束不自动ARM、STOP/DISARM/FAULT/通信断开/Bench过期、API失败UNKNOWN、未授权拒绝以及原Pulse回归。Python完整PTY交互验证人工更新和超时后拒绝/重新begin。所有测试SIMULATED，实际编译不等同真实Hold试验。

下一步仅授权该候选固件上传，动力物理断开时审核哈希、写入及默认锁定/复位验证；然后另授权一次独立无负载Bench实验。此次停止，不自动部署。

最终结果：93项Python测试通过，8个native可执行测试通过；三种Arduino配置全部编译成功。所有候选产物哈希复核一致，源码及配置哈希另存source_sha256.json。
