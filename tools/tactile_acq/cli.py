"""Command-line entry point for the real ADS1220 tactile acquisition tools."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .diagnose import evaluate_diag, format_diag_text, save_diag
from .monitor import PlotMonitor, Snapshot, TextMonitor
from .protocol import (
    FLAG_NEAR_RAIL,
    FLAG_SAT_HIGH,
    FLAG_SAT_LOW,
    SampleFrame,
    encode_command,
    flag_names,
    parse_message,
)
from .recorder import RunRecorder, default_run_directory
from .stats import RunStats, stats_from_csv
from .transport import (
    DeviceIdentityError,
    SerialSession,
    SerialTransportError,
    candidates,
    choose_port,
    list_serial_ports,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config/sensor_esp32.json"


def load_config() -> Dict[str, Any]:
    try:
        return json.loads(DEFAULT_CONFIG.read_text())
    except (OSError, ValueError):
        return {}


def print_ports(as_json: bool = False) -> None:
    ports = list_serial_ports()
    if as_json:
        print(json.dumps(ports, indent=2))
        return
    if not ports:
        print("No serial ports found.")
        return
    print("{:<28} {:<10} {:<20} {:<10} {}".format("DEVICE", "VID:PID", "SERIAL", "CANDIDATE", "DESCRIPTION"))
    for item in ports:
        vid_pid = "{}:{}".format(item["vid"], item["pid"]) if item["vid"] else "-"
        print(
            "{:<28} {:<10} {:<20} {:<10} {}".format(
                item["device"], vid_pid, item["serial_number"] or "-",
                "yes" if item["candidate"] else "no", item["description"],
            )
        )
    print("")
    print("Candidate = USB serial port. A port name is not proof of identity; use `identify`.")


def make_monitor(name: str):
    if name == "none":
        return None
    if name == "text":
        return TextMonitor()
    if name == "plot":
        return PlotMonitor()
    raise ValueError("unknown monitor: {}".format(name))


def command_list(args: argparse.Namespace) -> int:
    print_ports(args.json)
    return 0


def open_identified(args: argparse.Namespace):
    port = choose_port(args.port)
    session = SerialSession(port, baud=args.baud)
    session.open()
    identity = session.identify(timeout_s=args.identify_timeout)
    if args.expect_device_id and identity.device_id != args.expect_device_id:
        raise DeviceIdentityError(
            "device_id mismatch: expected {}, got {}".format(args.expect_device_id, identity.device_id)
        )
    return session, identity


def command_identify(args: argparse.Namespace) -> int:
    session = None
    try:
        session, identity = open_identified(args)
        print(json.dumps(identity.__dict__, indent=2))
        return 0
    except (SerialTransportError, DeviceIdentityError) as exc:
        print("IDENTIFY FAILED: {}".format(exc), file=sys.stderr)
        return 2
    finally:
        if session is not None:
            session.close()


def command_diag(args: argparse.Namespace) -> int:
    session = None
    try:
        session, identity = open_identified(args)
        print("identified {} on {} (firmware {})".format(identity.device_id, identity.port, identity.firmware_version))
        status = session.request_diag(timeout_s=args.diag_timeout)
        result = evaluate_diag(status)
        result["port"] = identity.port
        result["port_info"] = identity.port_info
        print(format_diag_text(result))
        if args.out:
            output = Path(args.out)
        else:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            output = ROOT / "evidence/sensor" / "diagnostics_{}.json".format(stamp)
        save_diag(result, output)
        print("\nDIAG saved to {}".format(output))
        return 0 if result["overall"] == "PASSED" else 1
    except (SerialTransportError, DeviceIdentityError) as exc:
        print("DIAG FAILED: {}".format(exc), file=sys.stderr)
        return 2
    finally:
        if session is not None:
            session.close()


def _timeout_threshold_s(recent: List[int]) -> float:
    if len(recent) < 4:
        return 2.0
    median = statistics.median(recent)
    return max(2.0, 3.0 * median / 1e9)


def command_run(args: argparse.Namespace) -> int:
    session = None
    recorder = None
    monitor = None
    run_dir: Optional[Path] = None
    identified = False
    try:
        session, identity = open_identified(args)
        identified = True
        print("REAL_HARDWARE_SERIAL: {} on {} (firmware {})".format(
            identity.device_id, identity.port, identity.firmware_version))
        if not identity.streaming:
            session.set_streaming(True)
            time.sleep(0.2)
        if args.out:
            run_dir = Path(args.out)
        else:
            run_dir = default_run_directory(identity.port, base=Path(args.data_root))
        run_dir.mkdir(parents=True, exist_ok=True)
        recorder = RunRecorder(run_dir, identity.port, args.baud, identity, load_config())
        monitor_name = args.monitor
        if monitor_name is None:
            monitor_name = "text" if sys.stdout.isatty() else "none"
        monitor = make_monitor(monitor_name)
        snapshot = Snapshot(
            status="STREAMING",
            port=identity.port,
            firmware_version=identity.firmware_version,
            device_id=identity.device_id,
            reference_mode=identity.reference_mode or "",
            adc_states=[item.get("state", "UNKNOWN") for item in identity.adc_status] or ["UNKNOWN"] * 3,
        )
        print("recording to {}".format(run_dir))
        print("press Ctrl+C to stop safely")
        started = time.monotonic()
        last_sample_monotonic = started
        last_rx_monotonic = started
        fatal_error: Optional[str] = None
        while True:
            now = time.monotonic()
            if args.duration and now - started >= args.duration:
                break
            try:
                lines = session.read_available()
            except SerialTransportError as exc:
                fatal_error = str(exc)
                snapshot.status = "DISCONNECTED"
                break
            if lines:
                last_rx_monotonic = now
            for line in lines:
                try:
                    parsed = parse_message(line)
                except Exception as exc:
                    parsed = exc
                recorder.record_line(line, parsed)
                if isinstance(parsed, SampleFrame):
                    snapshot.frame = parsed
                    snapshot.samples = recorder.stats.samples
                    snapshot.last_host_ns = time.time_ns()
                    snapshot.recent_host_ns.append(snapshot.last_host_ns)
                    snapshot.reference_mode = parsed.reference_mode
                    snapshot.adc_states = [status.state for status in parsed.adc_status]
                    last_sample_monotonic = now
                    saturating = any(
                        flag & (FLAG_SAT_HIGH | FLAG_SAT_LOW | FLAG_NEAR_RAIL)
                        for flag in parsed.channel_flags
                    )
                    if any(status.state != "OK" for status in parsed.adc_status):
                        snapshot.status = "ADC_FAULT"
                    elif not all(parsed.valid):
                        snapshot.status = "CHANNEL_INVALID"
                    elif saturating:
                        snapshot.status = "SATURATION"
                    else:
                        snapshot.status = "STREAMING"
                else:
                    if hasattr(parsed, "code"):
                        snapshot.last_error = "{}: {}".format(parsed.code, getattr(parsed, "message", ""))
            now = time.monotonic()
            if snapshot.samples > 0:
                threshold = _timeout_threshold_s(list(snapshot.recent_host_ns))
                if now - last_sample_monotonic > threshold:
                    snapshot.status = "TIMEOUT"
            elif now - started > 2.0:
                snapshot.status = "NO_DATA"
            if monitor is not None:
                monitor.draw(snapshot, recorder.stats)
            time.sleep(0.005)
        if fatal_error:
            print("\nSERIAL ERROR: {}".format(fatal_error), file=sys.stderr)
            return 2
        return 0
    except KeyboardInterrupt:
        print("\nCtrl+C received; flushing files...")
        return 0
    except (SerialTransportError, DeviceIdentityError) as exc:
        print("RUN FAILED: {}".format(exc), file=sys.stderr)
        return 2
    finally:
        if session is not None:
            if identified:
                try:
                    session.set_streaming(False, timeout_s=1.0)
                except Exception:
                    pass
            session.close()
        if monitor is not None:
            try:
                monitor.close()
            except Exception:
                pass
        if recorder is not None:
            run = recorder.finalize()
            text = recorder.stats.to_text()
            print("\n" + text)
            if run_dir is not None:
                print("\nfiles:")
                print("  {}".format(run_dir / "raw_frames.jsonl"))
                print("  {}".format(run_dir / "samples.csv"))
                print("  {}".format(run_dir / "events.jsonl"))
                print("  {}".format(run_dir / "run.json"))
            if recorder.stats.samples == 0:
                print("WARNING: no SAMPLE frames were recorded", file=sys.stderr)


def command_analyze(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if path.is_dir():
        run_path = path / "run.json"
        csv_path = path / "samples.csv"
        if run_path.is_file():
            run = json.loads(run_path.read_text())
            print("RUN {}".format(path))
            print(json.dumps(run.get("summary", {}), indent=2))
            return 0
        if csv_path.is_file():
            stats = stats_from_csv(str(csv_path))
            print(stats.to_text())
            return 0
        print("no run.json or samples.csv in {}".format(path), file=sys.stderr)
        return 2
    if path.suffix == ".csv":
        stats = stats_from_csv(str(path))
        print(stats.to_text())
        return 0
    print("unsupported path: {}".format(path), file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    config = load_config()
    default_baud = int(config.get("serial_baud", 921600))
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list serial ports")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=command_list)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--port", help="explicit serial port; otherwise the only USB candidate is used")
        p.add_argument("--baud", type=int, default=default_baud)
        p.add_argument("--identify-timeout", type=float, default=8.0)
        p.add_argument("--expect-device-id", default=None)

    p_identify = sub.add_parser("identify", help="identify the port as the tactile ESP32")
    add_common(p_identify)
    p_identify.set_defaults(func=command_identify)

    p_diag = sub.add_parser("diag", help="run ADS1220 register/self-test diagnostics")
    add_common(p_diag)
    p_diag.add_argument("--out", help="diagnostics JSON path")
    p_diag.add_argument("--diag-timeout", type=float, default=10.0)
    p_diag.set_defaults(func=command_diag)

    p_run = sub.add_parser("run", help="receive, validate, record and monitor real frames")
    add_common(p_run)
    p_run.add_argument("--duration", type=float, default=0.0, help="seconds; 0 = until Ctrl+C")
    p_run.add_argument("--out", help="exact run directory")
    p_run.add_argument("--data-root", default=str(ROOT / "data/real/tactile"))
    p_run.add_argument("--monitor", choices=["text", "plot", "none"], default=None)
    p_run.set_defaults(func=command_run)

    p_analyze = sub.add_parser("analyze", help="print statistics from a run directory or samples.csv")
    p_analyze.add_argument("path")
    p_analyze.set_defaults(func=command_analyze)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
