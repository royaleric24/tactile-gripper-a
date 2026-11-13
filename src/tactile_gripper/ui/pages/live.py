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
from ..text_zh import (
    action_label,
    event_detail_label,
    firmware_state_label,
    mode_label,
    sensor_label,
    source_label,
    source_short,
    stage_label,
    status_label,
    trial_status_label,
    error_text,
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
        "action": action_label(event.get("action", "—")),
        "stage": stage_label(event.get("stage", "—")),
        "pwm": event.get("commanded_pwm_us") if event.get("commanded_pwm_us") is not None else "—",
        "ack": "已确认" if event.get("device_ack") else "—",
        "device": firmware_state_label(event.get("firmware_state") or "—"),
        "detail": event_detail_label(event.get("detail"))[:80],
    }


def live_page(core) -> None:
    state = {"pending": 1500, "chart_key": None, "syncing": False}
    if core.gripper is not None:
        state["pending"] = core.gripper.pwm_initial_us or 1500
    limits = core.gripper.pwm_limits if core.gripper is not None else {
        "min_us": 500,
        "max_us": 2500,
        "initial_us": 1500,
        "source": "config/gripper_s3.json（Bench 配置范围）",
        "note": "Bench 配置范围；不是已验证的机械安全边界。",
    }

    with shell(
        "live",
        "实时监控",
        "单写入者控制台 · PWM 目标不等于实际机械位置",
        core,
        SOFTWARE_VERSION,
    ) as refs:
        with ui.element("div").classes("grid-12"):
            with ui.element("div").classes("col-3"):
                s3_value, s3_caption = metric_card("控制器状态", "memory", "离线（OFFLINE）", "尚无控制会话")
            with ui.element("div").classes("col-3"):
                sensor_value, sensor_caption = metric_card("传感器状态", "sensors", "等待传感器数据", "未连接真实传感器")
            with ui.element("div").classes("col-3"):
                mode_value, mode_caption = metric_card("控制模式", "tune", "待机（STANDBY）", "手动控制未启用")
            with ui.element("div").classes("col-3"):
                trial_value, trial_caption = metric_card("当前实验", "science", "暂无实验", "请在实验管理中创建")

        with ui.row().classes("w-full card notice-red items-center gap-3") as fault_banner:
            ui.icon("report_problem").style("color:#b91c1c;font-size:20px")
            fault_text = ui.label("故障锁存（FAULT）").classes("card-title").style("color:#991b1b")
            fault_reset_button = ui.button("清除故障", color="negative").props("outline no-caps").style("margin-left:auto")
        fault_banner.set_visibility(False)

        with ui.element("div").classes("grid-12"):
            with ui.element("div").classes("col-7"):
                with ui.column().classes("card gap-3"):
                    with ui.row().classes("w-full items-start justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label("触觉分布").classes("card-title")
                            ui.label("ADC 原始计数 · 无效通道不当作零接触 · 未标定数据不解释为压力/摩擦力/重量").classes("card-sub")
                        with ui.row().classes("items-center gap-3"):
                            sensor_connect_button = ui.button("连接传感器", color="secondary").props("outline no-caps")
                            demo_switch = ui.switch("仿真演示（SIMULATION）", value=False).props("dense")
                            source_pill = pill(source_label("SIMULATION"), "teal")
                    chart_holder = ui.column().classes("w-full")
                    with ui.row().classes("w-full items-center gap-4"):
                        contact_value = ui.label("未知").classes("metric-value")
                        with ui.column().classes("gap-0"):
                            ui.label("接触指标").classes("card-kicker")
                            contact_caption = ui.label("尚无标定接触指标").classes("metric-caption")
                        ui.element("div").classes("sidebar-spacer")
                        frame_caption = ui.label("暂无触觉帧").classes("mono").style("color:#94a3b8")
                    ui.label(
                        "仿真演示只产生合成数据，始终标注 SIMULATION；不会显示为真实设备（LIVE）。"
                    ).classes("card-sub")

            with ui.element("div").classes("col-5"):
                with ui.column().classes("card gap-3"):
                    with ui.row().classes("w-full items-start justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label("手动 PWM 控制").classes("card-title")
                            ui.label("滑块只调整待提交目标，点击 Apply 后才请求控制").classes("card-sub")
                        pending_pill = pill("待提交 1500 μs", "amber")
                    with ui.row().classes("items-baseline gap-2"):
                        pending_value = ui.label(str(state["pending"])).classes("value-mono")
                        ui.label("μs").classes("card-sub")
                        ui.label("目标值，不是实测位置").classes("card-sub").style("margin-left:auto")
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
                        ui.label(f"配置范围 {limits['min_us']}–{limits['max_us']} μs").classes("card-sub")
                    with ui.row().classes("w-full gap-2"):
                        apply_button = ui.button("提交 PWM（Apply）", color="primary").props("unelevated no-caps").classes("flex-1").style("height:42px")
                        stop_button = ui.button("STOP", color="negative").props("unelevated no-caps").classes("flex-1").style("height:42px")
                    apply_button.tooltip("提交一次 PWM 目标；设备确认（ACK）不等于实际机械位置")
                    stop_button.tooltip("关闭 PWM 输出；不保证机械爪继续保持夹持，不是独立硬件急停")
                    apply_hint = ui.label("建立控制会话后可提交 PWM").classes("card-sub")
                    ui.element("div").classes("hairline")
                    with ui.row().classes("w-full items-center justify-between"):
                        connection_label = ui.label("控制会话未建立").classes("card-kicker")
                        connect_button = ui.button("连接仿真 S3", color="secondary").props("unelevated no-caps")
                    with ui.row().classes("w-full items-center gap-2"):
                        manual_mode_button = ui.button("手动", color="primary").props("outline no-caps")
                        standby_mode_button = ui.button("待机", color="secondary").props("outline no-caps")
                        auto_mode_button = ui.button("自动", color="secondary").props("outline no-caps")
                        ui.label("MANUAL / STANDBY / AUTO · 自动模式需真实传感器与标定").classes("card-sub")
                    auto_hint = ui.label("自动模式不可用").classes("card-sub")
                    ui.label(
                        f"范围来源：{limits['source'].split('/config/')[-1]}。这是 Bench 配置范围，"
                        "不是已验证的机械安全边界。"
                    ).classes("card-sub")
                    ui.label("STOP 关闭 PWM 输出；不保证机械爪继续保持夹持，也不是独立硬件急停。").classes("notice notice-amber").style("width:100%")

        with ui.element("div").classes("grid-12"):
            with ui.element("div").classes("col-8"):
                with ui.column().classes("card gap-3"):
                    with card_header("最近控制事件", "请求 → 串口写入 → 设备确认（ACK）与真实位置分开记录"):
                        pass
                    decision_table = ui.table(
                        columns=[
                            {"name": "time", "label": "时间", "field": "time", "align": "left"},
                            {"name": "action", "label": "动作", "field": "action", "align": "left"},
                            {"name": "stage", "label": "阶段", "field": "stage", "align": "left"},
                            {"name": "pwm", "label": "PWM 目标", "field": "pwm", "align": "right"},
                            {"name": "ack", "label": "设备确认（ACK）", "field": "ack", "align": "center"},
                            {"name": "device", "label": "设备状态", "field": "device", "align": "left"},
                            {"name": "detail", "label": "说明", "field": "detail", "align": "left"},
                        ],
                        rows=[],
                        row_key="id",
                    ).props('flat dense no-data-label="暂无数据"').classes("w-full")
            with ui.element("div").classes("col-4"):
                with ui.column().classes("card gap-3"):
                    with card_header("实验记录状态", "实验（Trial）生命周期与写入状态"):
                        pass
                    trial_status = ui.label("暂无实验").classes("metric-value")
                    trial_meta = ui.label("请在实验管理中创建实验").classes("card-sub")
                    trial_counts = ui.label("触觉帧 0 · 事件 0").classes("mono")
                    with ui.row().classes("w-full gap-2"):
                        ui.link("打开实验管理", "/experiments").classes("card-sub").style("color:#0f766e;font-weight:650")
                    ui.label(
                        "仿真实验写入 data/simulated/；只有真实设备（LIVE）实验允许写入 data/real/。"
                    ).classes("card-sub")

    def set_pending(value: int) -> None:
        value = max(limits["min_us"], min(limits["max_us"], int(value)))
        state["pending"] = value
        pwm_slider.value = value
        pwm_number.value = value
        pending_value.set_text(str(value))
        pending_pill.set_content(f'<span class="dot"></span>待提交 {value} μs')
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
                ui.label(f"{invalid} 个通道无效——以空隙显示，不按零接触解释。").classes("card-sub")

    def refresh() -> None:
        snapshot = core.snapshot()
        set_pill(refs["mode"], mode_label(snapshot["mode"]), tone_for_state(snapshot["mode"]))
        source = snapshot["source"]
        set_pill(
            refs["source"],
            source_label(source),
            "purple" if source == "REPLAY" else "teal" if source == "SIMULATION" else "blue",
        )
        refs["s3"].set_text("在线" if snapshot["gripper"].get("connected") else "离线")
        refs["sensor"].set_text(sensor_label(snapshot["sensor_state_label"]))
        refs["source_side"].set_text(source_short(source))

        gripper = snapshot["gripper"]
        if snapshot["manual_session_active"]:
            s3_value.set_text("控制会话已建立")
        else:
            s3_value.set_text(status_label(gripper.get("state", "OFFLINE")))
        s3_caption.set_text(
            f"固件 {gripper.get('firmware_version') or '未知'} · 启动 ID {gripper.get('boot_id') or '—'}"
        )
        sensor_value.set_text(sensor_label(snapshot["sensor_state_label"]))
        rate = snapshot.get("sensor_sample_rate_hz")
        freshness = snapshot.get("sensor_freshness_ns")
        freshness_text = "新鲜度 —" if freshness is None else f"新鲜度 {freshness / 1e9:.2f}s"
        sensor_caption.set_text(
            f"{snapshot['sensor'].get('channel_count') or '—'} 通道"
            + (f" · 矩阵 {snapshot['sensor']['detail'].get('matrix')[0]}×{snapshot['sensor']['detail'].get('matrix')[1]}"
               if (snapshot['sensor'].get('detail') or {}).get('matrix') and (snapshot['sensor']['detail']['matrix'][0] is not None) else "")
            + f" · 已接收 {snapshot['frames_received']} 帧 · "
            f"{f'{rate:.1f} Hz' if rate else '采样率未知'} · {freshness_text}"
            + (f" · 重连 {snapshot.get('sensor_reconnect_count', 0)}" if snapshot.get("sensor_reconnect_count") else "")
            + (f" · {event_detail_label(snapshot['sensor'].get('last_error'))}" if snapshot['sensor'].get('last_error') else "")
        )
        mode_value.set_text(mode_label(snapshot["mode"]))
        mode_caption.set_text(
            "手动 PWM 已启用" if snapshot["mode"] == "MANUAL" else
            "主机更新已停止" if snapshot["mode"] == "STANDBY" else
            (snapshot.get("fault_reason") or "自动模式不可用")
        )
        trial = snapshot.get("trial")
        if trial:
            trial_value.set_text(trial_status_label(trial.get("status", "TRIAL")))
            trial_caption.set_text(trial.get("trial_id", "—"))
            counts = trial.get("counts") or {}
            trial_counts.set_text(
                f"触觉帧 {counts.get('frames', 0)} · 事件 {counts.get('events', 0)}"
                + (f" · 丢帧 {counts.get('dropped_frames', 0)}" if counts.get("dropped_frames") else "")
            )
            trial_status.set_text(trial_status_label(trial.get("status", "TRIAL")))
            trial_meta.set_text(
                (f"实验写入错误：{snapshot['trial_error']}" if snapshot.get("trial_error") else
                 f"{trial.get('name', '')} · {mode_label(trial.get('mode', ''))} · {source_label(trial.get('source', ''))}")
            )
        else:
            trial_value.set_text("暂无实验")
            trial_caption.set_text("请在实验管理中创建")
            trial_counts.set_text("触觉帧 0 · 事件 0")
            trial_status.set_text("暂无实验")
            trial_meta.set_text("请在实验管理中创建实验")

        fault_active = snapshot["mode"] == "FAULT"
        fault_banner.set_visibility(fault_active)
        if fault_active:
            fault_text.set_text(f"故障锁存（FAULT）· {event_detail_label(snapshot.get('fault_reason')) or '原因未知'}")
            fault_reset_button.set_enabled(snapshot["gripper"].get("state") != "FAULT")
        manual_mode_button.set_enabled(
            bool(snapshot["manual_session_active"])
            and snapshot["mode"] in ("STANDBY",)
            and not fault_active
        )
        standby_mode_button.set_enabled(snapshot["mode"] == "MANUAL")
        auto_mode_button.set_enabled(False)
        auto_hint.set_text("自动模式不可用：V1.0 强制禁用，需真实传感器、协议确认与标定。")
        apply_button.set_enabled(bool(snapshot["apply_enabled"]))
        stop_button.set_enabled(bool(snapshot["stop_enabled"]))
        apply_hint.set_text(
            event_detail_label(snapshot.get("apply_denial"))
            if snapshot.get("apply_denial")
            else "就绪 · Apply 提交一次 PWM 目标（设备确认 ACK 不是实际位置）"
        )
        connection_label.set_text(
            "控制会话已建立" if snapshot["manual_session_active"] else
            "设备已连接 · 会话未建立" if snapshot["gripper"].get("connected") else "控制会话未建立"
        )
        if core.source is DataSource.REPLAY:
            connect_button.set_text("只读回放 · 已禁用")
            connect_button.set_enabled(False)
        elif snapshot["manual_session_active"]:
            connect_button.set_text("断开连接")
            connect_button.set_enabled(True)
        elif snapshot["gripper"].get("connected"):
            connect_button.set_text("建立手动会话")
            connect_button.set_enabled(True)
        elif core.source is DataSource.SIMULATION:
            connect_button.set_text("连接仿真 S3")
            connect_button.set_enabled(True)
        else:
            connect_button.set_text("真实设备 · 通过命令行连接")
            connect_button.set_enabled(False)

        latest = snapshot.get("latest_frame")
        if latest:
            latest_source = latest.get("source", "UNKNOWN")
            set_pill(
                source_pill,
                source_label(latest_source),
                "teal" if latest_source == "SIMULATION" else "blue" if latest_source == "LIVE" else "purple",
            )
            contact = latest.get("contact_score")
            if contact is None:
                contact_value.set_text("未知")
                contact_caption.set_text("设备未上报接触评分；不推断压力/摩擦力/重量")
            else:
                contact_value.set_text(f"{contact:.3f}")
                contact_caption.set_text(
                    "仿真接触评分（SIMULATION）" if latest_source == "SIMULATION" else "设备上报 · 语义未标定"
                )
            frame_caption.set_text(
                f"帧 {latest['frame_seq']} · {latest['valid_count']}/{latest['channel_count']} 有效 · {fmt_ns(latest['host_received_ns'])}"
            )
            key = (latest["frame_seq"], latest["boot_id"], latest["valid_count"], latest_source)
            if key != state["chart_key"]:
                state["chart_key"] = key
                render_chart(latest)
        else:
            set_pill(source_pill, "暂无数据", "slate")
            contact_value.set_text("未知")
            contact_caption.set_text("没有真实传感器数据；不显示合成波形")
            frame_caption.set_text("暂无触觉帧 · 等待传感器数据")
            if state["chart_key"] != "empty":
                state["chart_key"] = "empty"
                chart_holder.clear()
                with chart_holder:
                    empty_state(
                        "sensors_off",
                        "等待传感器数据",
                        "没有真实触觉数据。可开启仿真演示查看界面数据，但会始终标注 SIMULATION。",
                    )

        decision_table.rows = [_format_event(item) for item in (snapshot.get("recent_events") or [])[:8]]
        decision_table.update()

        demo_switch.set_visibility(core.source is DataSource.SIMULATION)
        sensor_connect_button.set_visibility(core.source is DataSource.LIVE and core.sensor is not None)
        if core.source is DataSource.LIVE and core.sensor is not None:
            sensor_connected = bool(snapshot.get("sensor_connected"))
            sensor_connect_button.set_text("传感器已连接" if sensor_connected else "连接传感器")
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
            f"{stage_label(event.stage)}：{event_detail_label(event.detail) or action_label(event.action)}",
            type="positive" if event.stage in ("DEVICE_ACK", "SIMULATED") else "negative" if event.stage in ("FAILED", "REJECTED", "UNSUPPORTED") else "info",
        )
        refresh()

    async def stop_device() -> None:
        event = await asyncio.to_thread(core.stop)
        ui.notify(
            f"STOP：{stage_label(event.stage)} · 固件 {firmware_state_label(event.firmware_state or 'UNKNOWN')} — "
            "不保证保持/释放，不是独立硬件急停",
            type="warning",
        )
        refresh()

    async def set_manual_mode() -> None:
        try:
            await asyncio.to_thread(core.set_mode, Mode.MANUAL)
            ui.notify("已进入手动模式（MANUAL）", type="positive")
        except Exception as exc:
            ui.notify(error_text(exc), type="negative", timeout=6000)
        refresh()

    async def set_standby_mode() -> None:
        try:
            await asyncio.to_thread(core.set_mode, Mode.STANDBY)
            ui.notify("已进入待机（STANDBY）：主机停止更新，但设备输出不因此被假定停止", type="warning")
        except Exception as exc:
            ui.notify(error_text(exc), type="negative")
        refresh()

    async def reset_fault() -> None:
        try:
            await asyncio.to_thread(core.clear_fault)
            ui.notify("故障已清除；若固件曾处于 FAULT，请重新连接并重新授权", type="positive")
        except Exception as exc:
            ui.notify(error_text(exc), type="negative", timeout=6000)
        refresh()

    async def toggle_connection() -> None:
        try:
            if core.gripper is not None and core.gripper.connected:
                if not core.gripper.session_active:
                    event = await asyncio.to_thread(core.begin_manual_session)
                    ui.notify(f"控制会话：{stage_label(event.stage)}", type="positive" if event.stage in ("DEVICE_ACK", "SIMULATED") else "negative")
                else:
                    await asyncio.to_thread(core.disconnect_gripper)
                    ui.notify("已断开；PWM 输出状态可能未知（UNKNOWN）", type="warning")
            else:
                await asyncio.to_thread(core.connect_gripper)
                ui.notify("已连接并查询状态；尚未建立手动会话，也未发送 PWM", type="positive")
        except Exception as exc:
            ui.notify(error_text(exc), type="negative", timeout=6000)
        refresh()

    async def connect_sensor() -> None:
        try:
            await asyncio.to_thread(core.connect_sensor)
            ui.notify("传感器串口已连接；协议仍为 PROPOSED，未确认硬件实现", type="positive")
        except Exception as exc:
            ui.notify(error_text(exc), type="negative", timeout=6000)
        refresh()

    async def on_demo_change(event) -> None:
        if state["syncing"]:
            return
        try:
            await asyncio.to_thread(core.set_demo_stream, bool(event.value))
            if event.value:
                ui.notify("已连接仿真传感器（SIMULATION）——合成数据，不是真实硬件", type="warning", timeout=5000)
        except Exception as exc:
            ui.notify(error_text(exc), type="negative")
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
