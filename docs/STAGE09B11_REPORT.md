# Stage 0.9B-11 共地修正后PM15S独立单次试动

用户报告已补齐公共GND，确认脱联动、固定、自由轴、接线/可立即断电、无其他程序及已上电无异常。本轮获准单次1500μs/50Hz/固件最多500ms。没有按“绕过所有安全”要求解除保护，仍完整遵守现有Trial流程。未修改代码/配置、未编译、未上传。

REAL_SERIAL：设备身份匹配，初始DISARMED/UNCALIBRATED、无活动Trial、无UNKNOWN。BEGIN_TRIAL范围1500–1500、initial1500、LINKAGE_DETACHED获ACK；唯一TRIAL_PULSE(1500)获ACK/ACTIVE/PWM_COMMANDED_UNMEASURED；随后TRIAL_PULSE_ENDED/DISABLED_UNMEASURED。DISARM并查询确认DISARMED、UNCALIBRATED、hardware_enabled=false、motion_enabled=false、trial_active=false、目标null。串口关闭，无占用，无故障响应；不重试，不发1520。

原始日志及摘要：logs/real/stage09b11/20261111T142359Z/。API成功不证明物理波形/实际持续时间，波形NOT_MEASURED。用户实际运动/异常观察PENDING。共地缺失是用户报告的既往可能原因，尚不能据此确定之前不动的唯一根因。当前暂停，等待用户反馈与动力断开确认，再决定是否可继续人工标定，不自动动作。

## 最终用户反馈

用户明确确认已断电，“这次也是没有任何动静”。结论为未观察到运动，不能认定舵机定位成功；补共地没有使这次1500指令产生可见响应，但不证明共地无作用或舵机损坏。电压、电流、温度与实际PWM未测；尚不能区分已在目标附近、信号链/阈值、供电及本体故障。停止重复同一试动，下一步仅断电核对完整接线、P23与舵机插头定义/电源标签。
