#!/usr/bin/env python3
"""Run the ADS1220 low-speed raw-SPI diagnostic on the old ESP32.

The firmware command DIAG_SPI stops the acquisition loop, clocks each ADS1220 at
SENSOR_DIAG_SPI_HALF_PERIOD_US (default 25 us half period = 20 kHz), resets it,
reads the reset defaults, writes two different non-zero configurations, reads
them back byte-for-byte and repeats with MISO sampled after the rising and after
the falling SCLK edge.  This separates a CPHA/clock-edge problem from missing
power, a missing clock, or a disconnected MISO/CS line.

This is a real serial operation; it never fabricates a pass.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.tactile_acq.protocol import ErrorMessage, StatusMessage  # noqa: E402
from tools.tactile_acq.transport import (  # noqa: E402
    DeviceIdentityError,
    SerialSession,
    SerialTransportError,
)

EDGES = ("after_rising", "after_falling")
PATTERN_A = [0x81, 0x80, 0x00, 0x00]
PATTERN_B = [0x91, 0x80, 0x80, 0x00]


def bytes_equal(values, expected):
    return list(values or []) == expected


def hex_bytes(values):
    if not values:
        return "-"
    return " ".join("{:02X}".format(int(v)) for v in values)


def summarize(spi_diag):
    devices = spi_diag.get("devices") or []
    rows = []
    for item in devices:
        for edge_name in EDGES:
            edge = (item.get("edges") or {}).get(edge_name) or {}
            read_a_ok = bool(edge.get("read_a_return")) and bytes_equal(edge.get("read_a"), PATTERN_A)
            read_b_ok = bool(edge.get("read_b_return")) and bytes_equal(edge.get("read_b"), PATTERN_B)
            passed = bool(edge.get("reset_ok")) and read_a_ok and read_b_ok
            rows.append(
                {
                    "adc": item.get("adc"),
                    "cs": item.get("cs"),
                    "miso": item.get("miso"),
                    "idle_miso": item.get("idle_miso"),
                    "after_miso": item.get("after_miso"),
                    "edge": edge_name,
                    "reset_ok": bool(edge.get("reset_ok")),
                    "reset": edge.get("reset"),
                    "write_a_return": bool(edge.get("write_a_return")),
                    "read_a_return": bool(edge.get("read_a_return")),
                    "read_a": edge.get("read_a"),
                    "read_a_ok": read_a_ok,
                    "write_b_return": bool(edge.get("write_b_return")),
                    "read_b_return": bool(edge.get("read_b_return")),
                    "read_b": edge.get("read_b"),
                    "read_b_ok": read_b_ok,
                    "firmware_pass": bool(edge.get("pass")),
                    "pass": passed,
                }
            )
    passing = [row for row in rows if row["pass"]]
    return {
        "rows": rows,
        "passing": passing,
        "any_pass": bool(passing),
    }


def format_text(identity, spi_diag, summary):
    pins = spi_diag.get("pins") or {}
    commands = spi_diag.get("commands") or {}
    lines = [
        "ADS1220 LOW-SPEED RAW SPI DIAGNOSTIC (REAL HARDWARE)",
        "  device        : {}".format(identity.device_id),
        "  firmware      : {}".format(identity.firmware_version),
        "  port          : {}".format(identity.port),
        "  SCLK/MOSI     : GPIO{}/GPIO{}".format(pins.get("sclk"), pins.get("mosi")),
        "  slow half     : {} us ({} kHz)".format(
            spi_diag.get("slow_half_period_us"),
            round(1000.0 / (2 * float(spi_diag.get("slow_half_period_us") or 1)), 1),
        ),
        "  command bytes : RESET=0x{:02X} WREG=0x{:02X} RREG=0x{:02X} START=0x{:02X} RDATA=0x{:02X}".format(
            int(commands.get("reset", 0)),
            int(commands.get("wreg", 0)),
            int(commands.get("rreg", 0)),
            int(commands.get("start", 0)),
            int(commands.get("rdata", 0)),
        ),
        "",
        "  ADC  CS  MISO  idle  after  edge           reset  reset bytes     WrA  readA           A?   WrB  readB           B?   pass",
    ]
    for row in summary["rows"]:
        lines.append(
            "  {adc:>3}  {cs:>2}  {miso:>4}  {idle:>4}  {after:>5}  {edge:<13}  {reset:<5}  {rbytes:<14}  {wa:<4} {ra:<14}  {aok:<4} {wb:<4} {rb:<14}  {bok:<4} {passed}".format(
                adc=row["adc"],
                cs=row["cs"],
                miso=row["miso"],
                idle=row["idle_miso"],
                after=row["after_miso"],
                edge=row["edge"],
                reset="OK" if row["reset_ok"] else "FAIL",
                rbytes=hex_bytes(row["reset"]),
                wa="OK" if row["write_a_return"] else "FAIL",
                ra=hex_bytes(row["read_a"]),
                aok="OK" if row["read_a_ok"] else "FAIL",
                wb="OK" if row["write_b_return"] else "FAIL",
                rb=hex_bytes(row["read_b"]),
                bok="OK" if row["read_b_ok"] else "FAIL",
                passed="PASS" if row["pass"] else "FAIL",
            )
        )
    lines.append("")
    if summary["any_pass"]:
        lines.append("  SPI VERDICT: PASS on at least one ADC/edge")
        for row in summary["passing"]:
            lines.append(
                "    ADC{} (CS={} MISO={}) with MISO sampled {}".format(
                    row["adc"], row["cs"], row["miso"], row["edge"]
                )
            )
    else:
        lines.append("  SPI VERDICT: FAILED - no ADC/edge passed reset + both write/readback patterns")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--timeout", type=float, default=30.0, help="DIAG_SPI response timeout")
    parser.add_argument("--out", help="output JSON path")
    args = parser.parse_args(argv)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.out) if args.out else ROOT / "evidence/sensor" / "spi_diag_{}.json".format(stamp)
    session = None
    try:
        session = SerialSession(args.port, baud=args.baud)
        session.open()
        identity = session.identify(timeout_s=8.0)
        # Stop SAMPLE traffic before the probe (DIAG_SPI also stops it).
        try:
            session.set_streaming(False, timeout_s=2.0)
        except SerialTransportError:
            pass
        request_id = "spi-" + uuid.uuid4().hex[:12]
        session.send_command("DIAG_SPI", request_id=request_id)
        deadline = time.monotonic() + args.timeout
        status = None
        error = None
        while time.monotonic() < deadline:
            for item in session.messages(0.05):
                if isinstance(item, ErrorMessage):
                    error = item
                if isinstance(item, StatusMessage) and item.request_id == request_id:
                    if isinstance(item.raw.get("spi_diag"), dict):
                        status = item
            if status is not None or error is not None:
                break
            time.sleep(0.005)
        if error is not None:
            raise RuntimeError("device returned ERROR {}: {}".format(error.code, error.message))
        if status is None:
            raise RuntimeError("DIAG_SPI response timed out after {:.1f}s".format(args.timeout))
        spi_diag = status.raw["spi_diag"]
        summary = summarize(spi_diag)
        text = format_text(identity, spi_diag, summary)
        print(text)
        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "kind": "REAL_HARDWARE_SERIAL",
            "port": args.port,
            "device_id": identity.device_id,
            "firmware_version": identity.firmware_version,
            "boot_id": identity.boot_id,
            "spi_diag": spi_diag,
            "summary": summary,
            "any_pass": summary["any_pass"],
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2) + "\n")
        print("\nSPI DIAG saved to {}".format(out))
        return 0 if summary["any_pass"] else 1
    except (SerialTransportError, DeviceIdentityError, RuntimeError) as exc:
        print("SPI DIAG FAILED: {}".format(exc), file=sys.stderr)
        return 2
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":
    sys.exit(main())
