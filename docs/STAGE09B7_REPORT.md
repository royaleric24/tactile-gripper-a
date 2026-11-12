# Stage 0.9B-7 LEDC修复版部署

日期：2026-11-11（北京时间）。用户明确授权上传修复版和无运动验证，另确认动力物理断开、无人接触轴、其他控制程序退出。

## 已完成 REAL_SERIAL / 固件写入

- 项目无Git仓库；当前源码/配置/全部产物逐项匹配Stage 0.9B-6保存哈希。
- USB 10C4:EA60，序列号EXAMPLE_ESP32，/dev/cu.usbserial-EXAMPLE_ESP32；芯片ESP32-D0WDQ6 rev1.1，MAC 02:00:00:00:00:01匹配历史记录。
- Arduino-ESP32 3.3.2，FQBN esp32:esp32:nodemcu-32s；仅上传evidence/ledc_frequency_fix/build_trial内已审核产物，未重新编译或改变配置。
- 原始4MB备份及旧试动版本bin逐项验证哈希通过；旧清单中的源码已被授权修复，不用于旧回退bin核验。
- 上传成功，各写入区段Hash of data verified；仅常规写入所需区段擦除，无整片擦除，无恢复重试。
- 版本字符串仍gripper-control-trial-0.9b2.0；新应用bin SHA-256：`5d3fc7050343f9950f354743f26ddf63a6f0138fd6b033cd1b6607706ffdbaf8`。部署身份由审核哈希及写入校验绑定，串口协议没有独立构建哈希字段，不能只凭同版本字符串区分旧/新固件。
- 上传后GET_STATUS/PING通过，DISARMED、UNCALIBRATED、hardware_enabled=false、motion_enabled=false、trial_active=false、commanded_pulse_us=null、output_state=DISABLED_UNMEASURED。
- 串口已关闭，lsof无占用。没有BEGIN_TRIAL/TRIAL_PULSE/ARM/SET命令，没有授权或主动启用PWM。

## 重启后验证完成

用户确认已在动力断开条件下短按EN一次。随后GET_STATUS/PING通过，boot_id从b74b3e87fda865f01faa2b736fb94812变为8926b480a63f79a6c295f92cb3ce1dba，全部默认锁定字段仍符合预期，trial_window_remaining_ms=0、目标null。串口已关闭，lsof返回1且无输出（无占用）。

测量边界：打开CP210x串口本身也可能使ESP32复位，因此证明的是“用户EN操作后重新连接所见启动状态仍锁定”，无法把这个boot_id唯一归因于EN，也没有连续观测EN瞬态或GPIO物理波形。

本阶段完成，停止等待新的授权；没有上电/PWM/运动许可。

## 证据与边界

evidence/stage09b7/包含哈希预检、芯片身份、上传命令/输出和上传后状态；logs/real/stage09b7/保存原始JSONL收发，标REAL_SERIAL。旧证据保留。

真实LEDC修复效果/PWM波形/机械运动：NOT_TESTED。不得把无运动串口通过描述成PWM修复实测通过。后续仅可准备独立无负载单次试动，须重核脱联动、自由轴、固定、接线/断电条件并取得独立上电及具体单次目标/最长时间授权；本次上传许可不包含动作。
