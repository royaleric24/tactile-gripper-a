# A 组触觉闭环机械爪项目

## 软件 V1.0（2026-11-13，离线功能完成）

- **状态：OFFLINE_FEATURE_COMPLETE**。Dashboard、Trial 管理、回放/对比、传感器串口接收框架和 AUTO 离线策略框架已完成并通过离线测试；**真实传感器、真实 AUTO、真实 PWM 仍未验证**。
- 运行 Dashboard（默认 SIMULATION / OFFLINE，不打开真实串口）：

```bash
cd /home/example/Developer/research/tactile-gripper-a-sw
UV_CACHE_DIR=/tmp/uv-cache uv sync --locked
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --port 8080
# 明确 SIMULATION 演示（合成数据，只写 data/simulated/）
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo --port 8080
```

- 无界面完整演示（写模拟 Trial、导出 CSV）：

```bash
PYTHONPATH=src .venv/bin/python scripts/run_simulation_demo.py --ticks 30 --interval 0.05
```

- 文档：
  - [软件运行手册](docs/SOFTWARE_RUNBOOK.md)
  - [V1 数据格式](docs/DATA_FORMAT_V1.md)
  - [硬件联调前置条件/接口清单](docs/HARDWARE_INTEGRATION_CHECKLIST.md)
  - [协议协作说明](docs/PROTOCOL_COLLABORATION.md)
  - [V1 交付报告](docs/SOFTWARE_V1_REPORT.md)
- 安全边界：不连接真实硬件、不发送 PWM、不烧录固件；真实 LIVE 需显式 `--source LIVE --hardware-permission`，真实自动控制仍禁用。共享协议仍为 `PROPOSED v0.1`。


## 当前基线（2026-11-12 Stage 0.9B-26 验收后）

- **主控制器：ESP32-S3**（YD-ESP32-23 2022-V1.3 / S3-N16R8），GPIO4、50 Hz、14-bit LEDC，固件 `gripper-control-s3-0.9b26.0`，串口 `/dev/cu.usbserial-EXAMPLE_S3`。
- **回退：旧 ESP32**（NodeMCU ESP-32S V1.1），GPIO23、50 Hz、16-bit，稳定固件 `gripper-control-bench-0.9b24.0`；旧 BIN `bd02b1d2...`、配置、构建产物和历史日志保留，不覆盖、不重烧。
- **验收**：上传 PASS、通信 PASS、用户报告真实机械爪开合 PASS；精确位置误差与长期稳定性 **UNKNOWN**。
- 真实日志：`logs/real/bench/0e0571fd739d4f638541df1ccae5cc9b/transport.jsonl`。详见 [Stage 0.9B-26 报告](docs/STAGE09B26_REPORT.md) 和 [当前控制台说明](docs/PWM_CONSOLE.md)。
- 下一阶段 4×4 触觉接入尚未开始；GPIO/ADC 映射、供电/电平/共地、UART/USB 资源与 16 通道协议待确认。

> 以下 Stage 0.9B-12 及更早段落为历史记录，保留用于追溯，不代表当前主控制器状态。

Stage 0.9B-12：已开发[常驻手动PWM控制台](docs/PWM_CONSOLE.md)，默认模拟；Bench候选需另行授权上传，当前旧Trial固件不兼容。一次实验启动授权后，由用户终端逐次输入，不自动扫描。


最新（Stage 0.9B-10）：用户纠正实际舵机为 **PM15S，5–8.4V、270°、15KG**（用户报告，原件未独立核验）；此前PM10D参数是历史误认。电源标称5.3V/2A，信号兼容与舵机端供电仍待核实。已部署LEDC修复版，1500/1520 API试动通过不等于真实转动；详见[型号与无运动审查](docs/STAGE09B10_PM15S_REVIEW.md)。以下早期记录按历史保留。


Stage 0.5 历史阶段记录：**Stage 0.5 — ESP32 只读识别及软件架构准备；未识别到可归属 ESP32 的设备，禁止运动/固件写入，尚未进入 Stage 1。**

目标：接收 C 组真实 4×4 触觉矩阵，控制机械爪继续闭合、停止或释放，最终验证至少 3 个安全目标和 5 次真实闭环 Trial，保存数据、执行日志与视频。这些都是后续目标，目前没有实机测试结果。

## Stage 0 历史结果

- 2026-11-11（Asia/Shanghai）检查：macOS 27.0.1 / arm64，Python 3.9.6 可运行。
- 原项目目录为空，未初始化 Git；未修改系统 Python，未安装依赖。
- 只读枚举发现系统串口及普通 USB 外设，没有已确认的机械爪或控制板。
- 型号、协议、供电、反馈、限位及停止方式均为 `UNKNOWN`。
- 硬件通信测试 0 次、运动测试 0 次、真实闭环 Trial 0 次、软件模拟测试 0 次。

## 文件导航

- [硬件盘点](hardware_inventory.csv)：参数、确认状态、证据和缺失原因。
- [阻塞项](BLOCKERS.md)：解除条件及安全门槛。
- [C 组传感数据与 A 组日志约定](docs/SENSOR_CONTRACT.md)：已知字段与待协商项分开。
- [Stage 0 报告](docs/STAGE0_REPORT.md)：主机信息、检查范围、风险与下一步。
- [主机枚举证据](evidence/stage0_host_enumeration.json)：时间、命令、退出码和输出；属于主机只读观察，不是实机验收。

## 后续目录预留

`src/gripper_a/`、`tests/`、`config/` 仅占位，不含控制器、默认设备或默认运动参数。

`data/real/`、`logs/real/`、`videos/real/` 用于未来真实试验；`data/simulation/`、`logs/simulation/` 用于未来模拟结果。目录存在不代表已有试验。后续每次 Trial 应关联原始帧、命令记录、反馈证据和视频，并标记数据来源与控制器来源，禁止将混合测试计为真实闭环。

## 硬件操作门槛

在型号、对应官方协议、供电规格、有效限位、停止/故障行为、现场固定及人员安全均确认，并取得用户对具体运动步骤的明确同意之前，不得运动。接线或供电操作也必须另行说明并获得用户确认。

本轮不打开串口，不发送探测字节，不调用硬件 SDK，不操作电源或接线，不绕过保护。不默认把“程序退出”“停止发送”“释放”“断电”当成已验证的安全停止方式。

目标角度/开度是希望设备到达的值；实际角度/位置必须来自已核实的反馈或独立测量，没有反馈就写未知。电阻及 `contact_score` 不等于真实夹持力或摩擦力。

Stage 0 的下一步曾为获取舵机铭牌；当前优先动作以 Stage 0.5 报告为准。

## Stage 0.5 更新

- [项目规则](AGENTS.md)、[当前报告](docs/STAGE05_REPORT.md)、[架构和八步验证计划](docs/ARCHITECTURE.md)。
- 三线舵机、4–6V/180° 和 ESP-32 板面信息来自用户；参数未核实，不是安全控制值。
- `firmware/` 仅占位；`config/control.template.json` 是设计模板，硬件禁用，未知参数 null，无运行时控制器。
- 新模拟产物使用 `data/simulated/`、`logs/simulated/`；原 `simulation/` 目录保留为历史占位，不继续新增输出。真实目录不变。
- Stage 0 原始证据未修改；本轮无依赖安装、端口打开、固件上传或运动，真实/模拟 Trial 均为 0。

## Stage 0.6 最新状态

发现新增 CP210x USB 桥及 /dev/cu.usbserial-EXAMPLE_ESP32，系统树已建立映射，实物归属/双向通信尚未验证。PM10D 参数为用户转述。详见 [Stage 0.6 报告](docs/STAGE06_REPORT.md)；前述阶段描述均为历史状态。没有上传固件或舵机运动。

## Stage 0.7 最新状态

USB 受控插拔归属验证通过；12 项 SIMULATED 单元测试通过。独立舵机供电仍缺失，禁止实机运动。详见 [Stage 0.7 报告](docs/STAGE07_REPORT.md)。

## Stage 0.8

串口测试固件及客户端已准备；[当前报告](docs/STAGE08_REPORT.md)记录构建、备份、授权与真实通信进度。原始 Flash 备份在 evidence/stage08/，不提交到版本库；原始数据可能含旧固件配置。舵机控制仍禁用。

### Stage 0.8 真实结果更新

serial-test-0.8.0 已经用户授权上传，真实 PING/PONG、状态、异常帧、超时与恢复验证通过。USB 设备缺失检查等待用户拔下确认。日志在 logs/real/stage08/，标签 REAL_SERIAL；舵机仍完全隔离，真实闭环 Trial 为 0。

### Stage 0.8 完成

用户拔下 USB 后设备消失与缺失端口错误处理验证通过。真实串口阶段完成，证据与最终状态见 docs/STAGE08_REPORT.md。当前 ESP32 USB 已拔下；不自动进入后续硬件阶段。

## Stage 0.9A 最新状态

新增默认锁定的 LEDC 控制固件与 dry-run Python 控制器，仅离线验证/编译，未上传。参见 [报告](docs/STAGE09A_REPORT.md)和[控制协议](docs/GRIPPER_PROTOCOL.md)。Stage 0.8 设备固件/真实日志保留。

## Stage 0.9B-1 上传前审查

加固版 gripper-control-0.9b1.0 已离线验证并重新编译，保持硬件禁用和未标定。本次上传待单独授权，尚无该版本实机应用结果。见 [审查报告](docs/STAGE09B1_REPORT.md)。

### Stage 0.9B-1 真实验证更新

锁定版 gripper-control-0.9b1.0 已授权上传并通过真实串口拒绝测试，仍硬件禁用且未标定。独立 EN 检查进行中，当前结果见阶段报告；新对话先读 docs/HANDOFF.md。

### Stage 0.9B-1 完成

EN 操作后的新启动锁定检查通过，正式固件无运动串口验证完成，已关闭串口并暂停。新对话读取 docs/HANDOFF.md；不自动解锁或进入机械运动阶段。

## Stage 0.9B-3 最新状态

受限试动固件已部署且真实无运动验证通过，设备仍DISARMED/UNCALIBRATED，无Trial许可，无PWM试动。见 docs/STAGE09B3_REPORT.md 与 docs/HANDOFF.md；现暂停等待下一次具体授权。
