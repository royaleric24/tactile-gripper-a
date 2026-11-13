"""Visual theme and shared layout for the S2-A dashboard."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from nicegui import ui

from .text_zh import mode_label, source_label, status_label

CSS = """
:root {
  --navy-900: #0b1220;
  --navy-800: #101d33;
  --ink: #0f172a;
  --muted: #64748b;
  --line: #e5eaf2;
  --canvas: #f4f7fb;
}
html, body { background: var(--canvas) !important; color: var(--ink); }
body { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Heiti SC", "Noto Sans SC", "Helvetica Neue", sans-serif; }
.nicegui-content { padding: 0 !important; }
.app-shell { display: flex; width: 100%; height: 100vh; overflow: hidden; }
.sidebar {
  width: 238px; min-width: 238px; height: 100vh; box-sizing: border-box;
  background: linear-gradient(180deg, #0b1220 0%, #0e192b 58%, #101d33 100%);
  color: #cbd5e1; padding: 22px 14px 16px; display: flex; flex-direction: column;
  border-right: 1px solid rgba(148, 163, 184, .12);
}
.brand { display: flex; align-items: center; gap: 11px; padding: 0 8px 22px; }
.brand-mark {
  width: 38px; height: 38px; border-radius: 12px; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #14b8a6 0%, #0ea5e9 100%);
  box-shadow: 0 6px 18px rgba(20, 184, 166, .28); color: #062a2a;
}
.brand-name { color: #f8fafc; font-weight: 700; font-size: 14px; letter-spacing: .02em; line-height: 1.2; }
.brand-sub { color: #64748b; font-size: 10px; letter-spacing: .09em; text-transform: uppercase; margin-top: 2px; white-space: nowrap; }
.nav-group { color: #475569; font-size: 9.5px; letter-spacing: .14em; text-transform: uppercase; font-weight: 700; padding: 14px 10px 7px; }
.nav-item {
  display: flex; align-items: center; gap: 10px; padding: 9px 11px; border-radius: 10px;
  color: #94a3b8 !important; text-decoration: none; font-size: 13px; font-weight: 500; margin-bottom: 3px;
  transition: background .15s ease, color .15s ease;
}
.nav-item:hover { background: rgba(148, 163, 184, .08); color: #e2e8f0 !important; }
.nav-item.active { background: rgba(20, 184, 166, .13); color: #5eead4 !important; box-shadow: inset 0 0 0 1px rgba(45, 212, 191, .20); }
.nav-item .q-icon { font-size: 18px; }
.sidebar-spacer { flex: 1; }
.side-foot { border-top: 1px solid rgba(148, 163, 184, .12); padding: 14px 8px 0; }
.side-label { color: #475569; font-size: 9.5px; letter-spacing: .13em; text-transform: uppercase; font-weight: 700; }
.side-row { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; }
.side-name { color: #94a3b8; font-size: 11.5px; }
.side-value { color: #cbd5e1; font-size: 10.5px; font-weight: 600; }
.side-version { color: #475569; font-size: 10px; margin-top: 14px; }
.main-area { flex: 1; height: 100vh; overflow-y: auto; padding: 26px 30px 42px; box-sizing: border-box; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 20px; }
.page-title { font-size: 26px; font-weight: 700; letter-spacing: -.025em; line-height: 1.15; color: var(--ink); }
.page-subtitle { color: var(--muted); font-size: 12.5px; margin-top: 4px; }
.header-pills { display: flex; align-items: center; gap: 8px; padding-top: 3px; }
.card {
  background: #fff; border: 1px solid var(--line); border-radius: 16px; padding: 18px 20px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, .03), 0 12px 30px -24px rgba(15, 23, 42, .30);
  box-sizing: border-box;
}
.card-tight { padding: 15px 16px; }
.card-kicker { color: #94a3b8; font-size: 10px; letter-spacing: .12em; text-transform: uppercase; font-weight: 700; }
.card-title { color: var(--ink); font-size: 13.5px; font-weight: 650; letter-spacing: -.01em; }
.card-sub { color: var(--muted); font-size: 11.5px; }
.metric-card { min-height: 108px; }
.metric-value { color: var(--ink); font-size: 22px; font-weight: 700; letter-spacing: -.025em; line-height: 1.25; }
.metric-caption { color: var(--muted); font-size: 11px; line-height: 1.35; }
.metric-icon { color: #cbd5e1; font-size: 18px; }
.pill {
  display: inline-flex; align-items: center; gap: 6px; padding: 4px 9px; border-radius: 999px;
  font-size: 10.5px; font-weight: 650; border: 1px solid transparent; white-space: nowrap;
}
.pill .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.pill-green { background: #ecfdf5; color: #047857; border-color: #a7f3d0; }
.pill-amber { background: #fffbeb; color: #b45309; border-color: #fde68a; }
.pill-red { background: #fef2f2; color: #b91c1c; border-color: #fecaca; }
.pill-blue { background: #eff6ff; color: #1d4ed8; border-color: #bfdbfe; }
.pill-slate { background: #f1f5f9; color: #475569; border-color: #e2e8f0; }
.pill-teal { background: #f0fdfa; color: #0f766e; border-color: #99f6e4; }
.pill-purple { background: #f5f3ff; color: #6d28d9; border-color: #ddd6fe; }
.grid-12 { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 16px; width: 100%; }
.col-3 { grid-column: span 3; } .col-4 { grid-column: span 4; } .col-5 { grid-column: span 5; } .col-6 { grid-column: span 6; }
.col-7 { grid-column: span 7; } .col-8 { grid-column: span 8; } .col-12 { grid-column: span 12; }
@media (max-width: 1100px) {
  .col-3, .col-4, .col-5, .col-6, .col-7, .col-8 { grid-column: span 12; }
  .sidebar { width: 210px; min-width: 210px; }
}
.section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.empty-state { min-height: 230px; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #94a3b8; }
.empty-icon { font-size: 38px; color: #cbd5e1; margin-bottom: 8px; }
.empty-title { color: #64748b; font-size: 13px; font-weight: 650; }
.empty-text { color: #94a3b8; font-size: 11.5px; margin-top: 4px; text-align: center; max-width: 360px; }
.mono { font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace; font-size: 11px; }
.notice {
  background: #f8fafc; border: 1px dashed #dbe3ee; border-radius: 11px; padding: 10px 12px;
  color: #64748b; font-size: 11.5px; line-height: 1.45;
}
.notice-amber { background: #fffbeb; border-color: #fde68a; color: #92400e; }
.notice-red { background: #fef2f2; border-color: #fecaca; color: #991b1b; }
.q-table { font-size: 12px; }
.q-table__card { box-shadow: none !important; border: 1px solid #eef2f7; border-radius: 12px; }
.q-table th { color: #94a3b8 !important; font-weight: 700 !important; font-size: 9.5px !important; letter-spacing: .09em; text-transform: uppercase; }
.q-table tbody td { color: #334155 !important; }
.q-field--outlined .q-field__control { border-radius: 10px; }
.q-btn { border-radius: 10px; font-weight: 600; letter-spacing: .01em; }
.q-btn.disabled, .q-btn--disabled { opacity: .45 !important; filter: saturate(.25); }
.q-btn.disabled.bg-primary { background: #94a3b8 !important; }
.q-btn.disabled.bg-negative { background: #cbd5e1 !important; color: #64748b !important; }
.q-btn.disabled.q-btn--outline { color: #94a3b8 !important; border-color: #cbd5e1 !important; }
.q-btn.disabled.text-negative { color: #94a3b8 !important; }
.q-btn--unelevated { box-shadow: none; }
.value-mono { font-family: "SF Mono", ui-monospace, Menlo, monospace; font-size: 30px; font-weight: 700; letter-spacing: -.03em; }
.hairline { height: 1px; background: var(--line); width: 100%; }
"""


def apply_theme() -> None:
    ui.add_head_html(f"<style>{CSS}</style>")
    ui.colors(
        primary="#0f766e",
        secondary="#0f172a",
        accent="#14b8a6",
        positive="#16a34a",
        negative="#dc2626",
        warning="#d97706",
        info="#0284c7",
        dark="#0b1220",
    )
    ui.dark_mode(False)


def pill(text: str, tone: str = "slate"):
    return ui.html(f'<span class="dot"></span>{text}').classes(f"pill pill-{tone}")


def set_pill(element, text: str, tone: str) -> None:
    element.set_content(f'<span class="dot"></span>{text}')
    element.classes(replace=f"pill pill-{tone}")


def tone_for_state(state: str, ok_states=("STREAMING", "CONNECTED", "SESSION_ACTIVE", "MANUAL")) -> str:
    value = (state or "UNKNOWN").upper()
    if value in {item.upper() for item in ok_states}:
        return "green"
    if value in ("WAITING", "STANDBY", "CREATED", "RECORDING", "STALE"):
        return "amber"
    if value in ("FAULT", "FAILED", "ERROR", "DEVICE_ERROR", "OFFLINE", "REJECTED"):
        return "red"
    if value in ("REPLAY",):
        return "purple"
    if value in ("SIMULATED", "SIMULATION"):
        return "teal"
    return "slate"


@contextmanager
def shell(active: str, title: str, subtitle: str, core, version: str):
    apply_theme()
    nav = [
        ("live", "/", "monitor_heart", "实时监控"),
        ("experiments", "/experiments", "science", "实验管理"),
        ("analysis", "/analysis", "query_stats", "分析与诊断"),
    ]
    with ui.element("div").classes("app-shell"):
        with ui.element("aside").classes("sidebar"):
            with ui.element("div").classes("brand"):
                with ui.element("div").classes("brand-mark"):
                    ui.icon("precision_manufacturing").style("font-size:22px")
                with ui.column().classes("gap-0"):
                    ui.label("触觉闭环机械爪 A").classes("brand-name")
                    ui.label("触觉控制台 · V1.0").classes("brand-sub")
            ui.label("工作区").classes("nav-group")
            for key, target, icon, label in nav:
                classes = "nav-item active" if key == active else "nav-item"
                with ui.link(target=target).classes(classes):
                    ui.icon(icon)
                    ui.label(label)
            ui.element("div").classes("sidebar-spacer")
            with ui.element("div").classes("side-foot"):
                ui.label("设备连接").classes("side-label")
                with ui.element("div").classes("side-row"):
                    ui.label("S3 控制器").classes("side-name")
                    s3 = ui.label(status_label("OFFLINE")).classes("side-value")
                with ui.element("div").classes("side-row"):
                    ui.label("传感器").classes("side-name")
                    sensor = ui.label("等待数据").classes("side-value")
                with ui.element("div").classes("side-row"):
                    ui.label("数据来源").classes("side-name")
                    source = ui.label(source_label("SIMULATION")).classes("side-value")
                ui.label(f"{version} · PROPOSED v0.1").classes("side-version")
        with ui.element("main").classes("main-area"):
            with ui.element("div").classes("page-header"):
                with ui.column().classes("gap-0"):
                    ui.label(title).classes("page-title")
                    ui.label(subtitle).classes("page-subtitle")
                with ui.element("div").classes("header-pills"):
                    mode_pill = pill(mode_label("STANDBY"), "amber")
                    source_pill = pill(source_label("SIMULATION"), "teal")
            with ui.column().classes("w-full gap-4"):
                yield {
                    "mode": mode_pill,
                    "source": source_pill,
                    "s3": s3,
                    "sensor": sensor,
                    "source_side": source,
                    "core": core,
                }


def metric_card(kicker: str, icon: str, value: str = "—", caption: str = ""):
    with ui.column().classes("card metric-card gap-1"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(kicker).classes("card-kicker")
            ui.icon(icon).classes("metric-icon")
        value_label = ui.label(value).classes("metric-value")
        caption_label = ui.label(caption).classes("metric-caption")
    return value_label, caption_label


def card_header(title: str, subtitle: str | None = None):
    with ui.row().classes("w-full items-start justify-between gap-3"):
        with ui.column().classes("gap-0"):
            ui.label(title).classes("card-title")
            if subtitle:
                ui.label(subtitle).classes("card-sub")
        return ui.row().classes("items-center gap-2")


def empty_state(icon: str, title: str, text: str) -> None:
    with ui.column().classes("empty-state w-full"):
        ui.icon(icon).classes("empty-icon")
        ui.label(title).classes("empty-title")
        ui.label(text).classes("empty-text")


def notice(text: str, tone: str = "") -> ui.label:
    classes = "notice" + (f" notice-{tone}" if tone else "")
    return ui.label(text).classes(classes).style("width:100%")


def fmt_ns(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value / 1e9:.3f}s"
