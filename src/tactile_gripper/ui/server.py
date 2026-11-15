"""NiceGUI server entry point.

The ApplicationCore is created exactly once and injected into all pages.
Browser refreshes only rebuild view functions; they never construct another
gripper adapter or open another serial port.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

from nicegui import app, ui

from ..constants import SOFTWARE_VERSION
from ..control import build_core
from ..devices.firmware_fixture import FIXTURE_STREAMS
from ..models import utc_now_iso
from ..paths import PROJECT_ROOT
from ..protocol import CURRENT_SENSOR_PROFILES
from ..sources import DataSource, parse_source
from .pages import analysis_page, experiments_page, live_page
from .pages.demo_grid import demo_grid_page


def _write_json_atomic(path: Path, payload: dict) -> None:
    """Write a sidecar atomically so a reader never sees half JSON."""

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def start_ticker(core, interval_s: float = 0.25) -> threading.Event:
    stop = threading.Event()

    def loop() -> None:
        while not stop.wait(interval_s):
            try:
                core.tick()
            except Exception as exc:  # pragma: no cover - defensive background log
                print(f"[ticker] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

    thread = threading.Thread(target=loop, name="tactile-core-ticker", daemon=True)
    thread.start()
    return stop


def create_ui(core) -> None:
    @ui.page("/", title="实时监控 · 触觉闭环机械爪 A")
    def index() -> None:
        live_page(core)

    @ui.page("/experiments", title="实验管理 · 触觉闭环机械爪 A")
    def experiments() -> None:
        experiments_page(core)

    @ui.page("/analysis", title="分析与诊断 · 触觉闭环机械爪 A")
    def analysis() -> None:
        analysis_page(core)

    if core.source is DataSource.SIMULATION:
        @ui.page("/demo-6x6", title="36 格仿真 · 触觉闭环机械爪 A")
        def demo_grid() -> None:
            demo_grid_page(core)


def _demo_setup(core, profile: str = "FSR_ONLY") -> None:
    if core.source is not DataSource.SIMULATION:
        raise SystemExit("--demo 只适用于 --source SIMULATION")
    core.connect_gripper()
    core.begin_manual_session()
    core.set_demo_stream(True, profile=profile)
    core.create_trial(
        "演示抓取 · SIMULATION",
        conditions={
            "object": "demo block",
            "cup_type": "SIMULATION_DEMO",
            "material": "SIMULATION",
            "water_mass_g": None,
            "grasp_target": "1500 μs",
        },
        notes="Dashboard 仿真演示；不是真实实验。",
        operator="demo",
    )
    core.start_trial()
    core.request_pwm(core.gripper.pwm_initial_us or 1500)
    print("SIMULATION 演示已启动：合成传感器 + dry-run 控制器，未打开真实串口。", flush=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="触觉闭环机械爪 A · V2 Dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--source",
        choices=[item.value for item in DataSource],
        default=DataSource.SIMULATION.value,
        help="数据来源；LIVE 还需要 --hardware-permission",
    )
    parser.add_argument("--sensor-file", type=Path, help="replay JSONL（需要 --source REPLAY）")
    parser.add_argument("--firmware-fixture", choices=FIXTURE_STREAMS, help="仅 SIMULATION：读取固件 host 仿真生成的原始 JSONL")
    parser.add_argument("--record-fixture", action="store_true", help="将本次 fixture 写入隔离的仿真 Trial 并导出 CSV / REPLAY")
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--config", type=Path, help="控制器配置 JSON（默认 config/gripper_s3.json）")
    parser.add_argument("--hardware-permission", action="store_true", help="明确授权 LIVE 串口")
    parser.add_argument("--connect-port", help="LIVE 的 Mac 串口路径")
    parser.add_argument("--connect", action="store_true", help="启动时连接控制器并建立手动会话")
    parser.add_argument("--sensor-port", help="传感器串口路径（仅 LIVE）")
    parser.add_argument("--sensor-baud", type=int, help="传感器波特率（默认取配置文件）")
    parser.add_argument("--sensor-config", type=Path, default=PROJECT_ROOT / "config" / "sensor_serial.json")
    parser.add_argument("--connect-sensor", action="store_true", help="启动时打开传感器串口")
    parser.add_argument("--follow-pwm-log", type=Path, help="只读跟随 pwm_console 的 transport.jsonl（不打开串口）")
    parser.add_argument("--follow-fsr-log", type=Path, help="只读跟随 FSR 采集 JSONL（不打开串口）")
    parser.add_argument("--follow-session", type=Path, help="会话目录：transport.jsonl + fsr/fsr_stream.jsonl")
    parser.add_argument("--follow-record", action="store_true", help="跟随模式自动创建并记录一个 Trial，退出时导出 CSV")
    parser.add_argument("--demo", action="store_true", help="仅 SIMULATION 的 Dashboard 演示数据")
    parser.add_argument(
        "--demo-profile",
        choices=CURRENT_SENSOR_PROFILES,
        default="FSR_ONLY",
        help="仿真配置档（默认 FSR_ONLY；仅 --demo 使用）",
    )
    args = parser.parse_args(argv)

    source = parse_source(args.source)
    follow_pwm = args.follow_pwm_log
    follow_fsr = args.follow_fsr_log
    if args.follow_session is not None:
        session = args.follow_session
        if (session / "transport.jsonl").is_file():
            follow_pwm = follow_pwm or session / "transport.jsonl"
        candidate = session / "fsr" / "fsr_stream.jsonl"
        if not candidate.is_file():
            candidate = session / "fsr_stream.jsonl"
        if candidate.is_file():
            follow_fsr = follow_fsr or candidate
    follow_mode = follow_pwm is not None or follow_fsr is not None
    if args.follow_session is not None and not follow_mode:
        parser.error(
            f"会话目录里没有 transport.jsonl 或 fsr/fsr_stream.jsonl：{args.follow_session}"
        )
    if args.follow_record and not follow_mode:
        parser.error("--follow-record 需要 --follow-session / --follow-pwm-log / --follow-fsr-log")
    if follow_mode:
        if source is not DataSource.LIVE:
            parser.error("--follow-* 需要 --source LIVE（只读监控仍是真实数据）")
        if args.hardware_permission:
            parser.error("--follow-* 不打开串口；不要同时传 --hardware-permission")
        if args.connect or args.connect_sensor or args.connect_port or args.sensor_port:
            parser.error("--follow-* 与串口连接参数互斥")
        if follow_pwm is not None and not follow_pwm.is_file():
            parser.error(f"PWM 日志不存在：{follow_pwm}")
        if follow_fsr is not None and not follow_fsr.is_file():
            parser.error(f"FSR 日志不存在：{follow_fsr}")
        if not args.follow_record:
            print("[follow] 未启用 --follow-record：不会写 Trial。", flush=True)
    elif source is DataSource.LIVE:
        if not args.hardware_permission:
            parser.error("--source LIVE 需要 --hardware-permission")
        if args.connect and not args.connect_port:
            parser.error("LIVE 下 --connect 需要 --connect-port")
    if args.sensor_file is not None and source is not DataSource.REPLAY:
        parser.error("--sensor-file 需要 --source REPLAY")
    if (args.sensor_port or args.connect_sensor) and source is not DataSource.LIVE:
        parser.error("--sensor-port / --connect-sensor 需要 --source LIVE")
    if args.connect_sensor and not args.sensor_port:
        parser.error("--connect-sensor 需要 --sensor-port")
    if args.demo and source is not DataSource.SIMULATION:
        parser.error("--demo 需要 --source SIMULATION")
    if args.firmware_fixture and (source is not DataSource.SIMULATION or args.demo or args.hardware_permission):
        parser.error("--firmware-fixture 仅适用于独立离线 SIMULATION")
    if args.record_fixture and not args.firmware_fixture:
        parser.error("--record-fixture 需要 --firmware-fixture")

    core = build_core(
        source=source,
        root=args.data_root,
        config_path=args.config,
        hardware_permission=args.hardware_permission,
        port=args.connect_port,
        connect=args.connect,
        sensor_file=args.sensor_file,
        firmware_fixture=args.firmware_fixture,
        sensor_port=args.sensor_port,
        sensor_baud=args.sensor_baud,
        sensor_config_path=args.sensor_config,
        connect_sensor=args.connect_sensor,
        follow_pwm_log=follow_pwm if follow_mode else None,
        follow_fsr_log=follow_fsr if follow_mode else None,
    )
    follow_trial_id = None
    trial_sidecar = None
    session_dir = args.follow_session if follow_mode else None
    if follow_mode and args.follow_record:
        name = "LIVE 双日志 · " + (args.follow_session.name if args.follow_session else "monitor")
        metadata = core.create_trial(
            name,
            conditions={
                "object": "manual bench",
                "source_kind": "LIVE_LOG_FOLLOW",
                "pwm_log": str(follow_pwm) if follow_pwm else None,
                "fsr_log": str(follow_fsr) if follow_fsr else None,
            },
            notes="Dashboard 只读跟随 console/FSR 日志；PWM 由 pwm_console 独占发送。",
            operator="operator",
            tags=["LIVE", "LOG_FOLLOW"],
        )
        follow_trial_id = metadata["trial_id"]
        core.start_trial()
        print(f"[follow] Trial 记录中：{follow_trial_id}", flush=True)
        if session_dir is not None:
            trial_sidecar = session_dir / "trial.json"
            _write_json_atomic(
                trial_sidecar,
                {
                    "trial_id": follow_trial_id,
                    "directory": str(core.trial.directory) if core.trial is not None else None,
                    "status": "RECORDING",
                    "csv": None,
                    "replay": None,
                    "started_utc": utc_now_iso(),
                    "updated_utc": utc_now_iso(),
                },
            )
    if args.demo:
        _demo_setup(core, args.demo_profile)
    if args.firmware_fixture:
        core.tick()  # HELLO establishes the channel map before creating a Trial.
        if args.record_fixture:
            core.create_trial(f"固件仿真 · {args.firmware_fixture}", tags=["P3-A", "HOST_SIMULATION"])
            core.start_trial()
        for _ in core.sensor.transport.lines:
            if core.sensor.transport.at_end or core.last_sensor_error:
                break
            core.tick()
        if not core.sensor.transport.at_end or core.last_sensor_error:
            raise SystemExit(f"固件 fixture 读取失败：{core.last_sensor_error or '未读完'}")
        if args.record_fixture:
            trial_id = core.stop_trial("firmware fixture completed")["trial_id"]
            core.trial_store.export_csv(trial_id)
            replay = core.trial_store.export_replay_jsonl(trial_id)
            print(f"SIMULATION Trial: {trial_id}; REPLAY: {replay}", flush=True)
    stop = start_ticker(core)

    def _export_follow_trial() -> dict | None:
        """Drain JSONL, stop the Trial, then export CSV + REPLAY.

        The drain happens inside ``finish_log_follow_trial`` before the Trial
        is stopped, so records flushed by the collectors at exit are included.
        If the operator already stopped the Trial in the UI, the same Trial id
        is re-exported instead of guessing a different one.
        """
        if follow_trial_id is None:
            return None
        try:
            if core.trial is not None and core.trial.recording:
                result = core.finish_log_follow_trial("monitor shutdown")
                if result is not None:
                    return result
            record = core.trial_store.load(follow_trial_id)
            csv_path = core.trial_store.export_csv(follow_trial_id)
            replay_path = core.trial_store.export_replay_jsonl(follow_trial_id)
            return {
                "trial_id": follow_trial_id,
                "directory": str(record.directory),
                "csv": str(csv_path),
                "replay": str(replay_path),
                "status": "COMPLETED",
            }
        except Exception as exc:  # pragma: no cover - shutdown best effort
            print(
                f"[follow] Trial 保存失败：{type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            return {"trial_id": follow_trial_id, "status": "ERROR", "error": str(exc)}

    def shutdown() -> None:
        stop.set()
        if follow_mode:
            result = _export_follow_trial()
            if trial_sidecar is not None and follow_trial_id is not None:
                payload = {
                    "trial_id": follow_trial_id,
                    "status": "UNKNOWN",
                    "csv": None,
                    "replay": None,
                    "updated_utc": utc_now_iso(),
                }
                if result is not None:
                    payload.update(result)
                try:
                    _write_json_atomic(trial_sidecar, payload)
                except OSError as exc:
                    print(f"[follow] trial.json 写入失败：{exc}", file=sys.stderr, flush=True)
            if result is not None:
                print(f"[follow] Trial 已保存：{result.get('trial_id')}", flush=True)
                if result.get("csv"):
                    print(f"[follow] CSV: {result['csv']}", flush=True)
                if result.get("replay"):
                    print(f"[follow] REPLAY: {result['replay']}", flush=True)
        try:
            core.shutdown()
        except Exception as exc:  # pragma: no cover - shutdown best effort
            print(f"[shutdown] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

    app.on_shutdown(shutdown)
    create_ui(core)
    mode = "LOG_FOLLOW（只读，不打开串口）" if follow_mode else "DIRECT"
    print(
        f"触觉闭环机械爪 A · 控制台 · source={source.value} · {mode} · "
        f"http://{args.host}:{args.port}",
        flush=True,
    )
    if follow_mode:
        print(f"  PWM 日志: {follow_pwm}", flush=True)
        print(f"  FSR 日志: {follow_fsr}", flush=True)
    ui.run(
        host=args.host,
        port=args.port,
        title="触觉闭环机械爪 A · 控制台",
        reload=False,
        show=not args.no_browser,
        uvicorn_logging_level="warning",
    )


if __name__ == "__main__":
    main()
