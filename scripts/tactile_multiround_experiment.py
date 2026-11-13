#!/usr/bin/env python3
"""Randomized multi-round 36-point experiment with controls (2 rounds default).

Reuses the existing serial reader thread and RunRecorder.  Does not modify the
firmware, wiring, IDAC/PSW or ESP32-S3.  Labels/order are recorded but never fed
to the ML features; evaluation is by whole rounds.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.tactile_acq.recorder import RunRecorder, utc_now_iso  # noqa: E402
from tools.tactile_acq.transport import (  # noqa: E402
    DeviceIdentityError,
    SerialSession,
    SerialTransportError,
)
from tools.tactile_experiment.multiround import RoundProtocol, build_round_schedule  # noqa: E402
from tools.tactile_experiment.multiround_analysis import analyze_session  # noqa: E402
from scripts.tactile_36point_experiment import SerialReader  # noqa: E402


def make_session_dir(port: str, base: Optional[Path]) -> Path:
    base = base or ROOT / "data/real/tactile_36point_multiround"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = port.replace("/", "_").replace(":", "_")
    path = Path(base) / "{}_{}".format(stamp, safe)
    suffix = 2
    while path.exists():
        path = Path(base) / "{}_{}_{}".format(stamp, safe, suffix)
        suffix += 1
    return path


def write_json(path: Path, value: Dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


def augment_round_meta(round_dir: Path, schedule, args) -> None:
    meta_path = round_dir / "meta.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text())
    else:
        meta = {}
    meta["experiment"] = {
        "name": "36_point_randomized_round",
        "round_index": schedule.round_index,
        "seed": schedule.seed,
        "press_s": args.press,
        "release_s": args.release,
        "baseline_s": args.baseline,
        "confirm_each": not args.no_confirm,
        "approach_controls": args.approach_controls,
        "no_contact_controls": args.no_contact_controls,
        "schedule": schedule.as_dict(),
        "note": "Labels/order are for scoring only; features are raw-signal windows.",
    }
    write_json(meta_path, meta)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/cu.usbserial-EXAMPLE_ESP32")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20261113)
    parser.add_argument("--approach-controls", type=int, default=2)
    parser.add_argument("--no-contact-controls", type=int, default=2)
    parser.add_argument("--press", type=float, default=3.0)
    parser.add_argument("--release", type=float, default=3.0)
    parser.add_argument("--baseline", type=float, default=10.0)
    parser.add_argument("--rest", type=float, default=20.0)
    parser.add_argument("--no-confirm", action="store_true")
    parser.add_argument("--out", help="session directory (must not exist)")
    parser.add_argument("--skip-analysis", action="store_true")
    args = parser.parse_args(argv)
    if args.rounds < 2:
        parser.error("--rounds must be >=2 for cross-round evaluation")
    if args.out and Path(args.out).exists():
        print("refusing to overwrite existing directory: {}".format(args.out), file=sys.stderr)
        return 2

    session = None
    session_dir = None
    session_data: Dict[str, Any] = {}
    aborted = False
    try:
        session = SerialSession(args.port, baud=args.baud)
        session.open()
        identity = session.identify(timeout_s=8.0)
        print("identified {} on {} (firmware {})".format(identity.device_id, identity.port, identity.firmware_version))
        print("ADC states: {}".format(", ".join(
            "ADC{}={}".format(item.get("id"), item.get("state")) for item in identity.adc_status
        )))
        print("\nBEFORE START - confirm:")
        print("  1. Old ESP32 only via Mac USB; ESP32-S3 and gripper untouched.")
        print("  2. No external supply / no IDAC / no PSW / no rewiring.")
        print("  3. 12 electrodes connected; no short, loose wire, heat or smell.")
        print("  4. One non-conductive tool, consistent area/force; tool away during baselines.")
        print("  5. {} rounds, 36 press points each, randomized order + approach/no-contact controls.".format(args.rounds))
        if input("Type START to begin, anything else to abort: ").strip() != "START":
            print("aborted by user; no data collected")
            return 1

        session_dir = Path(args.out) if args.out else make_session_dir(args.port, None)
        session_dir.mkdir(parents=True, exist_ok=False)
        session_data = {
            "software_version": "tactile-multiround-0.1.0",
            "started_utc": utc_now_iso(),
            "port": args.port,
            "baud": args.baud,
            "base_seed": args.seed,
            "rounds_requested": args.rounds,
            "identity": identity.__dict__ if hasattr(identity, "__dict__") else str(identity),
            "rounds": [],
            "status": "running",
        }
        write_json(session_dir / "session.json", session_data)

        for round_index in range(1, args.rounds + 1):
            seed = args.seed + round_index - 1
            schedule = build_round_schedule(
                round_index, seed,
                press_s=args.press, release_s=args.release,
                approach_controls=args.approach_controls,
                no_contact_controls=args.no_contact_controls,
            )
            round_dir = session_dir / "round_{:02d}".format(round_index)
            round_dir.mkdir(parents=True, exist_ok=False)
            write_json(round_dir / "schedule.json", schedule.as_dict())
            # Each round starts streaming explicitly; the previous round ended
            # with STREAM false, so identity.streaming from boot is stale here.
            session.set_streaming(True)
            time.sleep(0.2)
            recorder = RunRecorder(round_dir, args.port, args.baud, identity, {"experiment": "36_point_randomized_round"})
            lock = threading.Lock()
            reader = SerialReader(session, recorder, lock)
            reader.start()
            protocol = RoundProtocol(
                schedule,
                emit_event=_make_emitter(reader, recorder, lock),
                status_provider=_make_status(reader, lock),
                baseline_s=args.baseline,
                confirm_each=not args.no_confirm,
            )
            result = {"completed_presses": 0, "segments": 0, "events": 0}
            failure = None
            try:
                result = protocol.run()
            except KeyboardInterrupt:
                failure = "KeyboardInterrupt"
                print("\nCtrl+C: stopping current round, saving partial data", file=sys.stderr)
            except (SerialTransportError, DeviceIdentityError) as exc:
                failure = str(exc)
                print("\nSERIAL/EXPERIMENT ERROR: {}".format(exc), file=sys.stderr)
            finally:
                reader.stop()
                reader.join(timeout=2.0)
                try:
                    session.set_streaming(False, timeout_s=1.0)
                except Exception:
                    pass
                run = recorder.finalize()
            augment_round_meta(round_dir, schedule, args)
            round_entry = {
                "round_index": round_index,
                "seed": seed,
                "dir": round_dir.name,
                "schedule": schedule.as_dict(),
                "completed_presses": result.get("completed_presses", 0),
                "segments": result.get("segments", 0),
                "failure": failure,
                "run_summary": run.get("summary") if isinstance(run, dict) else None,
            }
            session_data["rounds"].append(round_entry)
            write_json(session_dir / "session.json", session_data)
            if failure:
                aborted = True
                break
            if round_index < args.rounds:
                print("\n=== REST {:.0f}s before next round; keep tool away ===".format(args.rest), flush=True)
                _countdown_rest(args.rest)

        session_data["status"] = "aborted" if aborted else "completed"
        session_data["ended_utc"] = utc_now_iso()
        write_json(session_dir / "session.json", session_data)
        if not args.skip_analysis and len(session_data["rounds"]) >= 2:
            try:
                report = analyze_session(session_dir)
                print("\nPRELIMINARY ANALYSIS: quality {}, rounds {}".format(
                    report["quality"], [r["round_index"] for r in report["rounds"]]))
                print("report: {}".format(session_dir / "REPORT.md"))
            except Exception:
                print("ANALYSIS FAILED; raw data preserved", file=sys.stderr)
                traceback.print_exc()
                (session_dir / "analysis_error.txt").write_text(traceback.format_exc())
        print("\nSESSION DIR: {}".format(session_dir))
        print("FILES: round_01/... round_02/..., session.json, features.csv, ml_report.json, REPORT.md, confusion_matrix.svg")
        return 0 if not aborted else 2
    except (SerialTransportError, DeviceIdentityError) as exc:
        print("EXPERIMENT FAILED: {}".format(exc), file=sys.stderr)
        return 2
    except EOFError:
        print("no interactive input; aborted", file=sys.stderr)
        return 1
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass


def _make_emitter(reader, recorder, lock):
    def emit(kind: str, **fields: Any) -> Dict[str, Any]:
        if reader.error:
            raise SerialTransportError("serial reader stopped: {}".format(reader.error))
        with lock:
            latest = reader.latest
            if latest is not None and (time.monotonic_ns() - latest.host_monotonic_ns) > 5_000_000_000:
                raise SerialTransportError("no SAMPLE frame for >5 s")
            return recorder.record_event(kind, **fields)
    return emit


def _make_status(reader, lock):
    def status() -> Optional[Dict[str, Any]]:
        with lock:
            latest = reader.latest
            if latest is None:
                return None
            return {
                "device_timestamp_us": latest.device_timestamp_us,
                "frame_seq": latest.frame_seq,
                "host_monotonic_ns": latest.host_monotonic_ns,
            }
    return status


def _countdown_rest(seconds: float) -> None:
    end = time.monotonic() + max(0.0, seconds)
    while True:
        remaining = end - time.monotonic()
        if remaining <= 0:
            break
        print("  rest... {:.0f}s".format(max(1, int(remaining))), end="\r", flush=True)
        time.sleep(min(1.0, remaining))
    print(" " * 30, end="\r", flush=True)


if __name__ == "__main__":
    sys.exit(main())
