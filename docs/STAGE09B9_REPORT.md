# Stage 0.9B-9 同会话两次人工触发实验

用户确认全部现场条件且已上电无异常，授权1500后等待观察确认再1520。实际仅执行首条1500μs：BEGIN_TRIAL LINKAGE_DETACHED、范围1500–1520、initial1500获ACK；TRIAL_PULSE(1500)获ACK，随后TRIAL_PULSE_ENDED、DISABLED_UNMEASURED。

1520μs未执行。执行器未分配持续交互stdin，等待输入时立即收到EOF，按保守分支结束会话（NO_EXPLICIT_CONTINUE），已DISARM并关闭串口，无重试。不是用户已经报告异常，也不是本次固件窗口过期；不能把输入通道EOF当作用户确认。此为执行器输入方式问题，不是固件故障。今后若再获同类授权，须先在纯离线模式验证可持续输入通道，再进入真实Trial；不能自动重做本轮首条以恢复会话。

最终状态见原始记录，DISARMED/UNCALIBRATED、hardware_enabled=false、motion_enabled=false、trial_active=false、目标null。用户实际可见运动和异常反馈仍PENDING，物理波形NOT_MEASURED。logs/real/stage09b9/20261111T135827Z/保存完整实际收发与摘要；evidence/stage09b9/保留执行器。当前暂停，无进一步运动许可执行。

## 断电后的离线输入修复

用户补充“什么动静都没有”，并确认已物理断电。首条仅有API成功，未观察到运动；1520未执行。

已保存独立候选执行器evidence/stage09b9/two_step_runner_pty_candidate.py：打开串口前强制stdin为TTY，否则立即拒绝；后续真实执行必须显式分配PTY（tty=True）。原实际执行脚本保留，不修改控制器、固件或阈值。

新增tests/test_trial_interactive_input.py，用纯软件子进程/伪终端验证管道输入拒绝、保持等待、收到明确CONTINUE_1520后才接受输入。67项Python测试通过，证据evidence/stage09b9/offline/。候选执行器在非交互输入下实际拒绝、未打开串口。这仅验证输入通道和守卫，不冒充完整两步实机测试；30秒窗口和5秒失联保护不变，过期仍停止，不自动重开。后续两步实机需要新授权和现场确认，本轮不执行。

## 新授权后的同会话两步已完成（2026-11-11 22:02–22:03，北京时间）

用户重新授权并确认全部条件、上电无异常。采用已离线验证的PTY执行器，1500获ACK并报告TRIAL_PULSE_ENDED后暂停等待，期间仅发送心跳。用户明确回复“无转动，无异常，继续1520”。在原窗口仍有约2.3秒时仅发送一次1520，获ACK/ACTIVE/PWM_COMMANDED_UNMEASURED，随后TRIAL_PULSE_ENDED/DISABLED_UNMEASURED；没有超时重开、重复或第三条目标。每次固件上限500ms，实际波形/持续时间未经物理测量。

最终DISARMED、UNCALIBRATED、hardware_enabled=false、motion_enabled=false、trial_active=false、目标null；串口关闭且无占用。实际运动观察：1500无转动无异常（USER_REPORTED），1520仍待用户反馈；不将ACK解释成实际运动。

本轮新日志：logs/real/stage09b9/20261111T140223Z/，保留先前未完成实验，不覆盖。后续暂停，不发任何命令；需用户观察及独立动力断开确认。
