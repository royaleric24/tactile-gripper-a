# Stage 0.9B-3 受限试动固件部署与无运动验证

2026-11-11。**本阶段完成，真实上传/通信/重启验证通过，保持锁定并暂停。** 用户确认：独立舵机电源物理断开、PWM信号未接ESP32、上传/复位不会影响机械爪；供电接线由他人完成，本轮未重复审查或改接线。

## 本次部署

版本 gripper-control-trial-0.9b2.0；NodeMCU-32S，FQBN esp32:esp32:nodemcu-32s，Arduino-ESP32 3.3.2。上传已通过离线测试的 build_trial 产物，未重新修改固件/扩大范围。应用 SHA-256 01359e50dff53814cc960dea159d719d482d4bb5f60ec73e1770d17cf4edd35d。

全部固件/源码/试动配置/构建头哈希与 evidence/fast_track/build_manifest.json 匹配；旧4MB备份两份哈希核验通过。注意当前源码默认 generated_config.h 是锁定配置，不是此次试动构建使用的头；试动头快照在 evidence/fast_track/trial_generated_config.h。不得随意重编替换本次批准产物。

本轮先核对USB端口与占用，再实际检测ESP32-D0WDQ6 revision v1.1、MAC 02:00:00:00:00:01、Flash 4MB，与已知设备相符。一次上传成功，四段哈希校验通过，EraseFlash=none，仅必要引导/分区/boot_app0/应用扇区擦写，没有整片擦除或高风险恢复。

## REAL_SERIAL 结果

PING/PONG、GET_STATUS、版本与request_id匹配通过。默认DISARMED、UNCALIBRATED、hardware_enabled=false、motion_enabled=false、calibrated_motion_enabled=false，trial_capable=true但trial_active=false、窗口剩余0，目标脉宽null、DISABLED_UNMEASURED，实际角度/开度null。

ARM拒绝UNCALIBRATED_OR_DISABLED；DISARMED下TRIAL_PULSE(pulse=0)及SET_PULSE_US(pulse=0)拒绝NOT_ARMED；BEGIN_TRIAL使用错误boot_id且physical_condition=NOT_CONFIRMED，代码在trialPermit之前拒绝，实测SESSION_OR_REPLAY。没有发送合法BEGIN_TRIAL、没有进入Trial、没有发送可用PWM目标，所有回复均保持默认锁定。

工具读取MAC并执行RTS硬复位后再次只读PING/STATUS；boot_id变化且恢复同样锁定状态。串口打开也可能引发额外复位，不能独立归因复位源；新启动锁定已确认。结束后客户端关闭，lsof无占用。

证据：evidence/stage09b3/authorization.json、identity_real.txt、upload_real.txt、reset_real.txt、status_final.json、real_summary.json；完整收发日志 logs/real/stage09b3/no_motion.jsonl、restart.jsonl（REAL_SERIAL）。测试脚本 scripts/trial_no_motion_verify.py 固定无输出请求。

## SIMULATED / NOT_TESTED

先前36项Python和native测试为SIMULATED，本轮不重复计为实机运动。有效BEGIN_TRIAL、500ms实际PWM、活动窗口/失联撤销、舵机独立运动、机械爪开闭、物理波形/毛刺均NOT_TESTED。未产生自动运动命令是源码/命令记录和状态层结论，不是示波器无输出证明。

## 下一步与权限

Trial能力已部署，但没有运行许可。当前舵机电源断开、信号未接，不能直接开始动作；不再开展重复供电方案审查。下一轮先由用户在断电条件下确认输出与爪联动分离、固定和空间安全，然后按已完成接线方案恢复信号连接；相关人工操作必须另获明确许可，再分别批准舵机上电和Test1具体会话/首目标/每次脉冲。Test2复装与局部范围另行批准。

当前授权不包括上述接线、上电、PWM和运动。异常物理断电针对独立舵机电源，不是仅拔ESP32 USB。无仪器不阻止另获准功能试动，但功能运动不证明波形或长期可靠性。
