"""Analysis & Diagnostics page: read-only trial inspection and replay."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from datetime import datetime

from nicegui import ui

from ...constants import SOFTWARE_VERSION
from ..charts import bar_options, fsr_trend_options, heatmap_options, line_options, pwm_timeline_options
from ..theme import card_header, empty_state, notice, pill, set_pill, shell, tone_for_state
from ..text_zh import (
    action_label,
    error_text,
    event_detail_label,
    event_type_label,
    firmware_state_label,
    mode_label,
    record_type_label,
    source_label,
    stage_label,
    status_explanation,
    trial_status_label,
)


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
    return (
        f"{metadata['trial_id']} · {metadata['name']} · "
        f"{source_label(metadata['source'])} · {trial_status_label(metadata['status'])}"
    )


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
        "分析与诊断",
        "历史实验只读回放、控制事件、异常与数据完整性检查",
        core,
        SOFTWARE_VERSION,
    ) as refs:
        with ui.element("div").classes("card gap-3"):
            with ui.row().classes("w-full items-center gap-3"):
                ui.label("实验筛选").classes("card-kicker")
                source_filter = ui.select(
                    {
                        "ALL": "全部来源",
                        "SIMULATION": "仿真（SIMULATION）",
                        "LIVE": "真实设备（LIVE）",
                        "REPLAY": "只读回放（REPLAY）",
                    },
                    value="ALL",
                    label="来源",
                ).props("outlined dense").classes("w-40")
                status_filter = ui.select(
                    {
                        "ALL": "全部状态",
                        "COMPLETED": "正常完成（COMPLETED）",
                        "ABORTED": "已中止（ABORTED）",
                        "INTERRUPTED": "异常中断（INTERRUPTED）",
                        "ERROR": "写入错误（ERROR）",
                        "RECORDING": "记录中（RECORDING）",
                        "CREATED": "已创建（CREATED）",
                    },
                    value="ALL",
                    label="实验状态",
                ).props("outlined dense").classes("w-44")
                search_input = ui.input("搜索", placeholder="实验名 / ID / 操作员 / 视频").props("outlined dense").classes("flex-1")
                refresh_button = ui.button("刷新列表", color="secondary").props("outline no-caps")
                export_button = ui.button("导出 CSV", color="secondary").props("outline no-caps")
                ui.label("只读回放 · 不发送 PWM").classes("notice").style("width:auto")
            with ui.row().classes("w-full items-center gap-3"):
                trial_select = ui.select(
                    initial_options,
                    value=next(iter(initial_options), None),
                ).props("outlined dense placeholder=\"选择已保存的实验\"").classes("flex-1")
                load_button = ui.button("加载实验", color="primary").props("unelevated no-caps")
            with ui.row().classes("w-full items-center gap-3"):
                compare_select = ui.select(
                    initial_options, value=[], multiple=True, label="实验对比（可多选）",
                ).props("outlined dense").classes("flex-1")
                compare_button = ui.button("对比所选实验", color="secondary").props("outline no-caps")
            ui.label(
                "回放只读取 JSONL/CSV 与元数据；本页没有 Apply PWM 入口，也不会触碰 S3 串口。"
            ).classes("card-sub")
            comparison_holder = ui.column().classes("w-full")
            comparison_table = ui.table(
                columns=[
                    {"name": "trial", "label": "实验", "field": "trial", "align": "left"},
                    {"name": "source", "label": "来源", "field": "source", "align": "left"},
                    {"name": "status", "label": "状态", "field": "status", "align": "left"},
                    {"name": "frames", "label": "帧数", "field": "frames", "align": "right"},
                    {"name": "control", "label": "控制事件", "field": "control", "align": "right"},
                    {"name": "ack", "label": "设备确认（ACK）", "field": "ack", "align": "right"},
                    {"name": "dropped", "label": "丢帧", "field": "dropped", "align": "right"},
                    {"name": "invalid", "label": "无效通道样本", "field": "invalid", "align": "right"},
                    {"name": "video", "label": "视频", "field": "video", "align": "left"},
                ],
                rows=[],
                row_key="trial",
            ).props('flat dense no-data-label="暂无数据"').classes("w-full")
            comparison_holder.set_visibility(False)
            comparison_table.set_visibility(False)

        analysis_body = ui.column().classes("w-full gap-4")

        with ui.row().classes("w-full items-center gap-3"):
            play_button = ui.button("播放回放", color="secondary").props("outline no-caps")
            step_back = ui.button("上一帧", color="secondary").props("outline no-caps")
            step_forward = ui.button("下一帧", color="secondary").props("outline no-caps")
            replay_status = ui.label("尚未加载实验").classes("mono")
            ui.label("回放只更新界面帧索引，不发送控制命令").classes("card-sub").style("margin-left:auto")

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
            ui.notify("请至少选择两个实验进行对比", type="warning")
            return
        rows = []
        comparisons = []
        for trial_id in ids[:8]:
            try:
                record = core.read_trial(trial_id)
            except Exception as exc:
                ui.notify(f"{trial_id}：{error_text(exc)}", type="negative")
                continue
            comparisons.append(record)
            row = comparison_summary(record)
            row["source"] = source_label(row.get("source"))
            row["status"] = trial_status_label(row.get("status"))
            row["video"] = Path(row["video"]).name if row.get("video") else "—"
            rows.append(row)
        state["comparison"] = comparisons
        comparison_table.rows = rows
        comparison_table.update()
        comparison_table.set_visibility(bool(rows))
        if rows:
            ui.notify(f"已对比 {len(rows)} 个实验（只读）", type="info")

    def export_selected() -> None:
        trial_id = trial_select.value
        if not trial_id:
            ui.notify("请先选择一个实验", type="warning")
            return
        try:
            path = core.trial_store.export_csv(trial_id)
            ui.notify(f"CSV 已导出：{path}", type="positive")
        except Exception as exc:
            ui.notify(error_text(exc), type="negative")

    def load_selected() -> None:
        trial_id = trial_select.value
        if not trial_id:
            ui.notify("请先选择一个实验", type="warning")
            return
        try:
            record = core.read_trial(trial_id)
        except Exception as exc:
            ui.notify(error_text(exc), type="negative")
            return
        state["record"] = record
        state["index"] = 0
        state["playing"] = False
        state["channels"] = _channel_ids(record["frames"])[:4]
        play_button.set_text("播放回放")
        replay_status.set_text(f"{trial_id} · {len(record['frames'])} 帧 · 只读回放")
        analysis_body.refresh()
        ui.notify(f"已加载 {trial_id}（只读回放）", type="info")

    @ui.refreshable
    def render_body() -> None:
        record = state["record"]
        if record is None:
            with ui.column().classes("card w-full"):
                empty_state(
                    "query_stats",
                    "尚未加载实验",
                    "从上方选择已保存的实验。回放不会触发任何真实 PWM 或串口写入。",
                )
            return
        metadata = record["metadata"]
        frames = record["frames"]
        events = record["events"]
        summary = record.get("summary") or {}
        parameters = metadata.get("parameters") or {}
        sensor_config = parameters.get("sensor_config") or {}
        matrix_count = sum(
            1
            for channel in sensor_config.get("channels", [])
            if channel.get("sensor_kind") == "MATRIX_CELL"
            or (channel.get("matrix_row") is not None and channel.get("matrix_col") is not None)
        )
        integrity = summary.get("integrity") or {}
        status = metadata.get("status", "UNKNOWN")
        if status == "INTERRUPTED":
            notice(
                "实验异常中断（INTERRUPTED）：软件未正常结束录制。已有帧/事件保留，"
                "但本实验不视为正常完成，也不计入完成实验。",
                "red",
            )
        if status == "ERROR" or metadata.get("write_error"):
            notice(f"实验写入错误（ERROR）：{metadata.get('write_error') or '写入失败，详见事件日志'}。", "red")
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
                            ui.label(metadata.get("name", "实验")).classes("metric-value")
                            git = (metadata.get("git_commit") or "未知")[:10]
                            ui.label(
                                f"{metadata.get('trial_id')} · {mode_label(metadata.get('mode'))} · "
                                f"{source_label(metadata.get('source'))} · {trial_status_label(status)} · "
                                f"schema v{metadata.get('schema_version', 1)} · Git Commit {git}"
                            ).classes("card-sub")
                            ui.label(
                                f"操作员：{metadata.get('operator') or '—'} · "
                                f"视频：{metadata.get('video_path') or '—'}"
                            ).classes("card-sub").style("word-break:break-all")
                            explanation = status_explanation(status)
                            if explanation:
                                ui.label(explanation).classes("card-sub")
                        with ui.row().classes("items-center gap-2"):
                            source_pill = pill(
                                source_label(metadata.get("source", "UNKNOWN")),
                                "purple" if metadata.get("source") == "REPLAY" else "teal" if metadata.get("source") == "SIMULATION" else "blue",
                            )
                            pill(trial_status_label(status), tone_for_state(status))
                    with ui.row().classes("w-full gap-6"):
                        for label, value in (
                            ("帧数", summary.get("frames", len(frames))),
                            ("控制事件", summary.get("control_events", 0)),
                            ("ACK 事件", summary.get("ack_events", 0)),
                            ("异常事件", summary.get("anomalies", 0)),
                            ("丢帧", integrity.get("dropped_frames", 0)),
                            ("无效通道样本", integrity.get("invalid_channel_samples", 0)),
                            ("创建时间", _clock(metadata.get("created_at"))),
                        ):
                            with ui.column().classes("gap-0"):
                                ui.label(str(label)).classes("card-kicker")
                                ui.label(str(value)).classes("card-title")
                    ui.label(str(record.get("directory", ""))).classes("mono").style("color:#94a3b8;word-break:break-all")

            if record.get("read_errors"):
                with ui.element("div").classes("col-12"):
                    notice("读取问题：" + " | ".join(record["read_errors"][:4]), "amber")

            with ui.element("div").classes("col-7"):
                with ui.column().classes("card gap-3"):
                    with ui.row().classes("w-full items-start justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label("触觉帧检查").classes("card-title")
                            ui.label("无效通道显示为空隙，不按零接触解释").classes("card-sub")
                        frame_label = ui.label("无触觉帧").classes("mono")
                    if frames:
                        index = max(0, min(state["index"], len(frames) - 1))
                        state["index"] = index
                        frame = frames[index]
                        frame_label.set_text(
                            f"第 {index + 1}/{len(frames)} 帧 · 序号 {frame.get('frame_seq')} · "
                            f"{sum(1 for flag in (frame.get('valid_mask') or []) if flag)}/{frame.get('channel_count')} 有效"
                        )
                        slider = ui.slider(min=0, max=max(0, len(frames) - 1), value=index, step=1).props("label").classes("w-full")
                        chart_holder = ui.column().classes("w-full")
                        with chart_holder:
                            if matrix_count and frame.get("matrix_rows") and frame.get("matrix_cols"):
                                ui.echart(heatmap_options(frame, sensor_config)).classes("w-full").style("height:300px")
                            else:
                                ui.echart(bar_options(frame)).classes("w-full").style("height:300px")

                        def on_frame_change(event) -> None:
                            if event.value is None:
                                return
                            state["index"] = int(event.value)
                            state["playing"] = False
                            play_button.set_text("播放回放")
                            render_body.refresh()

                        slider.on_value_change(on_frame_change)
                    else:
                        empty_state("grid_off", "无触觉帧", "该实验没有保存触觉帧；控制事件仍可查看。")

            fsr_history = [
                {
                    "frame_seq": item.get("frame_seq"),
                    "score": (item.get("contact_assessment") or {}).get("score"),
                    "readings": (item.get("contact_assessment") or {}).get("readings") or [],
                }
                for item in frames
                if (item.get("contact_assessment") or {}).get("readings")
            ]
            if fsr_history:
                with ui.element("div").classes("col-5"):
                    with ui.column().classes("card gap-3"):
                        with card_header("FSR 相对接触", "原始 ADC 与相对评分；电压仅在 HELLO 基准完整时记录"):
                            pass
                        latest_fsr = fsr_history[-1]
                        with ui.row().classes("w-full gap-3"):
                            for reading in latest_fsr["readings"]:
                                with ui.column().classes("gap-0"):
                                    ui.label(str(reading.get("name") or f"FSR{reading.get('channel_id')}")).classes("card-kicker")
                                    raw = reading.get("raw")
                                    ui.label("无效/缺失" if not reading.get("valid") or raw is None else f"{int(raw)} counts").classes("mono")
                                    if reading.get("voltage_basis_complete") and reading.get("voltage_uv") is not None:
                                        ui.label(f"{reading['voltage_uv'] / 1e6:.3f} V").classes("card-sub")
                                    else:
                                        ui.label("电压基准未完整").classes("card-sub")
                                    if reading.get("relative_change") is not None:
                                        ui.label(f"{reading['relative_change'] * 100:+.1f}%").classes("card-sub")
                        ui.echart(fsr_trend_options(fsr_history[:300])).classes("w-full").style("height:180px")

            with ui.element("div").classes("col-5"):
                with ui.column().classes("card gap-3"):
                    with card_header("实验参数", "实验条件与参数快照"):
                        pass
                    for title, value in (("实验条件", metadata.get("conditions")), ("参数快照", metadata.get("parameters"))):
                        ui.label(title).classes("card-kicker")
                        ui.code(
                            json.dumps(value or {}, ensure_ascii=False, indent=2),
                            language="json",
                        ).classes("w-full").style("max-height:160px;overflow:auto;font-size:11px")

            with ui.element("div").classes("col-7"):
                with ui.column().classes("card gap-3"):
                    with card_header("控制事件", "命令阶段与设备确认（ACK）；实际位置始终为未知（UNKNOWN）"):
                        pass
                    control_rows = []
                    for item in events:
                        if item.get("record_type") != "CONTROL_EVENT":
                            continue
                        control_rows.append(
                            {
                                "id": item.get("event_id", ""),
                                "time": _clock(item.get("timestamp_utc")),
                                "action": action_label(item.get("action")),
                                "stage": stage_label(item.get("stage")),
                                "pwm": item.get("commanded_pwm_us") if item.get("commanded_pwm_us") is not None else "—",
                                "ack": "已确认" if item.get("device_ack") else "—",
                                "device": firmware_state_label(item.get("firmware_state") or "—"),
                                "detail": (
                                    (
                                        ((item.get("command_id") or "")[:8] + " · ")
                                        if item.get("command_id") else ""
                                    ) + event_detail_label(item.get("detail") or "")
                                )[:100],
                            }
                        )
                    ui.table(
                        columns=[
                            {"name": "time", "label": "时间", "field": "time", "align": "left", "style": "width:150px;white-space:nowrap"},
                            {"name": "action", "label": "动作", "field": "action", "align": "left", "style": "width:105px"},
                            {"name": "stage", "label": "阶段", "field": "stage", "align": "left", "style": "width:115px"},
                            {"name": "pwm", "label": "PWM 目标", "field": "pwm", "align": "right", "style": "width:80px"},
                            {"name": "ack", "label": "设备确认（ACK）", "field": "ack", "align": "center", "style": "width:90px"},
                            {"name": "device", "label": "设备状态", "field": "device", "align": "left", "style": "width:120px"},
                            {"name": "detail", "label": "说明", "field": "detail", "align": "left"},
                        ],
                        rows=control_rows,
                        row_key="id",
                    ).props('flat dense no-data-label="暂无数据"').classes("w-full")

            with ui.element("div").classes("col-5"):
                with ui.column().classes("card gap-3"):
                    with card_header("PWM 变化曲线", "SET_PWM 目标与时间；ACK 不是位置反馈"):
                        pass
                    pwm_options = pwm_timeline_options(events)
                    if pwm_options:
                        ui.echart(pwm_options).classes("w-full").style("height:250px")
                        ui.label(
                            "红点：失败/拒绝；深绿：有设备确认（ACK）；灰点：无 ACK 或仿真。曲线不代表实际机械位置。"
                        ).classes("card-sub")
                    else:
                        empty_state("timeline", "无 PWM 目标", "该实验没有可用的 SET_PWM 目标记录。")

            with ui.element("div").classes("col-6"):
                with ui.column().classes("card gap-3"):
                    with card_header("故障与异常", "异常、拒绝与中断事件"):
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
                                "type": event_type_label(item.get("event_type")) if item.get("event_type") else stage_label(item.get("stage")),
                                "detail": event_detail_label(item.get("message") or item.get("detail", "")),
                            }
                        )
                    if anomaly_rows:
                        ui.table(
                            columns=[
                                {"name": "time", "label": "时间", "field": "time", "align": "left"},
                                {"name": "type", "label": "类型", "field": "type", "align": "left"},
                                {"name": "detail", "label": "说明", "field": "detail", "align": "left"},
                            ],
                            rows=anomaly_rows,
                            row_key="id",
                        ).props('flat dense no-data-label="暂无数据"').classes("w-full")
                    else:
                        ui.label("未记录异常事件。").classes("card-sub")

            with ui.element("div").classes("col-6"):
                with ui.column().classes("card gap-3"):
                    with card_header("触觉趋势", "读取已保存帧；仅显示有效值"):
                        pass
                    if frames:
                        channels = _channel_ids(frames)
                        selected = [item for item in state["channels"] if item in channels][:8] or channels[:4]
                        channel_select = ui.select(
                            channels,
                            value=selected,
                            multiple=True,
                            label="通道",
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
                        ui.label("没有可绘制的触觉帧。").classes("card-sub")

            if events:
                with ui.element("div").classes("col-12"):
                    with ui.column().classes("card gap-3"):
                        with card_header("实验事件日志", "实验事件与操作标记"):
                            pass
                        rows = []
                        for item in events[-25:]:
                            rows.append(
                                {
                                    "id": item.get("event_id", ""),
                                    "time": _clock(item.get("timestamp_utc")),
                                    "record_type": record_type_label(item.get("record_type", "—")),
                                    "type": event_type_label(item.get("event_type")) if item.get("event_type") else action_label(item.get("action")) or "—",
                                    "message": event_detail_label(item.get("message") or item.get("detail", "")),
                                }
                            )
                        ui.table(
                            columns=[
                                {"name": "time", "label": "时间", "field": "time", "align": "left"},
                                {"name": "record_type", "label": "记录类型", "field": "record_type", "align": "left"},
                                {"name": "type", "label": "类型", "field": "type", "align": "left"},
                                {"name": "message", "label": "内容", "field": "message", "align": "left"},
                            ],
                            rows=rows,
                            row_key="id",
                        ).props('flat dense no-data-label="暂无数据"').classes("w-full")

    def step_replay() -> None:
        record = state["record"]
        if record is None or not record["frames"]:
            state["playing"] = False
            play_button.set_text("播放回放")
            return
        state["index"] = (state["index"] + 1) % len(record["frames"])
        render_body.refresh()

    play_timer = ui.timer(0.4, step_replay, active=False)

    def toggle_play() -> None:
        if state["record"] is None or not state["record"]["frames"]:
            ui.notify("没有可回放的触觉帧", type="warning")
            return
        state["playing"] = not state["playing"]
        play_timer.active = state["playing"]
        play_button.set_text("暂停回放" if state["playing"] else "播放回放")

    def step(delta: int) -> None:
        record = state["record"]
        if record is None or not record["frames"]:
            return
        state["playing"] = False
        play_timer.active = False
        play_button.set_text("播放回放")
        state["index"] = (state["index"] + delta) % len(record["frames"])
        render_body.refresh()

    play_button.on_click(toggle_play)
    step_back.on_click(lambda: step(-1))
    step_forward.on_click(lambda: step(1))
    refresh_button.on_click(lambda: (refresh_list(), ui.notify("实验列表已刷新", type="info")))
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
            replay_status.set_text(f"{record['metadata']['trial_id']} · {len(record['frames'])} 帧 · 只读回放")
        except Exception:
            pass
    with analysis_body:
        render_body()
