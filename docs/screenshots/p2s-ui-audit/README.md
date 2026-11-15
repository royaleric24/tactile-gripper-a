# P2-S Dashboard 视觉验收（1440×900 / 1280×800 / 1920×1080）

日期：2026-11-15 · 分支：`sw/fsr-live-v2` · 模式：**SIMULATION only**

本目录只包含离线仿真 Dashboard 的截图与布局度量。截取过程没有打开串口、烧录固件、
发送 PWM 或移动机械爪；未使用真实传感器数据。

## 目录

| 路径 | 内容 |
|---|---|
| `before/` | 中断会话修复前的 9 张视口截图 + `audit.json`（含内嵌滚动/溢出候选列表） |
| `after/` | 修复后 HYBRID_6X6_FSR2 仿真 9 张视口 + 9 张整页 + `after-audit.json` |
| `after-electrodes/` | 修复后 MATRIX_ELECTRODES_12 仿真 9 张视口 + 9 张整页 + `after-electrodes-audit.json` |

视口截图文件名：`<page>-<width>x<height>.png`（`live` / `experiments` / `analysis`）。
`*-full.png` 是展开内部滚动容器后的整页审计图，仅用于检查首屏以下卡片，不作为
视口验收尺寸。`before/` 只有视口截图。

复现：

```bash
# 终端 1：离线仿真（HYBRID 与 12 电极分别启动一个端口）
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo \
  --demo-profile HYBRID_6X6_FSR2 --data-root /tmp/gripper-ui-audit --port 8095
PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo \
  --demo-profile MATRIX_ELECTRODES_12 --data-root /tmp/gripper-electrode-audit --port 8096

# 终端 2：截图与布局度量
AUDIT_BASE=http://127.0.0.1:8095 OUT_DIR=docs/screenshots/p2s-ui-audit/after \
  LABEL=after node scripts/ui_screenshot_audit.mjs
AUDIT_BASE=http://127.0.0.1:8096 OUT_DIR=docs/screenshots/p2s-ui-audit/after-electrodes \
  LABEL=after-electrodes node scripts/ui_screenshot_audit.mjs
```

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
| 18 个页面 | Console / page error | 0 | 0 |

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
- 实验管理“实验历史”表在 1280 px 下内部横向滚动约 72 px，属表格自身滚动。

以上均为视觉层面；真实设备、真实 FSR 极性和 R/C→ADC/AIN 映射仍未验证。
