# Stage0.9B-16 Hold部署（已完成）

用户授权上传并确认舵机动力物理断开、其他串口程序退出。项目非Git仓库。预检发现唯一漂移为scripts/pwm_console.py，作为无关主机修改保留，未运行/覆盖；固件源码、配置和全部构建产物匹配Stage15。记录evidence/stage09b16/host_drift.json。

旧原始Flash备份、历史Trial回退文件及之前Bench版本产物存在；固件上传前重复核对审查哈希及芯片MAC 02:00:00:00:00:01、ESP32-D0WDQ6 rev1.1，CP210x 10C4:EA60/EXAMPLE_ESP32、/dev/cu.usbserial-EXAMPLE_ESP32。

仅上传审核产物evidence/stage09b15/build_bench，FQBN esp32:esp32:nodemcu-32s，Arduino核心3.3.2，无重新编译/修改范围/整片擦除。上传成功，Hash of data verified。

实际版本gripper-control-bench-0.9b15.0，应用SHA256=d20f9eca0024648583e161c406c4e341e1b14b04a7906e7c97526215ee405aa3。

上传后PING/GET_STATUS通过：DISARMED、UNCALIBRATED、hardware_enabled=false、motion_enabled=false、bench_active=false、hold_capable=true、hold_mode=false、hold_remaining_ms=0、commanded_pulse_us=null、DISABLED_UNMEASURED。串口已关闭无占用，尚待用户EN确认后的重启查询及最终DISARM。无BEGIN_BENCH/Hold/PWM/上电或机械运动，物理波形NOT_TESTED。

日志logs/real/stage09b16/，部署证据evidence/stage09b16/。新固件支持后续独立Hold实验，但必须另有实验启动授权；本轮不自动启动。主机CLI存在漂移，不能宣称其现版本已重新通过Stage15测试。

## 重启及最终关闭完成

用户确认EN后重连，PING/GET_STATUS及所有锁定字段通过；boot_id变化。打开CP210x串口也可能复位，因此不将新boot_id唯一归因于EN，不声称已测复位瞬态。最终显式DISARM获ACK，再GET_STATUS确认DISARMED/UNCALIBRATED、motion_enabled=false、bench_active=false、hold_mode=false、目标null和DISABLED_UNMEASURED。串口已关闭，lsof无占用。全程应用层仅3次GET_STATUS、2次PING及1次DISARM，无异常响应，无Bench/Hold/PWM启动。前文“待完成”为中间状态，现已完成。
