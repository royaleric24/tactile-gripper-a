# 项目进度记录（持续更新）

## 2026-11-16｜测试 A：无舵机负载的 S3 PWM + UART 隔离 PASS｜hw/p3b1-fsr-real

- **条件（操作者确认）**：PM15S 独立 5V 关闭；舵机信号线从 GPIO4 断开；保持 TX 修复固件
  `bd039a8…`；不重烧、不改 PWM 范围、不自动重试。
- **序列**：GET_STATUS → BEGIN_BENCH → BENCH_HOLD_MODE → 20× 无 PWM HEARTBEAT → STATUS →
  BENCH_HOLD 1500 → 60× HEARTBEAT → BENCH_HOLD 1450 → 60× HEARTBEAT → STATUS → DISARM。
- **结果**：**151 COMMAND / 151 RESPONSE / 151 MATCHED；151 条应答 0 NUL；0 corrupt_response；
  0 COMMUNICATION_ERROR；0 FAULT**。PWM 命令仅 1500/1450；PWM 期间心跳 120 次；
  heartbeat 时延 median 100.14 ms（max 101.64）；BENCH_HOLD 时延约 127.6 ms；
  boot_id `818fa…` 全程未变；最终 **DISARMED / DISABLED_UNMEASURED / commanded=null**。
- **解读**：在舵机电气隔离、GPIO4 仍输出 1500/1450 PWM 的条件下，S3 固件/Serial/UART 路径
  干净。因此“GPIO4 输出 PWM”本身（无舵机负载/无反向供电）不足以造成 NUL/超时；真实 PWM
  故障与舵机接通/通电（电流/地/EMI）或机械负载相关。**不证明 EMI，也不证明供电故障。**
- **未执行**：未做有舵机动力测试；未改固件/Dashboard/FSR/PWM 范围。
- **文档**：新增 [测试 A 报告](P3B1_TEST_A_NO_SERVO_PWM.md)；更新 I-219。
- **下一步（待单独授权）**：Phase B——有舵机动力、无杯、机械空载；1500/1450 + 60 次心跳；
  测 5V/地电位/停止位置重复性；Phase B 前不继续夹杯。

## 2026-11-16｜P3-B1 真实 PWM 期间串口应答损坏（空杯未成功）｜hw/p3b1-fsr-real

- **实际过程**：console 选择模式 1 成功；`1500` ACK、`1450` ACK；操作者观察 1450 附近机械爪不再运动；
  准备输入 `1400` 时出现 `response_timeout`。**日志中没有 1400 的 COMMAND/TX，1400 未发送。**
- **最后命令**：`HEARTBEAT` seq 31，request_id `1584ec4baf6f487eb61c3f759459b7b6`，
  16:51:24.861Z；最后 PWM 命令是 `BENCH_HOLD` 1450 μs seq 23（16:51:16.506Z），
  ACK `ACTIVE / TARGET_COMMANDED / PWM_COMMANDED_UNMEASURED`，无输出 API 错误。
- **超时直接原因**：16:51:24.961Z RX 957 B ACK 含 **7 个 NUL**（首个偏移 364），
  `state`/`fault_reason` 字符串被 NUL 替换；request_id 与最后 heartbeat 一致，
  `json.loads` 失败后主机记录 `corrupt_response`，3 s 后超时。
  **不是无 RX、不是 request_id 不匹配、不是会话内重启（boot_id `ba1412…` 未变）、
  不是设备 FAULT（损坏 ACK 仍 ACTIVE/TARGET_COMMANDED/PWM_COMMANDED_UNMEASURED）。**
- **关键对比**：无 PWM 验证 64/64 应答 0 NUL；本轮真实 1500/1450 输出后 heartbeat ACK 出现 7 NUL。
  唯一新增因素是舵机真实输出并可能在 1450 处堵转。**LEADING_HYPOTHESIS：舵机电流/地弹/EMI 耦合
  S3 UART TX**；TX 预留修复把 NUL 从 12/13 降到 7，但无法防止电气损坏。机制未证实。
- **1450 后不运动**：现场补充：**1500 时舵机确实运动；1450 ACK 后舵机突然停止，之后不再运动。**
  1450 控制侧已接受并施加（无 `output_api_stage`/写失败/频率失败）。**停止发生在主机超时前约 11 s
  （比 S3 5 s 通信超时早约 13 s），不是通信超时/PWM off 造成的**；最可能是目标到位/机械闭合限位，
  舵机供电/连接失稳不能排除；精确位置 **UNKNOWN**。FSR 1450 附近约 0.2–0.9M counts（高于近零基线），
  但本轮 capture 起点在 1500 之后，**没有干净空载基线**；FSR 最大值 2,614,877 出现在 16:54:17
  （超时之后），不能归因于 1450。
- **设备状态**：会话内 boot_id `ba1412…` 从连接到损坏 ACK 未变；16:56:15 只读 STATUS 查询
  （PM15S 动力断开）得到新 boot_id `caff3b25…`、uptime 1919 ms、DISARMED、BOOT、DISABLED_UNMEASURED。
  **打开 S3 串口会复位板子**，新 boot_id 是查询造成的，不是 PWM 期间重启证据；查询后通信正常。
- **数据保存（未标记成功）**：console 日志
  `logs/real/bench/2cedfa9ef4e342dda5431b9556a61b44/transport.jsonl`（SHA `a22cbd6f…`）；
  FSR `evidence/p3b1/private/cup_manual_real_20261115T165114Z/`（14,268 SAMPLE、100% valid、
  231.7 s）；失败证据包 `evidence/p3b1/private/pwm_timeout_20261116/summary.json`。
- **未执行**：未发送 1400、未继续 PWM/运动、未自动重试、未扩大超时、未启用 AUTO/Dashboard。
- **文档**：新增 [PWM 期间串口损坏诊断](P3B1_PWM_ACTIVE_SERIAL_CORRUPTION.md)；问题 I-218/I-219。
- **下一步（待授权/现场）**：隔离 PM15S 断电只发命令、PM15S 上电但机械空载、检查独立电源/共地/
  体电容/线束走向；确认机制前不继续真实空杯运动。

## 2026-11-16｜S3 修复固件重烧与无 PWM 验证 PASS｜hw/p3b1-fsr-real

- **重烧**：用户授权仅 `/dev/cu.usbserial-A5069RR4`，PM15S 独立动力电源断开；Arduino CLI 1.5.1 +
  esptool 5.1.0，**460800**，`EraseFlash=none`，无全片擦除；app `bd039a8…`（317840 B），
  bootloader/partitions 一致，每段 `Hash of data verified`。
  日志 `evidence/stage09b26/upload_s3_txfix_20261116T004412.log`。
- **真实无 PWM 序列**：`GET_STATUS` → `BEGIN_BENCH` → `BENCH_HOLD_MODE` → 3× `HEARTBEAT` →
  `STATUS` → `DISARM`，全部 PASS；最终 `DISARMED` / `DISABLED_UNMEASURED`。
- **连续命令复测**：5 次 `BEGIN_BENCH`→`BENCH_HOLD_MODE`→`HEARTBEAT`→`STATUS`→`DISARM` 全部 PASS；
  20 次背靠背 `HEARTBEAT`（无 sleep）全部 PASS。
- **统计**：64 COMMAND / 64 RESPONSE / 64 MATCHED；**64 条应答行 0 NUL、0 `corrupt_response`、
  0 `COMMUNICATION_ERROR`、0 FAULT**。连接时 ESP-ROM 启动 banner 106 条被过滤（其中一条 993 B
  含 264 NUL，属启动输出，不是控制应答）。
- **未发送 PWM、未驱动 PM15S、未启用 AUTO**；`BENCH_ACTION=0`、`pwm_commands=[]`。
- **证据**：`logs/real/bench/s3_txfix_verify_20261116T004448/transport.jsonl`
  （SHA `acedc696…`）、`evidence/stage09b26/s3_txfix_verify_summary.json`。
- **状态**：S3 TX 背压缺陷 **RESOLVED / VERIFIED_REAL（无 PWM）**；空杯 MANUAL 尚未重新开始，
  等待用户明确恢复；Dashboard LIVE 握手仍未验证（I-215），未作为前置条件。

## 2026-11-16｜P3-B1 S3 控制台 response_timeout 诊断与 TX 背压修复｜hw/p3b1-fsr-real

- **触发**：两次真实空杯 MANUAL 会话在 BEGIN_BENCH/模式选择后 `response_timeout`；均未发送 PWM、
  无 `BENCH_ACTION`、无机械运动。日志：
  `logs/real/bench/99f2a8023a344652b1a5c4e18e2756a6/`、`logs/real/bench/297580c6c93a4978921634193f34d3c6/`。
- **最后命令与 RX**：
  - 会话 1：`HEARTBEAT` seq 30，request_id `e4fddfe2f3f749f5b405adc071747545`，16:30:17.482Z；
    16:30:17.581Z RX 950 B ACK，**12 个 NUL**（首个偏移 103），request_id/state/last_sequence 仍完整；
    16:30:20.577Z 超时。
  - 会话 2：`BENCH_HOLD_MODE` seq 4，request_id `4d0c5503cd794368b2b171fa20c57e17`，16:31:45.928Z
    （BEGIN_BENCH ACK 后约 0.00004 s）；16:31:46.027Z RX 948 B ACK，**13 个 NUL**（首个偏移 595）；
    16:31:49.026Z 超时。
  - 分类：不是无 RX、不是 request_id 不匹配、不是固件重启（失败时无 ESP-ROM banner，boot_id 未变）、
    不是设备 FAULT（损坏 ACK 仍为 ARMED / BENCH_HOLD_SELECTED / DISABLED_UNMEASURED）；
    是 **TX 背压导致应答 JSON 中间出现 NUL 空洞**，主机解析失败后按 `boot_or_invalid_json` 丢弃并超时。
- **根因**：`respond()` 原阈值 `availableForWrite()<900` 小于实测 942–963 B 的 ACK/STATUS；
  连续命令时剩余空间 900–949 B，`serializeJson` 溢出，写出 12/13 B NUL。原 `<900` 分支还只
  `safety->fault()` 而不返回 ERROR，主机只能超时。
- **最小修复**：`measureJson(d)+2` 精确预留；`waitForTxSpace` 有界等待 150 ms（主机超时 3 s）；
  仍不足时发紧凑匹配 `ERROR`（`TX_BACKPRESSURE`）再 fault；保留全部通信保护。主机
  `SerialClient` 对长且以 `{"protocol_version"` 开头但解析失败的帧记录
  `IGNORED reason=corrupt_response length=… nul_count=…`，不修改超时。
- **离线验证**：`python3 scripts/build_firmware.py s3` **PASS**，修复 app
  `bd039a8ae54bb908c3d8afefcf1eb60326ff7c80d9fd3cca9620faec05cb48ee`（317840 B）；
  新增 NUL 损坏行测试；全套 **380 tests OK（1 PTY skipped）**。**未重烧 S3、未发 PWM。**
- **失败实验 FSR 原始数据（无 PWM，非空杯结果）**：
  `evidence/p3b1/private/cup_raw_20261115T163014Z/`，17,392 SAMPLE、17,391 有效、
  1 条 malformed（frame 10260）、281.708 s、61.734 Hz、基线中位 1,810 counts、
  `0x04` 7,908；失败证据包 `evidence/p3b1/private/console_failure_20261116/summary.json`。
- **Dashboard LIVE**：真实握手复测仍失败；未验证修改已保存
  `evidence/p3b1/private/dashboard_handshake_unverified.patch`，未提交、未合并，不再作为空杯前置条件。
- **文档**：新增 [S3 TX 背压诊断](P3B1_S3_TX_BACKPRESSURE_DIAGNOSIS.md)；更新问题 I-215/I-217/I-218。
- **下一步**：申请重烧授权（`bd039a8…`，PM15S 动力断开），做一次无 PWM 的
  GET_STATUS → BEGIN_BENCH → BENCH_HOLD_MODE → HEARTBEAT×N → STATUS → DISARM；稳定后再重跑 console。

## 2026-11-16｜P3-B1 S3 控制固件恢复与真实 STATUS｜hw/p3b1-fsr-real

- **授权/范围**：仅 `/dev/cu.usbserial-A5069RR4` 的 ESP32-S3 恢复；PM15S 独立动力电源断开
  （用户确认）；未发 PWM、未启动 AUTO、未操作旧 ESP32 FSR 固件、未做机械动作。
- **构建**：`python3 scripts/build_firmware.py s3` **PASS**（app 316139 B，10%）。
  完整 FQBN `esp32:esp32:esp32s3:FlashSize=16M,FlashMode=qio,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB,
  UploadSpeed=921600,USBMode=hwcdc,CDCOnBoot=default,UploadMode=default,EraseFlash=none`。
  生成头 `generated_config_s3.h` 与构建前逐字节一致，SHA `83c8af…`；`config/gripper_s3.json`
  `b4929f…`；`.ino` `7f709f…`；`SafetyCore.h` `dc083e…`，均与历史清单一致。
  `CFG_FIRMWARE_VERSION=gripper-control-s3-0.9b26.0`、GPIO4、50 Hz、14-bit、
  `HARDWARE_ENABLED=false`、`BENCH_ENABLED=true`、`CALIBRATED=false`。
- **产物**：app `d20782808447385a2ad090e63082f55e7f824652220441f07230f9dbf89830c4`（316288 B）；
  bootloader `a9e464…`；partitions `ace025…`；merged `71da3c…`；ELF `8bb2c8…`。
  历史验收 app `04c77eed…`（316272 B）与本次不是逐字节相同；bootloader/分区表/生成头/源码/
  配置一致，16 B 差异与构建路径/工具链非确定性一致，已从新二进制确认版本字符串。
- **上传**：项目 Arduino CLI 1.5.1 + esptool 5.1.0，端口 `/dev/cu.usbserial-A5069RR4`，
  **460800**（历史成功值），无全片擦除；每一段 `Hash of data verified`，**PASS**。
  日志 `evidence/stage09b26/upload_s3_20261115T235933.log`，SHA `76175d…`。
- **真实 STATUS（只发 GET_STATUS）**：`gripper-control-s3-0.9b26.0`、`board_target=esp32s3`、
  `pwm_gpio=4`、`pwm_frequency_hz=50`、`pwm_resolution_bits=14`、`chip_model=ESP32-S3`、
  Flash 16 MB、PSRAM 8 MB、**DISARMED**、`hardware_enabled=false`、`UNCALIBRATED`、
  `bench_capable=true`、`bench_active=false`、`output_state=DISABLED_UNMEASURED`、
  `commanded_pulse_us=null`、`fault_reason=BOOT`（启动原因，不是故障）。
  通信：1 次 GET_STATUS 匹配，159 条启动 banner 被过滤，0 ERROR/0 FAULT/0 timeout。
  完整 JSON `evidence/stage09b26/s3_status_20261116T000018.json`，SHA `6f8d1e…`。
- **文档**：新增 [S3 固件恢复记录](P3B1_S3_FIRMWARE_RECOVERY.md)。
- **下一步**：S3 已可进入 MANUAL；按已授权 **1300–1500 μs、50 μs 步进、1300 下限（不进 1270）**
  做无杯方向与空杯抓取，FSR 只记录不闭环；每 trial 前采连续空载基线。

## 2026-11-15｜P3-B1 真实 FSR_A 数据接管与探索性分析｜hw/p3b1-fsr-real

- **现场继承**：分支基线 `af1758e`（main 合入 PR #5 后）。Codex 已完成的真实采集在本地
  `evidence/p3b1/private/real_20261115_2314/`：固件 `tactile-fsr2-0.3.0`、`FSR_ONLY`、
  ADC4 AIN0/MUX8、921600 8N1、约 85.0 s、5247 个 SAMPLE。未重新初始化、未覆盖原始 JSONL。
- **数据质量（VERIFIED_REAL）**：5247/5247 有效，帧序 1–5247 无缺帧/重复，实测 61.74 Hz，
  ADC4 全程 `OK`，无饱和；ADC1–3 全程 `NO_RESPONSE`（本构建只装 ADC4，符合预期）。
  仅 3 帧 flag `0x04` 负单端（68.73–68.77 s，−124161/−230142/−1592）；采集开始有 1 条 875 B
  非 JSON 串口噪声，已丢弃，未进入样本。
- **关键发现**：采集脚本按三段式预写的 marker（25/32/40/47/55/62/70 s）与实际操作不符；
  操作者是“先一处按压、调整位置、另一处中等力度施压”。旧的窗口统计因此无效，已保留为
  `capture_analysis_schedule_assumed.json`，并用数据驱动分段生成 `capture_analysis_v2.json`。
  初始稳定段中位 4.163M counts、σ≈16k；约 4.6 s 首次持续下降 −470k、约 48.8 s 大幅下降 −1.72M、
  约 70 s 后方差下降并缓慢回升（+44.6k counts/s），但 85 s 内未回到初始基线。
  采集起点很可能是**第一处按压已在进行**，0–4.2 s 的 4.16M 不是已验证空载；按此读法，
  4.6 s 与 48.8 s 的下降是部分释放/释放移动，70 s 后的上升是第二处按压，方向与
  `VOLTAGE_RISES_WITH_FORCE` 一致。事后 15:37Z 的近零空载基线（见下）进一步支持该读法；
  但原始 capture 不是同一 trial 的连续空载→夹持→释放，极性标为 **SUPPORTED（非单 trial 验证）**。
- **结论**：FSR_A 对真实接触/位置变化有清晰、远超噪声的响应，初步响应验证 **成功**；
  不需要重做手指三段式。counts→牛顿/摩擦/滑移/杯重均 **NOT_SUPPORTED**；按压位置/力度/时间
  **NOT_TESTED**。
- **文件**：新增 [P3-B1 分析报告](P3B1_FSR_REAL_ANALYSIS.md) 与
  [真实曲线图](screenshots/p3b1/fsr_a_real_curve_v2.png)。原始 JSONL/CSV 留在本地 `evidence/`，未提交。
- **离线检查**：`tests.test_dashboard`、`tests.test_p3a_firmware_dashboard`、`tests.test_pwm_console`
  共 20 项 OK；`tests.test_fsr2_protocol`、`tests.test_fsr2_config` 共 51 项 OK。
- **事后空载基线复测（非阻塞）**：15:34Z 的 8 s 采集 485 帧中 19 帧 flag 0x04、中位 614k、
  值 0–1.57M → 释放过程中的余压/部分接触；15:37Z 的 8 s 采集 494 帧中 **230 帧 flag 0x04**、
  中位 1.7k、值约 −12k…+16k counts → 已释放的近零空载基线。ADC4 仍 `OK`，负帧是 0 附近
  零点噪声（±15k counts ≈ ±6mV），不是通信故障。**FSR_A 工作正常；空杯 trial 仍需在夹持前
  重新采连续空载基线。**
- **Dashboard LIVE 连接修复（OFFLINE_VERIFIED；REAL 复测 NOT_TESTED）**：真实 LIVE 首次启动显示
  “协议异常 · 帧已拒绝”。根因是 macOS 打开 FSR 串口会复位 ESP32；`SerialSensorTransport`
  在 `boot_wait_s=0` 时立即发 HELLO，2 s 握手窗口内只读到 boot HELLO 的半行，严格解析器拒绝后
  超时。最小修复：`config/sensor_serial.json` 的 `boot_wait_s` 改为 2.5 s；transport 在 boot wait 后
  清空输入缓冲并丢弃半行。离线测试 27 项 OK（含新增 boot 半行测试）。真实复测需要再次独占
  FSR 串口，本次升级请求被用户拒绝，故 REAL 复测 **NOT_TESTED**。
- **未执行**：未打开舵机串口、未发 PWM、未做机械动作、未重新烧录、未做 AUTO。
  当前 Mac 只枚举到旧 ESP32 的 CP2102；S3 的 FT232R 串口未出现，空杯实验暂不能开始。
- **下一步**：唯一硬件阻塞是 S3 FT232R 端口未枚举；确认 S3 板上的 USB **数据**口直连 Mac 后，
  按已授权范围 **1300–1500 μs、50 μs 步进、1300 下限（不进 1270）** 执行空杯 MANUAL；
  用户在自己的真实终端运行 `pwm_console.py --target s3`，本进程独占 FSR 串口采集；
  随后运行 Dashboard LIVE 的 FSR_A 曲线。

## 2026-11-15｜P3-A PR #5 复核增量｜integrate/hybrid-demo-v2

- 项目所有者确认唯一正常的 FSR_A 为 ADC4 AIN0，MUX 8，FSR_B 已损坏。新增现行 1/13 通道固件与 Dashboard，12 电极模式保持。原 2/14 通道 fixtures 与 Trial 继续兼容。[总控确认](https://github.com/royaleric24/tactile-gripper-a/pull/5#issuecomment-6895547216)
- 独立「36 格仿真」复用原热力图与合成格值，展示页没有控制、记录或真实设备输入。电极图仍是 R1–R6 / C1–C6 的 ADC 条形图。
- 固件样例的单 FSR 接触评分使用 FSR_A 与显式空载基线。离线 AUTO 拒绝坏帧、无效或饱和的 FSR_A、过期帧、失联及未确认指令。`AUTO_REAL_ENABLED=False`。
- 完整测试、五个 ESP32 构建、浏览器截图及复现命令见 [P3-A 验收报告](P3A_ACCEPTANCE.md)。物理隔离、映射、采样与机械闭环留待 P3-B；复核提交停在 [PR #5](https://github.com/royaleric24/tactile-gripper-a/pull/5)。

## 2026-11-15｜P3-A 首轮离线集成（历史基线 7e6c425）｜integrate/hybrid-demo-v2

- 从 GitHub 核对四条分支；文档起点 `633e570`。保留硬件 PR #2 `0827536` 与软件 PR #4 `2c5a996` 的 merge 历史。两个合并仅有文档冲突，原始组内内容按历史分节保留。
- V2 Dashboard 消费同一固件参考解析器；校验 profile、布线元数据、状态、通道编号、掩码与 null、会话、序号和时间。采集串口默认 921600 8N1，启动只握手及只读查询，原设置不自动开流。
- 2/12/14 通道的固件 host 仿真原帧进入实际 Dashboard / Trial / CSV / REPLAY。通信与数据质量分开。离线 AUTO 拒绝坏数据、掉线、过期与未确认命令；保持真实开关关闭。
- 测试、截图、失败记录与复现命令见 [P3-A 验收报告](P3A_ACCEPTANCE.md)。状态 **OFFLINE_VERIFIED，待总控审查集成 PR**；项目没有开始 P3-B 实机操作。

> 当前唯一总体路线：`docs/DEMO_PLAN_V2.md`；硬件接线：`docs/WIRING_FREEZE_V2.md`。只记实际完成内容，计划不冒充完成。每项进展结束同步此文件、根 `AGENTS.md` 和问题台账。

## 2026-11-15｜压敏布接线修正 / 文档同步｜docs/demo-v2

- **来源**：项目所有者在 2026-11-15 确认真实压敏布接线：12 根电极（R1–R6 各接 ADS1220 AIN + 各自 10 kΩ 下拉到 GND；C1–C6 各接 ADS1220 AIN + 各自 1 kΩ 上拉到 3.3 V），**无 GPIO 列激励、无 HI_Z、无 36 点扫描**。
- **改动（文档层，OFFLINE）**：`docs/WIRING_FREEZE_V2.md` 增加修正横幅与焊接检查清单，§4 改为 12 电极被动读取、§4.1 留空映射表（PENDING_REAL_WIRING）、§4.2 记录已废止方案；`docs/HARDWARE_DESIGN_V2.md`、`docs/DEMO_PLAN_V2.md` 删除列驱动/36 点承诺；`docs/PROTOCOL_V2_PROPOSAL.md` 新增 `MATRIX_ELECTRODES_12` 提案、`HYBRID_6X6_FSR2` 标记 HISTORICAL；`config/hybrid_sensor_v2.template.json` 改为 12 电极模板（空映射、FSR_ONLY 选中、不写 ADC/AIN 编号）；同步根 `AGENTS.md`、`docs/PROGRESS.md`、`docs/ISSUES.md`、`docs/HANDOFF_CURRENT.md` 及残留引用页。
- **测试命令与结果**：仅离线文档/JSON 检查（JSON 解析、全文 grep 检索“GPIO 列激励 / HI_Z / 36 点”）；**未运行**固件、串口、烧录、采样、PWM 或 AUTO。
- **状态**：所有真实设备相关动作暂停，等待项目所有者明确授权与真实接线记录（映射填表）。`MATRIX_ELECTRODES_12` 为 PROPOSED（validated=false）；`FSR_ONLY` 仍是当前唯一可用 profile。
- **关联问题**：I-004 改记“前提作废”；新增 I-012（映射缺失）、I-013（12 电极≠36 压力点）、I-014（HYBRID 禁用）、I-015（软件提交 8d4d7d8 未推送/评审）；I-009 状态不变，措辞更新。
- **下一步**：等真实焊接/台架记录填 `WIRING_FREEZE_V2.md` §4.1；填全并复核后再讨论生成固件 `channel_config`；在此之前不做任何实机采集或烧录。

## 2026-11-14｜P0 工程保护 / P1 文档落地｜docs/demo-v2

- **P0 OFFLINE_VERIFIED**：检查三目录 Git/HEAD/worktree、暂存/未暂存/未跟踪/忽略文件；实际共享旧 Git 仓库，main 与软件目录干净，硬件 7 修改 + 7 未跟踪。完整快照覆盖 47,302 个普通文件、8,556,395,224 字节；归档逐文件 SHA-256 与备份后原文件复核通过。数据目录候选 707 个文件、183,684,501 字节（含模拟/回放，未逐条判为实测）。原目录未写入。
- **P1**：从在线核实的公开 main `5ee92cd5a599bef497566638c7754e40a2edac4a` 创建独立 clone 和 `docs/demo-v2`。对照 ZIP 17 个文件，增量引入 docs 与 JSON；合并 README 导航及 AGENTS 规则，保留既有接口主体、历史报告、子目录指令、代码与锁文件。包内 REVIEW_FIRST/NEW_CHAT_PROMPT 留在私有来源快照。
- **检查**：检查方法与结果见 [LOCAL_INTEGRATION_V2.md](LOCAL_INTEGRATION_V2.md)。仅离线文件检查；未运行新硬件、固件烧录、串口、PWM 或 AUTO。
- **问题**：I-008 旧/公开历史隔离；I-009 协议与施工状态保持待验证；I-010 记录继承的 6 个历史缺失证据链接。I-001 设计映射维持 RESOLVED，实机验证不随文档导入升级。
- **下一步**：文档提交/PR 评审后，两组从公开组分支另建工作区开展离线任务；现场动作依后续明确授权。本次提交 SHA 由 Git 与私有交付报告记录，避免自引用。

## 2026-11-14｜交接包编制历史（导入前，仅文档副本）

- **任务**：对齐旧 ESP32 四 ADC 的引脚关系，落实文档协作与长上下文交接规则。
- **用户确认**：ADC1 `CS21/MISO34`，ADC2 `CS22/MISO35`，ADC3 `CS5/MISO26`。ADC4 `CS32/MISO33` 是后续新设计。
- **完成**：仅修改本次交付的离线文档副本、更新 JSON 配置模板、补充协作规则与交接模板。未进入本地三个工作目录，未执行真实硬件测试、Git 合并、GitHub push、Codex/DSH 操作。
- **文档核验**：对输出 JSON 解析、目标链接与旧 MISO 误标做静态检查。此项不等于固件编译或实机验证。
- **实际工程状态**：硬件分支与软件分支原有成果分别存在；V2 四 ADC/FSR 还未集成，Dashboard V1.0 仍是离线功能完成、真实 AUTO 未联调。
- **下一步**：在新对话先审查本地三个目录的实际 Git/worktree 与未提交文件；安全引入文档，再分配硬件组（ADC4/FSR）和软件组（协议/界面）的并行开发。

## 后续每次记录模板

### YYYY-MM-DD｜任务 / 阶段 / 分支

- 执行者与工作目录：
- 改动文件及功能：
- 测试命令与结果（OFFLINE / REAL / NOT_TESTED）：
- 证据/运行输出位置：
- 已解决问题与关联 Issues：
- 当前 Git SHA / 未提交文件状态：
- 下一项行动及依赖：

- 2026-11-14 补充核验：硬件 14 个 WIP 文件已恢复到隔离目录并逐文件核对 SHA-256，符号链接目标与清单一致。接线文档的 Markdown 行尾空格在暂存检查中被发现，已去除；保留首个提交，使用追加提交修正。

## 硬件组证据记录

## 2026-11-15｜压敏布 12 电极接线修正（离线）｜hw/fsr-v2

- **触发**：用户更正实物接线——R1–R6 各接一个 ADS1220 AIN 并各用 10 kΩ 下拉 GND；C1–C6 各接
  一个 AIN 并各用 1 kΩ 上拉 3.3 V。**不存在 GPIO 列驱动 / HI_Z / 36 点扫描**。
- **撤回**：`HYBRID_6X6_FSR2`（38 通道、36 扫描单元）标记为历史性实验实现；`COLUMN_SCAN_6X6`、
  `driveColumn()`、`parkColumns()`、GPIO 列激励代码与配置已从本分支删除；生成器对 HYBRID 直接
  报错，参考解析器报 `PROFILE_HISTORICAL`。
- **新增**：`MATRIX_ELECTRODES_12` profile（12 逻辑通道；+2 FSR = 14），R/C 各自独立单端读数，
  `electrode_layout` 描述 6 行 + 6 列、偏置方式与映射状态。真实 R/C→ADC/AIN 映射**仍缺失**，
  配置 `electrodes.map` 为空、`mapping_status = PENDING_REAL_WIRING`，生成头对 12 个通道使用
  0xFF sentinel，固件输出 `null` + `NO_DATA`，不伪造数值。
- **固件**：`firmware/sensor_fsr2/` 的驱动、帧构造器、采样器、sketch 与三个 profile 头文件同步
  更新；FSR_ONLY 采集路径保持不变并通过同一套回归测试。
- **离线证据**：
  - host 模拟 4 个用例 PASS（driver / FSR_ONLY / 14 通道未映射 / 12 通道合成映射）
  - `scripts/check_fsr2_frames.py` PASS，重建 9 个 fixtures（删除 3 个 hybrid fixtures）
  - `tests/test_fsr2_*.py` 49 用例 OK；仓库全量 python 套件 190 用例 OK
  - 三 profile 离线编译 PASS：FSR_ONLY 303819 B、12 电极 312611 B、12 电极 + FSR 312659 B
- **状态**：接线、烧录、上电、串口、采样、PWM、AUTO **全部暂停**，等待用户明确通知与现场映射表。
- **关联问题**：I-106（接线修正待现场复核）、I-107（R/C→ADC/AIN 映射缺失）、I-108（12 电极
  ≠ 36 压力点）、I-109（HYBRID 已封存）、I-110（合成映射样本仅供测试）。

## 2026-11-14｜V2 四 ADC + 双 FSR（FSR_ONLY 优先）

| 项 | 状态 | 证据类型 |
|---|---|---|
| V2 引脚与 profile 配置（`config/sensor_esp32_fsr2*.json`） | IMPLEMENTED | 生成器校验 + 单测 |
| 第四颗 ADS1220 driver（`ads1220_multi.*`，无 V1 配置依赖） | IMPLEMENTED_UNVERIFIED | host 模拟 31 条断言 |
| 帧构造器 / 采样器 / 命令层（`frame_builder_fsr2.*`、`sampler_fsr2.*`、`sensor_fsr2.ino`） | IMPLEMENTED_UNVERIFIED | host 模拟 + 离线编译 |
| FSR_ONLY 固件离线编译 | **PASS（离线编译）** | `evidence/fsr2/build_sensor_fsr2/` |
| HYBRID_6X6_FSR2 固件离线编译 | **PASS（离线编译）** | `evidence/fsr2/build_sensor_fsr2_hybrid/` |
| host 模拟（driver + sampler + hybrid sampler） | **PASS（host 仿真，非硬件）** | `evidence/fsr2/host_tests/` |
| 帧往返检查与 fixtures 生成 | **PASS（host 仿真，非硬件）** | `evidence/fsr2/frames/`、`tests/fixtures/fsr2/` |
| 参考解析器 `tools/fsr2/protocol_v2.py` | IMPLEMENTED | 18 条协议单测 |
| 真实接线 / 烧录 / 采样 | **NOT_STARTED（未授权）** | — |

### 历史复现命令（含已撤回的 HYBRID，不可用于当前 V2）

```bash
python3 scripts/generate_sensor_fsr2_config.py                      # FSR_ONLY 头文件
python3 scripts/generate_sensor_fsr2_config.py \
  --config config/sensor_esp32_fsr2_hybrid.json \
  --output firmware/sensor_fsr2/fsr2_config_hybrid.h
python3 scripts/run_fsr2_host_tests.py                              # g++ host 模拟
python3 scripts/check_fsr2_frames.py                                # 帧检查 + 重建 fixtures
ARDUINO_CLI="/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli" \
  python3 scripts/build_sensor_fsr2_firmware.py --build-dir "$PWD/evidence/fsr2/build_sensor_fsr2"
ARDUINO_CLI="..." \
  python3 scripts/build_sensor_fsr2_firmware.py --profile hybrid \
  --build-dir "$PWD/evidence/fsr2/build_sensor_fsr2_hybrid"
PYTHONPATH=src:. python3 -m unittest discover -s tests -p "test_fsr2_*.py"
```

`--build-dir` 必须是绝对路径（脚本用 `Path.relative_to` 记录证据路径）。

### 构建体积（离线编译结果）

| profile | program | 全局变量 |
|---|---:|---:|
| FSR_ONLY | 303471 B (23%) | 32872 B (10%) |
| HYBRID_6X6_FSR2 | 312695 B (23%) | 32872 B (10%) |

fqbn `esp32:esp32:nodemcu-32s`，arduino-cli 1.5.1，Arduino-ESP32 core 3.3.2。

### 实测行长度（帧构造器真实输出，非估算）

HELLO FSR_ONLY 1650 B；SAMPLE FSR_ONLY 931 B（ADC4 掉线 964 B）；
HELLO HYBRID 6554 B；SAMPLE HYBRID 2311 B。发送缓冲 8192 B。

### 下一步（需要现场授权）

接线核对 → 烧录 → 921600 打开串口收 HELLO → 空载基线 → 单路按压 → ADC4 断线/恢复语义。
逐条动作见 `docs/hardware/FSR_ONLY_INTERFACE_V2.md` §11。做完后把原始帧与 AVDD 实测值补到本文件，
并用真实样例替换/补充 `tests/fixtures/fsr2/`（现有一律来自 host 模拟）。

## 软件组记录（P2-S 历史快照）


更新：2026-11-14
分支：`sw/fsr-live-v2`（基于公开 `feat/dashboard-zh-v1` `9997853`）

> 本文件是任务分支的 P2-S 进度。V2 文档 PR #1（`docs/demo-v2` → main）尚未合并，
> 因此没有复制/覆盖 `docs/demo-v2` 的原始文档；PR #1 合并后再统一对齐路径与内容。

## 状态总览

| 条目 | 状态 | 证据/说明 |
|---|---|---|
| FSR_ONLY 2 通道 + HYBRID 38 逻辑通道 | PASS（离线） | HELLO/config 校验与 fixtures；不按设备猜矩阵 |
| 两路 FSR 原始 ADC/电压/相对变化/有效/趋势 | PASS（离线） | 单测 + 三个 Dashboard 路由启动；未做真实视觉走查 |
| 矩阵热图只消费 MATRIX_CELL，按 row/col | PASS（离线） | FSR 36/37 排除测试 |
| 显式空载基线 + 相对接触评分 | PASS（离线） | 无自动伪造真实基线；设备重启清基线 |
| 四态 + 无效/未标定滞回 | PASS（离线） | 边界、饱和、双 FSR 较弱通道测试 |
| 未完成命令/无效帧/过期帧不夹紧 | PASS（离线） | 策略返回 WAIT/FAULT，不调用 PWM |
| 真实 AUTO 关闭 + 显式未来入口 | PASS（离线） | `AUTO_REAL_ENABLED=False`；commissioning 必定拒绝 |
| 双设备身份/波特率/STATUS 查询 | IMPLEMENTED_UNVERIFIED | 921600 可配置；查询默认关闭；无真实串口 |
| Trial 原始帧/身份/命令/ACK/决策/CSV | PASS（离线） | 写入与导出测试；旧字段兼容 |
| Trial frames 直接 REPLAY | PASS（离线） | 自动补 HELLO 并解包 SENSOR_FRAME |
| Dashboard 三路由启动 | PASS（离线） | 当前测试套件覆盖 |
| 真实 FSR 电压/矩阵方向/串口链路 | UNKNOWN | 需硬件组确认基准、接线、扫描与方向 |
| 真实闭环 Demo | NOT_IMPLEMENTED | 未连接真实串口/烧录/动作 |

## 验证命令

```bash
PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests -v
# 278 tests, OK
```

离线演示：

```bash
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo \
  --demo-profile FSR_ONLY --data-root /tmp/gripper-fsr-demo --port 8080
```

## 2026-11-15 · 12 电极适配与 Dashboard 视觉验收

用户确认的最新接线：R1–R6 分别接 ADS1220 AIN，各自 10 kΩ 下拉到 GND；
C1–C6 分别接 ADS1220 AIN，各自 1 kΩ 上拉到 3.3 V。这不是 GPIO 逐列激励，
R/C 到具体 ADC/AIN 的物理映射仍待现场确认，12 个电极不能冒充 36 个压力点。

| 条目 | 状态 | 证据/说明 |
|---|---|---|
| `MATRIX_ELECTRODES_12` 配置与校验 | PASS（离线） | 12 个 `MATRIX_ELECTRODE`；row/column 索引各覆盖 0..5；禁止矩阵位置 |
| 12 路原始 ADC 仿真与图表 | PASS（离线） | 条形图 R1–R6/C1–C6；`heatmap_options` 对电极配置返回空图 |
| 不合成 36 点热图/接触评分 | PASS（离线） | 仿真不产生 contact_score；Live/Analysis 显示“36 点热图不可用” |
| FSR_ONLY / HYBRID / Trial / CSV / REPLAY | PASS（离线） | 既有 278 个测试保持通过，新增 7 个电极测试 |
| Dashboard 三视口 × 三页面视觉验收 | PASS（离线） | `docs/screenshots/p2s-ui-audit/`；console/page error 0 |
| R/C→ADC/AIN 物理映射 | UNKNOWN | 需硬件组现场确认 |
| 真实电极测量、串口、PWM、机械动作 | NOT_IMPLEMENTED | 本阶段未连接任何硬件 |

验证命令与结果（2026-11-15）：

```bash
PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests
# Ran 285 tests ... OK
```

UI 验收命令与截图脚本见
[docs/screenshots/p2s-ui-audit/README.md](screenshots/p2s-ui-audit/README.md) 与
`scripts/ui_screenshot_audit.mjs`。

## 2026-11-15 · P2-S 发布前最终验收（离线）

用户要求做发布前最终验收：核实工作区、重跑测试、实测 Dashboard、修复明显问题、
补文档、提交并推送软件分支、创建 PR（不合并）。本轮未进入新开发阶段，未接硬件。

### 验收环境

| 项 | 值 |
|---|---|
| 工作区 | `tactile-gripper-v2-sw`（本机 checkout，路径按机器而异） |
| 分支 | `sw/fsr-live-v2` |
| 验收前 HEAD | `884a8c41bc204d4e9c958c3b7c3821f8130103e7` |
| 公开基线 | `origin/feat/dashboard-zh-v1` = `999785308e0fb38659a90302a3388d82cdd0b424` |
| 祖先关系 | `git merge-base origin/feat/dashboard-zh-v1 HEAD` == `9997853`（成立） |
| Python | 3.13.15（`.venv`，`nicegui==4.0.0`） |
| 数据来源 | `SIMULATION` only（`--demo`），未打开任何串口 |

### 测试（本轮实际执行）

```bash
# 在仓库根目录执行
PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests
# Ran 290 tests ... OK (skipped=1)
git diff --check    # 无输出
```

- 290 通过 / 0 失败（Python 3.13.15）。此前交接记录的 285 项已复核：确实为 285，
  本轮新增 5 项显示层测试（`DashboardDisplayTests` 2 项、`ContactReasonTests` 2 项、
  `DynamicEventDetailTests` 1 项）。
- 1 项跳过：`test_trial_interactive_input.InteractiveInputTests.test_pty_waits_for_explicit_input`
  —— 本机沙箱无 pty（`out of pty devices`）。GitHub Actions 的 ubuntu 环境应可运行；
  本地无法证明。
- 工作区无 `tools/` 目录，CI 中 `for suite in tools/*/tests` 循环为空转。

### Dashboard 实测（重新运行，不只依赖旧截图）

```bash
# 终端 1 / 2：两个离线仿真 Dashboard（各自独立 data-root）
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo \
  --demo-profile HYBRID_6X6_FSR2 --data-root /tmp/gripper-ui-audit --port 8095
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo \
  --demo-profile MATRIX_ELECTRODES_12 --data-root /tmp/gripper-electrode-audit --port 8096

# 终端 3：真实无头 Chrome 截图 + 布局度量
CHROME_NO_SANDBOX=1 AUDIT_BASE=http://127.0.0.1:8095 OUT_DIR=/tmp/audit-final/after \
  LABEL=after node scripts/ui_screenshot_audit.mjs
CHROME_NO_SANDBOX=1 AUDIT_BASE=http://127.0.0.1:8096 OUT_DIR=/tmp/audit-final/after-electrodes \
  LABEL=after-electrodes node scripts/ui_screenshot_audit.mjs
CHROME_NO_SANDBOX=1 AUDIT_BASE=http://127.0.0.1:8095 OUT_DIR=/tmp/audit-final/narrow \
  LABEL=narrow VIEWPORTS=1024x768 node scripts/ui_screenshot_audit.mjs
```

结果：3 视口 × 3 页面 × 2 profile = 18 张视口截图 + 18 张整页审计图 + 1024×768 抽查
3 张；18 个页面 console/page error 均为 0；任何视口下 `body.scrollWidth` 都等于视口
宽度（无页面级横向滚动）。截图与度量见
[docs/screenshots/p2s-ui-audit/](screenshots/p2s-ui-audit/README.md)。

### 本轮修复（均为显示层，无协议/控制变化）

| 问题 | 证据 | 修复 |
|---|---|---|
| 帧时间显示 `3345443.070s`（主机单调时钟当秒数） | 旧 `after/live-*.png` | 帧说明改为 `接收于 HH:MM:SS（本机时间）`，取自 `host_received_utc` |
| 接触判断原因整段英文 | 旧 Live 截图 | `text_zh.contact_reason_label()` 翻译固定原因，动态原因保留数字 |
| 事件说明漏译 `SIMULATION sensor connected (PROFILE); ...` | 旧整页截图 | `event_detail_label()` 增加该前缀规则 |
| 三个页面各自复制 `_clock()`，把 UTC 当本机时间显示 | `live/experiments/analysis` | `theme.clock_label()` 统一转本机时间；表头改“时间（本机）” |
| 分析页侧栏残留“离线（OFFLINE）”“等待数据”、顶栏“待机” | 旧 `after/analysis-*.png` | 用只读 `core.snapshot()` 同步侧栏与顶栏（不新增写路径） |
| 12 电极条形图无单位、无读数、Y 轴出现 `2,134.55` 这类小数刻度 | 旧 `after-electrodes/live-*.png` | Y 轴名“ADC 计数”、柱顶读数（≤14 通道）、刻度取整 |
| 热图色条压在 C 轴标签行 | 旧截图 | 热图 `grid.bottom` 44→58，色条单独一行 |
| FSR 趋势图左侧轴名 `ADC` 与图例重叠 | 旧 `after/analysis-*.png` | 去掉与图例重复的轴名 |
| 无头 Chrome 在沙箱内启动失败时脚本静默退出 0、不产图（假 PASS） | 复现：WS 未 open 时 Promise 不落地 | `connect()` 增加 close/timeout 拒绝；新增 `CHROME_NO_SANDBOX=1` 开关 |
| `before/audit.json` 内含本机绝对路径 | `git grep /Users/` | 9 处改为仓库相对路径 |

未改：协议字段、单位换算、AUTO 门控、Trial/CSV/REPLAY 格式、硬件组固件代码。

### 发布状态

| 项 | 值 |
|---|---|
| 目标分支 | `feat/dashboard-zh-v1`（公开软件历史祖先，已确认） |
| 远程分支 | `origin/sw/fsr-live-v2`（本轮新建） |
| PR | [#4](https://github.com/royaleric24/tactile-gripper-a/pull/4) → `feat/dashboard-zh-v1`；本轮**不合并** |
| CI | GitHub Actions `Offline tests`：push 与 pull_request 两个 run 均 **PASS**（2026-11-15） |

### 状态标注

- OFFLINE_VERIFIED：上述 290 项测试、三视口截图与布局度量、AUTO 硬关闭、坏帧/
  失联不产生新的 PWM 目标。
- VERIFIED_REAL：**无**（本轮未接任何真实设备）。
- NOT_TESTED：真实串口、真实 FSR/电极读数、PWM 与机械动作、真实 AUTO。

## 下一步

1. 现场确认 R/C→ADS1220 AIN 的物理映射、ADS1220 通道/增益/基准与扫描顺序，
   再决定是否启用真实电极采样。
2. 与硬件/集成组确认 `docs/SOFTWARE_V2_P2S_REPORT.md` 第 10 节接口问题。
3. PR #1 合并后对齐 V2 文档，避免本分支 PROGRESS/ISSUES/HANDOFF 与主线重复。
4. 获得现场授权后，先做只读双串口识别与 HELLO/STATUS，再做单步 PWM，不直接开 AUTO。
5. 标定 FSR 基线、极性和饱和，确认电压换算与矩阵方位后，才讨论真实 AUTO。

## 发布记录

- 2026-11-15：`sw/fsr-live-v2` 推送至 `origin/sw/fsr-live-v2`
  （`7a1bf07ca62fe6cc27864d716a85b4f16799f5f3`）。
- 2026-11-15：创建 PR
  [#4](https://github.com/royaleric24/tactile-gripper-a/pull/4)
  → `feat/dashboard-zh-v1`（91 个文件、+9593/−127、3 个 commit、`MERGEABLE`）。
  GitHub Actions `Offline tests`：push run 19s PASS，pull_request run 22s PASS。
- **未合并**，也未操作 `integrate/hybrid-demo-v2` 或启动 P3-A；等待总控审核。
