# P2-S Dashboard 视觉验收（1440×900 / 1280×800 / 1920×1080 + 1024×768 抽查）

日期：2026-11-15 · 分支：`sw/fsr-live-v2` · 模式：**SIMULATION only**

本目录只包含离线仿真 Dashboard 的截图与布局度量。截取过程没有打开串口、烧录固件、
发送 PWM 或移动机械爪；未使用真实传感器数据，也没有任何图片生成或手工拼接的图片。

## 目录

| 路径 | 内容 |
|---|---|
| `before/` | 中断会话修复前的 9 张视口截图 + `audit.json`（含内嵌滚动/溢出候选列表） |
| `after/` | 最终验收重拍的 HYBRID_6X6_FSR2 仿真 9 张视口 + 9 张整页 + `after-audit.json` |
| `after-electrodes/` | 最终验收重拍的 MATRIX_ELECTRODES_12 仿真 9 张视口 + 9 张整页 + `after-electrodes-audit.json` |
| `narrow-1024/` | 补充抽查：1024×768 的 Live/Experiments/Analysis 3 张视口 + 3 张整页 + `narrow-audit.json`（非验收尺寸） |

视口截图文件名：`<page>-<width>x<height>.png`（`live` / `experiments` / `analysis`）。
`*-full.png` 是展开内部滚动容器后的整页审计图，仅用于检查首屏以下卡片，不作为
视口验收尺寸。`before/` 只有视口截图。

## 复现

```bash
# 终端 1：离线仿真（HYBRID 与 12 电极分别启动一个端口）
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo \
  --demo-profile HYBRID_6X6_FSR2 --data-root /tmp/gripper-ui-audit --port 8095
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo \
  --demo-profile MATRIX_ELECTRODES_12 --data-root /tmp/gripper-electrode-audit --port 8096

# 终端 2：截图与布局度量
CHROME_NO_SANDBOX=1 AUDIT_BASE=http://127.0.0.1:8095 \
  OUT_DIR=docs/screenshots/p2s-ui-audit/after LABEL=after \
  node scripts/ui_screenshot_audit.mjs
CHROME_NO_SANDBOX=1 AUDIT_BASE=http://127.0.0.1:8096 \
  OUT_DIR=docs/screenshots/p2s-ui-audit/after-electrodes LABEL=after-electrodes \
  node scripts/ui_screenshot_audit.mjs
CHROME_NO_SANDBOX=1 AUDIT_BASE=http://127.0.0.1:8095 \
  OUT_DIR=docs/screenshots/p2s-ui-audit/narrow-1024 LABEL=narrow \
  VIEWPORTS=1024x768 node scripts/ui_screenshot_audit.mjs
```

注意：

- `CHROME_NO_SANDBOX=1` 只在本机沙箱/容器里需要（Chrome 的 GPU/sandbox 辅助进程被
  拒绝时会直接退出）。普通桌面环境不要设置，脚本默认保留 Chrome 自带沙箱。
- 脚本在 CDP WebSocket 打不开时会报错退出，不再静默产出 0 张截图。
- 截图前建议清空 `--data-root`，否则分析页的 Trial 下拉会累积历史仿真 Trial。

## 检查项与结论（最终验收，2026-11-15）

| # | 检查项 | 结论 |
|---|---|---|
| 1 | 中文文字自然、完整、无截断 | 通过。接触原因、事件说明、时间列均已中文化；表头写明“时间（本机）” |
| 2 | 两列布局与卡片高度一致 | 通过。顶部 4 张指标卡在 1440/1280/1920 均为等高（121/136/121 px），见下表 |
| 3 | FSR_A / FSR_B 数据清晰 | 通过。两列并排，各自显示原始 ADC、电压、相对变化、Δ、有效/无效标记 |
| 4 | 12 电极条形图、名称、单位 | 通过。R1–R6 / C1–C6，Y 轴“ADC 计数”，柱顶读数，无 36 点热图 |
| 5 | 表格溢出、按钮遮挡 | 无明显问题。页面级无横向滚动；仅表格自身在 ≤1440 px 内部滚动（见下） |
| 6 | LIVE / SIMULATION 区分 | 通过。顶栏“仿真（SIMULATION）”胶囊、卡片内 profile 胶囊、页脚“数据来源 仿真” |
| 7 | Trial / CSV / REPLAY 入口 | 通过。实验管理页创建/记录/结束/导出 CSV 可见可用；回放入口在分析与诊断页 |
| 8 | 常见桌面宽度与较窄窗口 | 1440/1280/1920 通过；1024×768 抽查无溢出，指标卡改为整行堆叠 |
| 9 | 误导性数值/单位/AUTO 状态 | 未发现。无压力/牛顿单位；接触指标为相对评分或“未知”；真实 AUTO 标为硬关闭 |

## 修复前后对比（HYBRID 仿真，同一视口）

| 视口 | 检查项 | 修复前 | 修复后 |
|---|---|---|---|
| 1440×900 | 顶部 4 张指标卡高度 | 121 / 121 / 108 / 108 px | 121 / 121 / 121 / 121 px |
| 1440×900 | 触觉分布 / 手动 PWM 高度 | 557 / 586 px | 586 / 586 px |
| 1440×900 | FSR 卡片宽度 | 911 px（未对齐 12 列网格） | 1142 px（整行） |
| 1440×900 | FSR 两路读数 | 上下堆叠、整行拉伸 | 左右两列（`col-6` 生效） |
| 1280×800 | 顶部 4 张指标卡高度 | 121 / 136 / 134 / 134 px | 136 / 136 / 136 / 136 px |
| 1280×800 | 触觉分布 / 手动 PWM 高度 | 628 / 644 px | 644 / 644 px |
| 1920×1080 | 顶部 4 张指标卡高度 | 108 / 121 / 108 / 108 px | 121 / 121 / 121 / 121 px |
| 1920×1080 | 触觉分布 / 手动 PWM 高度 | 525 / 543 px | 543 / 543 px |
| 1440×900 | 分析与诊断 · 实验筛选卡宽度 | 1003 px | 1142 px |
| 1440×900 | 触觉帧检查 / FSR 相对接触高度 | 428 / 346 px | 428 / 428 px |
| 1920×1080 | 实验筛选卡宽度 | 1003 px | 1622 px |
| 1440×900 | 分析页表格横向溢出 | 4 处（最大 919 px 内容 / 616 px 容器） | 0 处（7 列控制表内部滚动） |
| 1280×800 | 实验管理 · “水量/质量（g）”标签 | 截断为“水…” | 完整显示 |
| 全视口 | Profile 下拉框 | `HYBRID_6X6_…` 截断 | 完整显示两个 profile 名 |
| 全视口 | 页面级横向滚动 | 无 | 无（`bodyScrollWidth == viewport`） |
| 18 个页面 | Console / page error | 0 | 0（最终验收重跑仍为 0） |

最终验收这一轮修复的显示层问题（详见 [../ISSUES.md](../ISSUES.md) 的 R1–R10）：

- Live 帧说明原先显示 `3345443.070s`（主机单调时钟当秒数），改为
  `接收于 HH:MM:SS（本机时间）`。
- 接触判断原因、带 profile 的“已连接仿真传感器”事件说明改为中文。
- 12 电极条形图补 Y 轴名“ADC 计数”和柱顶读数；Y 轴刻度取整（原先出现 `2,134.55`）。
- 分析页侧栏/顶栏原先残留“离线（OFFLINE）/等待数据/待机”占位，改为只读快照同步。
- 热图颜色条不再压在 C 轴标签行；FSR 趋势图去掉与图例重复的轴名。

12 电极视图（`after-electrodes/`）：

- Live 只显示 12 路 R1–R6 / C1–C6 原始 ADC 条形图，附“36 点压力热图不可用”提示；
  接触指标为“未知／设备未上报接触评分”，不合成压力或接触。
- Analysis 回放同样使用条形图 + 提示，不把 12 路电极回放成 36 点热图。
- 无 FSR 通道时不显示 FSR 卡片（`fsr_count=0`）。

## 保留的轻微不对称（未改布局结构）

- Live 底部“最近控制事件”高于“实验记录状态”；“故障与异常”短于“PWM 变化曲线”。
  卡片高度由内容决定，未强行拉伸以免留下大块空白。
- 分析页 7 列“控制事件”表在 ≤1440 px 使用卡片内横向滚动（`min-width: 760px`），
  避免中文单元格被压成一字一行；表格不会溢出卡片。
- 实验管理“实验历史”表在 1280 px 下内部横向滚动约 73 px，属表格自身滚动。
- 1024×768 抽查下四张指标卡改为整行堆叠（12 列栅格的小屏断点行为），无溢出，
  但首屏只能看到指标卡；这不是验收尺寸，仅为窄窗口抽查。

以上均为视觉层面与仿真数据；真实设备、真实 FSR 极性和 R/C→ADC/AIN 映射仍未验证。
