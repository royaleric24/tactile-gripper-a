# Stage 0.9B-5 串口启动超时修复（2026-11-11）

范围：仅修改Python连接/关闭行为，未改固件、ESP32配置或PWM参数。用户已确认舵机独立电源物理断开、其他控制程序退出。当前项目没有Git仓库，无法提供Git差异或提交号；原有证据保留。

## 根因与证据

失败日志 `logs/real/calibration/0d4c262e19ba41ef9cb6a5d9e8872455_transport.jsonl`：

- CONNECTED 13:23:16.920748 UTC，首次GET_STATUS在16.920851发送，仅相隔0.103ms。
- 16.925578起收到ESP32启动文字和复位信息，17.122134收到request_id=null的INVALID_JSON，随后response_timeout。客户端正确忽略启动文字及不匹配ID，没有把它们算作成功。
- 原成功脚本trial_no_motion_verify.py、serial_roundtrip.py均在连接后等待2秒；GripperController原路径立即查询，缺少等待。

据此确定为连接启动时序竞争，首请求在设备启动期间发送、没有匹配响应。打开串口时已将DTR/RTS设为false，但这不能保证驱动/硬件打开过程完全没有复位瞬态；日志证明发生启动，不足以独立判定具体哪根控制线引发复位。延长响应超时不能找回已经丢失的请求。

## 最小修改

- SerialClient.connect：打开后先等待2秒再允许发送，沿用既有成功方法；支持host配置boot_wait_s覆盖，有界校验。DTR/RTS仍为false，不自动重试，不自动重连，不清除输入缓冲，启动内容照常记录/过滤。打开/等待失败和Ctrl-C均关闭句柄。
- GripperController：连接查询发现非DISARMED即关闭报错，不隐式DISARM；close可显式禁止发送DISARM，默认控制模式保持原退出策略。
- CalibrationSession：无motion_permission的真实会话只查询，STOP/DISARM/退出及错误清理不发送控制命令；不是以hardware_permission代替运动许可。连接还核对UNCALIBRATED、motion_enabled=false。
- CLI：修正Ctrl-C提示，避免无运动模式声称会发送DISARM。

## SIMULATED 离线测试

65项通过（原56项，新增9项）。新增覆盖等待前禁止发送、启动文本过滤、配置等待时间、打开失败无重试、等待失败/Ctrl-C关闭、非法等待值、只读生命周期、异常初始状态关闭、完整CLI status/quit仅发送GET_STATUS。证据：`evidence/serial_connection_fix/offline_tests.txt`。

## REAL_SERIAL 实测

设备枚举：唯一CP210x，VID:PID=10C4:EA60，USB序列号EXAMPLE_ESP32，端口`/dev/cu.usbserial-EXAMPLE_ESP32`；无其他程序占用。不是重新进行USB插拔归属验证。

3次独立连接、7次查询均通过：一次GET_STATUS/PING/GET_STATUS；两次完整标定CLI执行status/quit，各发送两次GET_STATUS。无重试。所有匹配响应均校验版本/请求ID；无BEGIN_TRIAL、TRIAL_PULSE、ARM、SET_PULSE_US、STOP或DISARM发送。结束后串口关闭且lsof无占用。

全部状态匹配：固件gripper-control-trial-0.9b2.0、DISARMED、UNCALIBRATED、hardware_enabled=false、motion_enabled=false、trial_active=false、commanded_pulse_us=null、output_state=DISABLED_UNMEASURED。fault_reason=BOOT是设备当前启动原因字段，没有被当作实际输出测量。

证据：`evidence/serial_connection_fix/20261111T132827Z/`（枚举、占用、状态、两次CLI输出、摘要、验证脚本）；原始收发日志：`logs/real/serial_connection_fix/20261111T132827Z*`。首次沙箱访问被系统拒绝，未成功打开；自动审批曾因担心退出发送DISARM而拒绝，完整CLI模拟证据确认仅查询后重新审核通过，才进行了上述实测。

物理PWM、角度、机械运动及真实标定：NOT_TESTED。未上传任何固件。

## 使用与剩余条件

项目根目录执行原命令即可，首次状态在约2秒启动等待后出现：

```sh
PYTHONPATH=src .venv/bin/python scripts/calibrate_gripper.py \
  --real --port /dev/cu.usbserial-EXAMPLE_ESP32 --hardware-permission
```

本命令没有运动许可，可用status/quit；退出只关闭串口。打开串口仍可能引发ESP32复位，因此保持舵机动力断开进行连接检查。若仍超时，保留新日志并停止，不扩大重试次数。

连接阻塞已解除，不能据此直接开始真实标定。完整闭合机构仍缺有证据的安全首目标及必经路径/方向；1500μs与短脉冲均不能替代这些证据。实际上电、单次PWM和运动需现场条件复核与独立授权。本轮结束暂停。
