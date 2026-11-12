# Stage 0.9B-8 独立PM10D单次参考定位

2026-11-11 21:51（北京时间）。用户确认六项现场条件，明确授权上电及一次1500μs/最长500ms试动，随后确认已上电无异常。机械传动已脱离，不是完整机械爪标定。

REAL_SERIAL：设备身份CP210x 10C4:EA60/EXAMPLE_ESP32；核对Stage09B7修复版产物哈希5d3fc7050343f9950f354743f26ddf63a6f0138fd6b033cd1b6607706ffdbaf8。连接初始状态符合锁定预期。使用已有LimitedTrialController，不改代码/配置、不上传。

只执行一次TRIAL_PULSE：BEGIN_TRIAL声明LINKAGE_DETACHED，low=high=initial=1500；首目标1500μs、配置50Hz，设备端最长500ms。返回ACK、ACTIVE、PWM_COMMANDED_UNMEASURED。随后查询为TRIAL_PULSE_ENDED、DISABLED_UNMEASURED；DISARM后再次查询为DISARMED、UNCALIBRATED、hardware_enabled=false、motion_enabled=false、trial_active=false、目标null。无OUTPUT_API_FAILURE，无重试，无1520μs命令。串口已关闭，lsof无占用。

API/软件读回成功不代表实测波形；周期/脉宽/实际输出持续时间均未经仪器测量。用户真实运动观察及声音/振动/发热情况PENDING，不能称已确认舵机运动成功，也不等于机械爪安全范围已标定。

原始日志与状态：logs/real/stage09b8/20261111T135113Z/。执行脚本留档evidence/stage09b8/single_authorized_trial.py，不自动执行。等待用户观察反馈，不再发送命令；下一次试动需单独授权。

## 用户观察反馈

用户原话：“没有转动，没有异响等”。记录为未观察到运动、未报告异常（USER_REPORTED），不是已确认定位成功。实际轴角度未知；可能已处在目标附近，也可能供电/信号没有有效到达，当前证据不能区分。动力是否已断开尚待确认；没有追加命令。
