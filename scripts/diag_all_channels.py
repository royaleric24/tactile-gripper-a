#!/usr/bin/env python3
"""All-12-channel, three-phase ADS1220 diagnostic (old ESP32 only).

Sets AVDD_AVSS, verifies the real SPI config, then records all channels during
BASELINE, CONTACT and RELEASE.  No gripper/S3, no firmware write, no PASS logic.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_single_point_config import (ConfigResponseError, frame_evidence,
    print_diagnostics, wait_config_report, wait_sample, wait_set_ref)
from tools.cup_grasp.model import CHANNEL_LABELS
from tools.cup_grasp.single_point import validate_config_report
from tools.tactile_acq.protocol import SampleFrame, parse_message
from tools.tactile_acq.transport import SerialSession


def mean(values):
    return statistics.mean(values) if values else None


def channel_stats(rows, channel, avdd_mv):
    raw = [r["raw_adc"][channel] for r in rows if r["valid"][channel] and r["raw_adc"][channel] is not None]
    flags = [r["channel_flags"][channel] for r in rows if r["valid"][channel]]
    return {
        "samples": len(raw),
        "valid_fraction": (len(raw) / len(rows)) if rows else None,
        "raw_mean": mean(raw),
        "raw_min": min(raw) if raw else None,
        "raw_max": max(raw) if raw else None,
        "volts_mean": (mean(raw) / 8388607.0 * avdd_mv / 1000.0) if raw else None,
        "saturated_fraction": (sum(1 for f in flags if f & 0x0B) / len(flags)) if flags else None,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/cu.usbserial-EXAMPLE_ESP32")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--avdd-mv", type=float, default=3300.0)
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--label", default="R4C3")
    args = parser.parse_args(argv)
    session = SerialSession(args.port, baud=args.baud)
    session.open()
    identity = session.identify(timeout_s=8.0)
    if not identity.streaming:
        session.set_streaming(True)
        time.sleep(0.2)
    try:
        status, setref = wait_set_ref(session)
    except ConfigResponseError as exc:
        print_diagnostics(exc); session.close(); return 2
    try:
        report, cfg_diag = wait_config_report(session)
    except ConfigResponseError as exc:
        print_diagnostics(exc); session.close(); return 2
    frame = wait_sample(session, 3.0)
    if frame is None:
        print("NO POST-CONFIG SAMPLE", file=sys.stderr); session.close(); return 2
    # This diagnostic does not need ch0 to be valid; it only requires the real
    # SPI register configuration.  The all-channel table is the evidence.
    validation = validate_config_report(report, mode="scan", channel_config=None,
                                        frame=None, selected_channel=0,
                                        require_scan_evidence=False, require_full_channel_map=False)
    if not validation["passed"]:
        print(json.dumps(validation, indent=2)); session.close(); return 2
    print("SET_REF ->", status.reference_mode, "; post-config frame reference", frame.reference_mode)
    print("All-channel mapping labels are firmware constants (not a HELLO claim):", CHANNEL_LABELS)
    rows = []
    boundaries = []
    lock = threading.Lock()
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                lines = session.read_available()
            except Exception as exc:
                print("READER_ERROR", exc, file=sys.stderr); return
            for raw in lines:
                try:
                    item = parse_message(raw)
                except Exception:
                    continue
                if isinstance(item, SampleFrame):
                    with lock:
                        rows.append({
                            "host_monotonic_ns": time.monotonic_ns(),
                            "device_timestamp_us": item.timestamp_us,
                            "frame_seq": item.frame_seq,
                            "raw_adc": list(item.raw_adc), "valid": list(item.valid),
                            "sample_timestamp_us": list(item.sample_timestamp_us),
                            "channel_flags": list(item.channel_flags),
                            "reference_mode": item.reference_mode,
                        })
            time.sleep(0.002)

    thread = threading.Thread(target=reader, daemon=True); thread.start()
    def phase(label, start):
        end = time.monotonic_ns()
        boundaries.append({"phase": label, "start_ns": start, "end_ns": end})
        return end
    try:
        print("\n=== BASELINE {:.1f}s: no contact ===".format(args.seconds)); time.sleep(args.seconds)
        phase("BASELINE", time.monotonic_ns() - int(args.seconds * 1e9))
        if not args.baseline_only:
            input("\nHold light pressure at {} and press Enter... ".format(args.label))
            c0 = time.monotonic_ns(); print("=== CONTACT {:.1f}s ===".format(args.seconds)); time.sleep(args.seconds)
            phase("CONTACT", c0)
            input("\nRelease and press Enter... ")
            r0 = time.monotonic_ns(); print("=== RELEASE {:.1f}s ===".format(args.seconds)); time.sleep(args.seconds)
            phase("RELEASE", r0)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set(); thread.join(timeout=2.0)
        try: session.set_streaming(False, timeout_s=1.0)
        except Exception: pass
        session.close()
    out = ROOT / "data/real/diag_all_channels" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:6])
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "samples.jsonl", "w") as h:
        for r in rows: h.write(json.dumps(r) + "\n")
    phase_rows = {}
    for b in boundaries:
        phase_rows[b["phase"]] = [r for r in rows if b["start_ns"] <= r["host_monotonic_ns"] < b["end_ns"]]
    channels = {}
    for ch in range(12):
        item = {"label": CHANNEL_LABELS[ch], "phases": {}}
        for name, rws in phase_rows.items():
            item["phases"][name] = channel_stats(rws, ch, args.avdd_mv)
        b = item["phases"].get("BASELINE", {}).get("raw_mean")
        c = item["phases"].get("CONTACT", {}).get("raw_mean")
        if b is not None and c is not None:
            item["contact_minus_baseline_counts"] = c - b
            item["contact_minus_baseline_volts"] = (c - b) / 8388607.0 * args.avdd_mv / 1000.0
        channels[ch] = item
    summary = {"trial_id": out.name, "port": args.port, "firmware": identity.firmware_version,
               "position": args.label, "avdd_mv_nominal": args.avdd_mv,
               "reference_mode": frame.reference_mode, "config_report": report,
               "config_validation": validation, "phase_boundaries": boundaries,
               "frames": len(rows), "channels": channels,
               "note": "ADC counts/volts are proxies; all 12 channels recorded. No PASS threshold applied."}
    (out / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = ["# All-Channel Diagnostic {}".format(out.name), "",
             "- firmware: {}".format(identity.firmware_version),
             "- position label: {} (USER_REPORTED)".format(args.label),
             "- AVDD nominal: {} mV".format(args.avdd_mv),
             "- reference mode (post-config frame): {}".format(frame.reference_mode),
             "- frames: {}".format(len(rows)),
             "- phase frames: {}".format({k: len(v) for k, v in phase_rows.items()}), "",
             "| ch | label | baseline V | contact V | delta V | release V | valid | sat |",
             "|---:|---|---:|---:|---:|---:|---:|---:|"]
    for ch in range(12):
        p = channels[ch]["phases"]
        def v(name):
            x = p.get(name, {}).get("volts_mean"); return "-" if x is None else "{:.3f}".format(x)
        b = p.get("BASELINE", {}); c = p.get("CONTACT", {}); r = p.get("RELEASE", {})
        evidence = c if c.get("valid_fraction") is not None else b
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} |".format(
            ch, CHANNEL_LABELS[ch], v("BASELINE"), v("CONTACT"),
            "-" if b.get("volts_mean") is None or c.get("volts_mean") is None else "{:.3f}".format(c["volts_mean"] - b["volts_mean"]),
            v("RELEASE"), "{:.2f}".format(evidence.get("valid_fraction") or 0), "{:.2f}".format(evidence.get("saturated_fraction") or 0)))
    lines += ["", "## Notes", "",
              "No channel is declared PASS. If no channel follows the measured 1.0→2.4 V node, do not attribute the result to R4C3.",
              "The next stage is a known-voltage injection test (0 V / ~1.65 V), not another passive press."]
    (out / "REPORT.md").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))
    print("OUT", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
