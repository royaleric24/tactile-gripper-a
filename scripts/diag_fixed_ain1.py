#!/usr/bin/env python3
"""Reliable host for the fixed ADC2-AIN1 diagnostic firmware.

- raw bytes are written to raw.bin and raw_hex.log;
- only complete, strictly validated DIAG_SAMPLE lines are recorded;
- a HELLO request is sent and periodic HELLO is also accepted;
- no PASS threshold is applied.
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

from tools.cup_grasp.diag_serial import DiagProtocolError, LineFramer, parse_diag_line


def mean(values):
    return statistics.mean(values) if values else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/cu.usbserial-EXAMPLE_ESP32")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--avdd-mv", type=float, default=3388.0)
    parser.add_argument("--label", default="R4C3")
    parser.add_argument("--hello-timeout", type=float, default=8.0)
    args = parser.parse_args(argv)
    import serial
    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.05, exclusive=True)
    except (serial.SerialException, OSError) as exc:
        print("OPEN FAILED: {}".format(exc), file=sys.stderr)
        return 2
    try:
        ser.dtr = False
        ser.rts = False
    except Exception:
        pass
    try:
        ser.reset_input_buffer()
    except Exception:
        pass
    out = ROOT / "data/real/diag_fixed_ain1" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:6])
    out.mkdir(parents=True, exist_ok=True)
    raw_bin = open(out / "raw.bin", "wb")
    raw_hex = open(out / "raw_hex.log", "w", encoding="utf-8")
    framer = LineFramer()
    hello = None
    bad_lines = []
    raw_bytes = 0

    def read_chunk():
        chunk = ser.read(4096)
        if not chunk:
            return b""
        raw_bin.write(chunk); raw_bin.flush()
        raw_hex.write("{} {}\n".format(time.monotonic_ns(), chunk.hex())); raw_hex.flush()
        return chunk

    # Handshake: request HELLO explicitly; periodic HELLO is also accepted.
    try:
        ser.write(b"HELLO\n"); ser.flush()
        deadline = time.monotonic() + args.hello_timeout
        while time.monotonic() < deadline and hello is None:
            chunk = read_chunk()
            if not chunk:
                continue
            raw_bytes += len(chunk)
            for line in framer.feed(chunk):
                try:
                    kind, item = parse_diag_line(line)
                except DiagProtocolError as exc:
                    bad_lines.append({"error": str(exc), "raw_hex": line.hex(),
                                      "raw_text": line.decode("utf-8", errors="replace")})
                    continue
                if kind == "DIAG_HELLO":
                    hello = item
                    break
    finally:
        if hello is None:
            raw_bin.close(); raw_hex.close(); ser.close()
            print("NO DIAG_HELLO after {:.1f}s; raw bytes saved: {}".format(args.hello_timeout, out / "raw_hex.log"), file=sys.stderr)
            print("BAD LINE COUNT: {}; last errors:".format(len(bad_lines)), file=sys.stderr)
            for item in bad_lines[-5:]:
                print("  {} raw={}".format(item["error"], item["raw_hex"][:120]), file=sys.stderr)
            return 2
    print("DIAG_HELLO", json.dumps(hello, indent=2))
    rows = []
    phases = []
    lock = threading.Lock()
    stop = threading.Event()
    reader_error = {"value": None}

    def reader():
        nonlocal raw_bytes
        while not stop.is_set():
            try:
                chunk = ser.read(4096)
            except Exception as exc:
                reader_error["value"] = str(exc); return
            if not chunk:
                continue
            with lock:
                raw_bytes += len(chunk)
            raw_bin.write(chunk); raw_bin.flush()
            raw_hex.write("{} {}\n".format(time.monotonic_ns(), chunk.hex())); raw_hex.flush()
            for line in framer.feed(chunk):
                try:
                    kind, item = parse_diag_line(line)
                except DiagProtocolError as exc:
                    with lock:
                        bad_lines.append({"error": str(exc), "raw_hex": line.hex(),
                                          "raw_text": line.decode("utf-8", errors="replace")})
                    continue
                if kind == "DIAG_SAMPLE":
                    item["host_monotonic_ns"] = time.monotonic_ns()
                    with lock: rows.append(item)
            time.sleep(0.001)

    thread = threading.Thread(target=reader, daemon=True); thread.start()

    def mark(label, start):
        phases.append({"phase": label, "start_ns": start, "end_ns": time.monotonic_ns()})
    try:
        print("\n=== BASELINE {:.1f}s: no contact ===".format(args.seconds))
        time.sleep(args.seconds); mark("BASELINE", time.monotonic_ns() - int(args.seconds * 1e9))
        input("\nHold light pressure at {} and press Enter... ".format(args.label))
        c0 = time.monotonic_ns(); print("=== CONTACT {:.1f}s ===".format(args.seconds))
        time.sleep(args.seconds); mark("CONTACT", c0)
        input("\nRelease and press Enter... ")
        r0 = time.monotonic_ns(); print("=== RELEASE {:.1f}s ===".format(args.seconds))
        time.sleep(args.seconds); mark("RELEASE", r0)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set(); thread.join(timeout=2.0); ser.close()
        raw_bin.close(); raw_hex.close()
    with open(out / "samples.jsonl", "w") as h:
        for row in rows: h.write(json.dumps(row) + "\n")
    with open(out / "bad_lines.jsonl", "w") as h:
        for item in bad_lines: h.write(json.dumps(item) + "\n")
    summary = {"trial_id": out.name, "hello": hello, "label": args.label,
               "avdd_mv": args.avdd_mv, "raw_bytes": raw_bytes,
               "raw_bin": str(out / "raw.bin"), "raw_hex": str(out / "raw_hex.log"),
               "bad_lines": len(bad_lines), "reader_error": reader_error["value"],
               "phases": []}
    for phase in phases:
        items = [r for r in rows if phase["start_ns"] <= r["host_monotonic_ns"] < phase["end_ns"]]
        counts = [r["counts"] for r in items if r.get("read_ok") and isinstance(r.get("counts"), int)]
        volts = [c / 8388607.0 * args.avdd_mv / 1000.0 for c in counts]
        mux_ok = sum(1 for r in items if r.get("mux_before") == 9 and r.get("mux_after") == 9)
        vref_ok = sum(1 for r in items if r.get("vref_before") == 3 and r.get("vref_after") == 3)
        reg3_ok = sum(1 for r in items if r.get("reg3_before") == 2 and r.get("reg3_after") == 2)
        restored = sum(1 for r in items if r.get("restored_before_cs") is True)
        post_high = sum(1 for r in items if r.get("post_cs_high") is True)
        raw_counts = {}
        for r in items:
            if r.get("raw"): raw_counts[r["raw"]] = raw_counts.get(r["raw"], 0) + 1
        summary["phases"].append({
            "phase": phase["phase"], "frames": len(items),
            "ready": sum(1 for r in items if r.get("ready")),
            "high_seen": sum(1 for r in items if r.get("high_seen")),
            "read_ok": sum(1 for r in items if r.get("read_ok")),
            "mux_ok": mux_ok, "vref_ok": vref_ok, "reg3_ok": reg3_ok,
            "restored_before_cs": restored, "post_cs_high": post_high,
            "counts_mean": mean(counts), "counts_min": min(counts) if counts else None,
            "counts_max": max(counts) if counts else None,
            "volts_mean": mean(volts), "volts_min": min(volts) if volts else None,
            "volts_max": max(volts) if volts else None,
            "raw_top": sorted(raw_counts.items(), key=lambda kv: -kv[1])[:5],
        })
    (out / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = ["# Fixed ADC2 AIN1 Diagnostic", "",
             "- firmware: {}".format(hello.get("firmware")), "- label: {} (USER_REPORTED)".format(args.label),
             "- fixed MUX AIN1/AVSS, VREF=AVDD_AVSS, DRDYM=1",
             "- raw bytes: {}; malformed lines: {}".format(raw_bytes, len(bad_lines)),
             "- AVDD used for display: {} mV".format(args.avdd_mv), "",
             "| phase | frames | ready | high_seen | mux_ok | vref_ok | reg3_ok | restored_before_cs | post_cs_high | mean counts | mean V | raw top |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for p in summary["phases"]:
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            p["phase"], p["frames"], p["ready"], p["high_seen"], p["mux_ok"], p["vref_ok"],
            p["reg3_ok"], p["restored_before_cs"], p["post_cs_high"],
            "-" if p["counts_mean"] is None else "{:.0f}".format(p["counts_mean"]),
            "-" if p["volts_mean"] is None else "{:.4f}".format(p["volts_mean"]),
            p["raw_top"]))
    lines += ["", "## Interpretation", "",
              "Only complete valid DIAG_SAMPLE JSON lines are counted. Malformed lines are in bad_lines.jsonl and raw_hex.log.",
              "A timeout or restored_before_cs=false is not a valid state-restored conversion.",
              "Reg0 before/after 0x91, Reg2 0xC0, Reg3 0x02, MUX 9, VREF 3 are required for a trustworthy result."]
    (out / "REPORT.md").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))
    print("OUT", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
