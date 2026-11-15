# P3-A｜V2 Dashboard 离线集成验收（2026-11-15）

## PR #5 复核增量（2026-11-15）

当前目标为 `FSR_ONLY` 单通道和 `MATRIX_ELECTRODES_12` 的 12/13 通道。FSR_A 确认接 ADC4 AIN0、MUX 8。它在单通道布局的 ID 为 0，在组合布局的 ID 为 12。ADC4 使用 CS32、MISO33，四颗 ADS1220 共用 SCLK18/MOSI23。FSR_A 的 10 kΩ 下拉和 AVDD_AVSS 参考属于现行设计，FSR_B 已损坏，AIN1 的电气隔离尚待现场核对。[总控确认](https://github.com/royaleric24/tactile-gripper-a/pull/5#issuecomment-6895547216)

- 现行配置、生成头文件、Arduino 默认构建和主机适配器使用单 FSR。原 2/14 通道固件仍可离线编译，旧 fixtures 保持字节一致，Trial 保留原 FSR_B 与通道 ID。LIVE 拒绝旧双 FSR 布局及历史 HYBRID；2/14 通道仿真和回放仍可运行。
- 固件生成的 HELLO、SAMPLE、STATUS 原帧实际进入 Dashboard、Trial、CSV、REPLAY。1 通道 CSV 只有 `ch_0`；13 通道的 `ch_12` 为 FSR_A，电极映射待确认时 `ch_0` 至 `ch_11` 留空。ADC4 故障时 FSR_A 也以 `null/NO_DATA` 保存。
- 单 FSR 的分数仅由 FSR_A 相对空载基线计算，组合布局的电极不进入该评分或单 FSR 的离线步进判据。无基线时等待，坏帧、FSR_A 无效/饱和、ADC4 异常、过期或失联时停止进一步步进，待 ACK 时等待。测试验证了允许计算的离线步进决策且无命令下发。`AUTO_REAL_ENABLED=False`。
- 6×6 热力图位于独立 `/demo-6x6`，醒目标注 SIMULATION ONLY，使用 36 个分别生成的合成格值。浏览器实际点击了「下一仿真帧」。该视图没有执行器或 Trial 入口，REPLAY 下该地址返回 404；12 电极继续显示 R1–R6 / C1–C6 原始 ADC 条形图。

| 浏览器实测 | 观察 | 截图 |
| --- | --- | --- |
| 单 FSR | 1/1，FSR_A 762601 ADC counts | [单 FSR](screenshots/p3a-followup/fsr1.png) |
| 12 电极 + 单 FSR | 1/13，FSR_A 2287802 ADC counts，其余待映射 | [13 通道](screenshots/p3a-followup/electrodes12-fsr1.png) |
| 36 格仿真 | 第 2 帧，36/36 格合成值 | [6×6 演示](screenshots/p3a-followup/demo-6x6.png) |
| 12 电极 | 12/12，明确标注合成映射 | [12 电极原始 ADC](screenshots/p3a-followup/electrodes12.png) |
| 单 FSR ADC4 故障 | Trial 分析步进到第 2/2 帧，0/1，成功导出 CSV | [故障和 CSV](screenshots/p3a-followup/fsr1-fault-trial.png) |
| 13 通道回放 | 1/13，只读控制禁用，无新增 Trial | [只读 REPLAY](screenshots/p3a-followup/electrodes12-fsr1-replay.png) |

| 验证 | 结果 | 本地证据（`evidence/p3-a-followup/`） |
| --- | --- | --- |
| 所有 Python 套件 | 500 项通过，应用 378，工具 9 + 40 + 40 + 14 + 19 | `test-*.log` |
| C++ 主机测试与输出帧 | 6 套通过，20 个确定性 JSONL fixtures，原 12 个不变 | `firmware-host.log`、`fixture-generation.log`、`frames/frames_check.json` |
| ESP32 离线编译 | 现行 1/12/13 和历史 2/14 共 5 个通过 | `build-*.log`、`build-receipts/` |
| 浏览器 | 34 个视图，10 个固件仿真 Trial、15 帧、两个只读回放、两个 6×6 视图 | `browser.log`、`browser/summary.json`、[公开摘要](screenshots/p3a-followup/browser-summary.json) |
| Git 与发布 | 空白字符检查和敏感扫描通过，最终 SHA、PR 状态、CI 见交付记录 | `preflight.log`、`release-receipt.json` |

在集成工作区根目录复现：

```bash
export PYTHONPATH=src:.
for suite in tests tools/*/tests; do
  if test -d "$suite"; then
    .venv/bin/python -m unittest discover -s "$suite" || exit 1
  fi
done
.venv/bin/python scripts/run_fsr2_host_tests.py --evidence-dir evidence/p3-a-followup/host
.venv/bin/python scripts/check_fsr2_frames.py --evidence-dir evidence/p3-a-followup/frames
for profile in fsr1 electrodes12 electrodes12_fsr1 fsr electrodes12_fsr2; do
  .venv/bin/python scripts/build_sensor_fsr2_firmware.py --profile "$profile" \
    --build-dir "evidence/p3-a-followup/build-$profile" \
    --evidence-dir evidence/p3-a-followup/build-receipts || exit 1
done
.venv/bin/python scripts/p3a_verify_dashboard.py --out evidence/p3-a-followup/browser-reproduction
```

首轮日志保留了旧 demo 的双通道断言、固件样例自动基线和一次测试文件缩进错误；调整后重新执行了完整套件。记录见 `initial-python.log` 与 `initial-test-indent.log`。

证据等级为 **OFFLINE_VERIFIED**。实测串口、烧录、采样、上电、PWM、真实 AUTO 为 **NOT_TESTED**。P3-B 仍需确认 AIN1 电气隔离、AVDD 与分压、R/C→ADC/AIN 映射，以及单 FSR 对接触和滑移的实际响应。分支保留在 PR #5 待总控审核。

## 首轮验收记录（历史基线 `7e6c425`）

[Issue #3](https://github.com/royaleric24/tactile-gripper-a/issues/3) 的软件、固件帧和 Dashboard 离线验收通过。证据等级为 **OFFLINE_VERIFIED**。发布分支为 `integrate/hybrid-demo-v2`，目标分支为 `main`，由总控评审后决定是否合并。

## 工作区与来源

| 来源 | 执行前重新核对的远程提交 | 集成提交 |
| --- | --- | --- |
| `main` 与集成分支起点 | `633e570623d90777aa204142c269ebe69eb59ac2` | 集成基线 |
| `feat/hardware-acquisition` | `08275363736aace39ca893b4fb64660df95a7b8b` | `15af381cb17618b42b8119ebe98df250665fb881` |
| `feat/dashboard-zh-v1` | `2c5a996aacc86d9e100018ce3c4cb8fa77b16aee` | `938d6883d6867abc9a3bf2f5d083550eb9add49f` |

两组成果通过保留父提交的合并进入独立集成工作区。文档冲突合并保留双方记录，并在当前入口标明 P3-A 的接口与阶段；旧工作区、未提交改动和原始记录均未变更。最终提交、PR 和 CI 结果见 GitHub PR 及工作区内 `evidence/p3-a/release-receipt.json`。

## 接口与安全行为

- Dashboard 通过硬件组的 V2 参考解析器读取固件 JSONL。校验 HELLO、SAMPLE、STATUS 的 profile、启动会话、通道布局与映射声明，拒绝顶层/内层 profile 冲突和跨会话数据。重新握手会清除旧帧及 FSR 基线。当前采集只允许 `FSR_ONLY` 和 `MATRIX_ELECTRODES_12`；旧 `HYBRID_6X6_FSR2` 仅用于标注 HISTORICAL 的回放。
- 传感器串口文档及配置统一为 **921600、8N1**。通过假串口验证启动 HELLO、主动 HELLO 重试、STATUS 请求关联、超时、无阻塞读取和跨轮询分片。旧主机 QUERY 入口发固件支持的 `{"cmd":"STATUS","request_id":"…"}`；连接成功不会自动开流。
- 缺失通道按 `null` + `NO_DATA` 保存，CSV 原始值为空，图表留空并显示有效分数、缺失数和 ADC 异常。通信状态另列。电极使用 ADC 计数，名称为 R1–R6 / C1–C6；组合布局中两路 FSR 单独显示。没有电压基准时不推算电压，比较分数是相对接触指标。
- 离线 AUTO 使用同一固件样例路径验证：新鲜、全通道有效且有基线时可给出一次受限 STEP **决策**；有待完成或未确认指令时 WAIT；数据无效、过期或通信中断时 FAULT。测试断言不调用设备执行接口，`AUTO_REAL_ENABLED=False`。

## 实际 Dashboard 验收

Arduino 固件 C++ 帧构建器和模拟 ADC 生成原始 HELLO / SAMPLE / STATUS，Dashboard 实际服务读取这些字节，沿用应用的传感器、Trial、CSV、图表与回放路径。浏览器检查 **17 个页面/分辨率组合**，覆盖实时监控、实验管理、分析诊断，检查了中文文案、状态、数量、布局和浏览器错误。各场景共记录 **6 个 Trial、9 个触觉帧**。

| 场景 | 最后一帧有效通道 | 浏览器观察 |
| --- | ---: | --- |
| `fsr` | 2/2 | FSR_A 762601、FSR_B 889701 ADC 计数，[截图](screenshots/p3a/fsr.png) |
| `fsr-adc4-fault` | 0/2 | ADC4 无响应；分析页加载 Trial、步进到故障帧 `第 2/2 帧`、导出 CSV，[截图](screenshots/p3a/adc4-trial-replay.png) |
| `electrodes12` | 12/12 | 电极计数、`SIM_SYNTHETIC_MAPPING`，[截图](screenshots/p3a/electrodes12.png) |
| `electrodes12-partial` | 8/12 | ADC1 无响应，R1–R4 留空，[截图](screenshots/p3a/electrodes12-partial.png) |
| `electrodes12-fsr2` | 2/14 | 两路 FSR 有值；12 根电极待真实接线，`PENDING_REAL_WIRING`，[截图](screenshots/p3a/electrodes12-fsr2.png) |
| `electrodes12-fsr2-adc4-fault` | 0/14 | ADC4 无响应，电极待真实接线，显示全部缺失，[截图](screenshots/p3a/electrodes12-fsr2-adc4-fault.png) |
| 导出的组合 Trial → `REPLAY` | 2/14 | 单独启动只读进程，控制被禁用，未写入新记录，[截图](screenshots/p3a/replay.png) |

截图来自实际运行的 Dashboard；其中传感器输入来自固件离线模拟。14 通道通过的是**布局、缺失通道及实际应用处理链**；12 根电极在 14 通道场景中仍是空映射。

## 复现与结果

在集成工作区根目录运行。浏览器验收需要 Node.js、Chrome 和可绑定本机回环地址的运行环境；ESP32 编译需要本地已安装的工具链。以下命令不连接设备：

```bash
uv sync --locked --offline --python 3.13
export PYTHONPATH=src:.
for suite in tests tools/*/tests; do
  if test -d "$suite"; then
    .venv/bin/python -m unittest discover -s "$suite" || exit 1
  fi
done
.venv/bin/python scripts/run_fsr2_host_tests.py
.venv/bin/python scripts/check_fsr2_frames.py
for profile in fsr electrodes12 electrodes12_fsr2; do
  .venv/bin/python scripts/build_sensor_fsr2_firmware.py --profile "$profile" \
    --build-dir "$PWD/evidence/fsr2/p3-a-$profile" || exit 1
done
.venv/bin/python scripts/run_offline_checks.py
.venv/bin/python scripts/p3a_verify_dashboard.py --out evidence/p3-a/browser-reproduction
git status --short --branch
git diff --check
```

| 检查 | 结果 | 本地证据（相对于 `evidence/p3-a/`） |
| --- | --- | --- |
| Python 完整套件：应用 375，工具 9 + 40 + 40 + 14 + 19 | 497 通过 | `final-test-*.log` |
| V2 C++ 主机模拟、原始帧可确定性重建 | 4 套通过；原 9 个样例不变，新增 3 个 STATUS | `firmware-host-tests.log`、`firmware-frames.log` |
| V2 ESP32 构建：2 / 12 / 14 通道 | 3 个通过；303879 / 312751 / 312799 字节 | `build-*.log` |
| 旧版离线测试、固件编译及 C++ 帧构建 | 全部通过 | `legacy-offline-retry.log` |
| 浏览器实际运行与 Trial 回放 | 17 个视图通过，6 个 Trial，9 帧 | [公开摘要](screenshots/p3a/browser-summary.json)；`browser-delivery.log`、`browser-delivery/summary.json`、各场景的浏览器日志/截图和仿真 Trial |
| Git 历史、空白字符、待发布文件敏感信息自检 | 通过 | `preflight.log` |

过程失败记录保留：首轮 Python 测试暴露旧夹具/启动契约不一致；C++ 独立模拟时钟暴露了过严的时间顺序假设；首轮浏览器发现隐藏开关回调和分析页刷新错误；旧版编译脚本需在独立工作区补齐本地 CLI 路径；重截图时默认沙盒阻止绑定回环地址，改用回环专用运行环境重跑。对应 `initial-python.log`、`initial-timestamp-contract-failure.log`、`browser-final.log` 与当轮服务日志、`legacy-offline-checks.log`、`browser-publish.log` 留在工作区。

**尚无 VERIFIED_REAL 证据。** 真实 R/C→ADC/AIN 映射仍是 `PENDING_REAL_WIRING`。本阶段没有打开真实串口、烧录、实际采样、舵机上电、PWM 输出或真实 AUTO。交接后仍需总控授权，才能核对实际接线、串口吞吐、FSR 标定及机械边界。
