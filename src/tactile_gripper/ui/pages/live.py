"""Live Monitor page."""

from __future__ import annotations

import asyncio

from nicegui import ui

from ...constants import SOFTWARE_VERSION
from ...control import Mode
from ...protocol import CURRENT_SENSOR_PROFILES
from ...sources import DataSource
from ..charts import (
    bar_options,
    fsr_trend_options,
    heatmap_options,
    matrix_view,
    unified_timeline_options,
)
from ..theme import (
    card_header,
    clock_label,
    empty_state,
    metric_card,
    pill,
    set_pill,
    shell,
    tone_for_state,
)
from ..text_zh import (
    action_label,
    contact_reason_label,
    event_detail_label,
    firmware_state_label,
    mode_label,
    sensor_label,
    source_label,
    source_short,
    stage_label,
    status_label,
    target_status_label,
    trial_status_label,
    error_text,
)


CONTACT_STATE_ZH = {
    "NO_CONTACT": "未接触",
    "INSUFFICIENT": "接触不足",
    "NORMAL": "正常",
    "TIGHT": "偏紧",
    "INVALID": "无效帧",
    "UNCALIBRATED": "未标定",
    "NOT_APPLICABLE": "不适用",
}
CONTACT_TONE = {
    "NO_CONTACT": "slate",
    "INSUFFICIENT": "amber",
    "NORMAL": "green",
    "TIGHT": "red",
    "INVALID": "red",
    "UNCALIBRATED": "amber",
    "NOT_APPLICABLE": "slate",
}


def _format_event(event: dict) -> dict:
    return {
        "id": event.get("event_id", f"{event.get('timestamp_utc')}-{event.get('action')}"),
        "time": clock_label(event.get("timestamp_utc"), with_date=False),
        "action": action_label(event.get("action", "—")),
        "stage": stage_label(event.get("stage", "—")),
        "pwm": event.get("commanded_pwm_us") if event.get("commanded_pwm_us") is not None else "—",
        "ack": "已确认" if event.get("device_ack") else "—",
        "device": firmware_state_label(event.get("firmware_state") or "—"),
        "detail": event_detail_label(event.get("detail"))[:80],
    }


def live_page(core) -> None:
    state = {
        "pending": 1500,
        "chart_key": None,
        "fsr_key": None,
        "syncing": False,
        "demo_profile": getattr(core, "demo_profile", "FSR_ONLY"),
        "timeline_key": None,
    }
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
        monitor_notice = ui.label("").classes("notice notice-amber").style("width:100%")
        monitor_notice.set_visibility(False)
        with ui.element("div").classes("grid-12 metric-grid"):
            with ui.element("div").classes("col-3"):
                s3_value, s3_caption = metric_card("控制器状态", "memory", "离线（OFFLINE）", "尚无控制会话")
            with ui.element("div").classes("col-3"):
                sensor_value, sensor_caption = metric_card("传感器通信", "sensors", "等待传感器数据", "未连接真实传感器")
            with ui.element("div").classes("col-3"):
                mode_value, mode_caption = metric_card("控制模式", "tune", "待机（STANDBY）", "手动控制未启用")
            with ui.element("div").classes("col-3"):
                trial_value, trial_caption = metric_card("当前实验", "science", "暂无实验", "请在实验管理中创建")

        with ui.row().classes("w-full card notice-red items-center gap-3") as fault_banner:
            ui.icon("report_problem").style("color:#b91c1c;font-size:20px")
            fault_text = ui.label("故障锁存（FAULT）").classes("card-title").style("color:#991b1b")
            fault_reset_button = ui.button("清除故障", color="negative").props("outline no-caps").style("margin-left:auto")
        fault_banner.set_visibility(False)

        with ui.element("div").classes("grid-12 main-grid"):
            with ui.element("div").classes("col-7"):
                with ui.column().classes("card gap-3"):
                    with ui.row().classes("w-full items-start justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label("触觉读数").classes("card-title")
                            ui.label("ADC 原始计数 · 无效通道不当作零接触 · 未标定数据不解释为压力/摩擦力/重量").classes("card-sub")
                        with ui.row().classes("items-center gap-3"):
                            sensor_connect_button = ui.button("连接传感器", color="secondary").props("outline no-caps")
                            sensor_query_button = ui.button("查询状态", color="secondary").props("outline no-caps")
                            sensor_hello_button = ui.button("查询 HELLO", color="secondary").props("outline no-caps")
                            sensor_start_button = ui.button("开始采集", color="secondary").props("outline no-caps")
                            sensor_stop_button = ui.button("停止采集", color="secondary").props("outline no-caps")
                            demo_switch = ui.switch("仿真演示（SIMULATION）", value=False).props("dense")
                            demo_profile_select = ui.select(
                                list(CURRENT_SENSOR_PROFILES),
                                value=state["demo_profile"],
                            ).props("dense outlined").classes("w-60")
                            source_pill = pill(source_label("SIMULATION"), "teal")
                    sensor_follow_note = ui.label(
                        "传感器由 capture_fsr_live.py 独占；本页只读，不发送查询/采集命令。"
                    ).classes("card-sub")
                    sensor_follow_note.set_visibility(False)
                    with ui.row().classes("w-full items-center gap-2"):
                        ui.label("通道数据质量").classes("card-kicker")
                        quality_pill = pill("尚未收到帧", "slate")
                        adc_quality = ui.label("").classes("card-sub")
                    chart_holder = ui.column().classes("w-full")
                    with ui.row().classes("w-full items-center gap-4"):
                        contact_value = ui.label("未知").classes("metric-value")
                        with ui.column().classes("gap-0"):
                            ui.label("接触指标").classes("card-kicker")
                            contact_caption = ui.label("尚无标定接触指标").classes("metric-caption")
                        ui.element("div").classes("sidebar-spacer")
                        frame_caption = ui.label("暂无触觉帧").classes("mono").style("color:#94a3b8")
                    if core.firmware_fixture:
                        ui.label(
                            f"固件主机仿真（OFFLINE_VERIFIED） · {core.firmware_fixture} · 无真实设备"
                        ).classes("notice notice-amber")

            with ui.element("div").classes("col-5"):
                with ui.column().classes("card gap-3"):
                    with ui.row().classes("w-full items-start justify-between"):
                        with ui.column().classes("gap-0"):
                            pwm_card_title = ui.label("手动 PWM 控制").classes("card-title")
                            pwm_card_sub = ui.label("滑块只调整待提交目标，点击 Apply 后才请求控制").classes("card-sub")
                        pending_pill = pill("待提交 1500 μs", "amber")
                    manual_panel = ui.column().classes("w-full gap-3")
                    with manual_panel:
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
                        commission_button = ui.button("真实 AUTO 调试入口（当前拒绝）", color="secondary").props("outline no-caps").classes("w-full")
                        ui.label(
                            f"范围来源：{limits['source'].split('/config/')[-1]}。这是 Bench 配置范围，"
                            "不是已验证的机械安全边界。"
                        ).classes("card-sub")
                        ui.label("STOP 关闭 PWM 输出；不保证机械爪继续保持夹持，也不是独立硬件急停。").classes("notice notice-amber").style("width:100%")

                    with ui.column().classes("w-full gap-2") as monitor_panel:
                        with ui.row().classes("w-full items-baseline gap-2"):
                            monitor_target_value = ui.label("—").classes("value-mono")
                            ui.label("μs").classes("card-sub")
                            monitor_target_pill = pill("无 PWM 目标", "slate")
                        monitor_target_caption = ui.label("尚未收到 console 日志").classes("card-sub")
                        with ui.column().classes("w-full gap-1"):
                            monitor_device = ui.label("控制器状态 —").classes("card-sub")
                            monitor_output = ui.label("固件输出 —").classes("card-sub")
                            monitor_ack = ui.label("最新应答 —").classes("card-sub")
                            monitor_comm = ui.label("通信错误 —").classes("card-sub")
                            monitor_fresh = ui.label("日志新鲜度 —").classes("card-sub")
                        monitor_table = ui.table(
                            columns=[
                                {"name": "time", "label": "时间（本机）", "field": "time", "align": "left", "style": "width:24%;white-space:nowrap"},
                                {"name": "target", "label": "目标", "field": "target", "align": "right", "style": "width:20%;white-space:nowrap"},
                                {"name": "result", "label": "结果", "field": "result", "align": "left", "style": "width:26%"},
                                {"name": "output", "label": "固件输出", "field": "output", "align": "left", "style": "width:30%"},
                            ],
                            rows=[],
                            row_key="key",
                        ).props('flat dense wrap-cells no-data-label="暂无 PWM 命令"').classes("w-full data-table")
                        with ui.row().classes("w-full gap-2"):
                            record_button = ui.button("开始记录 Trial", color="primary").props("unelevated no-caps").classes("flex-1")
                            finish_button = ui.button("结束并导出 CSV", color="secondary").props("outline no-caps").classes("flex-1")
                        monitor_trial_hint = ui.label("同一 Trial 保存 FSR 帧、PWM 命令/ACK、操作事件与时间戳").classes("card-sub")
                        ui.label(
                            "Dashboard 只读：未打开串口，也不会发送 PWM；PWM 写入者是独占串口的 pwm_console。"
                        ).classes("notice notice-amber").style("width:100%")
                    monitor_panel.set_visibility(False)

        with ui.column().classes("card gap-3 w-full") as fsr_section:
            with ui.row().classes("w-full items-start justify-between"):
                with ui.column().classes("gap-0"):
                    ui.label("FSR 相对接触").classes("card-title")
                    ui.label(
                        "相对空载基线，不是压力/牛顿/摩擦力；电压仅在 HELLO 给出参考、增益和位数时显示。"
                    ).classes("card-sub")
                with ui.row().classes("items-center gap-2"):
                    baseline_hint = ui.label("基线未采集").classes("card-sub")
                    baseline_button = ui.button("采集空载基线", color="secondary").props("outline no-caps")
                    baseline_clear_button = ui.button("清除基线", color="secondary").props("outline no-caps")
            with ui.element("div").classes("grid-12"):
                fsr_cards = []
                for index in range(2):
                    with ui.column().classes("col-6 gap-1") as card:
                        with ui.row().classes("w-full items-center justify-between"):
                            fsr_name = ui.label(f"FSR {index + 1}").classes("card-kicker")
                            fsr_state = pill("—", "slate")
                        fsr_raw = ui.label("原始 ADC —").classes("value-mono")
                        fsr_voltage = ui.label("电压 —").classes("card-sub")
                        fsr_delta = ui.label("相对变化 —").classes("card-sub")
                        fsr_cards.append((card, fsr_name, fsr_state, fsr_raw, fsr_voltage, fsr_delta))
            fsr_chart_holder = ui.column().classes("w-full")
            fsr_follow_note = ui.label("").classes("card-sub")
        fsr_section.set_visibility(False)

        with ui.column().classes("card gap-3 w-full") as timeline_section:
            with ui.row().classes("w-full items-start justify-between"):
                with ui.column().classes("gap-0"):
                    ui.label("FSR 与 PWM 统一时间轴").classes("card-title")
                    ui.label(
                        "同一主机单调时钟对齐：FSR_A 原始 ADC（左轴）与 console 已发送 PWM 目标（右轴）。"
                    ).classes("card-sub")
                timeline_pill = pill("只读日志", "blue")
            timeline_holder = ui.column().classes("w-full")
            ui.label(
                "同步精度：两条记录都来自同一台 Mac 的 host_monotonic_ns（同一次开机的系统单调时钟）；"
                "FSR 采样约 60 Hz，PWM 点为命令写入时刻，JSONL 落盘延迟为毫秒级。"
                "绝对时间以各记录自带的 host UTC 为准，Dashboard 不重新打时间。"
                "PWM 点颜色：蓝=已 ACK；灰=已发送未确认；红=失败/超时/应答损坏。"
            ).classes("card-sub")
        timeline_section.set_visibility(False)

        with ui.element("div").classes("grid-12"):
            with ui.element("div").classes("col-8"):
                with ui.column().classes("card gap-3"):
                    with card_header("最近控制事件", "请求 → 串口写入 → 设备确认（ACK）与真实位置分开记录"):
                        pass
                    decision_table = ui.table(
                        columns=[
                            {"name": "time", "label": "时间（本机）", "field": "time", "align": "left", "style": "width:14%;white-space:nowrap"},
                            {"name": "action", "label": "动作", "field": "action", "align": "left", "style": "width:13%"},
                            {"name": "stage", "label": "阶段", "field": "stage", "align": "left", "style": "width:12%"},
                            {"name": "pwm", "label": "PWM 目标", "field": "pwm", "align": "right", "style": "width:10%"},
                            {"name": "ack", "label": "设备确认（ACK）", "field": "ack", "align": "center", "style": "width:14%"},
                            {"name": "device", "label": "设备状态", "field": "device", "align": "left", "style": "width:11%"},
                            {"name": "detail", "label": "说明", "field": "detail", "align": "left", "style": "width:26%"},
                        ],
                        rows=[],
                        row_key="id",
                    ).props('flat dense wrap-cells no-data-label="暂无数据"').classes("w-full data-table")
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

    def render_chart(frame: dict, config: dict | None) -> None:
        chart_holder.clear()
        view = matrix_view(config)
        with chart_holder:
            if view == "CELLS":
                ui.label("HISTORICAL · 历史矩阵回放").classes("notice notice-amber")
                ui.echart(heatmap_options(frame, config)).classes("w-full").style("height:310px")
            elif view == "ELECTRODES":
                ui.echart(bar_options(frame, config, electrode_only=True)).classes("w-full").style("height:280px")
                mapping = (config or {}).get("mapping_status")
                message = (
                    "本图使用合成映射（SIM_SYNTHETIC_MAPPING）；真实映射待现场核对。"
                    if mapping == "SIM_SYNTHETIC_MAPPING" else
                    "真实 R/C→ADC/AIN 映射待核对（PENDING_REAL_WIRING）。"
                )
                ui.label("R1–R6 / C1–C6 · 12 路被动电极原始计数。 " + message).classes(
                    "notice notice-amber"
                ).style("width:100%")
            elif config is not None:
                ui.echart(bar_options(frame, config)).classes("w-full").style("height:260px")
            else:
                ui.echart(bar_options(frame)).classes("w-full").style("height:310px")
            invalid = frame.get("channel_count", 0) - frame.get("valid_count", 0)
            if invalid:
                ui.label(f"{invalid} 个通道无效——以空隙显示，不按零接触解释。").classes("card-sub")

    def _output_state_label(value: str | None) -> str:
        return {
            "DISABLED_UNMEASURED": "输出关闭（未测量）",
            "PWM_COMMANDED_UNMEASURED": "PWM 已命令（未测量）",
            "SIMULATED_UNMEASURED": "仿真（未测量）",
            "UNKNOWN": "未知",
            None: "—",
        }.get(value, str(value))

    def _pwm_result_label(value: str | None) -> str:
        return {
            "ACKED": "已 ACK",
            "SENT": "已发送 · 等待 ACK",
            "TIMEOUT": "未确认（ACK 超时）",
            "CORRUPT_RESPONSE": "未确认（应答损坏）",
            "FAILED": "失败",
        }.get(str(value or ""), str(value or "—"))

    def refresh_monitor(snapshot) -> None:
        """Read-only console/FSR panel.  Never claims output from a stale target."""
        monitor = snapshot.get("monitor") or {}
        counts = monitor.get("counts") or {}
        commands = monitor.get("commands") or []
        target = monitor.get("current_target") or {}
        status = str(monitor.get("target_status") or "NO_PWM")
        closed = bool(monitor.get("pwm_log_closed"))
        stale = bool(monitor.get("data_stale"))
        sensor_detail = (snapshot.get("sensor") or {}).get("detail") or {}
        fsr_log = ((sensor_detail.get("log") or {}).get("path")) if sensor_detail else None
        pwm_log = monitor.get("pwm_log")

        monitor_notice.set_text(
            f"LIVE · 日志跟随（只读） · Dashboard 未打开串口 · PWM 日志：{pwm_log or '未提供'} · "
            f"FSR 日志：{fsr_log or '未提供'}"
        )

        show_target = status in (
            "ACKED",
            "ACKED_UNKNOWN_OUTPUT",
            "ACK_STALE",
            "SENT_UNACKED",
            "TIMEOUT",
            "UNCONFIRMED",
            "FAILED",
        )
        monitor_target_value.set_text(str(target.get("pulse_us")) if show_target and target.get("pulse_us") is not None else "—")
        tone = {
            "ACKED": "green",
            "ACKED_UNKNOWN_OUTPUT": "amber",
            "ACK_STALE": "amber",
            "SENT_UNACKED": "amber",
            "TIMEOUT": "amber",
            "UNCONFIRMED": "amber",
            "FAILED": "red",
            "OUTPUT_OFF": "slate",
            "STOP_UNCONFIRMED": "red",
            "OFFLINE": "red",
            "NO_PWM": "slate",
        }.get(status, "slate")
        set_pill(monitor_target_pill, target_status_label(status), tone)
        if status in ("OUTPUT_OFF", "STOP_UNCONFIRMED", "NO_PWM", "OFFLINE"):
            monitor_target_caption.set_text(
                "STOP 已 ACK：不再显示旧目标为实时输出；实际机械状态未测量。"
                if status == "OUTPUT_OFF"
                else "没有仍被确认的 PWM 目标；不等于机械爪的实际位置。"
            )
        else:
            sent = clock_label(target.get("sent_utc"), with_date=False)
            ack = clock_label(target.get("ack_utc"), with_date=False)
            age = monitor.get("target_age_s")
            monitor_target_caption.set_text(
                f"已发送 {sent} · ACK {ack if target.get('ack_utc') else '—'} · "
                f"距命令 {age:.1f}s" if age is not None else f"已发送 {sent} · 未确认"
            )

        monitor_device.set_text(
            f"控制器：{firmware_state_label(monitor.get('device_state') or 'LOG_WAITING')} · "
            f"固件 {monitor.get('firmware_version') or '未知'} · boot {monitor.get('boot_id') or '—'}"
        )
        monitor_output.set_text(
            f"固件输出：{monitor.get('output_state') or '—'} · fault_reason {monitor.get('fault_reason') or '—'}"
        )
        response = monitor.get("last_response") or {}
        monitor_ack.set_text(
            f"最新应答：{response.get('type') or '—'} {response.get('state') or ''} · "
            f"{clock_label(monitor.get('last_response_utc'), with_date=False)}"
        )
        unconfirmed = sum(1 for item in commands if item.get("result") in ("SENT", "TIMEOUT", "CORRUPT_RESPONSE"))
        failed = sum(1 for item in commands if item.get("result") == "FAILED")
        monitor_comm.set_text(
            f"通信：已 ACK 命令 {counts.get('acked', 0)} · 未确认 {unconfirmed} · 失败 {failed} · "
            f"应答损坏 {counts.get('corrupt_responses', 0)} · NUL {counts.get('nul_bytes', 0)} · "
            f"超时 {counts.get('timeouts', 0)}"
        )
        tail = monitor.get("tail") or {}
        if closed:
            monitor_fresh.set_text(
                f"日志已结束（console CLOSED @ {clock_label(monitor.get('closed_at_utc'), with_date=False)}）；"
                f"最后 output_state={monitor.get('final_output_state') or monitor.get('output_state') or 'UNKNOWN'}"
            )
        elif stale:
            monitor_fresh.set_text(
                f"STALE：PWM 日志已 {monitor.get('pwm_log_age_s') or 0:.1f}s 未更新；不把最后目标当作实时输出。"
            )
        else:
            monitor_fresh.set_text(
                f"日志更新中（最近 {monitor.get('pwm_log_age_s') or 0:.1f}s）"
                + (
                    f" · 截断 {tail.get('truncations')} / 轮转 {tail.get('rotations')}"
                    if tail.get("truncations") or tail.get("rotations")
                    else ""
                )
            )

        monitor_table.rows = [
            {
                "key": f"{item.get('seq')}-{item.get('sent_utc')}-{item.get('command')}",
                "time": clock_label(item.get("sent_utc"), with_date=False),
                "target": (
                    f"{item['pulse_us']} μs"
                    if item.get("pulse_us") is not None
                    else str(item.get("command") or "—")
                ),
                "result": _pwm_result_label(item.get("result")),
                "output": _output_state_label(item.get("output_state")),
            }
            for item in list(reversed(commands))[:12]
        ]
        monitor_table.update()

        recording = bool((snapshot.get("trial") or {}).get("recording"))
        record_button.set_enabled(not recording)
        finish_button.set_enabled(recording)
        record_button.set_text("记录中（RECORDING）" if recording else "开始记录 Trial")
        trial = snapshot.get("trial")
        monitor_trial_hint.set_text(
            f"Trial {trial.get('trial_id')} 记录中：FSR 帧 + PWM 命令/ACK + 事件（同一时间戳）"
            if recording and trial
            else "同一 Trial 保存 FSR 帧、PWM 命令/ACK、操作事件与时间戳（需点击开始记录）"
        )

        notes: list[str] = []
        flags = sensor_detail.get("channel_flags") or []
        if any(flag and flag & 0x04 for flag in flags):
            notes.append(
                "FSR_A 标记 0x04 NEGATIVE_SINGLE_ENDED（近零负计数/零点噪声）——数据质量提示，不当作接触"
            )
        if any(flag and flag & 0x20 for flag in flags):
            notes.append("存在 0x20 NO_DATA 无效通道：保留为空隙，不按零读数解释")
        if snapshot.get("sensor_state_label") in ("SENSOR STALE", "SENSOR OFFLINE", "STALE", "OFFLINE"):
            notes.append("FSR 日志已停止更新（STALE/OFFLINE）：曲线末端不是实时数据")
        if (sensor_detail.get("log") or {}).get("truncations") or (sensor_detail.get("log") or {}).get("rotations"):
            notes.append(
                "FSR 日志发生过截断/轮转，已从新文件重新读取；跨文件的数据不连续"
            )
        fsr_follow_note.set_text(" · ".join(notes))

        points = snapshot.get("fsr_timeline") or []
        events = monitor.get("pwm_events") or []
        last_event = events[-1].get("sent_ns") if events else None
        key = (
            points[-1].get("seq") if points else None,
            len(points),
            len(events),
            last_event,
            status,
            snapshot.get("frames_received"),
        )
        if key != state["timeline_key"]:
            state["timeline_key"] = key
            timeline_holder.clear()
            with timeline_holder:
                option = unified_timeline_options(points, events)
                if option:
                    ui.echart(option).classes("w-full").style("height:280px")
                else:
                    empty_state(
                        "show_chart",
                        "等待 FSR 与 PWM 数据",
                        "左侧曲线来自 FSR 采集日志，蓝色阶梯来自 pwm_console 日志；两者都只读。",
                    )

        s3_value.set_text(
            "日志已结束（OFFLINE）"
            if closed
            else "STALE（日志未更新）"
            if stale
            else f"{firmware_state_label(monitor.get('device_state') or 'LOG_WAITING')}（日志）"
        )
        s3_caption.set_text(
            f"pwm_console 日志 · 固件 {monitor.get('firmware_version') or '未知'} · "
            f"boot {monitor.get('boot_id') or '—'}"
        )
        mode_value.set_text("只读监控（LOG-FOLLOW）")
        mode_caption.set_text("Dashboard 未打开串口；PWM 只由 pwm_console 发送")
        set_pill(refs["mode"], "只读监控（LOG-FOLLOW）", "blue")
        refs["s3"].set_text(
            "日志已结束（OFFLINE）" if closed else "STALE（日志未更新）" if stale else "在线（只读日志）"
        )

    def refresh() -> None:
        snapshot = core.snapshot()
        monitor = snapshot.get("monitor") or {}
        following = bool(snapshot.get("log_follow"))
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
        gripper_identity = (snapshot.get("device_identities") or {}).get("gripper") or {}
        s3_caption.set_text(
            f"固件 {gripper.get('firmware_version') or '未知'} · 启动 ID {gripper.get('boot_id') or '—'}"
            + (f" · {gripper_identity.get('port')}@{gripper_identity.get('baudrate')}" if gripper_identity.get("port") else "")
        )
        sensor_value.set_text(sensor_label(snapshot["sensor_state_label"]))
        rate = snapshot.get("sensor_sample_rate_hz")
        freshness = snapshot.get("sensor_freshness_ns")
        freshness_text = "新鲜度 —" if freshness is None else f"新鲜度 {freshness / 1e9:.2f}s"
        config = snapshot.get("sensor_config")
        sensor_identity = (snapshot.get("device_identities") or {}).get("sensor") or {}
        profile = (config or {}).get("sensor_profile") or sensor_identity.get("sensor_profile") or "UNKNOWN"
        if profile == "HYBRID_6X6_FSR2" or (config and matrix_view(config) == "CELLS"):
            profile = f"HISTORICAL · {profile}"
        fsr_count = sum(
            1 for channel in (config or {}).get("channels", [])
            if channel.get("sensor_kind") == "FSR"
            or (
                (config or {}).get("sensor_profile") in ("FSR_ONLY", "HYBRID_6X6_FSR2")
                and channel.get("matrix_row") is None
                and channel.get("matrix_col") is None
            )
        )
        matrix_count = sum(
            1 for channel in (config or {}).get("channels", [])
            if channel.get("sensor_kind") == "MATRIX_CELL"
            or (channel.get("matrix_row") is not None and channel.get("matrix_col") is not None)
        )
        if fsr_count == 2 and not matrix_count:
            profile = f"{profile} · 历史双 FSR"
        electrode_count = sum(
            1 for channel in (config or {}).get("channels", [])
            if channel.get("sensor_kind") == "MATRIX_ELECTRODE"
            or channel.get("electrode_axis") is not None
        )
        channel_summary = f"FSR {fsr_count}" + (f" / 历史矩阵 {matrix_count}" if matrix_count else "")
        if electrode_count:
            channel_summary = f"FSR {fsr_count} / 电极 {electrode_count}"
        sensor_detail = snapshot["sensor"].get("detail") or {}
        query = {"PENDING": "等待 STATUS", "TIMEOUT": "STATUS 回复超时", "RECEIVED": "已收到 STATUS"}.get(
            sensor_detail.get("status_query_result"), ""
        )
        sensor_caption.set_text(
            f"{profile} · {snapshot['sensor'].get('channel_count') or '—'} 通道 / {channel_summary}"
            + (f" · {sensor_identity.get('port')}@{sensor_identity.get('baudrate')}" if sensor_identity.get("port") else "")
            + f" · 已接收 {snapshot['frames_received']} 帧 · "
            f"{f'{rate:.1f} Hz' if rate else '帧率未知'}"
            + (f" · {freshness_text}" if source == "LIVE" else "")
            + (f" · 日志 {monitor.get('fsr_log')}" if following and monitor.get("fsr_log") else "")
            + (f" · {query}" if query else "")
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

        if following:
            monitor_notice.set_visibility(True)
            manual_panel.set_visibility(False)
            monitor_panel.set_visibility(True)
            timeline_section.set_visibility(True)
            pending_pill.set_visibility(False)
            pwm_card_title.set_text("PWM 监控（只读日志）")
            pwm_card_sub.set_text("来自 pwm_console 的 transport.jsonl；ACK 不等于实测位置")
            refresh_monitor(snapshot)
        else:
            monitor_notice.set_visibility(False)
            manual_panel.set_visibility(True)
            monitor_panel.set_visibility(False)
            timeline_section.set_visibility(False)
            pending_pill.set_visibility(True)
            pwm_card_title.set_text("手动 PWM 控制")
            pwm_card_sub.set_text("滑块只调整待提交目标，点击 Apply 后才请求控制")

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
        auto_hint.set_text(
            "真实 AUTO 硬关闭（AUTO_REAL_ENABLED=False）。仿真决策只记录动作与原因，不写 PWM；"
            "真实入口需现场协议、硬件与标定签核。"
        )
        commission_button.set_visibility(core.source is DataSource.LIVE)
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
        used_adcs = {
            channel.get("ads1220_id")
            for channel in (config or {}).get("channels", [])
            if channel.get("ads1220_id") is not None
        }
        adc_faults = [
            item
            for item in sensor_detail.get("adc_status", [])
            if item.get("state") != "OK" and (not used_adcs or item.get("id") in used_adcs)
        ]
        adc_states = {"NO_RESPONSE": "无响应", "CONFIG_ERROR": "配置错误", "RECOVERING": "恢复中", "FAILED": "故障"}
        adc_quality.set_text(" · ".join(
            f"ADC{item['id']} {adc_states.get(item['state'], item['state'])}" for item in adc_faults
        ))
        if latest:
            valid, count = latest["valid_count"], latest["channel_count"]
            flagged = sum(1 for flag in sensor_detail.get("channel_flags", []) if flag and not flag & 0x20)
            prefix = "最近一帧 · " if snapshot["sensor"]["state"] in ("STALE", "OFFLINE", "DATA_ERROR", "STOPPED") else ""
            label = f"{prefix}{valid}/{count} 有效"
            label += " · 全部缺失" if valid == 0 else f" · {count - valid} 路无效" if valid < count else ""
            if flagged:
                label += f" · {flagged} 路 ADC 告警"
            set_pill(quality_pill, label, "green" if valid == count and not flagged and not adc_faults and not prefix else "amber")
        else:
            set_pill(quality_pill, "尚未收到帧", "slate")
        if latest:
            latest_source = latest.get("source", "UNKNOWN")
            set_pill(
                source_pill,
                source_label(latest_source),
                "teal" if latest_source == "SIMULATION" else "blue" if latest_source == "LIVE" else "purple",
            )
            assessment = snapshot.get("fsr_assessment")
            if assessment:
                contact_state = assessment.get("state", "INVALID")
                score = assessment.get("score")
                contact_value.set_text("—" if score is None else f"{score:.3f}")
                contact_caption.set_text(
                    f"{CONTACT_STATE_ZH.get(contact_state, contact_state)} · 质量 {assessment.get('quality', 0):.2f} · "
                    f"{contact_reason_label(assessment.get('reason'))}"
                )
            else:
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
                f"帧 {latest['frame_seq']} · {latest['valid_count']}/{latest['channel_count']} 有效 · "
                f"接收于 {clock_label(latest.get('host_received_utc'), with_date=False)}（本机时间）"
            )
            key = (latest["frame_seq"], latest["boot_id"], latest["valid_count"], latest_source)
            if key != state["chart_key"]:
                state["chart_key"] = key
                render_chart(latest, config)
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

        fsr_readings = (snapshot.get("fsr_assessment") or {}).get("readings") or []
        fsr_section.set_visibility(bool(fsr_readings))
        if fsr_readings:
            baseline_ready = bool(snapshot.get("baseline_ready"))
            baseline_hint.set_text(
                "基线已采集：" + str((snapshot.get("fsr_assessment") or {}).get("baseline_source") or "—")
                if baseline_ready
                else "基线未采集：相对变化与接触状态不可用"
            )
            latest_seq = (latest or {}).get("frame_seq")
            fsr_key = (latest_seq, baseline_ready, (snapshot.get("fsr_assessment") or {}).get("state"))
            for index, card_refs in enumerate(fsr_cards):
                card, fsr_name, fsr_state, fsr_raw, fsr_voltage, fsr_delta = card_refs
                if index >= len(fsr_readings):
                    card.set_visibility(False)
                    continue
                card.set_visibility(True)
                reading = fsr_readings[index]
                fsr_name.set_text(str(reading.get("name") or f"FSR {index + 1}"))
                if not reading.get("valid") or reading.get("raw") is None:
                    fsr_raw.set_text("原始 ADC —（无效/缺失，不当作零）")
                    fsr_voltage.set_text("电压 —")
                    fsr_delta.set_text("相对变化 —")
                    set_pill(fsr_state, "无效 / 无数据", "red")
                else:
                    fsr_raw.set_text(f"原始 ADC {int(reading['raw'])}")
                    voltage_uv = reading.get("voltage_uv")
                    if reading.get("voltage_basis_complete") and voltage_uv is not None:
                        fsr_voltage.set_text(f"电压 {voltage_uv / 1e6:.3f} V（按 HELLO 换算基准）")
                    else:
                        fsr_voltage.set_text("电压 —（参考/增益/位数不全，不默认 3.3V）")
                    if reading.get("baseline_raw") is not None and reading.get("relative_change") is not None:
                        fsr_delta.set_text(
                            f"相对 {reading['relative_change'] * 100:+.1f}% · Δ {reading['delta_counts']:+.0f} counts"
                        )
                    else:
                        fsr_delta.set_text("相对变化 —（需先采集空载基线）")
                    set_pill(
                        fsr_state,
                        "饱和" if reading.get("saturated") else "有效",
                        "amber" if reading.get("saturated") else "green",
                    )
            if fsr_key != state["fsr_key"]:
                state["fsr_key"] = fsr_key
                fsr_chart_holder.clear()
                with fsr_chart_holder:
                    ui.echart(fsr_trend_options(snapshot.get("fsr_history") or [])).classes("w-full").style("height:170px")
            baseline_button.set_enabled(bool(latest) and snapshot["mode"] != "FAULT")
            baseline_clear_button.set_enabled(baseline_ready)

        decision_table.rows = [_format_event(item) for item in (snapshot.get("recent_events") or [])[:8]]
        decision_table.update()

        demo_switch.set_visibility(core.source is DataSource.SIMULATION and not core.firmware_fixture)
        demo_profile_select.set_visibility(core.source is DataSource.SIMULATION and not core.firmware_fixture)
        sensor_follow_note.set_visibility(following)
        sensor_connect_button.set_visibility(core.source is DataSource.LIVE and core.sensor is not None and not following)
        sensor_query_button.set_visibility(core.source is DataSource.LIVE and core.sensor is not None and not following)
        sensor_query_button.set_enabled(core.sensor is not None and hasattr(core.sensor, "query_status"))
        sensor_hello_button.set_visibility(core.source is DataSource.LIVE and core.sensor is not None and not following)
        sensor_hello_button.set_enabled(core.sensor is not None and hasattr(core.sensor, "query_hello"))
        live_sensor = core.source is DataSource.LIVE and core.sensor is not None
        sensor_start_button.set_visibility(live_sensor and not following)
        sensor_stop_button.set_visibility(live_sensor and not following)
        if live_sensor:
            ready = bool(snapshot.get("sensor_connected") and sensor_detail.get("hello") and query != "等待 STATUS")
            sensor_start_button.set_enabled(ready and snapshot["sensor"]["state"] != "STREAMING")
            sensor_stop_button.set_enabled(ready)
        if core.source is DataSource.SIMULATION and state["demo_profile"] != getattr(core, "demo_profile", state["demo_profile"]):
            state["demo_profile"] = core.demo_profile
            demo_profile_select.value = state["demo_profile"]
            demo_profile_select.update()
        if core.source is DataSource.LIVE and core.sensor is not None:
            sensor_connected = bool(snapshot.get("sensor_connected"))
            sensor_connect_button.set_text("传感器已连接" if sensor_connected else "连接传感器")
            sensor_connect_button.set_enabled(not sensor_connected)
        if core.source is DataSource.SIMULATION and not core.firmware_fixture:
            connected = bool(snapshot.get("sensor_connected"))
            if demo_switch.value != connected:
                state["syncing"] = True
                demo_switch.value = connected
                state["syncing"] = False

    async def capture_baseline() -> None:
        try:
            assessment = await asyncio.to_thread(core.capture_fsr_baseline)
            ui.notify(
                f"空载基线已采集（{assessment.baseline_source}）；仅用于相对接触评分，不是力标定",
                type="positive",
            )
        except Exception as exc:
            ui.notify(error_text(exc), type="negative", timeout=6000)
        refresh()

    async def clear_baseline() -> None:
        try:
            await asyncio.to_thread(core.clear_fsr_baseline)
            ui.notify("FSR 基线已清除；AUTO 接触状态回到未标定", type="warning")
        except Exception as exc:
            ui.notify(error_text(exc), type="negative")
        refresh()

    async def start_recording() -> None:
        try:
            def begin():
                if core.trial is None:
                    core.create_trial(
                        "LIVE 双日志 · Dashboard",
                        conditions={
                            "object": "manual bench",
                            "source_kind": "LIVE_LOG_FOLLOW",
                            "pwm_log": (core.snapshot().get("monitor") or {}).get("pwm_log"),
                        },
                        notes="Dashboard 只读跟随 pwm_console 与 FSR 采集日志；未发送 PWM。",
                        tags=["LIVE", "LOG_FOLLOW"],
                    )
                return core.start_trial()

            await asyncio.to_thread(begin)
            ui.notify("Trial 已开始记录 FSR 帧、PWM 命令/ACK 与事件", type="positive")
        except Exception as exc:
            ui.notify(error_text(exc), type="negative", timeout=6000)
        refresh()

    async def finish_recording() -> None:
        try:
            def finish():
                metadata = core.stop_trial("operator stop")
                trial_id = metadata["trial_id"]
                csv_path = core.trial_store.export_csv(trial_id)
                replay = core.trial_store.export_replay_jsonl(trial_id)
                return csv_path, replay

            csv_path, replay = await asyncio.to_thread(finish)
            ui.notify(f"CSV 已导出：{csv_path}", type="positive", timeout=9000)
            ui.notify(f"REPLAY：{replay}", type="info", timeout=9000)
        except Exception as exc:
            ui.notify(error_text(exc), type="negative", timeout=6000)
        refresh()

    async def query_sensor() -> None:
        try:
            ok = await asyncio.to_thread(core.query_sensor_status)
            ui.notify(
                "STATUS 查询已发送；回复走正常读取路径" if ok else "STATUS 查询未发送，见事件日志",
                type="positive" if ok else "warning",
            )
        except Exception as exc:
            ui.notify(error_text(exc), type="negative", timeout=6000)
        refresh()

    async def query_sensor_hello() -> None:
        try:
            ok = await asyncio.to_thread(core.query_sensor_hello)
            ui.notify(
                "HELLO 查询已发送；回复走正常读取路径" if ok else "HELLO 查询未发送，见事件日志",
                type="positive" if ok else "warning",
            )
        except Exception as exc:
            ui.notify(error_text(exc), type="negative", timeout=6000)
        refresh()

    async def request_commissioning() -> None:
        try:
            await asyncio.to_thread(core.request_real_auto_commissioning)
        except Exception as exc:
            ui.notify(error_text(exc), type="negative", timeout=8000)
        refresh()

    async def set_sensor_stream(enabled: bool) -> None:
        try:
            ok = await asyncio.to_thread(core.request_sensor_stream, enabled)
            ui.notify("采集命令已发送，等待 STATUS 确认" if ok else "采集命令未发送", type="info" if ok else "warning")
        except Exception as exc:
            ui.notify(error_text(exc), type="negative")
        refresh()

    async def on_demo_profile(event) -> None:
        if not event.value or event.value == state["demo_profile"]:
            return
        state["demo_profile"] = event.value
        try:
            if demo_switch.value:
                await asyncio.to_thread(core.set_demo_stream, True, profile=event.value)
                ui.notify(f"仿真配置切换为 {event.value}（SIMULATION）", type="warning")
            else:
                await asyncio.to_thread(core.select_demo_profile, event.value)
                ui.notify(f"离线仿真将使用 {event.value}；开启仿真后生效", type="info")
        except Exception as exc:
            ui.notify(error_text(exc), type="negative", timeout=6000)
        refresh()

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
            ui.notify("传感器串口已连接，等待 V2 HELLO。采集需要单独启动。", type="positive")
        except Exception as exc:
            ui.notify(error_text(exc), type="negative", timeout=6000)
        refresh()

    async def on_demo_change(event) -> None:
        if state["syncing"] or core.firmware_fixture:
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
    demo_profile_select.on_value_change(on_demo_profile)
    baseline_button.on_click(capture_baseline)
    baseline_clear_button.on_click(clear_baseline)
    sensor_query_button.on_click(query_sensor)
    sensor_hello_button.on_click(query_sensor_hello)
    async def start_sensor_stream():
        await set_sensor_stream(True)
    async def stop_sensor_stream():
        await set_sensor_stream(False)
    sensor_start_button.on_click(start_sensor_stream)
    sensor_stop_button.on_click(stop_sensor_stream)
    commission_button.on_click(request_commissioning)
    record_button.on_click(start_recording)
    finish_button.on_click(finish_recording)

    refresh()
    ui.timer(0.6, refresh)
