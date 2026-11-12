"""Analysis & Diagnostics page: read-only trial inspection and replay."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from nicegui import ui

from ...constants import SOFTWARE_VERSION
from ..charts import bar_options, heatmap_options, line_options
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


def analysis_page(core) -> None:
    state: dict = {"record": None, "index": 0, "playing": False, "channels": []}
    initial_options: dict[str, str] = {}
    for stored in core.trial_store.list_trials():
        metadata = stored.metadata
        initial_options[metadata.trial_id] = (
            f"{metadata.trial_id} · {metadata.name} · {metadata.source.value} · {metadata.status}"
        )

    with shell(
        "analysis",
        "Analysis & Diagnostics",
        "历史 Trial 只读回放、控制事件与异常检查",
        core,
        SOFTWARE_VERSION,
    ) as refs:
        with ui.element("div").classes("card gap-3"):
            with ui.row().classes("w-full items-center gap-3"):
                with ui.column().classes("gap-0 min-w-[260px]"):
                    ui.label("Trial Index").classes("card-kicker")
                    trial_select = ui.select(
                        initial_options,
                        value=next(iter(initial_options), None),
                    ).props("outlined dense placeholder=\"Select a saved trial\"").style("width:420px")
                refresh_button = ui.button("Refresh list", color="secondary").props("outline no-caps")
                load_button = ui.button("Load trial", color="primary").props("unelevated no-caps")
                ui.label("READ-ONLY REPLAY · 不发送 PWM").classes("notice").style("width:auto;margin-left:auto")
            ui.label(
                "回放只读取 JSONL/CSV 与元数据；此页面没有 Apply PWM 入口，也不会触碰 S3 串口。"
            ).classes("card-sub")

        analysis_body = ui.column().classes("w-full gap-4")

        with ui.row().classes("w-full items-center gap-3"):
            play_button = ui.button("Play replay", color="secondary").props("outline no-caps")
            step_back = ui.button("−1", color="secondary").props("outline no-caps")
            step_forward = ui.button("+1", color="secondary").props("outline no-caps")
            replay_status = ui.label("No trial loaded").classes("mono")
            ui.label("replay ticker 只更新界面帧索引").classes("card-sub").style("margin-left:auto")

    def trial_options() -> dict[str, str]:
        options = {}
        for stored in core.trial_store.list_trials():
            metadata = stored.metadata
            options[metadata.trial_id] = (
                f"{metadata.trial_id} · {metadata.name} · {metadata.source.value} · {metadata.status}"
            )
        return options

    def refresh_list() -> None:
        options = trial_options()
        trial_select.options = options
        if options and trial_select.value not in options:
            trial_select.value = next(iter(options))
        trial_select.update()

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
        with ui.element("div").classes("grid-12"):
            with ui.element("div").classes("col-12"):
                with ui.column().classes("card gap-2"):
                    with ui.row().classes("w-full items-start justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label(metadata.get("name", "Trial")).classes("metric-value")
                            ui.label(
                                f"{metadata.get('trial_id')} · {metadata.get('mode')} · {metadata.get('source')} · "
                                f"{metadata.get('status')}"
                            ).classes("card-sub")
                        with ui.row().classes("items-center gap-2"):
                            source_pill = pill(metadata.get("source", "UNKNOWN"), "purple" if metadata.get("source") == "REPLAY" else "teal" if metadata.get("source") == "SIMULATION" else "blue")
                            pill(metadata.get("status", "UNKNOWN"), tone_for_state(metadata.get("status", "")))
                    with ui.row().classes("w-full gap-6"):
                        for label, value in (
                            ("FRAMES", summary.get("frames", len(frames))),
                            ("CONTROL EVENTS", summary.get("control_events", 0)),
                            ("ANOMALIES", summary.get("anomalies", 0)),
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

            with ui.element("div").classes("col-12"):
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
                                "detail": item.get("detail", ""),
                            }
                        )
                    ui.table(
                        columns=[
                            {"name": "time", "label": "TIME", "field": "time", "align": "left"},
                            {"name": "action", "label": "ACTION", "field": "action", "align": "left"},
                            {"name": "stage", "label": "STAGE", "field": "stage", "align": "left"},
                            {"name": "pwm", "label": "PWM", "field": "pwm", "align": "right"},
                            {"name": "ack", "label": "ACK", "field": "ack", "align": "center"},
                            {"name": "detail", "label": "DETAIL", "field": "detail", "align": "left"},
                        ],
                        rows=control_rows,
                        row_key="id",
                    ).props("flat dense").classes("w-full")

            with ui.element("div").classes("col-6"):
                with ui.column().classes("card gap-3"):
                    with card_header("Anomalies", "异常与拒绝事件"):
                        pass
                    anomaly_rows = []
                    for item in events:
                        is_anomaly = (
                            item.get("record_type") == "TRIAL_EVENT"
                            and item.get("event_type") in ("ANOMALY", "SENSOR_ERROR", "FRAME_ANOMALY", "FAULT")
                        ) or (item.get("record_type") == "CONTROL_EVENT" and item.get("stage") in ("REJECTED", "FAILED", "UNSUPPORTED", "INVALID_DATA", "OFFLINE", "DEVICE_ERROR"))
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
