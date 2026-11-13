"""Experiments page: create, record and review trials."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from nicegui import ui

from ...constants import SOFTWARE_VERSION
from ...sources import DataSource
from ..theme import card_header, empty_state, notice, pill, set_pill, shell, tone_for_state


def _clock(stamp: str | None) -> str:
    if not stamp:
        return "—"
    try:
        return datetime.fromisoformat(stamp).strftime("%m-%d %H:%M:%S")
    except ValueError:
        return stamp


def _recent_events(recorder, limit: int = 6) -> list[dict]:
    path = getattr(recorder, "events_path", None)
    if path is None or not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def experiments_page(core) -> None:
    with shell(
        "experiments",
        "Experiments",
        "Trial 创建、录制与元数据留档",
        core,
        SOFTWARE_VERSION,
    ) as refs:
        if core.source is DataSource.REPLAY:
            notice("REPLAY 来源为只读：不能创建或写入 Trial。", "red")
        recovery_notice = ui.label("").classes("notice notice-amber").style("width:100%")
        recovery_notice.set_visibility(False)
        with ui.element("div").classes("grid-12"):
            with ui.element("div").classes("col-5"):
                with ui.column().classes("card gap-3"):
                    with card_header("Create Trial", "记录条件、参数快照与数据来源"):
                        pass
                    name_input = ui.input("Trial name", placeholder="e.g. silicone cup baseline").props("outlined dense").classes("w-full")
                    with ui.row().classes("w-full gap-2"):
                        object_input = ui.input("Object", placeholder="cup / block / none").props("outlined dense").classes("flex-1")
                        material_input = ui.select(
                            ["UNKNOWN", "FABRIC", "SILICONE", "OTHER"],
                            value="UNKNOWN",
                            label="Material",
                        ).props("outlined dense").classes("w-36")
                    target_input = ui.input("Grasp target / condition", placeholder="e.g. 1500 μs approach").props("outlined dense").classes("w-full")
                    notes_input = ui.textarea("Notes", placeholder="Setup, observations, operator").props("outlined dense").classes("w-full")
                    create_button = ui.button("Create Trial", color="primary").props("unelevated no-caps").classes("w-full").style("height:42px")
                    source_note = ui.label("").classes("card-sub")
                    ui.label(
                        "Trial 目录由来源决定：SIMULATION → data/simulated/trials，LIVE → data/real/trials。"
                    ).classes("notice").style("width:100%")

            with ui.element("div").classes("col-7"):
                with ui.column().classes("card gap-3"):
                    with ui.row().classes("w-full items-start justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label("Active Trial").classes("card-title")
                            ui.label("Start/stop recording; add markers while running").classes("card-sub")
                        active_pill = pill("NO TRIAL", "slate")
                    with ui.row().classes("w-full items-start justify-between"):
                        with ui.column().classes("gap-0"):
                            active_name = ui.label("No trial created").classes("metric-value")
                            active_meta = ui.label("Create a trial on the left").classes("card-sub")
                        trial_id_label = ui.label("—").classes("mono")
                    with ui.row().classes("w-full items-center gap-2"):
                        start_button = ui.button("Start recording", color="primary").props("unelevated no-caps")
                        stop_button = ui.button("Stop & complete", color="negative").props("outline no-caps")
                        abort_button = ui.button("Abort trial", color="negative").props("outline no-caps")
                        export_button = ui.button("Export CSV", color="secondary").props("outline no-caps")
                        ui.link("Open in Analysis", "/analysis").classes("card-sub").style("color:#0f766e;font-weight:650;margin-left:auto")
                    trial_alert = ui.label("").classes("notice notice-red").style("width:100%")
                    trial_alert.set_visibility(False)
                    active_counts = ui.label("frames 0 · events 0").classes("mono")
                    active_dir = ui.label("—").classes("mono").style("color:#94a3b8;word-break:break-all")
                    ui.element("div").classes("hairline")
                    with ui.row().classes("w-full items-center gap-2"):
                        event_input = ui.input("Event message", placeholder="operator note / anomaly").props("outlined dense").classes("flex-1")
                        event_type = ui.select(["MARKER", "NOTE", "ANOMALY"], value="MARKER", label="Type").props("outlined dense").classes("w-40")
                        add_event_button = ui.button("Add", color="secondary").props("unelevated no-caps")
                    events_table = ui.table(
                        columns=[
                            {"name": "time", "label": "TIME", "field": "time", "align": "left"},
                            {"name": "type", "label": "TYPE", "field": "type", "align": "left"},
                            {"name": "message", "label": "MESSAGE", "field": "message", "align": "left"},
                        ],
                        rows=[],
                        row_key="id",
                    ).props("flat dense").classes("w-full")

        with ui.element("div").classes("grid-12"):
            with ui.element("div").classes("col-12"):
                with ui.column().classes("card gap-3"):
                    with card_header("Trial History", "只读索引；点击 Analysis 页面查看曲线与事件"):
                        pass
                    history_table = ui.table(
                        columns=[
                            {"name": "trial_id", "label": "TRIAL ID", "field": "trial_id", "align": "left"},
                            {"name": "name", "label": "NAME", "field": "name", "align": "left"},
                            {"name": "source", "label": "SOURCE", "field": "source", "align": "left"},
                            {"name": "mode", "label": "MODE", "field": "mode", "align": "left"},
                            {"name": "status", "label": "STATUS", "field": "status", "align": "left"},
                            {"name": "frames", "label": "FRAMES", "field": "frames", "align": "right"},
                            {"name": "created", "label": "CREATED", "field": "created", "align": "left"},
                        ],
                        rows=[],
                        row_key="trial_id",
                    ).props("flat dense").classes("w-full")

    def refresh() -> None:
        trial_items = core.list_trials()
        snapshot = core.snapshot()
        set_pill(refs["mode"], snapshot["mode"], tone_for_state(snapshot["mode"]))
        set_pill(refs["source"], snapshot["source"], "purple" if snapshot["source"] == "REPLAY" else "teal")
        refs["s3"].set_text("ONLINE" if snapshot["gripper"].get("connected") else "OFFLINE")
        refs["sensor"].set_text(snapshot["sensor_state_label"].replace("SENSOR ", ""))
        refs["source_side"].set_text(snapshot["source"])
        source_note.set_text(
            f"Recording source: {snapshot['source']} · mode {snapshot['mode']} · "
            f"{'write allowed' if snapshot['source'] != 'REPLAY' else 'read-only'}"
        )
        trial = core.trial
        if trial is None:
            active_pill.set_content('<span class="dot"></span>NO TRIAL')
            active_pill.classes(replace="pill pill-slate")
            active_name.set_text("No active trial")
            active_meta.set_text("Create a trial on the left")
            trial_id_label.set_text("—")
            active_counts.set_text("frames 0 · events 0")
            active_dir.set_text("—")
            start_button.set_enabled(False)
            stop_button.set_enabled(False)
            abort_button.set_enabled(False)
            add_event_button.set_enabled(False)
            export_button.set_enabled(core.last_trial is not None)
            events_table.rows = []
            events_table.update()
        else:
            metadata = trial.metadata
            recording = trial.recording
            set_pill(active_pill, metadata.status, "green" if recording else tone_for_state(metadata.status))
            active_name.set_text(metadata.name)
            active_meta.set_text(f"{metadata.source.value} · {metadata.mode} · started {_clock(metadata.started_at)}")
            trial_id_label.set_text(metadata.trial_id)
            active_counts.set_text(
                f"frames {trial.frame_count} · events {trial.event_count}"
                + (f" · dropped {trial.dropped_frames}" if trial.dropped_frames else "")
                + (f" · invalid ch {trial.invalid_channel_samples}" if trial.invalid_channel_samples else "")
            )
            active_dir.set_text(str(trial.directory))
            start_button.set_text("Recording…" if recording else "Start recording")
            start_button.set_enabled(not recording and metadata.status in ("CREATED",))
            stop_button.set_enabled(recording)
            abort_button.set_enabled(recording)
            add_event_button.set_enabled(recording)
            export_button.set_enabled(not recording)
            if metadata.write_error or snapshot.get("trial_error"):
                trial_alert.set_text(f"TRIAL WRITE ERROR: {metadata.write_error or snapshot.get('trial_error')}")
                trial_alert.set_visibility(True)
            else:
                trial_alert.set_visibility(False)
            rows = []
            for item in _recent_events(trial):
                rows.append(
                    {
                        "id": item.get("event_id", ""),
                        "time": _clock(item.get("timestamp_utc")),
                        "type": item.get("record_type", item.get("event_type", "—")),
                        "message": item.get("message", item.get("detail", "")),
                    }
                )
            events_table.rows = rows
            events_table.update()
        incomplete = [
            item["trial_id"]
            for item in trial_items
            if item.get("status") in ("INTERRUPTED", "ERROR")
        ]
        if snapshot.get("recovered_trials"):
            recovery_notice.set_text(
                "已恢复意外中断的 Trial（标记 INTERRUPTED，不视为正常完成）："
                + " · ".join(snapshot["recovered_trials"][-3:])
            )
            recovery_notice.set_visibility(True)
        elif incomplete:
            recovery_notice.set_text(
                f"历史中有 {len(incomplete)} 个 INTERRUPTED/ERROR Trial；"
                "数据保留但不会计为正常完成。请在 Analysis 查看完整性摘要。"
            )
            recovery_notice.set_visibility(True)
        else:
            recovery_notice.set_visibility(False)
        if core.trial is None:
            trial_alert.set_visibility(False)
        create_button.set_enabled(core.source is not DataSource.REPLAY and core.trial is None)
        rows = []
        for metadata in trial_items:
            counts = metadata.get("counts") or {}
            frames = counts.get("frames", 0)
            if core.trial is not None and metadata.get("trial_id") == core.trial.metadata.trial_id:
                frames = core.trial.frame_count
            rows.append(
                {
                    "trial_id": metadata.get("trial_id"),
                    "name": metadata.get("name"),
                    "source": metadata.get("source"),
                    "mode": metadata.get("mode"),
                    "status": metadata.get("status"),
                    "frames": frames,
                    "created": _clock(metadata.get("created_at")),
                }
            )
        history_table.rows = rows
        history_table.update()

    async def create_trial() -> None:
        name = (name_input.value or "").strip()
        if not name:
            ui.notify("Trial name is required", type="warning")
            return
        conditions = {
            "object": (object_input.value or "UNKNOWN").strip() or "UNKNOWN",
            "material": material_input.value or "UNKNOWN",
            "grasp_target": (target_input.value or "").strip() or "UNKNOWN",
            "protocol_note": "conditions entered by operator; no force/angle claim",
        }
        try:
            metadata = await asyncio.to_thread(
                core.create_trial, name, conditions=conditions, notes=(notes_input.value or "")
            )
            ui.notify(f"Trial created: {metadata['trial_id']}", type="positive")
        except Exception as exc:
            ui.notify(str(exc), type="negative", timeout=6000)
        refresh()

    async def start_trial() -> None:
        try:
            await asyncio.to_thread(core.start_trial)
            ui.notify("Recording started", type="positive")
        except Exception as exc:
            ui.notify(str(exc), type="negative")
        refresh()

    async def stop_trial() -> None:
        try:
            metadata = await asyncio.to_thread(core.stop_trial, "operator stop")
            ui.notify(f"Trial completed: {metadata['trial_id']}", type="positive")
        except Exception as exc:
            ui.notify(str(exc), type="negative", timeout=6000)
        refresh()

    async def abort_trial() -> None:
        try:
            metadata = await asyncio.to_thread(core.stop_trial, "operator abort", aborted=True)
            ui.notify(f"Trial aborted and saved as ABORTED: {metadata['trial_id']}", type="warning")
        except Exception as exc:
            ui.notify(str(exc), type="negative", timeout=6000)
        refresh()

    async def add_event() -> None:
        message = (event_input.value or "").strip()
        if not message:
            ui.notify("Event message is required", type="warning")
            return
        try:
            await asyncio.to_thread(core.add_trial_event, event_type.value or "MARKER", message, {"source": core.source.value})
            event_input.value = ""
            ui.notify("Event added", type="positive")
        except Exception as exc:
            ui.notify(str(exc), type="negative")
        refresh()

    async def export_csv() -> None:
        trial_id = None
        if core.trial is not None:
            trial_id = core.trial.metadata.trial_id
        elif core.last_trial is not None:
            trial_id = core.last_trial.get("trial_id")
        if not trial_id:
            ui.notify("No trial to export", type="warning")
            return
        try:
            path = await asyncio.to_thread(core.trial_store.export_csv, trial_id)
            ui.notify(f"CSV exported: {path}", type="positive")
        except Exception as exc:
            ui.notify(str(exc), type="negative")
        refresh()

    create_button.on_click(create_trial)
    start_button.on_click(start_trial)
    stop_button.on_click(stop_trial)
    abort_button.on_click(abort_trial)
    add_event_button.on_click(add_event)
    export_button.on_click(export_csv)

    refresh()
    ui.timer(1.0, refresh)
