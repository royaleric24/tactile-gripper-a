#!/usr/bin/env python3
"""Interactive 36-point press experiment on the existing 12-channel firmware.

Serial reads run in a dedicated thread; the main thread only prints prompts,
counts down and waits for optional Enter confirmation.  The firmware, wiring and
ADC configuration are not modified.  No IDAC/PSW/excitation is enabled.

This is an exploratory raw-ADC experiment, not a validated pressure measurement.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.tactile_acq.protocol import SampleFrame, parse_message  # noqa: E402
from tools.tactile_acq.recorder import RunRecorder  # noqa: E402
from tools.tactile_acq.transport import (  # noqa: E402
    DeviceIdentityError,
    SerialSession,
    SerialTransportError,
)
from tools.tactile_experiment.analysis import analyze_run  # noqa: E402
from tools.tactile_experiment.protocol import POINTS, ExperimentProtocol  # noqa: E402


@dataclass
class LatestFrame:
    device_timestamp_us: int
    frame_seq: int
    host_monotonic_ns: int


class SerialReader(threading.Thread):
    def __init__(self, session: SerialSession, recorder: RunRecorder, lock: threading.Lock) -> None:
        super().__init__(daemon=True)
        self.session = session
        self.recorder = recorder
        self.lock = lock
        self.stop_event = threading.Event()
        self.latest: Optional[LatestFrame] = None
        self.error: Optional[str] = None
        self.line_count = 0

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                lines = self.session.read_available()
            except SerialTransportError as exc:
                self.error = str(exc)
                return
            for raw in lines:
                try:
                    parsed = parse_message(raw)
                except Exception as exc:  # record malformed lines and continue
                    parsed = exc
                host_mono_ns = time.monotonic_ns()
                with self.lock:
                    self.recorder.record_line(raw, parsed)
                    if isinstance(parsed, SampleFrame):
                        self.latest = LatestFrame(
                            device_timestamp_us=parsed.timestamp_us,
                            frame_seq=parsed.frame_seq,
                            host_monotonic_ns=host_mono_ns,
                        )
                    self.line_count += 1
            time.sleep(0.002)

    def stop(self) -> None:
        self.stop_event.set()


def make_run_dir(port: str, base: Optional[Path]) -> Path:
    base = base or ROOT / "data/real/tactile_36point"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = port.replace("/", "_").replace(":", "_")
    candidate = Path(base) / "{}_{}".format(stamp, safe)
    suffix = 2
    while candidate.exists():
        candidate = Path(base) / "{}_{}_{}".format(stamp, safe, suffix)
        suffix += 1
    return candidate


def augment_metadata(run_dir: Path, args, events_count: int, completed: int) -> None:
    meta_path = run_dir / "meta.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text())
        meta["experiment"] = {
            "name": "36_point_press",
            "points": [
                {"point_id": p.point_id, "row": p.row, "column": p.column, "label": p.label}
                for p in POINTS
            ],
            "baseline_s": args.baseline,
            "press_s": args.press,
            "release_s": args.release,
            "confirm_each": not args.no_confirm,
            "completed_points": completed,
            "event_count": events_count,
            "note": "Exploratory raw-ADC experiment; no new excitation, no pressure calibration.",
        }
        meta_path.write_text(json.dumps(meta, indent=2) + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/cu.usbserial-EXAMPLE_ESP32")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--out", help="exact new output directory (must not exist)")
    parser.add_argument("--baseline", type=float, default=10.0)
    parser.add_argument("--press", type=float, default=3.0)
    parser.add_argument("--release", type=float, default=3.0)
    parser.add_argument("--no-confirm", action="store_true", help="skip Enter before every point")
    parser.add_argument("--skip-analysis", action="store_true")
    args = parser.parse_args(argv)
    if args.out and Path(args.out).exists():
        print("refusing to overwrite existing directory: {}".format(args.out), file=sys.stderr)
        return 2

    session = None
    recorder = None
    reader = None
    lock = threading.Lock()
    completed = 0
    events_count = 0
    try:
        session = SerialSession(args.port, baud=args.baud)
        session.open()
        identity = session.identify(timeout_s=8.0)
        print("identified {} on {} (firmware {})".format(identity.device_id, identity.port, identity.firmware_version))
        print("ADC states: {}".format(", ".join(
            "ADC{}={}".format(item.get("id"), item.get("state")) for item in identity.adc_status
        )))
        if not identity.streaming:
            session.set_streaming(True)
            time.sleep(0.2)

        print("\nBEFORE START - confirm all of the following:")
        print("  1. Old ESP32 only, powered by Mac USB; ESP32-S3 and gripper are untouched.")
        print("  2. No external supply or new excitation is connected to the cloth/ADS1220s.")
        print("  3. No visible short, hot smell, or loose electrode; 12 electrodes remain connected.")
        print("  4. You will use one non-conductive tool with consistent area/force; do not touch bare electrodes.")
        print("  5. The tool is away from the cloth for the 10 s baseline.")
        confirm = input("Type START to begin, anything else to abort: ").strip()
        if confirm != "START":
            print("aborted by user; no acquisition started")
            return 1

        run_dir = Path(args.out) if args.out else make_run_dir(args.port, None)
        run_dir.mkdir(parents=True, exist_ok=False)
        recorder = RunRecorder(run_dir, args.port, args.baud, identity, {"experiment": "36_point_press"})
        reader = SerialReader(session, recorder, lock)
        reader.start()

        def emit_event(kind: str, **fields: Any) -> Dict[str, Any]:
            if reader.error:
                raise SerialTransportError("serial reader stopped: {}".format(reader.error))
            with lock:
                latest = reader.latest
                if latest is not None and (time.monotonic_ns() - latest.host_monotonic_ns) > 5_000_000_000:
                    raise SerialTransportError("no SAMPLE frame for >5 s")
                return recorder.record_event(kind, **fields)

        def status_provider() -> Optional[Dict[str, Any]]:
            with lock:
                latest = reader.latest
                if latest is None:
                    return None
                return {
                    "device_timestamp_us": latest.device_timestamp_us,
                    "frame_seq": latest.frame_seq,
                    "host_monotonic_ns": latest.host_monotonic_ns,
                }

        protocol = ExperimentProtocol(
            emit_event=emit_event,
            status_provider=status_provider,
            baseline_s=args.baseline,
            press_s=args.press,
            release_s=args.release,
            confirm_each=not args.no_confirm,
        )
        try:
            result = protocol.run()
            completed = result["completed"]
            events_count = result["events"]
        except KeyboardInterrupt:
            print("\nCtrl+C: stopping experiment and saving partial data", file=sys.stderr)
            completed = 0
        finally:
            if reader is not None:
                reader.stop()
                reader.join(timeout=2.0)
            try:
                session.set_streaming(False, timeout_s=1.0)
            except Exception:
                pass
            session.close()
            run = recorder.finalize()
        augment_metadata(run_dir, args, events_count, completed)
        (run_dir / "experiment_result.json").write_text(json.dumps({
            "completed_points": completed,
            "total_points": 36,
            "events": events_count,
            "reader_error": reader.error if reader else None,
            "reader_lines": reader.line_count if reader else 0,
            "run": run,
        }, indent=2) + "\n")

        if not args.skip_analysis:
            try:
                analysis = analyze_run(run_dir)
                print("\nANALYSIS: completed {}/36, signal quality {}, {}".format(
                    analysis["completed_points"], analysis["signal_quality"],
                    "; ".join(analysis["quality_reasons"])))
            except Exception:
                print("ANALYSIS FAILED; raw data is preserved", file=sys.stderr)
                traceback.print_exc()
                (run_dir / "analysis_error.txt").write_text(traceback.format_exc())
        print("\nDATA DIR: {}".format(run_dir))
        print("FILES: raw_frames.jsonl, samples.csv, events.jsonl, meta.json, run.json, analysis.json, REPORT.md, timeseries.svg, response_map.svg")
        return 0
    except (SerialTransportError, DeviceIdentityError) as exc:
        print("EXPERIMENT FAILED: {}".format(exc), file=sys.stderr)
        return 2
    except EOFError:
        print("no interactive input; aborted", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
