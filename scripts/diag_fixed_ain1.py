#!/usr/bin/env python3
"""Host for the fixed ADC2-AIN1 diagnostic firmware.

The firmware must be `tactile-sense-diag-ain1-0.1.0` or newer.  This host does
not use the normal SAMPLE/HELLO protocol; it reads DIAG_HELLO/DIAG_SAMPLE lines.
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

from tools.tactile_acq.transport import SerialSession


def mean(values):
    return statistics.mean(values) if values else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/cu.usbserial-EXAMPLE_ESP32")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--avdd-mv", type=float, default=3390.0)
    parser.add_argument("--label", default="R4C3")
    args = parser.parse_args(argv)
    session = SerialSession(args.port, baud=args.baud)
    session.open()
    hello = None
    bad_lines = []
    deadline = time.monotonic() + 6.0
    while time.monotonic() < deadline and hello is None:
        for raw in session.read_available():
            text = raw.decode("utf-8", errors="replace")
            try:
                item = json.loads(text)
            except ValueError:
                bad_lines.append(text); continue
            if item.get("type") == "DIAG_HELLO":
                hello = item; break
        time.sleep(0.003)
    if hello is None:
        print("NO DIAG_HELLO: is the fixed-AIN1 diagnostic firmware flashed?", file=sys.stderr)
        for line in bad_lines[-10:]: print("RAW", line, file=sys.stderr)
        session.close(); return 2
    print("DIAG_HELLO", json.dumps(hello, indent=2))
    rows = []
    phases = []
    lock = threading.Lock()
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                lines = session.read_available()
            except Exception as exc:
                print("READER_ERROR", exc, file=sys.stderr); return
            for raw in lines:
                text = raw.decode("utf-8", errors="replace")
                try:
                    item = json.loads(text)
                except ValueError:
                    with lock: bad_lines.append(text)
                    continue
                if item.get("type") != "DIAG_SAMPLE":
                    continue
                item["host_monotonic_ns"] = time.monotonic_ns()
                with lock: rows.append(item)
            time.sleep(0.002)

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
        stop.set(); thread.join(timeout=2.0); session.close()
    out = ROOT / "data/real/diag_fixed_ain1" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:6])
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "samples.jsonl", "w") as h:
        for row in rows: h.write(json.dumps(row) + "\n")
    summary = {"trial_id": out.name, "hello": hello, "label": args.label,
               "avdd_mv": args.avdd_mv, "phases": []}
    for phase in phases:
        items = [r for r in rows if phase["start_ns"] <= r["host_monotonic_ns"] < phase["end_ns"]]
        counts = [r["counts"] for r in items if r.get("read_ok") and isinstance(r.get("counts"), int)]
        volts = [c / 8388607.0 * args.avdd_mv / 1000.0 for c in counts]
        mux_ok = sum(1 for r in items if r.get("mux_before") == 9 and r.get("mux_after") == 9)
        vref_ok = sum(1 for r in items if r.get("vref_before") == 3 and r.get("vref_after") == 3)
        reg3_ok = sum(1 for r in items if r.get("reg3_before") == 2 and r.get("reg3_after") == 2)
        post_cs_high = sum(1 for r in items if r.get("post_cs_high") is True)
        extra_clock = sum(1 for r in items if r.get("extra_clock") is True)
        raw_counts = {}
        for r in items:
            if r.get("raw"): raw_counts[r["raw"]] = raw_counts.get(r["raw"], 0) + 1
        summary["phases"].append({
            "phase": phase["phase"], "frames": len(items),
            "ready": sum(1 for r in items if r.get("ready")),
            "high_seen": sum(1 for r in items if r.get("high_seen")),
            "read_ok": sum(1 for r in items if r.get("read_ok")),
            "mux_ok": mux_ok, "vref_ok": vref_ok, "reg3_ok": reg3_ok,
            "post_cs_high": post_cs_high, "extra_clock": extra_clock,
            "reconfigured": sum(1 for r in items if r.get("reconfigured")),
            "counts_mean": mean(counts), "counts_min": min(counts) if counts else None,
            "counts_max": max(counts) if counts else None,
            "volts_mean": mean(volts), "volts_min": min(volts) if volts else None,
            "volts_max": max(volts) if volts else None,
            "raw_top": sorted(raw_counts.items(), key=lambda kv: -kv[1])[:5],
        })
    (out / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = ["# Fixed ADC2 AIN1 Diagnostic", "",
             "- firmware: {}".format(hello.get("firmware")), "- label: {} (USER_REPORTED)".format(args.label),
             "- fixed MUX: AIN1/AVSS (Reg0=0x91), VREF=AVDD_AVSS (Reg2=0xC0), DRDYM=1 (Reg3=0x02)",
             "- AVDD used for display: {} mV (not measured by this host)".format(args.avdd_mv), "",
             "| phase | frames | ready | high_seen | mux_ok | vref_ok | reg3_ok | post_cs_high | extra_clock | mean counts | mean V | raw top |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for p in summary["phases"]:
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            p["phase"], p["frames"], p["ready"], p["high_seen"], p["mux_ok"], p["vref_ok"],
            p["reg3_ok"], p["post_cs_high"], p["extra_clock"],
            "-" if p["counts_mean"] is None else "{:.0f}".format(p["counts_mean"]),
            "-" if p["volts_mean"] is None else "{:.4f}".format(p["volts_mean"]),
            p["raw_top"]))
    lines += ["", "## Interpretation", "",
              "Reg0 before/after must remain 0x91, Reg2 0xC0, and Reg3 0x02 (DRDYM=1). If so, MUX/DRDYM stayed configured during conversion.",
              "Ready requires DOUT/DRDY high then low with CS low; timeout results have no counts and are not valid conversions.",
              "If counts remain ~8388607 while the meter at the ADC pin is 1.0/2.4 V, this is an external input/front-end issue, not a MUX-register issue.",
              "No PASS threshold is applied; this is a diagnostic."]
    (out / "REPORT.md").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))
    print("OUT", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
