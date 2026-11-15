# 问题与阻塞台账（持续更新）

## P3-A 当前状态（2026-11-15；下方组内条目保留历史上下文）

| 编号 | 状态 | 变更 / 后续 |
|---|---|---|
| I-006 / I-101 | OFFLINE_VERIFIED | Dashboard 使用 921600 8N1、V2 参考解析器；旧三 ADC 工具保留原协议。实际 Mac UART 尚待 P3-B。 |
| I-015 / I-105 | RESOLVED | GitHub PR #4 已合入软件组分支；两组及 main 文档基线已保留在集成提交中。 |
| I-104 | PARTIAL | HELLO/STATUS 及主机命令字节、超时经离线验证，实际板端收发仍未实测。 |
| I-106 / I-107 | OPEN | 电极物理映射仍 PENDING_REAL_WIRING；未映射通道 null/NO_DATA。硬件组与项目所有者待现场核对。 |
| I-109 | OFFLINE_VERIFIED | 现行采集/演示拒绝 HYBRID；历史样例仅供带标识的回放。 |
| I-201 | RESOLVED | 零等待串口轮询原来不读，分片不保留；修复后用固件原帧分片通过假串口。 |
| I-202 | RESOLVED | 浏览器点“加载实验”触发 NiceGUI 容器刷新错误，已改为刷新试次视图，复测加载、步进、CSV。 |
| I-204 | OFFLINE_VERIFIED | 所有者确认 FSR_A 为 ADC4 AIN0。1/13 通道固件、单 FSR 评分/AUTO、Trial 与回放通过离线验证；2/14 留作离线兼容。 |
| I-205 | OPEN | FSR_B 已损坏。AIN1 是否已电气隔离、AVDD 实际参考值、分压、FSR_A 阈值与滑移代理等待总控/现场组核对。 |
| I-206 | OFFLINE_VERIFIED | 36 格仅在独立 SIMULATION 演示和历史矩阵回放中显示，现行采集保留 12 电极原始 ADC 条形图。 |
| I-203 | OPEN | P3-B 需核对实际波特率、包吞吐、真实时间基准、FSR 极性与阈值、滑移代理、杯体机械风险。负责人：总负责人 / 现场硬件与软件组。 |

## P3-B1 当前问题（2026-11-15 真实 FSR 接管）

| 编号 | 状态 | 问题 / 证据 / 下一步 |
|---|---|---|
| I-207 | **SUPPORTED（非单 trial）** | 原始 capture 起点很可能是第一处按压已在进行（0–4.2 s 的 4.16M）；事后 15:37Z 空载基线中位 1.7k counts（≈0），与“未载≈0、按压≈4.16M”一致，支持 `VOLTAGE_RISES_WITH_FORCE`。但原始 capture 不是同一 trial 的连续空载→夹持→释放；空杯 trial 仍需在夹持前采连续空载基线。Dashboard 接触评分仍只认正向增量，未做单 trial 确认前不当唯一判据。`AUTO_REAL_ENABLED=False`。 |
| I-208 | **RESOLVED（分析已纠正）** | 采集脚本预写的三段式 marker 与实际操作不符；旧 `capture_analysis.json` 的窗口统计无效。已保留为 `capture_analysis_schedule_assumed.json`，用数据驱动分段生成 `capture_analysis_v2.json`。后续采集不得再写计划 marker 冒充真实事件。 |
| I-209 | **OPEN（低优先级，零点噪声）** | 原 capture 68.734/68.750/68.766 s 有 3 帧 flag `0x04`；15:37Z 空载基线 494 帧中 230 帧负单端（值约 −12k…+16k counts，中位 1.7k），是 0 附近零点噪声而非通信故障，ADC4 全程 `OK`。分析时把 `0x04` 当基线噪声/无效样本，不解释为负力；空杯 trial 监控是否出现远离零点的负跳变。 |
| I-210 | **RESOLVED（2026-11-16）** | S3 真实端口 `/dev/cu.usbserial-A5069RR4` 已识别（ESP32-S3 QFN56 r0.2、8 MB PSRAM、MAC c4:9e:7e:08:25:78）。已构建并上传 `gripper-control-s3-0.9b26.0`（460800、无全片擦除、每段 hash verified），只读 STATUS 返回 DISARMED、GPIO4、50 Hz、14-bit、`output_state=DISABLED_UNMEASURED`、0 ERROR/FAULT/timeout。未发 PWM。 |
| I-211 | **OPEN（环境限制）** | 本会话沙箱无 PTY（`openpty: Operation not permitted`），`pwm_console.py --real` 的交互终端无法由代理运行。下一步：用户在自己的真实 Terminal 运行 console，本进程独占 FSR 串口采集；或经用户明确同意改用 Dashboard LIVE 手动入口。不得修改 `isatty` 安全检查。 |
| I-212 | **OPEN（影响重复性）** | 末段 S4 从约 1.1M 回升到 2.3M，85 s 内未回到初始 4.16M；S3 段还有 −61.6k counts/s 的慢漂移。释放恢复/蠕变时间常数未知。每个 trial 必须重新采空载基线，并保留足够长的释放后窗口。 |
| I-213 | **ACCEPTED_LIMITATION** | 历史验收 app 二进制 `04c77eed…`（316272 B）仍不在本 worktree；2026-11-16 已用同源同配置重新构建 `d20782…`（316288 B）并上传，bootloader/分区表哈希与历史一致，生成头/源码/配置哈希与历史清单一致。历史二进制继续从独立备份保留，不作为当前运行版本。 |
| I-214 | **PARTIAL（显示层已缓解，2026-11-16）** | Dashboard `fsr_history` 仍保留 180 帧（约 2.9 s @61.7 Hz）供原有小趋势图；新增只读日志监控的 `fsr_timeline` 保留 8000 帧（约 2 min @62 Hz，快照降采样到 ≤1800 点）用于 FSR/PWM 统一时间轴。空杯长时间观察是否仍需加大趋势窗口，待真实 LIVE 实测；不重构。 |
| I-215 | **OPEN（已有可用替代路径，2026-11-16）** | Dashboard **直接**打开 FSR 串口的 LIVE 握手仍拿不到完整 HELLO；未验证修改保存在 `evidence/p3b1/private/dashboard_handshake_unverified.patch`，**未提交、未合并**。P3-B 改为 **LOG-FOLLOW 只读双日志**（Dashboard 不打开串口，FSR 由 `capture_fsr_live.py` 独占），因此展示真实 FSR+PWM 不再依赖本项。直接串口 LIVE 仍不做空杯前置条件；下一步单独集中修复。 |
| I-216 | **ACCEPTED_LIMITATION** | 2026-11-16 恢复构建 app SHA `d20782808447385a2ad090e63082f55e7f824652220441f07230f9dbf89830c4`（316288 B）与历史验收 `04c77eed…`（316272 B）不是逐字节相同。bootloader/分区表/生成头/源码/配置均一致，版本字符串与 GPIO/频率/位数已从新二进制和真实 STATUS 确认；16 B 差异与构建路径/工具链非确定性一致，不视为源码变更。 |
| I-217 | **RESOLVED（VERIFIED_REAL，无 PWM）** | 两次 S3 控制台 `response_timeout` 根因：`respond()` 的 900 B TX 阈值小于实测 942–963 B 的 ACK/STATUS；连续命令时 TX 空间不足，`serializeJson` 写出 12/13 个 NUL，主机 JSON 解析失败后 3 s 超时。修复：`measureJson(d)+2` 精确预留 + 150 ms 有界等待 + 紧凑 `TX_BACKPRESSURE` ERROR；主机记录 `corrupt_response`。修复版 `bd039a8…` 已 460800 重烧；真实无 PWM 验证 64/64 应答匹配、0 NUL、0 corrupt_response、0 COMM_ERROR、0 FAULT；5 次连续会话 + 20 次背靠背 HEARTBEAT 全部 PASS；最终 DISARMED/DISABLED_UNMEASURED。 |
| I-218 | **OPEN（1040 机械成功；P3-B4 两会话仍未完成 1040+FSR 同步）** | `cab808…` 已确认 1500 全开、1040 稳定夹杯；但 P3-B4 的 `0fce` 在 BENCH_HOLD_MODE 因 ACK NUL 损坏失败（无 PWM），`a804` 只到 1500 保持便因心跳 ACK NUL 损坏超时；两者均未到 1040，也没有可用的 1040+FSR 同步记录。下一步按 P3B4 报告顺序：舵机通电无 PWM → 1500-only → 1500→1040+FSR。 | 操作者已实测 1500 全开、1040 稳定夹住空杯、无明显形变/下滑；`cab808…` 会话 409/409、0 NUL、最终 DISARMED，但**该会话无 FSR 同步**。随后重开 console 的 `a1790d/296054/ab8d2f` 均出现 NUL ACK + timeout；`ab8d2f` 无 PWM 命令却损坏，重开直接闭合不是 PWM 命令。1040 + FSR 同步仍 **NOT_TESTED**。 |
| I-219 | **OPEN（新证据 2026-11-16；主机重试已缓解；根因 UNKNOWN）** | 两个真实会话 `0fce`/`a804` 的 ACK 被 **0x00 替换**字段中间字节：0fce BENCH_HOLD_MODE ACK 953 B、13 NUL @192–204，`pwm_first_readback_settle_ms`→`pwm_firettle_ms`；a804 HEARTBEAT(1500 保持 4.2 s 后) ACK 957 B、4 NUL @897/899–901，`commanded_pulse_us`→`commanded_puss`。去 NUL 可解析但字段名错误，禁止剥 NUL 修复。boot_id 稳定、无 FAULT/重启、无 TX_BACKPRESSURE；主机逐字节读取远快于 3 s。可排除主机 JSON 误判、设备失联、已证的 TX 缓冲耗尽；UART break/地弹/舵机供电/共地/线束/EMI 与形态一致但未证实（0fce 无 PWM 命令也损坏；Test A 舵机断电 151/151、0 NUL）。修复：HEARTBEAT 与无目标时 mode 命令有界重试（默认 2 次/200 ms，最多 3 次）、长帧 0.2 ms 快速失败、PWM/STOP/DISARM/BEGIN_BENCH 不重试、耗尽后 FAULT/UNKNOWN/close。未烧录。详见 P3B4_FAULT_ANALYSIS.md。 | 真实 PWM 会话 heartbeat ACK 曾 7/12/24 NUL；Test A（PM15S 5V 关、信号线断开）151/151、0 NUL；成功 1040 会话 409/409、0 NUL；但重开的 `ab8d2f` **没有任何 PWM 命令**却在 BEGIN_BENCH ACK 出现 12 NUL。说明损坏可发生在舵机连接/通电但无 PWM 时，**不是 S3 产生 PWM 本身**；指向舵机 5V/共地/线束/EMI 或闭合堵转状态，尚未实测证实。下一步：舵机通电但无 PWM 的 no-PWM 会话 → 1500-only → 1040；测 5V/地电位/电流；不改固件、不自动重试 PWM。 |
| I-222 | **RESOLVED（OFFLINE_VERIFIED，2026-11-16）** | P3-B4 联调前三项安全缺陷：① FSR HELLO 超时/采集进程退出时启动器仍会启动 PWM Console；② 退出时 Dashboard 可能在采集器 flush 尾部 JSONL 前停止 Trial，导致 CSV/REPLAY 缺最后帧/ACK；③ 启动器用全局最新 `frames.csv` 代替本会话 Trial。修复：启动器门控失败退出码 3、不启动 Dashboard/console，Dashboard 就绪后二次检查 FSR；`core.drain_log_follow()` + `finish_log_follow_trial()` 先 drain 再 stop/export；启动器先停 console→FSR→Dashboard，Dashboard 独立 session 避免 Ctrl+C 抢先；Dashboard 写 `<session>/trial.json`，启动器只读本会话 sidecar。测试 420 OK（含门控/进程退出/超时/drain-before-export/sidecar 端到端）。未操作硬件。 |
| I-223 | **RESOLVED（OFFLINE_VERIFIED，2026-11-16）** | Dashboard 先于 `pwm_console` 启动时，`--follow-session` 只发现 FSR，两个真实会话的 `dashboard.log` 均为 `PWM 日志: None`，PWM/ACK 未进入 Trial。修复：session 模式始终跟随预期 `<session>/transport.jsonl`；`LogFollowGripper(require_existing=False)` 进入 `LOG_WAITING`，文件出现后自动接入；显式 `--follow-pwm-log` 仍要求存在。页面显示等待状态；端到端测试确认晚创建日志的 `SET_PWM` 进入 Trial。 |
| I-224 | **OPEN（FSR 高频波动，来源 UNKNOWN）** | 两会话 FSR 100% valid、61.7 Hz、0/1 丢帧、ADC4 全程 OK；0fce 的 1 s 平台与按压/释放一致，a804 的 1 s range 中位 1.73M、残差 239k（历史 FSR-only 约 0.14–0.20M/23–84k）。a804 高频波动在 S3 命令前已存在，与 PWM/ACK 损坏无唯一时间相关；机械接触不稳定 vs 电气噪声无法仅凭 counts 区分，标 UNKNOWN。Dashboard 增加“短窗平滑（仅显示）”，Trial/CSV/REPLAY 保留原始 counts；不推断牛顿/摩擦/杯重。 |
| I-221 | **OPEN（离线审计完成，根因 UNKNOWN）** | 启动 console 后、未输入 PWM 时机械爪非预期闭合。最新会话 `d499e640…`（2026-11-15 18:18:05–18:19:06Z）打开串口时收到 ESP-ROM `rst:0x1 (POWERON)`，首个 STATUS `uptime_ms=1920`，即 S3 在端口打开同时启动（`serial_client.py` 注释已记录 CP210x 打开可能复位）；首个 1500 命令在 17 s 后才出现，之前只有 GET_STATUS/BEGIN_BENCH/BENCH_HOLD_MODE/HEARTBEAT，**无任何 PWM 命令**；本会话 53/53 应答匹配、0 NUL、0 timeout，最终 DISARMED/DISABLED_UNMEASURED。代码审计：connect 只发 GET_STATUS，begin/select_mode 只发 BEGIN_BENCH/BENCH_HOLD_MODE，close 只发 DISARM，无自动恢复旧目标；Dashboard 自动 PWM 仅在 `--demo` SIMULATION 且被 source 检查拦截。**可排除本会话主机 PWM 命令**；S3 复位/舵机失信号、5V/地/线束/EMI、上电毛刺、机械失持均**未验证**，不写根因。处理：现场测 5V/地/电流与线束；no-PWM 会话 → 1500-only → 1040；不新增自动开爪/自恢复/端点扫描。 |
| I-220 | **ACCEPTED_LIMITATION（操作风险）** | `STOP`/`DISARM` 不保证保持夹持：舵机失电后机械爪可能因弹簧/残余位置闭合。`ab8d2f` 日志证明重开后的闭合**没有 PWM 命令**（仅 GET_STATUS×2 + BEGIN_BENCH，无 BENCH_HOLD/PULSE），最后有效 STATUS 为 DISARMED/DISABLED_UNMEASURED。处理：需要保持张开时不要 1040 后 `stop`/退出；先回 1500 并保持会话，或物理支撑/手动张开；重开后第一条 1500 必须等串口链路稳定。**不增加自动开爪 PWM。** |

> 状态为 OPEN / WAITING / RESOLVED / ACCEPTED_LIMITATION。解决后留历史记录，不直接删掉。每个开发进展后检查是否需要更新。

| ID | 问题 | 状态 | 当前判断与下一步 |
|---|---|---|---|
| I-001 | 旧 ADC1–3 MISO 映射文档写错 | **RESOLVED（设计）** | 用户确认 `ADC1=CS21/MISO34`、`ADC2=CS22/MISO35`、`ADC3=CS5/MISO26`。本文档与 V2 模板已修正；旧固件的 `[35,26,34]` 需在实际 V2 开发时迁移并用 SPI 读回验证。 |
| I-002 | FSR 两路独立分压的焊接与响应 | OPEN | 正式施工时确保 AIN0/AIN1 各自 10kΩ 下拉到 GND、测量节点不短接；暂未进行 V2 实物采样。 |
| I-003 | 新 ADC4（CS32/MISO33）尚未接入 | OPEN | 硬件组在后续阶段实施，核验 3.3V/共地、CS、SPI 读回和两路 FSR。 |
| I-004 | 6×6 扫描方案已作废（2026-11-15 修正） | **RESOLVED（前提作废，非完成）** | 项目所有者确认真实压敏布为 12 电极被动读取：无 GPIO 列激励、无 HI_Z、无 36 点扫描。原“六列 GPIO 激励 + GPIO19 给 C6”的设想与真实硬件不符，已从当前设计移除（HISTORICAL）。`HYBRID_6X6_FSR2` 随之撤回，见 I-014。 |
| I-005 | 软硬件分支未集成 | OPEN | 2026-11-14 P0 保护完成；本轮只落地文档。后续仅在公开脱敏历史的集成分支合并组成果。负责人：集成组。 |
| I-006 | 串口波特率/协议两组旧配置不一致 | OPEN | 采集历史固件用 921600；软件模板 115200；真实联调时识别设备并统一。 |
| I-007 | 真实 AUTO、加水实验未完成 | OPEN | 优先 FSR-only 真采集 + S3 MANUAL，再做规则闭环；实验次数按时间弹性调整。 |

| I-008 | 旧三 worktree 与公开仓库历史独立 | ACCEPTED_LIMITATION | 已核实、完整备份；文档改用公开 main 独立 clone。禁止将旧提交直接导入公开仓库。后续文件级迁移由集成组单独核验。 |
| I-009 | V2 协议及施工尚未验证 | WAITING | 设计映射已确认；ADC4、FSR、12 电极、波特率与真实帧由后续硬件/软件组联合核实。P0/P1 不启动 P2/P3。 |

| I-010 | 历史报告 6 处本地证据链接缺失 | ACCEPTED_LIMITATION | Markdown 检查确认均继承自公开 main，涉及 STAGE0/05/06/09B26 报告中的本地证据或原始日志；公开库未包含原件。保留历史正文、不上传原始日志。负责人：文档集成组。 |

| I-011 | 交接包接线文档行尾空格 | RESOLVED | 暂存检查发现 Markdown 双空格换行；已改成普通换行，追加提交修正，不重写历史。 |

| I-012 | 12 电极 → ADC/AIN 物理映射缺失（2026-11-15） | **OPEN** | 真实布料每根 R/C 电极进哪颗 ADC（ADC1/2/3）的哪个 AIN 尚不知道，必须由真实焊接/台架记录填写 `docs/WIRING_FREEZE_V2.md` §4.1 空白表；填表前不得写任何 ADC/AIN 编号、不得假设行优先、不得给“示例映射”。`MATRIX_ELECTRODES_12` 因此保持 `mapping_status: "PENDING_REAL_WIRING"`、`validated: false`。负责人：硬件组（施工后）。 |

| I-013 | 12 电极不能代表 36 个压力点 | ACCEPTED_LIMITATION | 12 个电极电压是 12 个单端测量值，不是 36 个独立压力点；无行列交点语义，空间分辨率受限。任何热图、Demo 文案与验收标准都不得宣称 36 点或“矩阵已验证”。后果：演示只能用电压趋势/粗接触区域，不能用 6×6 热图证明定位精度。 |

| I-014 | `HYBRID_6X6_FSR2` 不得用于真实布料 | **OPEN** | 该 profile 依赖不存在的 GPIO 列激励，真实布料不可用；已撤回为 HISTORICAL（仅保留历史回放识别）。软件组需拒绝将其作为当前 profile、不据此发起真实采集、不把 36 逻辑值渲染为实测点。负责人：软件组。 |

| I-015 | P2-S 软件提交 `8d4d7d8` 尚未推送/评审 | **OPEN** | 见 PR #2 评论提及的软件提交；本仓库文档 PR #1 不含该提交。需确认其基线、是否已在公开仓库可见、是否需要评审后合入。负责人：软件组 / 总负责人。 |

## 更新规则

新问题添加 ID、复现条件、影响、临时方案和负责人（如果明确）；现有问题的状态变化说明证据与日期。仅讨论未施工时，不能把实际电气验收标 PASS。

## 硬件组问题记录（保留原编号）

### I-101｜软件侧严格解析器仍硬编码 12 通道 / 3 ADC（OPEN，阻塞联调）

- 现象：`tools/tactile_acq/protocol.py` 的 `CHANNEL_COUNT = 12`、`ADC_COUNT = 3`，`parse_sample` /
  `parse_hello` 要求 12 通道与 3 个 `adc_status` 条目。FSR_ONLY 的 2 通道帧会被直接判错，
  HYBRID 的 38 通道帧同样被拒。
- 影响：软件组无法用现有解析器消费 V2 帧；目前只能参考 `tools/fsr2/protocol_v2.py`。
- 建议：按 `sensor_profile` 取通道数与 ADC 数量（FSR_ONLY 2/4、HYBRID 38/4、V1 12/3），
  保留旧路径；复用 `protocol_v2` 的 null/valid 语义。
- 负责人：软件组。

### I-102｜四颗 ADS1220 共用 bit-bang SCLK/MOSI 的真实时序未验证（OPEN）

- 现状：host 模拟按理想 SPI 行为建模，未建模 MISO 竞争、走线容性、器件间 CS 建立/保持差异。
- 风险：ADC1–3 与 ADC4 共用总线时，若 MISO 在 CS 拉高后仍被驱动，可能出现串扰读错。
- 需要：逻辑分析仪抓 SCLK/MOSI/各 CS/各 MISO，确认 CS 拉高到下一次传输之间的三态时间。
- 只读证据：离线编译与仿真不能替代。

### I-103｜FSR 分压取值与极性未标定（OPEN）

- 现状：10 kΩ 下拉、3.3 V 激励、`VOLTAGE_RISES_WITH_FORCE` 均为首轮设计值，尚未实测。
- 待做：空载/轻压/重压各记录 counts，换算 AVDD 实测值；必要时比较 4.7 kΩ / 10 kΩ / 47 kΩ。
- 约束：没有独立标定前只能报告 ADC counts，禁止换算成牛顿。

### I-104｜命令层仅编译通过，未逐命令验证（OPEN）

- 现状：`.ino` 的 ArduinoJson 命令解析编译通过，但 host 仿真不覆盖串口解析路径，
  也没有真实串口会话记录。
- 待做：实机按 `docs/hardware/FSR_ONLY_INTERFACE_V2.md` §11 第 6 步逐条执行 PING/STATUS/
  STREAM/STOP/RESET_ADC/VERIFY_CONFIG，并保存原始应答。

### I-105｜两套文档基线并行（OPEN，流程）

- `docs/demo-v2`（PR #1）含 V2 计划、接线冻结、协议提案、进度/问题/交接；本分支只新增硬件范围内的
  同名文件并引用其条目，未复制其内容。
- 合并 PR #1 时需要：以 demo-v2 的 I-001..I-011 为主干，把本文件 I-101 起并入；确认引脚、
  波特率、null 语义三处不产生分叉。

### I-106｜压敏布接线由"6 列 GPIO 扫描"更正为"12 电极被动读数"（OPEN，现场复核）

- 事实：R1–R6 各接一个 ADS1220 AIN + 各自 10 kΩ 下拉 GND；C1–C6 各接一个 AIN + 各自 1 kΩ 上拉
  3.3 V；无 GPIO 列驱动、无 HI_Z、无 36 点扫描。
- 已做：固件/配置/解析器/文档全部改为 `MATRIX_ELECTRODES_12`，删除 GPIO 列激励代码。
- 待做：现场按接口文档 §11/§12 核对焊接，填写电极映射表；确认 12 根电极的偏置电阻实际装配。

### I-107｜R/C → ADC/AIN 映射缺失（OPEN，阻塞电极读数）

- 现状：配置 `electrodes.map = []`、`mapping_status = PENDING_REAL_WIRING`；12 个通道在 SAMPLE
  中固定为 `null` + `NO_DATA`。
- 影响：无法判断 12 路电极电压，也无法做任何空间/位置相关分析。
- 下一步：按 `docs/hardware/FSR_ONLY_INTERFACE_V2.md` §12 填表 → 填 `map` → 改
  `mapping_status = TABLE_PROVIDED` → 重新生成头文件并编译。禁止猜测或按行优先"示例"填充。

### I-108｜12 路电极电压不能代表 36 个压力点（ACCEPTED_LIMITATION）

- 12 根电极是 12 个电位节点，不是 36 个独立测量单元。界面/分析/报告都不得把 12 通道渲染成
  6×6 热图或宣称 36 点已测；`matrix_rows/cols` 恒为 `null`，解析器拒绝旧的 38 通道 HYBRID 帧。

### I-109｜HYBRID_6X6_FSR2 已封存（OPEN，流程）

- 旧 profile/配置/头文件/fixtures 已从本分支删除（仍可在 git 历史 2026-11-14 提交中查看）。
- 生成器对 `HYBRID_6X6_FSR2` 报错；参考解析器报 `PROFILE_HISTORICAL`；软件若仍缓存旧 fixture，
  升级时必须删除，不能把 36 通道帧当当前数据。

### I-110｜合成电极映射只用于测试（OPEN，流程）

- `tools/fsr2_sim/electrode_test_profile.h` 的 `SIM_SYNTHETIC_MAPPING` 与对应 fixture 仅用于验证
  "映射齐全时读数正确"的代码路径。它不是真实接线，不得作为配置模板或验收证据。

### I-111｜命令层仍仅编译验证（继承 I-104）

- 12 电极 profile 的 `.ino` 命令面与之前相同（PING/HELLO/STATUS/STREAM/STOP/RESET_ADC/
  VERIFY_CONFIG），仍未逐命令实测；实机验收步骤见接口文档 §11。

## 软件组记录（P2-S 历史快照）


更新：2026-11-15。协议仍为 **PROPOSED**；以下不是已冻结契约。

## 阻塞真实闭环的接口问题

1. **波特率不一致**：历史采集固件可能 921600，软件默认 115200。当前可由配置/
   `--sensor-baud` 指定，但实际设备值未确认。错误波特率会表现为无 HELLO/乱码，
   不能推断为无矩阵或无接触。
2. **HELLO/STATUS 查询未冻结**：当前接受顶层或 `channel_config.sensor_profile`，
   channel_config 优先；查询发送 `{"type":"QUERY","query":"HELLO"}` 或
   `{"type":"QUERY","query":"STATUS"}`，回复格式与超时未与硬件组确认。查询默认关闭。
3. **FSR 电压换算依据**：只有显式 `adc_reference_uv/adc_gain/adc_bits` 才显示电压。
   ADS1220 单端/差分、有符号计数、实际基准与增益未确认；未确认前不能把换算值当
   真实电压或力。
4. **FSR 极性与饱和**：按下通常使电压升高，但实际极性、饱和阈值、通道顺序
   （FSR_A/B）需硬件确认。当前只报告相对评分。
5. **矩阵映射/扫描**：`matrix_row/col` 到物理方位的对应、6×6 扫描率与串扰未验证；
   热图只按 HELLO 元数据绘制，不代表已标定触觉图。
6. **双设备身份**：S3 与采集板的 `device_id/boot_id/firmware_version` 是否稳定、
   何时发送 HELLO 未联合确认；当前分别记录，不能证明“同一 Trial 的两台设备”已
   经硬件同步。
7. **ACK 语义**：ACK 只表示命令回复，不是位置/夹持力/到位反馈。Trial 分开保存
   `pwm_command_id`、目标、ACK；`actual_pwm_us` 保持未知。
8. **真实 AUTO 签核**：`AUTO_REAL_ENABLED=False`， commissioning 入口当前必拒绝。
   需要协议冻结、硬件授权、FSR 标定、PWM 方向/范围、急停/失联策略与现场证据。
9. **12 电极 R/C→ADC/AIN 映射未确认**：用户确认 R1–R6 各经 10 kΩ 下拉到 GND、
   C1–C6 各经 1 kΩ 上拉到 3.3 V 并分别接 ADS1220 AIN，但未给出哪一路接哪个
   AIN/ADS1220/mux。当前 `MATRIX_ELECTRODES_12` 的 `adc_input`、`ads1220_id`、
   `mux_channel` 全部为 null，`electrode_index` 只是逻辑序号，不能当物理通道。
10. **12 电极 ≠ 36 压力点**：R/C 单端测量不是逐列激励的互电容/电阻矩阵，不能由
    12 路值推算 36 个独立压力点。软件只显示 12 路原始 ADC；热图、压力、接触评分
    均不可用，除非硬件组给出经过验证的扫描与标定方案。

## 当前实现的限制

- 阈值（0.10/0.20/0.45/0.80）是软件初始值，不是杯子/夹爪安全边界；1300 μs 与
  1270 μs 只是人工观察，不是自动限位。
- 相对评分依赖空载基线；杯子/夹爪重新装夹或设备重启后必须重采。真实数据不会
  自动采集基线。
- 仿真首次有效帧自动采集基线，标记 `SIMULATION_AUTO`；该路径不得用于真实 PWM。
- Trial 原始 SAMPLE 依赖设备/适配器提供 `raw`；旧 Trial 无 raw 时 REPLAY 用已验证
  字段重建，不能恢复未落盘的原始字节。
- `frames.jsonl` 直接 REPLAY 依赖同目录 `metadata.json` 的 `sensor_config`；手工
  移动文件会失去自动 HELLO。
- Dashboard 已完成 1440×900、1280×800、1920×1080 的 Live/Experiments/Analysis
  离线截图验收（`docs/screenshots/p2s-ui-audit/`），但仍是仿真数据；真实设备错误
  提示、长时间运行和交互路径需现场走查。
- 视觉验收保留的轻微不对称：Live 底部事件/记录卡高度由内容决定；分析页 7 列
  “控制事件”表在 ≤1440 px 使用卡片内横向滚动；实验历史表在 1280 px 内部滚动
  约 72 px。均不溢出卡片，未为此重排页面。

## 非目标

- 不新增页面、不重做 UI、不引入未标定的牛顿/摩擦系数。
- 不自动回中、扫描端点、重放旧运动，不自动开真实 AUTO。

## 2026-11-15 最终验收：已解决

以下问题在本轮验收中确认、修复并有测试或截图证据（均在离线环境）：

| # | 问题（修复前） | 处理 | 证据 |
|---|---|---|---|
| R1 | Live 帧说明把主机单调时钟当秒数显示（如 `3345443.070s`），像是已经录了 38 天 | 改为 `接收于 HH:MM:SS（本机时间）`，取自 `host_received_utc` | 新 `after/live-*.png` |
| R2 | 接触判断原因整段英文（`relative contact above tight threshold; do not keep tightening`） | `contact_reason_label()` 翻译固定原因，动态原因保留数字 | `tests/test_text_zh.py::ContactReasonTests` |
| R3 | 事件说明漏译带 profile 的形式 `SIMULATION sensor connected (HYBRID_6X6_FSR2); ...` | `event_detail_label()` 前缀规则 | `DynamicEventDetailTests` |
| R4 | 三个页面各复制 `_clock()`，把 UTC 时间戳当本机时间显示且互不一致 | 统一 `theme.clock_label()`，表头写明“时间（本机）” | `DashboardDisplayTests` + 截图 |
| R5 | 分析页侧栏残留占位“离线（OFFLINE）/等待数据”，顶栏“待机”，与同进程其他页面矛盾 | 用只读 `core.snapshot()` 同步侧栏与顶栏，不新增写路径 | 新 `after/analysis-*.png` |
| R6 | 12 电极条形图无单位/读数，Y 轴出现 `2,134.55` 这类小数刻度 | 轴名“ADC 计数”、柱顶读数、刻度取整 | `DashboardDisplayTests::test_bar_chart_shows_units_and_electrode_counts` |
| R7 | 热图色条压在 C 轴标签行；FSR 趋势图轴名与图例重叠 | 热图 `grid.bottom` 加大；删除与图例重复的轴名 | 新整页截图 |
| R8 | 无头 Chrome 启动失败时审计脚本静默退出 0、不产图（会伪造“截图通过”） | `connect()` 对 close/timeout 拒绝；提供 `CHROME_NO_SANDBOX=1` | 复现后修复，重跑 18+3 张截图 |
| R9 | `docs/screenshots/p2s-ui-audit/before/audit.json` 含 9 处本机绝对路径 | 改为仓库相对路径 | `git grep /Users/` 为空 |
| R10 | 工作区遗留 0 字节未跟踪文件 `Ran` | 确认无引用后删除 | 见 PROGRESS 本轮记录 |

## 2026-11-15 最终验收：仍开放（交 P3-A / P3-B）

1. **P3-A 协议**：`QUERY` 请求/回复 wire 格式、超时、HELLO 发送时机仍未冻结；
   第 1 节的第 2、4、5 项仍是集成前的硬阻塞。
2. **P3-A 通道映射**：R1–R6 / C1–C6 → ADS1220 AIN 的物理映射、单端/差分、增益、
   基准、扫描顺序仍未知。软件中 `adc_input/ads1220_id/mux_channel` 保持 null。
3. **P3-A 命名冲突**：矩阵热图行/列用 0 基索引（`R0…R5` / `C0…C5`），电极用 1 基
   逻辑名（`R1…R6` / `C1…C6`）。两者同屏出现时容易误读为同一组通道；需在接口契约里
   统一命名或加前缀（例如 `M-R0` 与 `E-R1`）。本轮未改，避免影响既有 Trial 字段。
4. **P3-A 数据契约**：`sensor_profile` 只用顶层还是 `channel_config` 内层，是否允许
   两者不一致；当前 channel_config 优先且都接受，硬件组未确认。
5. **P3-A/P3-B 视觉**：本轮只做桌面 1024–1920 px。真实设备错误提示、长时间运行、
   断连/重连交互仍未现场走查；1024 px 下四张指标卡会整行堆叠（无溢出，但纵向变长）。
6. **P3-B 标定**：FSR 极性/饱和/基线、阈值（0.10/0.20/0.45/0.80）与 1300/1270 μs
   观察值都不是标定结果；真实 AUTO 仍需现场证据与签核。
7. **CI 覆盖**：本机沙箱无 pty，`test_pty_waits_for_explicit_input` 被跳过；PTY 交互
   路径在本地未验证，只能依赖 CI/现场复核。
