"""Live Monitor page."""

from __future__ import annotations

import asyncio
from datetime import datetime

from nicegui import ui

from ...constants import SOFTWARE_VERSION
from ...control import Mode
from ...sources import DataSource
from ..charts import bar_options, heatmap_options
from ..theme import (
    card_header,
    empty_state,
    fmt_ns,
    metric_card,
    pill,
    set_pill,
    shell,
    tone_for_state,
)


def _format_event(event: dict) -> dict:
    stamp = event.get("timestamp_utc") or ""
    try:
        clock = datetime.fromisoformat(stamp).strftime("%H:%M:%S")
    except ValueError:
        clock = "—"
    return {
        "id": event.get("event_id", f"{stamp}-{event.get('action')}"),
        "time": clock,
        "action": event.get("action", "—"),
        "stage": event.get("stage", "—"),
        "pwm": event.get("commanded_pwm_us") if event.get("commanded_pwm_us") is not None else "—",
        "ack": "ACK" if event.get("device_ack") else "—",
        "device": event.get("firmware_state") or "—",
        "detail": (event.get("detail") or "")[:70],
    }


def live_page(core) -> None:
    state = {"pending": 1500, "chart_key": None, "syncing": False}
    if core.gripper is not None:
        state["pending"] = core.gripper.pwm_initial_us or 1500
    limits = core.gripper.pwm_limits if core.gripper is not None else {
        "min_us": 500,
        "max_us": 2500,
        "initial_us": 1500,
        "source": "config/gripper_s3.json (Bench range)",
        "note": "Bench config range; NOT a verified mechanical safety limit.",
    }

    with shell(
        "live",
        "Live Monitor",
        "触觉闭环机械爪 · 单写入者控制台",
        core,
        SOFTWARE_VERSION,
    ) as refs:
        with ui.element("div").classes("grid-12"):
            with ui.element("div").classes("col-3"):
                s3_value, s3_caption = metric_card("S3 CONTROLLER", "memory", "OFFLINE", "No serial session")
            with ui.element("div").classes("col-3"):
                sensor_value, sensor_caption = metric_card("SENSOR LINK", "sensors", "SENSOR WAITING", "No real sensor")
            with ui.element("div").classes("col-3"):
                mode_value, mode_caption = metric_card("CONTROL MODE", "tune", "STANDBY", "Manual control idle")
            with ui.element("div").classes("col-3"):
                trial_value, trial_caption = metric_card("EXPERIMENT", "science", "NO TRIAL", "Create in Experiments")

        with ui.row().classes("w-full card notice-red items-center gap-3") as fault_banner:
            ui.icon("report_problem").style("color:#b91c1c;font-size:20px")
            fault_text = ui.label("FAULT").classes("card-title").style("color:#991b1b")
            fault_reset_button = ui.button("Reset fault", color="negative").props("outline no-caps").style("margin-left:auto")
        fault_banner.set_visibility(False)

        with ui.element("div").classes("grid-12"):
            with ui.element("div").classes("col-7"):
                with ui.column().classes("card gap-3"):
                    with ui.row().classes("w-full items-start justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label("Tactile Field").classes("card-title")
                            ui.label("原始 ADC 计数 · 无效通道不当作零接触").classes("card-sub")
                        with ui.row().classes("items-center gap-3"):
                            sensor_connect_button = ui.button("Connect sensor", color="secondary").props("outline no-caps")
                            demo_switch = ui.switch("SIMULATION demo", value=False).props("dense")
                            source_pill = pill("SIMULATION", "teal")
                    chart_holder = ui.column().classes("w-full")
                    with ui.row().classes("w-full items-center gap-4"):
                        contact_value = ui.label("UNKNOWN").classes("metric-value")
                        with ui.column().classes("gap-0"):
                            ui.label("CONTACT METRIC").classes("card-kicker")
                            contact_caption = ui.label("No calibrated contact metric").classes("metric-caption")
                        ui.element("div").classes("sidebar-spacer")
                        frame_caption = ui.label("no frames").classes("mono").style("color:#94a3b8")
                    ui.label(
                        "SIMULATION demo 只产生合成数据，始终标注来源；不会显示为 LIVE。"
                    ).classes("card-sub")

            with ui.element("div").classes("col-5"):
                with ui.column().classes("card gap-3"):
                    with ui.row().classes("w-full items-start justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label("Manual PWM").classes("card-title")
                            ui.label("Slider adjusts the pending target only").classes("card-sub")
                        pending_pill = pill("PENDING 1500 μs", "amber")
                    with ui.row().classes("items-baseline gap-2"):
                        pending_value = ui.label(str(state["pending"])).classes("value-mono")
                        ui.label("μs").classes("card-sub")
                        ui.label("target, not measured position").classes("card-sub").style("margin-left:auto")
                    pwm_slider = ui.slider(
                        min=limits["min_us"],
                        max=limits["max_us"],
                        step=10,
                        value=state["pending"],
                    ).props("label").classes("w-full")
                    with ui.row().classes("w-full items-center gap-2"):
                        pwm_number = ui.number(
                            value=state["pending"],
                            min=limits["min_us"],
                            max=limits["max_us"],
                            step=10,
                        ).props("outlined dense").classes("w-28")
                        ui.label(f"{limits['min_us']}–{limits['max_us']} μs from config").classes("card-sub")
                    with ui.row().classes("w-full gap-2"):
                        apply_button = ui.button("Apply PWM", color="primary").props("unelevated no-caps").classes("flex-1").style("height:42px")
                        stop_button = ui.button("STOP", color="negative").props("unelevated no-caps").classes("flex-1").style("height:42px")
                    apply_hint = ui.label("Connect a session to enable Apply").classes("card-sub")
                    ui.element("div").classes("hairline")
                    with ui.row().classes("w-full items-center justify-between"):
                        connection_label = ui.label("SESSION OFFLINE").classes("card-kicker")
                        connect_button = ui.button("Connect simulated S3", color="secondary").props("unelevated no-caps")
                    with ui.row().classes("w-full items-center gap-2"):
                        manual_mode_button = ui.button("MANUAL", color="primary").props("outline no-caps")
                        standby_mode_button = ui.button("STANDBY", color="secondary").props("outline no-caps")
                        auto_mode_button = ui.button("AUTO", color="secondary").props("outline no-caps")
                        ui.label("AUTO 需真实传感器 + 标定").classes("card-sub")
                    auto_hint = ui.label("AUTO unavailable").classes("card-sub")
                    ui.label(
                        f"Range: {limits['source'].split('/config/')[-1]}。Bench 配置范围，"
                        "不是已验证的机械安全边界。"
                    ).classes("card-sub")
                    ui.label("STOP 发送固件 STOP；不保证保持或释放，且不是硬件急停。").classes("notice notice-amber").style("width:100%")

        with ui.element("div").classes("grid-12"):
            with ui.element("div").classes("col-8"):
                with ui.column().classes("card gap-3"):
                    with card_header("Recent Control Decisions", "请求 → 写入 → ACK 与真实位置分开记录"):
                        pass
                    decision_table = ui.table(
                        columns=[
                            {"name": "time", "label": "TIME", "field": "time", "align": "left"},
                            {"name": "action", "label": "ACTION", "field": "action", "align": "left"},
                            {"name": "stage", "label": "STAGE", "field": "stage", "align": "left"},
                            {"name": "pwm", "label": "PWM", "field": "pwm", "align": "right"},
                            {"name": "ack", "label": "ACK", "field": "ack", "align": "center"},
                            {"name": "device", "label": "DEVICE", "field": "device", "align": "left"},
                            {"name": "detail", "label": "DETAIL", "field": "detail", "align": "left"},
                        ],
                        rows=[],
                        row_key="id",
                    ).props("flat dense").classes("w-full")
            with ui.element("div").classes("col-4"):
                with ui.column().classes("card gap-3"):
                    with card_header("Experiment Record", "Trial 生命周期与写入状态"):
                        pass
                    trial_status = ui.label("NO TRIAL").classes("metric-value")
                    trial_meta = ui.label("Create a trial in Experiments").classes("card-sub")
                    trial_counts = ui.label("frames 0 · events 0").classes("mono")
                    with ui.row().classes("w-full gap-2"):
                        ui.link("Open Experiments", "/experiments").classes("card-sub").style("color:#0f766e;font-weight:650")
                    ui.label(
                        "SIMULATION Trial 写入 data/simulated/；LIVE 才允许 data/real/。"
                    ).classes("card-sub")

    def set_pending(value: int) -> None:
        value = max(limits["min_us"], min(limits["max_us"], int(value)))
        state["pending"] = value
        pwm_slider.value = value
        pwm_number.value = value
        pending_value.set_text(str(value))
        pending_pill.set_content(f'<span class="dot"></span>PENDING {value} μs')
        pending_pill.classes(replace="pill pill-amber")
        pwm_slider.update()
        pwm_number.update()

    def on_slider(event) -> None:
        if event.value is None:
            return
        set_pending(int(round(event.value)))

    def on_number(event) -> None:
        if event.value is None:
            return
        set_pending(int(round(event.value)))

    pwm_slider.on_value_change(on_slider)
    pwm_number.on_value_change(on_number)

    def render_chart(frame: dict) -> None:
        chart_holder.clear()
        with chart_holder:
            if frame.get("matrix_rows") and frame.get("matrix_cols") and frame.get("channel_count") == frame["matrix_rows"] * frame["matrix_cols"]:
                ui.echart(heatmap_options(frame)).classes("w-full").style("height:310px")
            else:
                ui.echart(bar_options(frame)).classes("w-full").style("height:310px")
            invalid = frame.get("channel_count", 0) - frame.get("valid_count", 0)
            if invalid:
                ui.label(f"{invalid} channel(s) invalid — shown as gaps, not zero.").classes("card-sub")

    def refresh() -> None:
        snapshot = core.snapshot()
        set_pill(refs["mode"], snapshot["mode"], tone_for_state(snapshot["mode"]))
        source = snapshot["source"]
        set_pill(refs["source"], source, "purple" if source == "REPLAY" else "teal" if source == "SIMULATION" else "blue")
        refs["s3"].set_text("ONLINE" if snapshot["gripper"].get("connected") else "OFFLINE")
        refs["sensor"].set_text(snapshot["sensor_state_label"].replace("SENSOR ", ""))
        refs["source_side"].set_text(source)

        gripper = snapshot["gripper"]
        if snapshot["manual_session_active"]:
            s3_value.set_text("SESSION ACTIVE")
        else:
            s3_value.set_text(gripper.get("state", "OFFLINE"))
        s3_caption.set_text(
            f"{gripper.get('firmware_version') or 'firmware UNKNOWN'} · boot {gripper.get('boot_id') or '—'}"
        )
        sensor_value.set_text(snapshot["sensor_state_label"])
        rate = snapshot.get("sensor_sample_rate_hz")
        freshness = snapshot.get("sensor_freshness_ns")
        freshness_text = "age —" if freshness is None else f"age {freshness / 1e9:.2f}s"
        sensor_caption.set_text(
            f"{snapshot['sensor'].get('channel_count') or '—'} ch"
            + (f" · matrix {snapshot['sensor']['detail'].get('matrix')[0]}×{snapshot['sensor']['detail'].get('matrix')[1]}"
               if (snapshot['sensor'].get('detail') or {}).get('matrix') and (snapshot['sensor']['detail']['matrix'][0] is not None) else "")
            + f" · {snapshot['frames_received']} frames · "
            f"{f'{rate:.1f} Hz' if rate else 'rate UNKNOWN'} · {freshness_text}"
            + (f" · reconnect {snapshot.get('sensor_reconnect_count', 0)}" if snapshot.get("sensor_reconnect_count") else "")
            + (f" · {snapshot['sensor'].get('last_error')}" if snapshot['sensor'].get('last_error') else "")
        )
        mode_value.set_text(snapshot["mode"])
        mode_caption.set_text(
            "Manual PWM enabled" if snapshot["mode"] == "MANUAL" else
            "Host updates stopped" if snapshot["mode"] == "STANDBY" else
            snapshot.get("fault_reason") or "AUTO unavailable"
        )
        trial = snapshot.get("trial")
        if trial:
            trial_value.set_text(trial.get("status", "TRIAL"))
            trial_caption.set_text(trial.get("trial_id", "—"))
            counts = trial.get("counts") or {}
            trial_counts.set_text(
                f"frames {counts.get('frames', 0)} · events {counts.get('events', 0)}"
                + (f" · dropped {counts.get('dropped_frames', 0)}" if counts.get("dropped_frames") else "")
            )
            trial_status.set_text(trial.get("status", "TRIAL"))
            trial_meta.set_text(
                (f"WRITE ERROR: {snapshot['trial_error']}" if snapshot.get("trial_error") else
                 f"{trial.get('name', '')} · {trial.get('mode', '')} · {trial.get('source', '')}")
            )
        else:
            trial_value.set_text("NO TRIAL")
            trial_caption.set_text("Create in Experiments")
            trial_counts.set_text("frames 0 · events 0")
            trial_status.set_text("NO TRIAL")
            trial_meta.set_text("Create a trial in Experiments")

        fault_active = snapshot["mode"] == "FAULT"
        fault_banner.set_visibility(fault_active)
        if fault_active:
            fault_text.set_text(f"FAULT · {snapshot.get('fault_reason') or 'reason UNKNOWN'}")
            fault_reset_button.set_enabled(snapshot["gripper"].get("state") != "FAULT")
        manual_mode_button.set_enabled(
            bool(snapshot["manual_session_active"])
            and snapshot["mode"] in ("STANDBY",)
            and not fault_active
        )
        standby_mode_button.set_enabled(snapshot["mode"] == "MANUAL")
        auto_mode_button.set_enabled(False)
        auto_hint.set_text("AUTO 不可用：" + "；".join(snapshot.get("auto_reasons") or ["UNKNOWN"]))
        apply_button.set_enabled(bool(snapshot["apply_enabled"]))
        stop_button.set_enabled(bool(snapshot["stop_enabled"]))
        apply_hint.set_text(snapshot.get("apply_denial") or "Ready · Apply submits one target (ACK is not position)")
        connection_label.set_text(
            "SESSION ACTIVE" if snapshot["manual_session_active"] else
            "SESSION CONNECTED" if snapshot["gripper"].get("connected") else "SESSION OFFLINE"
        )
        if core.source is DataSource.REPLAY:
            connect_button.set_text("REPLAY · read-only")
            connect_button.set_enabled(False)
        elif snapshot["manual_session_active"]:
            connect_button.set_text("Disconnect")
            connect_button.set_enabled(True)
        elif snapshot["gripper"].get("connected"):
            connect_button.set_text("Begin manual session")
            connect_button.set_enabled(True)
        elif core.source is DataSource.SIMULATION:
            connect_button.set_text("Connect simulated S3")
            connect_button.set_enabled(True)
        else:
            connect_button.set_text("LIVE · connect via CLI")
            connect_button.set_enabled(False)

        latest = snapshot.get("latest_frame")
        if latest:
            source_label = latest.get("source", "UNKNOWN")
            set_pill(source_pill, source_label, "teal" if source_label == "SIMULATION" else "blue" if source_label == "LIVE" else "purple")
            contact = latest.get("contact_score")
            if contact is None:
                contact_value.set_text("UNKNOWN")
                contact_caption.set_text("device did not report a contact score")
            else:
                contact_value.set_text(f"{contact:.3f}")
                contact_caption.set_text(
                    "SIMULATED contact score" if source_label == "SIMULATION" else "device-reported · semantics UNKNOWN"
                )
            frame_caption.set_text(
                f"frame {latest['frame_seq']} · {latest['valid_count']}/{latest['channel_count']} valid · {fmt_ns(latest['host_received_ns'])}"
            )
            key = (latest["frame_seq"], latest["boot_id"], latest["valid_count"], source_label)
            if key != state["chart_key"]:
                state["chart_key"] = key
                render_chart(latest)
        else:
            set_pill(source_pill, "NO FRAME", "slate")
            contact_value.set_text("UNKNOWN")
            contact_caption.set_text("No real sensor data; no waveform is fabricated")
            frame_caption.set_text("no frames · SENSOR WAITING")
            if state["chart_key"] != "empty":
                state["chart_key"] = "empty"
                chart_holder.clear()
                with chart_holder:
                    empty_state(
                        "sensors_off",
                        "SENSOR WAITING",
                        "没有真实触觉数据。可开启 Simulation demo 查看界面数据，但会始终标注 SIMULATION。",
                    )

        decision_table.rows = [_format_event(item) for item in (snapshot.get("recent_events") or [])[:8]]
        decision_table.update()

        demo_switch.set_visibility(core.source is DataSource.SIMULATION)
        sensor_connect_button.set_visibility(core.source is DataSource.LIVE and core.sensor is not None)
        if core.source is DataSource.LIVE and core.sensor is not None:
            sensor_connected = bool(snapshot.get("sensor_connected"))
            sensor_connect_button.set_text("Sensor connected" if sensor_connected else "Connect sensor")
            sensor_connect_button.set_enabled(not sensor_connected)
        if core.source is DataSource.SIMULATION:
            connected = bool(snapshot.get("sensor_connected"))
            if demo_switch.value != connected:
                state["syncing"] = True
                demo_switch.value = connected
                state["syncing"] = False

    async def apply_pwm() -> None:
        value = int(state["pending"])
        event = await asyncio.to_thread(core.request_pwm, value)
        ui.notify(
            f"{event.stage}: {event.detail or event.action}",
            type="positive" if event.stage in ("DEVICE_ACK", "SIMULATED") else "negative" if event.stage in ("FAILED", "REJECTED", "UNSUPPORTED") else "info",
        )
        refresh()

    async def stop_device() -> None:
        event = await asyncio.to_thread(core.stop)
        ui.notify(
            f"STOP: {event.stage} · firmware {event.firmware_state or 'UNKNOWN'} — "
            "no hold/release guarantee, not a hardware E-stop",
            type="warning",
        )
        refresh()

    async def set_manual_mode() -> None:
        try:
            await asyncio.to_thread(core.set_mode, Mode.MANUAL)
            ui.notify("MANUAL enabled", type="positive")
        except Exception as exc:
            ui.notify(str(exc), type="negative", timeout=6000)
        refresh()

    async def set_standby_mode() -> None:
        try:
            await asyncio.to_thread(core.set_mode, Mode.STANDBY)
            ui.notify("STANDBY: host updates stopped; device output is not assumed stopped", type="warning")
        except Exception as exc:
            ui.notify(str(exc), type="negative")
        refresh()

    async def reset_fault() -> None:
        try:
            await asyncio.to_thread(core.clear_fault)
            ui.notify("Fault cleared; reconnect/re-authorize if the device was in FAULT", type="positive")
        except Exception as exc:
            ui.notify(str(exc), type="negative", timeout=6000)
        refresh()

    async def toggle_connection() -> None:
        try:
            if core.gripper is not None and core.gripper.connected:
                if not core.gripper.session_active:
                    event = await asyncio.to_thread(core.begin_manual_session)
                    ui.notify(f"Session: {event.stage}", type="positive" if event.stage in ("DEVICE_ACK", "SIMULATED") else "negative")
                else:
                    await asyncio.to_thread(core.disconnect_gripper)
                    ui.notify("Disconnected; output state may be UNKNOWN", type="warning")
            else:
                await asyncio.to_thread(core.connect_gripper)
                ui.notify("Connected and status queried; no manual session and no PWM yet", type="positive")
        except Exception as exc:
            ui.notify(str(exc), type="negative", timeout=6000)
        refresh()

    async def connect_sensor() -> None:
        try:
            await asyncio.to_thread(core.connect_sensor)
            ui.notify("Sensor transport connected; protocol still PROPOSED", type="positive")
        except Exception as exc:
            ui.notify(str(exc), type="negative", timeout=6000)
        refresh()

    async def on_demo_change(event) -> None:
        if state["syncing"]:
            return
        try:
            await asyncio.to_thread(core.set_demo_stream, bool(event.value))
            if event.value:
                ui.notify("SIMULATION sensor connected — synthetic data, not real hardware", type="warning", timeout=5000)
        except Exception as exc:
            ui.notify(str(exc), type="negative")
        refresh()

    apply_button.on_click(apply_pwm)
    stop_button.on_click(stop_device)
    connect_button.on_click(toggle_connection)
    manual_mode_button.on_click(set_manual_mode)
    standby_mode_button.on_click(set_standby_mode)
    sensor_connect_button.on_click(connect_sensor)
    fault_reset_button.on_click(reset_fault)
    demo_switch.on_value_change(on_demo_change)

    refresh()
    ui.timer(0.6, refresh)
