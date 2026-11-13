#!/usr/bin/env python3
"""H4 single-point contact detection demo / 3-round repeatability test.

Examples:
  python scripts/contact_demo.py --live --port /dev/cu.usbserial-EXAMPLE_ESP32 --web-port 8765
  python scripts/contact_demo.py --live --port /dev/cu.usbserial-EXAMPLE_ESP32 --rounds 3 --phase-seconds 3
  python scripts/contact_demo.py --replay data/real/diag_fixed_ain1/<trial>/samples.jsonl --no-web
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.contact_detection.config import DetectorConfig
from tools.contact_detection.detector import ContactDetector
from tools.contact_detection.sources import LiveSerialSource, ReplaySource
from tools.contact_detection.state import DemoState
from tools.contact_detection.store import TrialStore
from tools.contact_detection.webapp import start_web


def make_state(args, data_kind, source_name, firmware=None):
    cfg = DetectorConfig(avdd_mv=args.avdd_mv)
    root = ROOT / ("data/real/contact_demo" if data_kind in ("LIVE_REAL", "REPLAY_REAL") else "data/simulated/contact_demo")
    store = TrialStore(root, source=source_name, data_kind=data_kind, label=args.label,
                       config={
                           "avdd_mv": cfg.avdd_mv, "baseline_frames": cfg.baseline_frames,
                           "ema_alpha": cfg.ema_alpha, "contact_drop_v": cfg.contact_drop_v,
                           "release_recover_v": cfg.release_recover_v,
                           "contact_confirm_frames": cfg.contact_confirm_frames,
                           "release_confirm_frames": cfg.release_confirm_frames,
                           "unknown_timeout_s": cfg.unknown_timeout_s,
                       }, firmware=firmware)
    state = DemoState(store, ContactDetector(cfg), source_name=source_name)
    return state, store


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--live", action="store_true")
    group.add_argument("--replay", type=Path)
    parser.add_argument("--port", default="/dev/cu.usbserial-EXAMPLE_ESP32")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--web-port", type=int, default=8765)
    parser.add_argument("--no-web", action="store_true")
    parser.add_argument("--rounds", type=int, default=0, help="0 = continuous until Ctrl+C")
    parser.add_argument("--phase-seconds", type=float, default=3.0)
    parser.add_argument("--replay-speed", type=float, default=10.0)
    parser.add_argument("--avdd-mv", type=float, default=3388.0)
    parser.add_argument("--label", default="R4C3")
    args = parser.parse_args(argv)
    if args.rounds < 0:
        parser.error("--rounds must be >= 0")
    if args.replay:
        samples = Path(args.replay)
        if not samples.is_file():
            print("replay samples missing: {}".format(samples), file=sys.stderr)
            return 2
        summary_path = samples.parent / "SUMMARY.json"
        hello = None
        if summary_path.is_file():
            hello = json.loads(summary_path.read_text()).get("hello")
        state, store = make_state(args, "REPLAY_REAL", str(samples), hello.get("firmware") if hello else None)
        source = ReplaySource(samples, state, speed=args.replay_speed, hello=hello)
    else:
        state, store = make_state(args, "LIVE_REAL", "serial:{}".format(args.port))
        source = LiveSerialSource(args.port, args.baud, state, store)
    server = None
    web_thread = None
    if not args.no_web:
        try:
            server, web_thread = start_web(state, args.web_port)
            print("DASHBOARD http://127.0.0.1:{}/".format(args.web_port))
        except OSError as exc:
            print("WEB START FAILED: {}".format(exc), file=sys.stderr)
            return 2
    source.start()
    try:
        if args.replay:
            source.join()
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline and state.connection not in ("DONE", "ERROR"):
                time.sleep(0.05)
        else:
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline and state.connection not in ("STREAMING", "ERROR"):
                time.sleep(0.05)
            if state.connection == "ERROR":
                print("SERIAL ERROR: {}".format(state.last_error), file=sys.stderr)
                return 2
            if args.rounds:
                for r in range(1, args.rounds + 1):
                    state.round_marker("R{}_BASELINE".format(r))
                    input("\nRound {}/{}: no contact. Press Enter to start baseline... ".format(r, args.rounds))
                    time.sleep(args.phase_seconds)
                    state.round_marker("R{}_CONTACT".format(r))
                    input("Hold light pressure at {}. Press Enter to start CONTACT... ".format(args.label))
                    time.sleep(args.phase_seconds)
                    state.round_marker("R{}_RELEASE".format(r))
                    input("Release now. Press Enter to start RELEASE... ")
                    time.sleep(args.phase_seconds)
            else:
                print("\nContinuous mode; press Ctrl+C to finish.")
                while True:
                    time.sleep(0.25)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        source.stop()
        try:
            source.join(timeout=2.0)
        except Exception:
            pass
        if server is not None:
            server.shutdown(); server.server_close()
        summary = store.finalize(status="DONE" if state.connection != "ERROR" else "ERROR",
                                 errors=[state.last_error] if state.last_error else [])
        print(json.dumps({"trial_dir": str(store.dir), "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
