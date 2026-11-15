"""Experiments page: create, record and review trials."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from nicegui import ui

from ...constants import SOFTWARE_VERSION
from ...sources import DataSource
from ..theme import card_header, clock_label, empty_state, notice, pill, set_pill, shell, tone_for_state
from ..text_zh import (
    error_text,
    event_detail_label,
    mode_label,
    record_type_label,
    sensor_label,
    source_label,
    source_short,
    trial_status_label,
)


def _time_label(stamp: str | None) -> str:
    """Local MM-DD HH:MM:SS for the compact experiment tables."""
    text = clock_label(stamp)
    return text[5:] if len(text) == 19 else text


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
        "实验管理",
        "创建实验、记录触觉帧与控制事件、保存实验元数据",
        core,
        SOFTWARE_VERSION,
    ) as refs:
        if core.source is DataSource.REPLAY:
            notice("只读回放（REPLAY）来源不能创建或写入实验。", "red")
        recovery_notice = ui.label("").classes("notice notice-amber").style("width:100%")
        recovery_notice.set_visibility(False)
        with ui.element("div").classes("grid-12"):
            with ui.element("div").classes("col-5"):
                with ui.column().classes("card gap-3"):
                    with card_header("创建实验", "记录实验条件、参数快照与数据来源"):
                        pass
                    name_input = ui.input("实验名称", placeholder="例如：硅胶杯基线").props("outlined dense").classes("w-full")
                    with ui.row().classes("w-full gap-2"):
                        object_input = ui.input("物体名称", placeholder="杯子 / 方块 / 无").props("outlined dense").classes("flex-1")
                        cup_type_input = ui.input("杯子类型", placeholder="玻璃 / 纸杯 / 无").props("outlined dense").classes("flex-1")
                    with ui.row().classes("w-full gap-2"):
                        material_input = ui.select(
                            {"UNKNOWN": "未知", "FABRIC": "织物（FABRIC）", "SILICONE": "硅胶（SILICONE）", "OTHER": "其他"},
                            value="UNKNOWN",
                            label="材料",
                        ).props("outlined dense").classes("w-40")
                        operator_input = ui.input("操作人员", placeholder="姓名/缩写").props("outlined dense").classes("flex-1")
                    with ui.row().classes("w-full gap-2"):
                        water_mass_input = ui.number("水量/质量（g）", value=None, min=0, step=1).props("outlined dense").classes("w-40")
                        target_input = ui.input("抓取目标 / 实验条件", placeholder="例如：1500 μs 接近").props("outlined dense").classes("flex-1")
                    video_input = ui.input("视频文件路径", placeholder="/path/to/capture.mov（可选）").props("outlined dense").classes("w-full")
                    notes_input = ui.textarea("备注", placeholder="装配、观察、现场条件等").props("outlined dense").classes("w-full")
                    create_button = ui.button("创建实验", color="primary").props("unelevated no-caps").classes("w-full").style("height:42px")
                    source_note = ui.label("").classes("card-sub")
                    ui.label(
                        "创建实验不会自动开始记录；请点击“开始记录”。开始后系统保存触觉帧、控制事件和实验元数据。"
                    ).classes("card-sub")
                    ui.label(
                        "实验目录由来源决定：仿真（SIMULATION）→ data/simulated/trials；真实设备（LIVE）→ data/real/trials。"
                    ).classes("notice").style("width:100%")

            with ui.element("div").classes("col-7"):
                with ui.column().classes("card gap-3"):
                    with ui.row().classes("w-full items-start justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label("当前实验").classes("card-title")
                            ui.label("创建后需点击“开始记录”；开始后保存触觉帧、控制事件和元数据").classes("card-sub")
                        active_pill = pill("暂无实验", "slate")
                    with ui.row().classes("w-full items-start justify-between"):
                        with ui.column().classes("gap-0"):
                            active_name = ui.label("尚未创建实验").classes("metric-value")
                            active_meta = ui.label("请在左侧创建实验").classes("card-sub")
                        trial_id_label = ui.label("—").classes("mono")
                    with ui.row().classes("w-full items-center gap-2"):
                        start_button = ui.button("开始记录", color="primary").props("unelevated no-caps")
                        stop_button = ui.button("正常结束", color="negative").props("outline no-caps")
                        abort_button = ui.button("中止实验", color="negative").props("outline no-caps")
                        export_button = ui.button("导出 CSV", color="secondary").props("outline no-caps")
                        ui.link("在分析中打开", "/analysis").classes("card-sub").style("color:#0f766e;font-weight:650;margin-left:auto")
                    trial_alert = ui.label("").classes("notice notice-red").style("width:100%")
                    trial_alert.set_visibility(False)
                    active_counts = ui.label("触觉帧 0 · 事件 0").classes("mono")
                    active_dir = ui.label("—").classes("mono").style("color:#94a3b8;word-break:break-all")
                    active_video = ui.label("视频：—").classes("card-sub")
                    with ui.row().classes("w-full items-center gap-2"):
                        attach_video_input = ui.input("关联/更新视频路径", placeholder="/path/to/capture.mov").props("outlined dense").classes("flex-1")
                        attach_video_button = ui.button("更新视频", color="secondary").props("outline no-caps")
                    ui.element("div").classes("hairline")
                    with ui.row().classes("w-full items-center gap-2"):
                        event_input = ui.input("事件内容", placeholder="例如：加水 100 g / 发生打滑 / 异常").props("outlined dense").classes("flex-1")
                        event_type = ui.select(
                            {"MARKER": "标记", "NOTE": "备注", "ANOMALY": "异常"},
                            value="MARKER",
                            label="类型",
                        ).props("outlined dense").classes("w-40")
                        add_event_button = ui.button("添加", color="secondary").props("unelevated no-caps")
                    events_table = ui.table(
                        columns=[
                            {"name": "time", "label": "时间（本机）", "field": "time", "align": "left"},
                            {"name": "type", "label": "类型", "field": "type", "align": "left"},
                            {"name": "message", "label": "内容", "field": "message", "align": "left"},
                        ],
                        rows=[],
                        row_key="id",
                    ).props('flat dense no-data-label="暂无数据"').classes("w-full")

        with ui.element("div").classes("grid-12"):
            with ui.element("div").classes("col-12"):
                with ui.column().classes("card gap-3"):
                    with card_header("实验历史", "只读索引；可在“分析与诊断”中查看曲线、事件与完整性"):
                        pass
                    history_table = ui.table(
                        columns=[
                            {"name": "trial_id", "label": "实验 ID（Trial ID）", "field": "trial_id", "align": "left"},
                            {"name": "name", "label": "名称", "field": "name", "align": "left"},
                            {"name": "source", "label": "来源", "field": "source", "align": "left"},
                            {"name": "mode", "label": "模式", "field": "mode", "align": "left"},
                            {"name": "status", "label": "状态", "field": "status", "align": "left"},
                            {"name": "frames", "label": "帧数", "field": "frames", "align": "right"},
                            {"name": "video", "label": "视频", "field": "video", "align": "left"},
                            {"name": "created", "label": "创建时间", "field": "created", "align": "left"},
                        ],
                        rows=[],
                        row_key="trial_id",
                    ).props('flat dense no-data-label="暂无数据"').classes("w-full")

    def refresh() -> None:
        trial_items = core.list_trials()
        snapshot = core.snapshot()
        set_pill(refs["mode"], mode_label(snapshot["mode"]), tone_for_state(snapshot["mode"]))
        set_pill(
            refs["source"],
            source_label(snapshot["source"]),
            "purple" if snapshot["source"] == "REPLAY" else "teal",
        )
        refs["s3"].set_text("在线" if snapshot["gripper"].get("connected") else "离线")
        refs["sensor"].set_text(sensor_label(snapshot["sensor_state_label"]))
        refs["source_side"].set_text(source_short(snapshot["source"]))
        source_note.set_text(
            f"记录来源：{source_label(snapshot['source'])} · 模式：{mode_label(snapshot['mode'])} · "
            f"{'允许写入' if snapshot['source'] != 'REPLAY' else '只读'}"
        )
        trial = core.trial
        if trial is None:
            active_pill.set_content('<span class="dot"></span>暂无实验')
            active_pill.classes(replace="pill pill-slate")
            active_name.set_text("暂无进行中的实验")
            active_meta.set_text("请在左侧创建实验")
            trial_id_label.set_text("—")
            active_counts.set_text("触觉帧 0 · 事件 0")
            active_dir.set_text("—")
            active_video.set_text("视频：—")
            attach_video_input.value = ""
            attach_video_button.set_enabled(False)
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
            set_pill(active_pill, trial_status_label(metadata.status), "green" if recording else tone_for_state(metadata.status))
            active_name.set_text(metadata.name)
            active_meta.set_text(
                f"{source_label(metadata.source.value)} · {mode_label(metadata.mode)} · 开始 {_time_label(metadata.started_at)}"
            )
            trial_id_label.set_text(metadata.trial_id)
            video = metadata.video_path or "—"
            exists = "（文件存在）" if metadata.video_path and Path(metadata.video_path).is_file() else ""
            active_video.set_text(f"视频：{video}{exists}")
            attach_video_input.value = metadata.video_path or ""
            attach_video_button.set_enabled(True)
            active_counts.set_text(
                f"触觉帧 {trial.frame_count} · 事件 {trial.event_count}"
                + (f" · 丢帧 {trial.dropped_frames}" if trial.dropped_frames else "")
                + (f" · 无效通道样本 {trial.invalid_channel_samples}" if trial.invalid_channel_samples else "")
            )
            active_dir.set_text(str(trial.directory))
            start_button.set_text("记录中（RECORDING）" if recording else "开始记录")
            start_button.set_enabled(not recording and metadata.status in ("CREATED",))
            stop_button.set_enabled(recording)
            abort_button.set_enabled(recording)
            add_event_button.set_enabled(recording)
            export_button.set_enabled(not recording)
            if metadata.write_error or snapshot.get("trial_error"):
                trial_alert.set_text(f"实验写入错误（ERROR）：{metadata.write_error or snapshot.get('trial_error')}")
                trial_alert.set_visibility(True)
            else:
                trial_alert.set_visibility(False)
            rows = []
            for item in _recent_events(trial):
                rows.append(
                    {
                        "id": item.get("event_id", ""),
                        "time": _time_label(item.get("timestamp_utc")),
                        "type": record_type_label(item.get("record_type", item.get("event_type", "—"))),
                        "message": event_detail_label(item.get("message") or item.get("detail", "")),
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
                "已恢复意外中断的实验（INTERRUPTED，不视为正常完成）："
                + " · ".join(snapshot["recovered_trials"][-3:])
            )
            recovery_notice.set_visibility(True)
        elif incomplete:
            recovery_notice.set_text(
                f"历史中有 {len(incomplete)} 个异常中断/写入错误实验；"
                "数据保留，但不会计为正常完成。请在“分析与诊断”查看完整性摘要。"
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
                    "source": source_label(metadata.get("source")),
                    "mode": mode_label(metadata.get("mode")),
                    "status": trial_status_label(metadata.get("status")),
                    "frames": frames,
                    "video": (Path(metadata.get("video_path")).name if metadata.get("video_path") else "—"),
                    "created": _time_label(metadata.get("created_at")),
                }
            )
        history_table.rows = rows
        history_table.update()

    async def create_trial() -> None:
        name = (name_input.value or "").strip()
        if not name:
            ui.notify("请填写实验名称", type="warning")
            return
        conditions = {
            "object": (object_input.value or "UNKNOWN").strip() or "UNKNOWN",
            "cup_type": (cup_type_input.value or "UNKNOWN").strip() or "UNKNOWN",
            "material": material_input.value or "UNKNOWN",
            "water_mass_g": float(water_mass_input.value) if water_mass_input.value is not None else None,
            "grasp_target": (target_input.value or "").strip() or "UNKNOWN",
            "protocol_note": "conditions entered by operator; no force/angle claim",
        }
        try:
            metadata = await asyncio.to_thread(
                core.create_trial,
                name,
                conditions=conditions,
                notes=(notes_input.value or ""),
                operator=(operator_input.value or "").strip() or None,
                video_path=(video_input.value or "").strip() or None,
            )
            ui.notify(f"实验已创建：{metadata['trial_id']}；请点击“开始记录”", type="positive")
        except Exception as exc:
            ui.notify(error_text(exc), type="negative", timeout=6000)
        refresh()

    async def start_trial() -> None:
        try:
            await asyncio.to_thread(core.start_trial)
            ui.notify("已开始记录触觉帧、控制事件和元数据", type="positive")
        except Exception as exc:
            ui.notify(error_text(exc), type="negative")
        refresh()

    async def stop_trial() -> None:
        try:
            metadata = await asyncio.to_thread(core.stop_trial, "operator stop")
            ui.notify(f"实验已正常结束并保存：{metadata['trial_id']}", type="positive")
        except Exception as exc:
            ui.notify(error_text(exc), type="negative", timeout=6000)
        refresh()

    async def abort_trial() -> None:
        try:
            metadata = await asyncio.to_thread(core.stop_trial, "operator abort", aborted=True)
            ui.notify(f"实验已中止并保存为 ABORTED：{metadata['trial_id']}", type="warning")
        except Exception as exc:
            ui.notify(error_text(exc), type="negative", timeout=6000)
        refresh()

    async def confirm_abort() -> None:
        abort_dialog.close()
        await abort_trial()

    with ui.dialog() as abort_dialog, ui.card().classes("card gap-3"):
        ui.label("确认中止当前实验？").classes("card-title")
        ui.label(
            "中止后保存为 ABORTED；已记录的触觉帧、控制事件和元数据会保留，"
            "但不会标记为正常完成。"
        ).classes("card-sub")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("取消", on_click=abort_dialog.close).props("flat no-caps")
            ui.button("确认中止", color="negative", on_click=confirm_abort).props("unelevated no-caps")

    async def attach_video() -> None:
        path = (attach_video_input.value or "").strip() or None
        try:
            await asyncio.to_thread(core.set_trial_video, path)
            ui.notify("视频路径已更新（仅关联已有文件，不自动录像）", type="positive")
        except Exception as exc:
            ui.notify(error_text(exc), type="negative")
        refresh()

    async def add_event() -> None:
        message = (event_input.value or "").strip()
        if not message:
            ui.notify("请填写事件内容", type="warning")
            return
        try:
            await asyncio.to_thread(core.add_trial_event, event_type.value or "MARKER", message, {"source": core.source.value})
            event_input.value = ""
            ui.notify("事件标记已添加", type="positive")
        except Exception as exc:
            ui.notify(error_text(exc), type="negative")
        refresh()

    async def export_csv() -> None:
        trial_id = None
        if core.trial is not None:
            trial_id = core.trial.metadata.trial_id
        elif core.last_trial is not None:
            trial_id = core.last_trial.get("trial_id")
        if not trial_id:
            ui.notify("没有可导出的实验", type="warning")
            return
        try:
            path = await asyncio.to_thread(core.trial_store.export_csv, trial_id)
            ui.notify(f"CSV 已导出：{path}", type="positive")
        except Exception as exc:
            ui.notify(error_text(exc), type="negative")
        refresh()

    create_button.on_click(create_trial)
    start_button.on_click(start_trial)
    stop_button.on_click(stop_trial)
    abort_button.on_click(abort_dialog.open)
    attach_video_button.on_click(attach_video)
    add_event_button.on_click(add_event)
    export_button.on_click(export_csv)

    refresh()
    ui.timer(1.0, refresh)
