"""NiceGUI server entry point.

The ApplicationCore is created exactly once and injected into all pages.
Browser refreshes only rebuild view functions; they never construct another
gripper adapter or open another serial port.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

from nicegui import app, ui

from ..constants import SOFTWARE_VERSION
from ..control import build_core
from ..paths import PROJECT_ROOT
from ..sources import DataSource, parse_source
from .pages import analysis_page, experiments_page, live_page


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


def _demo_setup(core) -> None:
    if core.source is not DataSource.SIMULATION:
        raise SystemExit("--demo 只适用于 --source SIMULATION")
    core.connect_gripper()
    core.begin_manual_session()
    core.set_demo_stream(True)
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
    parser = argparse.ArgumentParser(description="触觉闭环机械爪 A 控制台（V1.0）")
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
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--config", type=Path, help="控制器配置 JSON（默认 config/gripper_s3.json）")
    parser.add_argument("--hardware-permission", action="store_true", help="明确授权 LIVE 串口")
    parser.add_argument("--connect-port", help="LIVE 的 Mac 串口路径")
    parser.add_argument("--connect", action="store_true", help="启动时连接控制器并建立手动会话")
    parser.add_argument("--sensor-port", help="传感器串口路径（仅 LIVE）")
    parser.add_argument("--sensor-baud", type=int, help="传感器波特率（默认取配置文件）")
    parser.add_argument("--sensor-config", type=Path, default=PROJECT_ROOT / "config" / "sensor_serial.json")
    parser.add_argument("--connect-sensor", action="store_true", help="启动时打开传感器串口")
    parser.add_argument("--demo", action="store_true", help="仅 SIMULATION 的 Dashboard 演示数据")
    args = parser.parse_args(argv)

    source = parse_source(args.source)
    if source is DataSource.LIVE:
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

    core = build_core(
        source=source,
        root=args.data_root,
        config_path=args.config,
        hardware_permission=args.hardware_permission,
        port=args.connect_port,
        connect=args.connect,
        sensor_file=args.sensor_file,
        sensor_port=args.sensor_port,
        sensor_baud=args.sensor_baud,
        sensor_config_path=args.sensor_config,
        connect_sensor=args.connect_sensor,
    )
    if args.demo:
        _demo_setup(core)
    stop = start_ticker(core)

    def shutdown() -> None:
        stop.set()
        try:
            core.shutdown()
        except Exception as exc:  # pragma: no cover - shutdown best effort
            print(f"[shutdown] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

    app.on_shutdown(shutdown)
    create_ui(core)
    print(
        f"触觉闭环机械爪 A · 控制台 · source={source.value} · "
        f"http://{args.host}:{args.port}",
        flush=True,
    )
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
