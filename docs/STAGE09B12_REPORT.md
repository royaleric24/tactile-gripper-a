# Stage 0.9B-12 常驻手动PWM控制台交付

## 结果

已实现scripts/pwm_console.py，新增src/gripper_a/bench.py和config/gripper_bench.json。一次启动参数确认DETACHED_BENCH实验，随后用户直接在终端逐次输入数字，不需Codex逐条审批。默认模拟，启动/BEGIN_BENCH无PWM，首目标必须人工输入1500。不自动扫描、重试或续期。

## 固件最小扩展

SafetyCore.h新增独立Bench入口和期限字段，复用现有序号/boot_id、有限脉冲、STOP/DISARM、fault/off/UNKNOWN机制；gripper_control.ino增加独立benchPermit输出门、JSON入口及状态。generate_gripper_config.py新增Bench编译配置校验，默认能力false。

Bench构建版本gripper-control-bench-0.9b12.0；1400–1600μs、50Hz/16bit、相邻≤50μs、首目标1500μs、单次≤500ms、绝对会话300000ms、失联5000ms。会话内不再使用原Trial的80μs累计路径上限，否则无法持续手动往返；这项调整仅限Bench，不放宽旧Trial。原Trial仍1460–1540、step20、total80、30s。正式ARM和hardware_enabled=false/UNCALIBRATED默认不变，启动无GPIO/LEDC初始化。

数字指令发送一次后非阻塞等待设备报告结束；期间STOP可直接发起，其他数字拒绝而不排队；本地越界/步进拒绝不发送。通信/固件版本/boot_id异常、FAULT/UNKNOWN、超时都停止并退出；没有自动重连或重放。STOP/DISARM不是物理断电，串口有界请求耗时使终端stop不是即时硬件急停。硬件异常以用户物理断电为优先。触碰后偶发转动及静态万用表正常仍不足以证明电气稳定，不扩大范围掩盖故障。

## 测试与编译

- 85项Python离线测试通过，包括FakeGripper及完整控制台PTY连续输入1500/1550/1600、范围拒绝、STOP后拒绝、Ctrl+C关闭、授权/首目标/50μs限制、无自动扫描、失效无重试、过期和日志保存。非TTY真实入口在串口打开前拒绝。
- 7个native可执行测试通过：原SafetyCore、Trial状态机、锁定固件入口、Bench状态机、Trial适配器、LEDC回归、Bench实际JSON/LEDC适配器。均SIMULATED，无物理设备。
- Arduino CLI 1.5.1 + Arduino-ESP32 3.3.2 + esp32:esp32:nodemcu-32s实际编译control/trial/bench三种配置成功。不是以Mock代替编译。
- Bench程序303235字节，静态RAM21784字节。证据evidence/stage09b12/：python_tests.txt、各native编译/运行日志、三个compile日志、生成配置快照、source_sha256.json和sha256.json。
- 生成头已恢复默认锁定配置；历史构建/真实日志保留。旧部署gripper-control-trial-0.9b2.0仍在板上，未被修改。

## 使用与兼容

完整步骤和真实启动命令见PWM_CONSOLE.md。可立即默认模拟运行，真实模式需重新上传Bench候选。旧Trial固件不支持BEGIN_BENCH/BENCH_PULSE，也不具新范围或5分钟期限；严格版本匹配不允许将旧固件当新Bench运行。故不能现在对旧板启动真实Bench实验。

下一次仅需单独授权上传此Bench构建，在舵机动力断开的条件下核对芯片/哈希，上传、写入校验、PING/GET_STATUS及复位默认锁定验证；此后另授权一次现场Bench实验启动，用户在自己的终端人工输入数字。每条数字就是人工触发，不需要额外Yes/No；不据此生成机械爪标定。

本轮未打开真实串口、未上传/擦除、未上电、未输出真实PWM、未改实际接线。至此停止等待部署授权。
