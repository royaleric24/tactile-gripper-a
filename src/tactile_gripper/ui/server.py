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
    @ui.page("/", title="Live Monitor · Tactile Gripper A")
    def index() -> None:
        live_page(core)

    @ui.page("/experiments", title="Experiments · Tactile Gripper A")
    def experiments() -> None:
        experiments_page(core)

    @ui.page("/analysis", title="Analysis & Diagnostics · Tactile Gripper A")
    def analysis() -> None:
        analysis_page(core)


def _demo_setup(core) -> None:
    if core.source is not DataSource.SIMULATION:
        raise SystemExit("--demo is only valid with --source SIMULATION")
    core.connect_gripper()
    core.begin_manual_session()
    core.set_demo_stream(True)
    core.create_trial(
        "Demo grasp · SIMULATION",
        conditions={"object": "demo block", "material": "SIMULATION", "grasp_target": "1500 μs"},
        notes="Synthetic dashboard demo. Not a real experiment.",
    )
    core.start_trial()
    core.request_pwm(core.gripper.pwm_initial_us or 1500)
    print("SIMULATION demo active: synthetic sensor + dry-run gripper, no serial port opened.", flush=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Tactile Gripper A dashboard (S2-A)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--source",
        choices=[item.value for item in DataSource],
        default=DataSource.SIMULATION.value,
        help="data source; LIVE also needs --hardware-permission",
    )
    parser.add_argument("--sensor-file", type=Path, help="replay JSONL (requires --source REPLAY)")
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--config", type=Path, help="gripper config JSON (default config/gripper_s3.json)")
    parser.add_argument("--hardware-permission", action="store_true", help="explicit permission for LIVE serial")
    parser.add_argument("--connect-port", help="explicit Mac serial port for LIVE")
    parser.add_argument("--connect", action="store_true", help="connect and begin a manual session at startup")
    parser.add_argument("--demo", action="store_true", help="SIMULATION-only dashboard demo data")
    args = parser.parse_args(argv)

    source = parse_source(args.source)
    if source is DataSource.LIVE:
        if not args.hardware_permission:
            parser.error("--source LIVE requires --hardware-permission")
        if not args.connect_port:
            parser.error("--source LIVE requires --connect-port")
    if args.sensor_file is not None and source is not DataSource.REPLAY:
        parser.error("--sensor-file requires --source REPLAY")
    if args.demo and source is not DataSource.SIMULATION:
        parser.error("--demo requires --source SIMULATION")

    core = build_core(
        source=source,
        root=args.data_root,
        config_path=args.config,
        hardware_permission=args.hardware_permission,
        port=args.connect_port,
        connect=args.connect,
        sensor_file=args.sensor_file,
    )
    if args.demo:
        _demo_setup(core)
    stop = start_ticker(core)

    def shutdown() -> None:
        stop.set()
        try:
            if core.trial is not None and core.trial.recording:
                core.stop_trial("server shutdown")
            if core.gripper is not None and core.gripper.connected:
                core.disconnect_gripper()
        except Exception as exc:  # pragma: no cover - shutdown best effort
            print(f"[shutdown] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

    app.on_shutdown(shutdown)
    create_ui(core)
    print(
        f"Tactile Gripper A · S2-B dashboard · source={source.value} · "
        f"http://{args.host}:{args.port}",
        flush=True,
    )
    ui.run(
        host=args.host,
        port=args.port,
        title="Tactile Gripper A · Control Room",
        reload=False,
        show=not args.no_browser,
        uvicorn_logging_level="warning",
    )


if __name__ == "__main__":
    main()
