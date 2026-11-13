#!/usr/bin/env python3
"""Interactive 5-cycle single-point contact/release validation.

No gripper, no motion, no firmware upload.  Uses the existing 12-channel tactile
firmware, selects one ADC channel and optionally sets AVDD_AVSS reference.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.cup_grasp.model import load_config  # noqa: E402
from tools.cup_grasp.single_point import summarize_single_point, validate_config_report  # noqa: E402
from tools.cup_grasp.tactile import TactileProcessor  # noqa: E402
from tools.tactile_acq.protocol import SampleFrame, parse_message  # noqa: E402
from tools.tactile_acq.transport import SerialSession  # noqa: E402
from scripts.verify_single_point_config import (ConfigResponseError, channel_config_from_identity,
    frame_evidence, print_diagnostics, wait_config_report, wait_sample, wait_set_ref)  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/cu.usbserial-EXAMPLE_ESP32")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--channel", type=int, default=0)
    parser.add_argument("--cycles", type=int, default=5)
    parser.add_argument("--baseline", type=float, default=3.0)
    parser.add_argument("--contact", type=float, default=2.0)
    parser.add_argument("--release", type=float, default=2.0)
    parser.add_argument("--config", default=str(ROOT / "config/cup_grasp.template.json"))
    parser.add_argument("--avdd-mv", type=float, default=3300.0)
    parser.add_argument("--r-ref-ohm", type=float, default=10000.0)
    parser.add_argument("--r-row-ohm", type=float, default=1000.0)
    parser.add_argument("--v-exc", type=float, default=3.3)
    args = parser.parse_args(argv)
    config = load_config(Path(args.config))
    if not 0 <= args.channel <= 11:
        parser.error("--channel must be 0..11")
    processor = TactileProcessor(config.tactile)
    # use the requested channel even if the template says 0
    processor.config = type(processor.config)(**{**processor.config.__dict__, "channel": args.channel})
    print("Single-point validation: channel {} ({})".format(args.channel, config.tactile.channel_label))
    print("This uses ADC counts only; it is not a pressure/force calibration.")
    session = SerialSession(args.port, baud=args.baud)
    session.open()
    identity = session.identify(timeout_s=8.0)
    if not identity.streaming:
        session.set_streaming(True)
        time.sleep(0.2)
    frame = wait_sample(session)
    if frame is None:
        print("NO SAMPLE FRAME: cannot verify ch0 conversion mapping", file=sys.stderr)
        session.close()
        return 2
    channel_config = channel_config_from_identity(identity)
    if channel_config is None:
        print("CHANNEL_CONFIG_MISSING: HELLO/channel_config absent; refusing SCAN_MODE_PASS", file=sys.stderr)
        session.close()
        return 2
    try:
        setref_status, setref_diagnostics = wait_set_ref(session)
        print("SET_REF -> reference_mode={}".format(setref_status.reference_mode))
    except ConfigResponseError as exc:
        print_diagnostics(exc)
        session.close()
        return 2
    try:
        report, config_diagnostics = wait_config_report(session)
    except ConfigResponseError as exc:
        print_diagnostics(exc)
        session.close()
        return 2
    validation = validate_config_report(report or {}, mode="scan", channel_config=channel_config,
                                        frame=frame_evidence(frame), require_scan_evidence=True)
    print(json.dumps(validation, indent=2))
    if not validation["passed"]:
        print("CONFIG VERIFICATION FAILED; refusing single-point interpretation", file=sys.stderr)
        session.close()
        return 2
    print("Expected AIN0 voltage with R_ref=10k, R_row=1k: 36k -> {:.3f} V, 12k -> {:.3f} V, 2k -> {:.3f} V".format(
        3.3 * 10000 / (36000 + 11000), 3.3 * 10000 / (12000 + 11000), 3.3 * 10000 / (2000 + 11000)))
    records = []
    lock = threading.Lock()
    stop = threading.Event()
    error = {"value": None}

    def reader():
        while not stop.is_set():
            try:
                lines = session.read_available()
            except Exception as exc:
                error["value"] = str(exc)
                return
            for raw in lines:
                try:
                    frame = parse_message(raw)
                except Exception:
                    continue
                if not isinstance(frame, SampleFrame):
                    continue
                now = time.monotonic_ns()
                sample = processor.update(frame, now)
                with lock:
                    records.append({
                        "host_monotonic_ns": now,
                        "device_timestamp_us": sample.device_timestamp_us,
                        "frame_seq": sample.frame_seq,
                        "raw": sample.raw,
                        "filtered": sample.filtered,
                        "baseline": sample.baseline,
                        "delta": sample.delta,
                        "valid": sample.valid,
                        "usable": sample.usable,
                        "saturated": sample.saturated,
                        "saturation_fraction": sample.saturation_fraction,
                        "flags": sample.flags,
                    })
            time.sleep(0.002)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    trial_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:6]
    out = ROOT / "data/real/single_point" / trial_id
    out.mkdir(parents=True, exist_ok=False)
    cycles = []
    try:
        print("\n=== BASELINE {:.0f}s: no contact at R1C1 ===".format(args.baseline))
        time.sleep(args.baseline)
        for index in range(1, args.cycles + 1):
            input("\nCycle {}/{}: position the tool at R1C1, then press Enter to start CONTACT... ".format(index, args.cycles))
            press_ns = time.monotonic_ns()
            print(">>> CONTACT NOW for {:.0f}s".format(args.contact), flush=True)
            time.sleep(args.contact)
            release_ns = time.monotonic_ns()
            print(">>> RELEASE NOW for {:.0f}s".format(args.release), flush=True)
            time.sleep(args.release)
            cycles.append({"index": index, "press_ns": press_ns, "release_ns": release_ns})
            print("    cycle {} recorded".format(index), flush=True)
    except KeyboardInterrupt:
        print("\nCtrl+C: saving partial single-point data", file=sys.stderr)
    finally:
        stop.set()
        thread.join(timeout=2.0)
        try:
            session.set_streaming(False, timeout_s=1.0)
        except Exception:
            pass
        session.close()
    with open(out / "samples.jsonl", "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    summary = summarize_single_point(records, cycles, avdd_mv=args.avdd_mv,
                                     r_ref_ohm=args.r_ref_ohm, r_row_ohm=args.r_row_ohm,
                                     v_exc=args.v_exc)
    metrics = {
        "trial_id": trial_id,
        "data_kind": "REAL_HARDWARE_SERIAL",
        "port": args.port,
        "channel": args.channel,
        "firmware": identity.firmware_version,
        "cycles_requested": args.cycles,
        "cycles_recorded": len(cycles),
        "frames": len(records),
        "reader_error": error["value"],
        "reference_mode_requested": "AVDD_AVSS",
        "config_report": report,
        "channel_config": channel_config,
        "frame_evidence": frame_evidence(frame),
        "setref_diagnostics": setref_diagnostics,
        "config_diagnostics": config_diagnostics,
        "config_validation": validation,
        "summary": summary,
        "note": "ADC counts only; not pressure/force. Electrical validity must be reviewed.",
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    (out / "meta.json").write_text(json.dumps({
        "trial_id": trial_id,
        "protocol": {"baseline_s": args.baseline, "contact_s": args.contact, "release_s": args.release,
                     "cycles": args.cycles, "channel": args.channel},
        "identity": identity.__dict__,
    }, indent=2) + "\n")
    (out / "REPORT.md").write_text(
        "# Single-Point Validation {}\n\n- cycles: {}/{}\n- passed: {}/{}\n- frames: {}\n"
        "- result: {}\n\nADC counts only; not pressure/force.\n".format(
            trial_id, len(cycles), args.cycles, summary["passed_cycles"], summary["total_cycles"],
            len(records), "PASS" if summary["pass"] else "FAIL/INSUFFICIENT"))
    print("\nSINGLE-POINT SUMMARY: passed {}/{}, result {}".format(
        summary["passed_cycles"], summary["total_cycles"], "PASS" if summary["pass"] else "FAIL/INSUFFICIENT"))
    print("DATA DIR: {}".format(out))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
