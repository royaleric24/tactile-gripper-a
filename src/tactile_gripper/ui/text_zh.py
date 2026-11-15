"""Display-layer Chinese labels.

Internal business values stay in stable English (MANUAL, RECORDING, ...).  This
module only maps those values and known operator-facing messages for the UI.
It has no side effects and must not be used to change protocol/data fields.
"""

from __future__ import annotations

SOURCE_LABELS = {
    "LIVE": "真实设备（LIVE）",
    "SIMULATION": "仿真（SIMULATION）",
    "REPLAY": "只读回放（REPLAY）",
    "ALL": "全部来源",
}

SOURCE_SHORT = {"LIVE": "真实", "SIMULATION": "仿真", "REPLAY": "回放", "ALL": "全部"}

STATUS_LABELS = {
    "MANUAL": "手动模式（MANUAL）",
    "AUTO": "自动模式（AUTO）",
    "STANDBY": "待机（STANDBY）",
    "FAULT": "故障锁存（FAULT）",
    "OFFLINE": "离线（OFFLINE）",
    "ONLINE": "在线",
    "CONNECTED": "已连接（CONNECTED）",
    "SESSION_ACTIVE": "控制会话已建立",
    "WAITING": "等待数据",
    "STREAMING": "数据正常",
    "STALE": "数据已过期",
    "DEVICE_ERROR": "设备错误",
    "COMMUNICATION_ERROR": "通信错误（COMMUNICATION_ERROR）",
    "REPLAY": "只读回放（REPLAY）",
    "SIMULATED": "仿真（SIMULATION）",
    "SIMULATION": "仿真（SIMULATION）",
    "CREATED": "已创建（CREATED）",
    "RECORDING": "记录中（RECORDING）",
    "COMPLETED": "正常完成（COMPLETED）",
    "ABORTED": "已中止（ABORTED）",
    "INTERRUPTED": "异常中断（INTERRUPTED）",
    "ERROR": "写入错误（ERROR）",
    "UNKNOWN": "未知",
    "LOG_WAITING": "等待 console 日志",
    "LOG_FOLLOW": "日志跟随（只读）",
    "DISARMED": "已撤防（DISARMED）",
    "ARMED": "已授权（ARMED）",
    "ACTIVE": "固件输出中（ACTIVE）",
    "NO TRIAL": "暂无实验",
    "NO FRAME": "暂无数据",
    "NO PWM COMMANDS": "无 PWM 目标",
    "NO SENSOR FRAMES": "无触觉帧",
    "NO TRIAL LOADED": "尚未加载实验",
}

SENSOR_LABELS = {
    "SENSOR WAITING": "等待传感器数据",
    "SENSOR STREAMING": "通信在线 · 接收数据",
    "SENSOR OFFLINE": "传感器离线",
    "SENSOR STALE": "传感器数据已过期",
    "SENSOR ERROR": "传感器错误",
    "SENSOR REPLAY": "只读回放数据",
    "WAITING": "等待传感器数据",
    "STREAMING": "通信在线 · 接收数据",
    "STOPPED": "设备在线 · 采集已停止",
    "DATA_ERROR": "协议异常 · 帧已拒绝",
    "FIXTURE_COMPLETE": "离线固件帧已读完",
    "OFFLINE": "传感器离线",
    "STALE": "传感器数据已过期",
    "DEVICE_ERROR": "传感器错误",
    "REPLAY": "只读回放数据",
}

STAGE_LABELS = {
    "INFO": "信息",
    "DEVICE_ACK": "设备确认（ACK）",
    "SIMULATED": "仿真指令",
    "REJECTED": "已拒绝",
    "FAILED": "失败",
    "UNSUPPORTED": "不支持",
    "SOFTWARE_ONLY": "仅主机操作",
    "INVALID_DATA": "无效数据",
    "OFFLINE": "离线",
    "DEVICE_ERROR": "设备错误",
    "CONNECT_FAILED": "连接失败",
    "TIMEOUT": "超时",
    "WARNING": "警告",
    "ERROR": "错误",
    "FRAME_GAP": "丢帧",
    "DEVICE_RESTART": "设备重启",
    "TIMESTAMP_ANOMALY": "时间戳异常",
    "HOST_CLOCK_ANOMALY": "主机时钟异常",
    "SEQUENCE_REGRESSION": "帧序号回退",
    "DUPLICATE_FRAME": "重复帧",
}

ACTION_LABELS = {
    "CONNECT": "连接设备",
    "DISCONNECT": "断开设备",
    "BEGIN_SESSION": "建立控制会话",
    "SET_PWM": "提交 PWM 目标",
    "STOP": "STOP",
    "STOP_UPDATES": "停止主机更新",
    "DISARM": "DISARM",
    "HEARTBEAT": "心跳",
    "QUERY_STATUS": "查询设备状态",
    "HOLD": "保持（无固件命令）",
    "RELEASE": "松开（无固件命令）",
    "TRIAL_START": "实验开始",
    "TRIAL_STOP": "实验结束",
    "TRIAL_CREATED": "实验已创建",
    "TRIAL_VIDEO": "更新视频路径",
    "TRIAL_WRITE_ERROR": "实验写入错误",
    "DEMO_STREAM": "仿真数据流",
    "MODE_CHANGE": "切换模式",
    "SENSOR": "传感器",
    "SENSOR_CONNECT": "连接传感器",
    "SENSOR_RECONNECT": "传感器重连",
    "SENSOR_ANOMALY": "传感器异常",
    "CLEAR_FAULT": "清除故障",
    "TRIAL": "实验",
    "SYSTEM": "系统",
}

EVENT_TYPE_LABELS = {
    "TRIAL_START": "实验开始",
    "TRIAL_STOP": "实验结束",
    "TRIAL_INTERRUPTED": "实验异常中断",
    "TRIAL_WRITE_ERROR": "实验写入错误",
    "MARKER": "标记",
    "NOTE": "备注",
    "ANOMALY": "异常",
    "SENSOR_ERROR": "传感器错误",
    "FRAME_ANOMALY": "帧异常",
    "FAULT": "故障",
}

RECORD_TYPE_LABELS = {
    "CONTROL_EVENT": "控制事件",
    "TRIAL_EVENT": "实验事件",
    "SENSOR_FRAME": "触觉帧",
}

TARGET_STATUS_LABELS = {
    "NO_PWM": "无 PWM 目标",
    "SENT_UNACKED": "已发送 · 等待 ACK",
    "ACKED": "已 ACK · 目标已确认",
    "ACKED_UNKNOWN_OUTPUT": "已 ACK · 输出状态未知",
    "ACK_STALE": "ACK 已过期 · 不视为当前输出",
    "TIMEOUT": "未确认 · ACK 超时",
    "UNCONFIRMED": "未确认 · 应答损坏",
    "FAILED": "失败",
    "OUTPUT_OFF": "输出已关闭（STOP ACK）",
    "STOP_UNCONFIRMED": "STOP 未确认 · 输出状态未知",
    "OFFLINE": "日志已结束 · 输出状态未知",
}

FIRMWARE_STATE_LABELS = {
    "LOG_WAITING": "等待 console 日志",
    "DISARMED": "已撤防（DISARMED）",
    "ARMED": "已授权（ARMED）",
    "ACTIVE": "输出中（ACTIVE）",
    "FAULT": "固件故障（FAULT）",
    "COMMUNICATION_ERROR": "通信错误（COMMUNICATION_ERROR）",
    "SIMULATED_ACTIVE": "仿真输出中",
    "UNKNOWN": "未知",
}

STATUS_EXPLANATIONS = {
    "INTERRUPTED": "软件未正常结束记录；已有数据保留，但不能视为正常完成。",
    "ERROR": "记录期间发生帧、事件或锁写入失败；已有数据保留，需检查完整性。",
    "ABORTED": "操作员或应用关停时主动中止；不是正常完成。",
    "COMPLETED": "已通过正常结束操作完成记录。",
    "RECORDING": "正在记录触觉帧、控制事件和元数据。",
    "CREATED": "实验已创建，尚未开始记录。",
}


def _lookup(mapping: dict[str, str], value, fallback: str | None = None) -> str:
    if value is None:
        return fallback or "—"
    text = str(value)
    return mapping.get(text, fallback if fallback is not None else text)


def source_label(value) -> str:
    return _lookup(SOURCE_LABELS, value)


def source_short(value) -> str:
    return _lookup(SOURCE_SHORT, value)


def target_status_label(value) -> str:
    return _lookup(TARGET_STATUS_LABELS, value, "未知状态")


def status_label(value) -> str:
    return _lookup(STATUS_LABELS, value)


def mode_label(value) -> str:
    return _lookup(STATUS_LABELS, value)


def sensor_label(value) -> str:
    return _lookup(SENSOR_LABELS, value)


def stage_label(value) -> str:
    return _lookup(STAGE_LABELS, value)


def action_label(value) -> str:
    return _lookup(ACTION_LABELS, value)


def event_type_label(value) -> str:
    return _lookup(EVENT_TYPE_LABELS, value)


def record_type_label(value) -> str:
    return _lookup(RECORD_TYPE_LABELS, value)


def firmware_state_label(value) -> str:
    return _lookup(FIRMWARE_STATE_LABELS, value)


def status_explanation(value) -> str:
    return STATUS_EXPLANATIONS.get(str(value), "")


def trial_status_label(value) -> str:
    return status_label(value)


def event_detail_label(text: str | None) -> str:
    """Translate common operator-facing event details; keep unknown technical detail."""
    if not text:
        return "—"
    value = str(text)
    exact = {
        "dry-run simulation; no serial write, no device ACK": "仿真模式：未写串口，无设备确认（ACK）",
        "BENCH_HOLD accepted; ACK is not position feedback": "BENCH_HOLD 已被固件接受；ACK 不是位置反馈",
        "BEGIN_BENCH + BENCH_HOLD_MODE; no PWM output": "已建立 BENCH 会话并选择保持模式；未输出 PWM",
        "heartbeat only refreshes communication lease": "心跳只刷新通信存活期，不延长输出许可",
        "status query response": "设备状态查询响应",
        "simulated status response": "仿真的设备状态响应",
        "session already active": "控制会话已建立",
        "gripper connected (SIMULATION)": "已连接仿真控制器（未打开真实串口）",
        "gripper connected (LIVE)": "已连接真实控制器",
        "gripper closed; output state may be UNKNOWN": "控制器已关闭；PWM 输出状态可能未知",
        "SIMULATION sensor connected; not real hardware": "已连接仿真传感器；不是真实硬件",
        "SIMULATION sensor disconnected": "仿真传感器已断开",
        "leaving MANUAL stops host updates; device output is unchanged": "离开手动模式只停止主机更新，不会自动改变设备输出",
        "host stops submitting targets; device output is not changed": "主机停止提交目标，但不会自动改变设备输出",
        "no verified firmware command for HOLD": "固件没有已验证的保持命令",
        "no verified firmware command for RELEASE": "固件没有已验证的松开命令",
        "gripper is OFFLINE": "控制器离线",
        "manual session is not active": "控制会话尚未建立",
        "REPLAY is read-only; no hardware write": "回放为只读，不会写入硬件",
        "REPLAY is read-only": "回放为只读",
        "another command is in flight": "上一条命令仍在处理中",
        "begin_session_required": "需要先建立控制会话",
        "pwm must be an integer": "PWM 目标必须是整数",
        "no frames to replay": "没有可回放的触觉帧",
        "not_connected": "设备未连接",
        "recording started": "开始记录",
        "recording stopped": "记录结束",
    }
    if value in exact:
        return exact[value]
    if value.startswith("SIMULATION sensor connected"):
        return "已连接仿真传感器；不是真实硬件"
    if value.startswith("STOP revokes permits"):
        return "STOP 已撤销输出许可并调用固件 output.off()；不保证保持/释放，不是硬件急停；STOP 不会清除既有 FAULT（DISARM 才清除）"
    if value.startswith("DISARM revokes permits"):
        return "DISARM 已撤销输出许可并调用固件 output.off()；成功后固件可清除 FAULT"
    if value.startswith("recording T-"):
        return "正在记录 " + value[len("recording "):]
    if value.startswith("recording "):
        return "正在记录 " + value[len("recording "):]
    if value.startswith("trial ") and value.endswith(" created"):
        return "实验已创建：" + value[len("trial "):-len(" created")]
    if value.startswith("trial ") and " stopped: " in value:
        return "实验已结束：" + value[len("trial "):]
    if value.startswith("video path set to "):
        return "视频路径已更新：" + value[len("video path set to "):]
    if value.startswith("pwm outside configured range"):
        return "PWM 超出配置范围：" + value.split("range", 1)[-1].strip()
    if value.startswith("mode is ") and ", not MANUAL" in value:
        return "当前模式不是手动模式（MANUAL）"
    if value.startswith("gripper is in FAULT"):
        return "控制器处于故障锁存（FAULT），需要重新连接/授权"
    if value == "PROBE_OR_CONFIG_READBACK_FAILED":
        return "ADC 探测/配置回读失败（FSR_ONLY 下 ADC1–3 未接时属预期；ADC4 仍 OK）"
    if value.startswith("PROBE_OR_CONFIG_READBACK_FAILED"):
        return "ADC 探测/配置回读失败（FSR_ONLY 下 ADC1–3 未接时属预期；ADC4 仍 OK）"
    if value.startswith("pwm_console log"):
        suffix = value.split("·", 1)[-1].strip()
        return "pwm_console 日志：" + {
            "pwm_console ACK; target is not measured position": "已 ACK；目标不是实测位置",
            "no matched ACK before the console timeout; output not confirmed": "console 超时前未收到匹配 ACK；输出未确认",
            "response corrupted (NUL/parse); ACK not confirmed": "应答损坏（NUL/解析失败）；ACK 未确认",
        }.get(suffix, suffix)
    if value.startswith("LOG-FOLLOW"):
        return "只读监控：PWM 只能由独占串口的 pwm_console 发送"
    if value.startswith("connection/command failure"):
        return "通信或命令失败：" + value.split(":", 1)[-1].strip()
    if value.startswith("communication/command failure"):
        return "通信或命令失败：" + value.split(":", 1)[-1].strip()
    return value


def error_text(exc: BaseException | str) -> str:
    """Short Chinese prefix for errors while preserving technical detail."""
    text = str(exc)
    translated = event_detail_label(text)
    if translated != text:
        return translated
    if any("\u4e00" <= char <= "\u9fff" for char in text):
        return text
    return f"操作未完成：{text}"


CONTACT_REASON_LABELS = {
    "no FSR channels in HELLO channel_config": "HELLO 通道配置中没有 FSR 通道",
    "no sensor frame": "没有传感器帧",
    "frame marked invalid": "该帧被标记为无效",
    "unloaded FSR baseline not captured for every channel": "并非所有 FSR 通道都已采集空载基线",
    "FSR score unavailable": "FSR 相对接触评分不可用",
    "relative FSR increase below no-contact threshold": "FSR 相对增量低于未接触阈值",
    "relative contact insufficient; tightening may be considered": "相对接触不足；可考虑小幅夹紧",
    "relative contact in the normal band": "相对接触处于正常区间",
    "relative contact above tight threshold; do not keep tightening": "相对接触超过偏紧阈值；不要再继续夹紧",
}


def contact_reason_label(reason: str | None) -> str:
    """Translate the fixed contact-assessment reasons; keep unknown text verbatim."""
    if not reason:
        return ""
    value = str(reason)
    translated = CONTACT_REASON_LABELS.get(value)
    if translated:
        return translated
    prefix, _, detail = value.partition(":")
    if prefix.strip() == "invalid or saturated FSR channel(s)":
        return f"无效或饱和的 FSR 通道：{detail.strip()}"
    if value.startswith("stale frame (") and value.endswith(")"):
        return f"帧已过期：{value[len('stale frame ('):-1]}"
    return value
