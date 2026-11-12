# Stage 0.9B-6 LEDC零占空比频率误判修复

日期：2026-11-11。范围仅固件最小修改、SIMULATED离线测试和实际编译；没有打开串口、写Flash或启用真实PWM。舵机电源由用户确认已物理断开。

## 根因和修改

`firmware/gripper_control/gripper_control.ino` 的 `LedcOutput::set()` 原先在attach后、首次写入前检查 `ledcReadFreq()==50`。项目锁定的3.3.2核心 `cores/esp32/esp32-hal-ledc.c` 中，该函数在duty为0时返回0，导致初始化误报。工程源码现只有一处频率读回调用（旧构建目录作为历史证据保留）。

初始化仍调用 `ledcAttach(GPIO23,50,16)` 并检查返回值。该核心实现检查频率/分辨率、分配定时器并检查 `ledc_timer_config()` 的返回值；定时器匹配/配置是初始化依据。此阶段不写入测试用非零duty，不调用ledcWriteTone，不用零duty的ledcReadFreq假装验证配置。

关键差异：

```diff
- if(ledcReadFreq(CFG_GPIO)!=CFG_FREQUENCY_HZ){uncertain=true;return false;}
  uint32_t duty=pulseDuty(us,CFG_FREQUENCY_HZ,CFG_RESOLUTION_BITS);
- bool ok=duty>0 && ledcWrite(CFG_GPIO,duty) && ledcRead(CFG_GPIO)==duty;
+ bool ok=duty>0 && ledcWrite(CFG_GPIO,duty) && ledcRead(CFG_GPIO)==duty
+         && ledcReadFreq(CFG_GPIO)==CFG_FREQUENCY_HZ;
```

频率读回作为**获准目标实际写入后的附加软件检查**，前提为非零duty；不是为了初始化校验而发出非零duty。写入后已经可能存在PWM，若频率或占空比读回异常，SafetyCore立即尝试off并锁存UNKNOWN。因此不能宣称该检查可在发出第一个周期前发现所有硬件故障。API返回/寄存器配置均不是物理波形测量。

## 回归测试

Python：65项离线测试。

Native：5个可执行测试，直接编译实际SafetyCore和固件入口，串口/LEDC为SIMULATED替身。修改Arduino.h使频率读回准确遵循“零duty返回0”语义；原trial_adapter_test显式注入读回失败，而不是依赖永久返回0的替身。

新增ledc_regression_test覆盖：零duty初始化不误报；未许可/启动不输出；BEGIN不输出；attach、write、占空比读回、频率读回及detach失败；500ms结束；停止后重新attach；STOP/DISARM；FAULT/UNKNOWN锁存；通信超时及重启默认禁用。

证据与运行结果在 `evidence/ledc_frequency_fix/`：python_tests.txt、各native compile/run日志、两份生成配置、两种Arduino实际compile日志及sha256.json。

## 安全机制和交付边界

未改SafetyCore、配置JSON、GPIO23、50Hz、16bit、默认hardware_enabled=false、DISARMED/UNCALIBRATED、试动声明与授权、局部范围、单步/累计/输出持续时间、STOP/DISARM/FAULT或UNKNOWN锁存。生成头在构建后恢复原内容。没有开机自动定位/非零PWM，没有上传；板上仍是原先失败的gripper-control-trial-0.9b2.0。

候选编译保留原配置版本字符串，须用此轮SHA-256与配置快照区分修复构建，不能仅凭版本字符串判断已部署。本轮不声称故障已在真实设备消失。可进入下一次上传前审核；上传须新的明确许可，之后只做隔离条件下锁定验证。新的PWM单次试动仍需另外授权，旧的一次许可已使用。

## 最终验证结果

全部完成：65项Python测试通过；5个native可执行测试全部通过；锁定版与受限试动版均使用Arduino CLI 1.5.1、Arduino-ESP32 3.3.2、FQBN esp32:esp32:nodemcu-32s完成真实离线编译。实际CLI来自已安装Arduino IDE，不安装全局工具；项目CLI缓存不完整，未用于最终编译。

两份生成头均保持hardware_enabled=false、UNCALIBRATED；锁定版trial_enabled=false，试动版trial_enabled=true。原生成头已恢复为锁定版。每个产物SHA-256见sha256.json，源码/配置哈希见source_sha256.json；编译与哈希只能证明候选文件，不是上传或PWM实测。

主要修改文件：gripper_control.ino；tests/native_control/Arduino.h；trial_adapter_test.cpp；新增ledc_regression_test.cpp。SafetyCore和两份配置JSON未改。
