"""Analysis & Diagnostics page: read-only trial inspection and replay."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from datetime import datetime

from nicegui import ui

from ...constants import SOFTWARE_VERSION
from ..charts import bar_options, heatmap_options, line_options, pwm_timeline_options
from ..theme import card_header, empty_state, notice, pill, set_pill, shell, tone_for_state


def _clock(stamp: str | None) -> str:
    if not stamp:
        return "—"
    try:
        return datetime.fromisoformat(stamp).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return stamp


def _channel_ids(records: list[dict]) -> list[int]:
    result: list[int] = []
    for frame in records:
        ids = frame.get("channel_ids")
        if ids is None:
            ids = list(range(frame.get("channel_count", 0)))
        for channel_id in ids:
            if int(channel_id) not in result:
                result.append(int(channel_id))
    return sorted(result)


def _option(metadata: dict) -> str:
    return f"{metadata['trial_id']} · {metadata['name']} · {metadata['source']} · {metadata['status']}"


def _matches(metadata: dict, source: str, status: str, search: str) -> bool:
    if source != "ALL" and metadata.get("source") != source:
        return False
    if status != "ALL" and metadata.get("status") != status:
        return False
    if search:
        haystack = " ".join(
            str(metadata.get(key) or "")
            for key in ("trial_id", "name", "operator", "video_path", "tags", "conditions")
        ).lower()
        if search.lower() not in haystack:
            return False
    return True


def analysis_page(core) -> None:
    state: dict = {"record": None, "index": 0, "playing": False, "channels": [], "comparison": []}
    initial_trials = core.list_trials()
    initial_options = {item["trial_id"]: _option(item) for item in initial_trials}

    with shell(
        "analysis",
        "Analysis & Diagnostics",
        "历史 Trial 只读回放、控制事件与异常检查",
        core,
        SOFTWARE_VERSION,
    ) as refs:
        with ui.element("div").classes("card gap-3"):
            with ui.row().classes("w-full items-center gap-3"):
                ui.label("Trial Index").classes("card-kicker")
                source_filter = ui.select(
                    {"ALL": "ALL sources", "SIMULATION": "SIMULATION", "LIVE": "LIVE", "REPLAY": "REPLAY"},
                    value="ALL",
                    label="Source",
                ).props("outlined dense").classes("w-40")
                status_filter = ui.select(
                    {"ALL": "ALL status", "COMPLETED": "COMPLETED", "ABORTED": "ABORTED", "INTERRUPTED": "INTERRUPTED", "ERROR": "ERROR", "RECORDING": "RECORDING", "CREATED": "CREATED"},
                    value="ALL",
                    label="Status",
                ).props("outlined dense").classes("w-44")
                search_input = ui.input("Search", placeholder="name / id / operator / video").props("outlined dense").classes("flex-1")
                refresh_button = ui.button("Refresh", color="secondary").props("outline no-caps")
                export_button = ui.button("Export CSV", color="secondary").props("outline no-caps")
                ui.label("READ-ONLY REPLAY · 不发送 PWM").classes("notice").style("width:auto")
            with ui.row().classes("w-full items-center gap-3"):
                trial_select = ui.select(
                    initial_options,
                    value=next(iter(initial_options), None),
                ).props("outlined dense placeholder=\"Select a saved trial\"").classes("flex-1")
                load_button = ui.button("Load trial", color="primary").props("unelevated no-caps")
            with ui.row().classes("w-full items-center gap-3"):
                compare_select = ui.select(
                    initial_options, value=[], multiple=True, label="Compare trials",
                ).props("outlined dense").classes("flex-1")
                compare_button = ui.button("Compare selected", color="secondary").props("outline no-caps")
            ui.label(
                "回放只读取 JSONL/CSV 与元数据；此页面没有 Apply PWM 入口，也不会触碰 S3 串口。"
            ).classes("card-sub")
            comparison_holder = ui.column().classes("w-full")
            comparison_table = ui.table(
                columns=[
                    {"name": "trial", "label": "TRIAL", "field": "trial", "align": "left"},
                    {"name": "source", "label": "SOURCE", "field": "source", "align": "left"},
                    {"name": "status", "label": "STATUS", "field": "status", "align": "left"},
                    {"name": "frames", "label": "FRAMES", "field": "frames", "align": "right"},
                    {"name": "control", "label": "CONTROL", "field": "control", "align": "right"},
                    {"name": "ack", "label": "ACK", "field": "ack", "align": "right"},
                    {"name": "dropped", "label": "DROPPED", "field": "dropped", "align": "right"},
                    {"name": "invalid", "label": "INVALID", "field": "invalid", "align": "right"},
                    {"name": "video", "label": "VIDEO", "field": "video", "align": "left"},
                ],
                rows=[],
                row_key="trial",
            ).props("flat dense").classes("w-full")
            comparison_holder.set_visibility(False)
            comparison_table.set_visibility(False)

        analysis_body = ui.column().classes("w-full gap-4")

        with ui.row().classes("w-full items-center gap-3"):
            play_button = ui.button("Play replay", color="secondary").props("outline no-caps")
            step_back = ui.button("−1", color="secondary").props("outline no-caps")
            step_forward = ui.button("+1", color="secondary").props("outline no-caps")
            replay_status = ui.label("No trial loaded").classes("mono")
            ui.label("replay ticker 只更新界面帧索引").classes("card-sub").style("margin-left:auto")

    def filtered_trials() -> list[dict]:
        return [
            item for item in core.list_trials()
            if _matches(item, source_filter.value or "ALL", status_filter.value or "ALL", (search_input.value or "").strip())
        ]

    def trial_options() -> dict[str, str]:
        return {item["trial_id"]: _option(item) for item in filtered_trials()}

    def refresh_list() -> None:
        options = trial_options()
        trial_select.options = options
        if options and trial_select.value not in options:
            trial_select.value = next(iter(options))
        if not options:
            trial_select.value = None
        trial_select.update()
        compare_select.options = options
        if compare_select.value:
            compare_select.value = [item for item in compare_select.value if item in options]
        compare_select.update()

    def compare_selected() -> None:
        ids = list(compare_select.value or [])
        if len(ids) < 2:
            ui.notify("Select at least two trials to compare", type="warning")
            return
        rows = []
        comparisons = []
        for trial_id in ids[:8]:
            try:
                record = core.read_trial(trial_id)
            except Exception as exc:
                ui.notify(f"{trial_id}: {exc}", type="negative")
                continue
            comparisons.append(record)
            row = comparison_summary(record)
            row["video"] = Path(row["video"]).name if row.get("video") else "—"
            rows.append(row)
        state["comparison"] = comparisons
        comparison_table.rows = rows
        comparison_table.update()
        comparison_table.set_visibility(bool(rows))
        if rows:
            ui.notify(f"Compared {len(rows)} trials (read-only)", type="info")

    def export_selected() -> None:
        trial_id = trial_select.value
        if not trial_id:
            ui.notify("Select a trial first", type="warning")
            return
        try:
            path = core.trial_store.export_csv(trial_id)
            ui.notify(f"CSV exported: {path}", type="positive")
        except Exception as exc:
            ui.notify(str(exc), type="negative")

    def load_selected() -> None:
        trial_id = trial_select.value
        if not trial_id:
            ui.notify("Select a trial first", type="warning")
            return
        try:
            record = core.read_trial(trial_id)
        except Exception as exc:
            ui.notify(str(exc), type="negative")
            return
        state["record"] = record
        state["index"] = 0
        state["playing"] = False
        state["channels"] = _channel_ids(record["frames"])[:4]
        play_button.set_text("Play replay")
        replay_status.set_text(f"{trial_id} · {len(record['frames'])} frames · read-only")
        analysis_body.refresh()
        ui.notify(f"Loaded {trial_id} (REPLAY)", type="info")

    @ui.refreshable
    def render_body() -> None:
        record = state["record"]
        if record is None:
            with ui.column().classes("card w-full"):
                empty_state(
                    "query_stats",
                    "NO TRIAL LOADED",
                    "从上方选择已保存的 Trial。回放不会触发任何真实 PWM 或串口写入。",
                )
            return
        metadata = record["metadata"]
        frames = record["frames"]
        events = record["events"]
        summary = record.get("summary") or {}
        integrity = summary.get("integrity") or {}
        status = metadata.get("status", "UNKNOWN")
        if status == "INTERRUPTED":
            notice(
                "TRIAL INTERRUPTED：软件未正常结束录制。已有帧/事件保留，但本 Trial "
                "不视为正常完成，不计入完成 Trial。",
                "red",
            )
        if status == "ERROR" or metadata.get("write_error"):
            notice(f"TRIAL WRITE ERROR：{metadata.get('write_error') or '写入失败，详见事件日志'}。", "red")
        if integrity.get("truncated_tail"):
            notice("检测到不完整的 JSONL 尾行；已忽略该尾行并保留之前完整记录。", "amber")
        if integrity.get("dropped_frames") or integrity.get("frames_with_invalid_channels"):
            notice(
                f"数据完整性：丢帧 {integrity.get('dropped_frames', 0)}，"
                f"含无效通道的帧 {integrity.get('frames_with_invalid_channels', 0)}。"
                "无效通道不会被当作零接触。",
                "amber",
            )
        with ui.element("div").classes("grid-12"):
            with ui.element("div").classes("col-12"):
                with ui.column().classes("card gap-2"):
                    with ui.row().classes("w-full items-start justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label(metadata.get("name", "Trial")).classes("metric-value")
                            git = (metadata.get("git_commit") or "UNKNOWN")[:10]
                            ui.label(
                                f"{metadata.get('trial_id')} · {metadata.get('mode')} · {metadata.get('source')} · "
                                f"{status} · schema v{metadata.get('schema_version', 1)} · git {git}"
                            ).classes("card-sub")
                            ui.label(
                                f"operator: {metadata.get('operator') or '—'} · "
                                f"video: {metadata.get('video_path') or '—'}"
                            ).classes("card-sub").style("word-break:break-all")
                        with ui.row().classes("items-center gap-2"):
                            source_pill = pill(metadata.get("source", "UNKNOWN"), "purple" if metadata.get("source") == "REPLAY" else "teal" if metadata.get("source") == "SIMULATION" else "blue")
                            pill(status, tone_for_state(status))
                    with ui.row().classes("w-full gap-6"):
                        for label, value in (
                            ("FRAMES", summary.get("frames", len(frames))),
                            ("CONTROL EVENTS", summary.get("control_events", 0)),
                            ("ACK EVENTS", summary.get("ack_events", 0)),
                            ("ANOMALIES", summary.get("anomalies", 0)),
                            ("DROPPED", integrity.get("dropped_frames", 0)),
                            ("INVALID SAMPLES", integrity.get("invalid_channel_samples", 0)),
                            ("CREATED", _clock(metadata.get("created_at"))),
                        ):
                            with ui.column().classes("gap-0"):
                                ui.label(str(label)).classes("card-kicker")
                                ui.label(str(value)).classes("card-title")
                    ui.label(str(record.get("directory", ""))).classes("mono").style("color:#94a3b8;word-break:break-all")

            if record.get("read_errors"):
                with ui.element("div").classes("col-12"):
                    notice("Read issues: " + " | ".join(record["read_errors"][:4]), "amber")

            with ui.element("div").classes("col-7"):
                with ui.column().classes("card gap-3"):
                    with ui.row().classes("w-full items-start justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label("Frame Inspector").classes("card-title")
                            ui.label("无效通道显示为空隙，不按零接触解释").classes("card-sub")
                        frame_label = ui.label("no frames").classes("mono")
                    if frames:
                        index = max(0, min(state["index"], len(frames) - 1))
                        state["index"] = index
                        frame = frames[index]
                        frame_label.set_text(
                            f"frame {index + 1}/{len(frames)} · seq {frame.get('frame_seq')} · "
                            f"{sum(1 for flag in (frame.get('valid_mask') or []) if flag)}/{frame.get('channel_count')} valid"
                        )
                        slider = ui.slider(min=0, max=max(0, len(frames) - 1), value=index, step=1).props("label").classes("w-full")
                        chart_holder = ui.column().classes("w-full")
                        with chart_holder:
                            if frame.get("matrix_rows") and frame.get("matrix_cols") and frame.get("channel_count") == frame["matrix_rows"] * frame["matrix_cols"]:
                                ui.echart(heatmap_options(frame)).classes("w-full").style("height:300px")
                            else:
                                ui.echart(bar_options(frame)).classes("w-full").style("height:300px")

                        def on_frame_change(event) -> None:
                            if event.value is None:
                                return
                            state["index"] = int(event.value)
                            state["playing"] = False
                            play_button.set_text("Play replay")
                            render_body.refresh()

                        slider.on_value_change(on_frame_change)
                    else:
                        empty_state("grid_off", "NO SENSOR FRAMES", "该 Trial 没有保存触觉帧；控制事件仍可查看。")

            with ui.element("div").classes("col-5"):
                with ui.column().classes("card gap-3"):
                    with card_header("Conditions & Parameters", "实验条件与参数快照"):
                        pass
                    for title, value in (("Conditions", metadata.get("conditions")), ("Parameters", metadata.get("parameters"))):
                        ui.label(title).classes("card-kicker")
                        ui.code(
                            json.dumps(value or {}, ensure_ascii=False, indent=2),
                            language="json",
                        ).classes("w-full").style("max-height:160px;overflow:auto;font-size:11px")

            with ui.element("div").classes("col-7"):
                with ui.column().classes("card gap-3"):
                    with card_header("Control Events", "命令阶段与设备 ACK；actual position 始终为 UNKNOWN"):
                        pass
                    control_rows = []
                    for item in events:
                        if item.get("record_type") != "CONTROL_EVENT":
                            continue
                        control_rows.append(
                            {
                                "id": item.get("event_id", ""),
                                "time": _clock(item.get("timestamp_utc")),
                                "action": item.get("action"),
                                "stage": item.get("stage"),
                                "pwm": item.get("commanded_pwm_us") if item.get("commanded_pwm_us") is not None else "—",
                                "ack": "ACK" if item.get("device_ack") else "—",
                                "device": item.get("firmware_state") or "—",
                                "detail": (
                                    (
                                        ((item.get("command_id") or "")[:8] + " · ")
                                        if item.get("command_id") else ""
                                    ) + (item.get("detail") or "")
                                )[:85],
                            }
                        )
                    ui.table(
                        columns=[
                            {"name": "time", "label": "TIME", "field": "time", "align": "left", "style": "width:150px;white-space:nowrap"},
                            {"name": "action", "label": "ACTION", "field": "action", "align": "left", "style": "width:105px"},
                            {"name": "stage", "label": "STAGE", "field": "stage", "align": "left", "style": "width:105px"},
                            {"name": "pwm", "label": "PWM", "field": "pwm", "align": "right", "style": "width:70px"},
                            {"name": "ack", "label": "ACK", "field": "ack", "align": "center", "style": "width:60px"},
                            {"name": "device", "label": "DEVICE", "field": "device", "align": "left", "style": "width:115px"},
                            {"name": "detail", "label": "DETAIL", "field": "detail", "align": "left"},
                        ],
                        rows=control_rows,
                        row_key="id",
                    ).props("flat dense").classes("w-full")

            with ui.element("div").classes("col-5"):
                with ui.column().classes("card gap-3"):
                    with card_header("PWM Timeline", "SET_PWM 目标与时间；ACK 不是位置反馈"):
                        pass
                    pwm_options = pwm_timeline_options(events)
                    if pwm_options:
                        ui.echart(pwm_options).classes("w-full").style("height:250px")
                        ui.label(
                            "红点：失败/拒绝；深绿：有 ACK；灰点：无 ACK 或模拟。未绘制的点不代表机械位置。"
                        ).classes("card-sub")
                    else:
                        empty_state("timeline", "NO PWM COMMANDS", "该 Trial 没有可用的 SET_PWM 目标记录。")

            with ui.element("div").classes("col-6"):
                with ui.column().classes("card gap-3"):
                    with card_header("Anomalies", "异常与拒绝事件"):
                        pass
                    anomaly_rows = []
                    for item in events:
                        is_anomaly = (
                            item.get("record_type") == "TRIAL_EVENT"
                            and item.get("event_type") in (
                                "ANOMALY", "SENSOR_ERROR", "FRAME_ANOMALY", "FAULT",
                                "TRIAL_INTERRUPTED", "TRIAL_WRITE_ERROR",
                            )
                        ) or (item.get("record_type") == "CONTROL_EVENT" and item.get("stage") in (
                            "REJECTED", "FAILED", "UNSUPPORTED", "TIMEOUT",
                            "INVALID_DATA", "OFFLINE", "DEVICE_ERROR",
                        ))
                        if not is_anomaly:
                            continue
                        anomaly_rows.append(
                            {
                                "id": item.get("event_id", ""),
                                "time": _clock(item.get("timestamp_utc")),
                                "type": item.get("event_type") or item.get("stage"),
                                "detail": item.get("message") or item.get("detail", ""),
                            }
                        )
                    if anomaly_rows:
                        ui.table(
                            columns=[
                                {"name": "time", "label": "TIME", "field": "time", "align": "left"},
                                {"name": "type", "label": "TYPE", "field": "type", "align": "left"},
                                {"name": "detail", "label": "DETAIL", "field": "detail", "align": "left"},
                            ],
                            rows=anomaly_rows,
                            row_key="id",
                        ).props("flat dense").classes("w-full")
                    else:
                        ui.label("No anomaly events recorded.").classes("card-sub")

            with ui.element("div").classes("col-6"):
                with ui.column().classes("card gap-3"):
                    with card_header("Channel Trend", "读取已保存帧；仅显示有效值"):
                        pass
                    if frames:
                        channels = _channel_ids(frames)
                        selected = [item for item in state["channels"] if item in channels][:8] or channels[:4]
                        channel_select = ui.select(
                            channels,
                            value=selected,
                            multiple=True,
                            label="Channels",
                        ).props("outlined dense").classes("w-full")
                        trend_holder = ui.column().classes("w-full")
                        with trend_holder:
                            ui.echart(line_options(frames, selected)).classes("w-full").style("height:250px")

                        def on_channel_change(event) -> None:
                            state["channels"] = [int(item) for item in (event.value or [])][:8]
                            trend_holder.clear()
                            with trend_holder:
                                ui.echart(line_options(frames, state["channels"] or channels[:4])).classes("w-full").style("height:250px")

                        channel_select.on_value_change(on_channel_change)
                    else:
                        ui.label("No frames to plot.").classes("card-sub")

            if events:
                with ui.element("div").classes("col-12"):
                    with ui.column().classes("card gap-3"):
                        with card_header("Event Log", "Trial events and markers"):
                            pass
                        rows = []
                        for item in events[-25:]:
                            rows.append(
                                {
                                    "id": item.get("event_id", ""),
                                    "time": _clock(item.get("timestamp_utc")),
                                    "record_type": item.get("record_type", "—"),
                                    "type": item.get("event_type") or item.get("action") or "—",
                                    "message": item.get("message") or item.get("detail", ""),
                                }
                            )
                        ui.table(
                            columns=[
                                {"name": "time", "label": "TIME", "field": "time", "align": "left"},
                                {"name": "record_type", "label": "RECORD", "field": "record_type", "align": "left"},
                                {"name": "type", "label": "TYPE", "field": "type", "align": "left"},
                                {"name": "message", "label": "MESSAGE", "field": "message", "align": "left"},
                            ],
                            rows=rows,
                            row_key="id",
                        ).props("flat dense").classes("w-full")

    def step_replay() -> None:
        record = state["record"]
        if record is None or not record["frames"]:
            state["playing"] = False
            play_button.set_text("Play replay")
            return
        state["index"] = (state["index"] + 1) % len(record["frames"])
        render_body.refresh()

    play_timer = ui.timer(0.4, step_replay, active=False)

    def toggle_play() -> None:
        if state["record"] is None or not state["record"]["frames"]:
            ui.notify("No frames to replay", type="warning")
            return
        state["playing"] = not state["playing"]
        play_timer.active = state["playing"]
        play_button.set_text("Pause replay" if state["playing"] else "Play replay")

    def step(delta: int) -> None:
        record = state["record"]
        if record is None or not record["frames"]:
            return
        state["playing"] = False
        play_timer.active = False
        play_button.set_text("Play replay")
        state["index"] = (state["index"] + delta) % len(record["frames"])
        render_body.refresh()

    play_button.on_click(toggle_play)
    step_back.on_click(lambda: step(-1))
    step_forward.on_click(lambda: step(1))
    refresh_button.on_click(lambda: (refresh_list(), ui.notify("Trial list refreshed", type="info")))
    load_button.on_click(load_selected)
    compare_button.on_click(compare_selected)
    export_button.on_click(export_selected)
    source_filter.on_value_change(lambda _: refresh_list())
    status_filter.on_value_change(lambda _: refresh_list())
    search_input.on_value_change(lambda _: refresh_list())

    refresh_list()
    if trial_select.value:
        try:
            record = core.read_trial(trial_select.value)
            state["record"] = record
            state["channels"] = _channel_ids(record["frames"])[:4]
            replay_status.set_text(f"{record['metadata']['trial_id']} · {len(record['frames'])} frames · read-only")
        except Exception:
            pass
    with analysis_body:
        render_body()
