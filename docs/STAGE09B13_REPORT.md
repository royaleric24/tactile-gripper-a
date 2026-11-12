# Stage 0.9B-13 Bench部署完成

2026-11-11。用户明确授权上传并确认舵机独立动力物理断开、其他串口程序退出；随后确认短按EN一次。本轮没有舵机上电或Bench实验许可。

- 预检：Stage09B12源码、配置与全部产物哈希匹配；原始4MB备份、旧Trial回退bin哈希匹配。项目无Git仓库，未初始化。工具Arduino CLI 1.5.1，产物核心Arduino-ESP32 3.3.2、esp32:esp32:nodemcu-32s。
- 设备CP210x 10C4:EA60/EXAMPLE_ESP32、/dev/cu.usbserial-EXAMPLE_ESP32；读芯片确认ESP32-D0WDQ6 rev1.1，MAC 02:00:00:00:00:01。
- 仅上传evidence/stage09b12/build_bench内已审核产物，无重新编译/配置修改/整片擦除。写入校验Hash of data verified通过，无重试。
- 部署版本gripper-control-bench-0.9b12.0；应用SHA-256：a47093afe77d84ff61036f76b64e853a2f4a471836788cfa6fed9c7bbd0cfc56。
- 上传后、用户EN操作后重连各执行GET_STATUS/PING，通过版本/ID/类型及默认锁定检查；boot_id变化。注意开串口也可能复位，因此不将新boot_id唯一归因于EN，不声称连续测得重启瞬态。
- 最终DISARMED、UNCALIBRATED、hardware_enabled=false、motion_enabled=false、calibrated_motion_enabled=false、bench_capable=true、bench_active=false、trial_active=false、窗口0、commanded_pulse_us=null、DISABLED_UNMEASURED。
- 串口已关闭且lsof无占用。本轮应用层仅两次PING和两次GET_STATUS，无BEGIN_BENCH/BENCH_PULSE/Trial/PWM指令，无故障响应。物理PWM/运动NOT_TESTED，不证明硬件电气问题已解决。

证据：evidence/stage09b13/，真实原始JSONL：logs/real/stage09b13/。保留全部旧构建/备份/日志。

已满足PWM Console固件兼容条件。可先默认模拟；真实Console启动会发BEGIN_BENCH，须另获一次Bench实验启动授权及现场条件/上电确认，本轮不运行。用户之后逐次输入数字即可，不需Codex逐条审批。STOP不是物理断电；触碰后偶发转动等硬件问题仍须排查。至此暂停。
