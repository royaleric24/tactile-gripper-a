# Stage 0.9A 控制协议与边界

保留 Stage 0.8 的 UTF-8 JSONL、115200 8N1、protocol_version=1、request_id、command、PING/PONG、GET_STATUS/STATUS。控制固件版本为 gripper-control-0.9a.0；原 serial-test-0.8.0 不支持新增命令。旧客户端严格检查固件版本，因此不能直接当控制客户端使用；新的 GripperController 复用 SerialClient，额外接受 ACK。旧串口固件与日志保留。

| 命令 | 语义 |
|---|---|
| ARM | 仅允许 DISARMED、hardware_enabled=true、CONFIRMED 有效限位；进入 ARMED，不 attach LEDC、不输出脉冲 |
| SET_PULSE_US | 整数 pulse_us；首个目标必须为单独核准的 initial_pulse_us；通过边界、相邻步幅、累计绝对变化量、速率、会话与期限后才设 PWM |
| STOP / DISARM | 取消后续输出许可，尝试写 duty=0 并 detach；成功返回 DISARMED，否则 FAULT/UNKNOWN。不提供保持或释放保证 |
| HEARTBEAT | 仅刷新通信存活期限，不延长首次输出后的最大输出租约，不隐含 SET |
| PING / GET_STATUS | 只读，不刷新运动存活期限；状态返回 boot_id、last_sequence、命令脉宽及未测输出状态 |

每个请求必须有 1–64 字节 request_id；ARM/SET/HEARTBEAT 还须提供本次启动的 boot_id 和严格递增的正整数 sequence。boot_id 每次启动重新生成。STOP/DISARM 不要求会话，便于无会话时请求禁用；不能用它们解锁输出。状态中的 last_sequence 用于显式重连后同步编号。未实现重发：不自动重连、不重放积压命令。

回复含 protocol_version、request_id、firmware_version、type、state、fault_reason、boot_id、uptime_ms、last_sequence、calibration_state、motion_enabled、output_state。未知实际角度/开度为 null；commanded_pulse_us 不代表实际位置。ACK 表示固件逻辑接受/输出设定检查通过，不代表舵机到位。不能解析的错误帧 request_id=null。

DISARMED → ARM → ARMED → 首个 SET → ACTIVE；STOP/DISARM 撤销许可。ACTIVE/ARMED 遇到无效输入、范围/步幅/速率/重放错误、通信超时、输出 API 故障或输出租约到期进入 FAULT，尝试禁用 PWM。FAULT 须显式 DISARM 后再 ARM；旧目标不恢复。输出 API 失败或关闭失败标 UNKNOWN。LED API 返回成功及寄存器值均不能证明外部波形或机械状态。

串口解析每轮最多 64 字节、512 字节行上限、1000ms 半帧期限；循环及处理前检查通信租约。发送前检查 TX 空间，背压触发 FAULT，避免发送阻塞延误超时。故障原因保留在状态回复，Python JSONL 保存命令、响应、状态、超时和拒绝。UART USB 断开并非实时可感知，依赖 1000ms 通信期限；CPU/驱动卡死仍需硬件/看门狗策略另行验证。

暂定软件参数：50Hz、16bit、100ms 最小命令间隔、1000ms 通信期限、2000ms 最大输出租约。它们是设计参数，不是实机安全性能结论。断 PWM 可能失去保持力而掉落物体；这些策略必须在负载支撑和人工断电条件下另行验证。

Python 默认 dry_run，写入 SIMULATED 日志，不导入或打开硬件串口。真实连接需要 dry_run=False、hardware_permission=True、明确端口；运动还受配置和固件双重限制。close 尝试 DISARM 并关闭串口，断连异常状态设 UNKNOWN，不能声称硬件已经停止。

配置唯一源 config/gripper_control.json，经 scripts/generate_gripper_config.py 生成固件头。默认 hardware_enabled=false、UNCALIBRATED，所有实机安全脉宽/步幅/累计幅度为空；不提供运行时解锁/远程标定命令。将来标定后改配置、重新生成/构建、再单独批准上传和实机操作。当前合成测试边界仅写于测试，不能用于实机配置。

## Stage 0.9B-1 版本增量

当前候选版本改为 gripper-control-0.9b1.0：增加输出适配器的独立硬件/标定/边界检查，状态显式返回 hardware_enabled；协议封装不变。之前段落的 0.9a.0 是历史版本。重复锁定 ARM 均拒绝，但 request_id 本身不做缓存去重；有效运动的重放保护依靠 boot_id + sequence。尚未上传，实机结果见阶段报告。

## Stage 0.9B-12 独立Bench扩展（候选未部署）

独立构建gripper-control-bench-0.9b12.0支持BEGIN_BENCH（physical_condition=DETACHED_BENCH）/BENCH_PULSE，保留原封装和重放保护。专用编译能力/输出门控；范围1400–1600、首目标1500、相邻≤50、单次500ms、会话300000ms且不可由心跳续期、失联5000ms。启动默认不输出，hardware_enabled=false、UNCALIBRATED不变。Bench不使用旧Trial的80μs累计路程上限，旧Trial参数不变；详见PWM_CONSOLE.md。Bench状态独立报告，不自动产生真实校准结果。
