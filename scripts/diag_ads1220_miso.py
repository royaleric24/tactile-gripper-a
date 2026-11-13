#!/usr/bin/env python3
"""Determine the ADC2/ADC3 MISO mapping without a nine-way search.

ADC1 is already confirmed on GPIO35.  The firmware command MISO_MAP tests:
  ADC1 / CS21 with MISO35 (confirmation)
  ADC2 / CS22 with MISO34 and MISO26
  ADC3 / CS5  with MISO34 and MISO26
at 20 kHz, using RESET + two non-zero register write/readback patterns.  The
host re-compares the raw bytes and prints the unambiguous mapping.
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

from tools.tactile_acq.transport import (  # noqa: E402
    DeviceIdentityError,
    SerialSession,
    SerialTransportError,
)

PATTERN_A = [0x81, 0x80, 0x00, 0x00]
PATTERN_B = [0x91, 0x80, 0x80, 0x00]


def hex_bytes(values):
    if not values:
        return "-"
    return " ".join("{:02X}".format(int(v)) for v in values)


def item_pass(item):
    result = item.get("result") or {}
    return bool(
        result.get("reset_ok")
        and result.get("read_a_return")
        and list(result.get("read_a") or []) == PATTERN_A
        and result.get("read_b_return")
        and list(result.get("read_b") or []) == PATTERN_B
    )


def infer_mapping(items):
    by_adc = {1: [], 2: [], 3: []}
    for item in items:
        if item_pass(item):
            by_adc.setdefault(int(item.get("adc")), []).append(int(item.get("miso")))
    mapping = {}
    problems = []
    for adc in (1, 2, 3):
        passing = sorted(set(by_adc.get(adc, [])))
        if len(passing) == 1:
            mapping[adc] = passing[0]
        else:
            problems.append(
                "ADC{} has {} passing MISO candidates: {}".format(
                    adc, len(passing), passing or "none"
                )
            )
    if len(mapping) == 3 and len(set(mapping.values())) != 3:
        problems.append("MISO mapping is not one-to-one: {}".format(mapping))
    return mapping, problems


def format_report(items, mapping, problems):
    lines = [
        "ADS1220 MISO MAPPING (20 kHz, real hardware)",
        "  ADC  CS   candidate MISO  reset        RREG A         RREG B         verdict",
    ]
    for item in items:
        result = item.get("result") or {}
        lines.append(
            "  {adc:>3}  {cs:>2}   GPIO{miso:<8}  {reset:<12}  {ra:<14}  {rb:<14}  {verdict}".format(
                adc=item.get("adc"),
                cs=item.get("cs"),
                miso=item.get("miso"),
                reset=hex_bytes(result.get("reset")),
                ra=hex_bytes(result.get("read_a")),
                rb=hex_bytes(result.get("read_b")),
                verdict="PASS" if item_pass(item) else "FAIL",
            )
        )
    lines.append("")
    if mapping and not problems:
        order = [mapping[1], mapping[2], mapping[3]]
        lines.append("  MAPPING CONFIRMED: ADC1=GPIO{}  ADC2=GPIO{}  ADC3=GPIO{}".format(*order))
        lines.append("  pins.miso = {}".format(order))
    else:
        lines.append("  MAPPING INCOMPLETE:")
        for problem in problems:
            lines.append("    - {}".format(problem))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--out-dir", default=str(ROOT / "evidence/sensor"))
    args = parser.parse_args(argv)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    txt_path = out_dir / "miso_map_{}.txt".format(stamp)
    json_path = out_dir / "miso_map_{}.json".format(stamp)
    session = None
    raw_lines = []
    final = None
    try:
        session = SerialSession(args.port, baud=args.baud)
        session.open()
        identity = session.identify(timeout_s=8.0)
        try:
            session.set_streaming(False, timeout_s=2.0)
        except SerialTransportError:
            pass
        request_id = "miso-" + uuid.uuid4().hex[:12]
        session.send_command("MISO_MAP", request_id=request_id)
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            for raw in session.read_available():
                text = raw.decode("utf-8", errors="replace").rstrip("\r")
                if not text:
                    continue
                raw_lines.append(text)
                if "miso_map" in text:
                    try:
                        candidate = json.loads(text)
                    except ValueError:
                        continue
                    if candidate.get("request_id") == request_id:
                        final = candidate
            if final is not None:
                break
            time.sleep(0.01)
        if final is None:
            raise RuntimeError("MISO_MAP response timed out after {:.1f}s".format(args.timeout))
        items = final["miso_map"]["results"]
        mapping, problems = infer_mapping(items)
        print(format_report(items, mapping, problems))
        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "kind": "REAL_HARDWARE_SERIAL",
            "port": args.port,
            "device_id": identity.device_id,
            "firmware_version": identity.firmware_version,
            "boot_id": identity.boot_id,
            "miso_map": final["miso_map"],
            "mapping": {str(k): v for k, v in mapping.items()},
            "problems": problems,
            "complete": bool(mapping and not problems),
            "raw_log": str(txt_path),
        }
        txt_path.write_text("\n".join(raw_lines) + "\n")
        json_path.write_text(json.dumps(payload, indent=2) + "\n")
        print("\nMISO MAP saved to {}".format(json_path))
        return 0 if payload["complete"] else 1
    except (SerialTransportError, DeviceIdentityError, RuntimeError) as exc:
        print("MISO MAP FAILED: {}".format(exc), file=sys.stderr)
        return 2
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":
    sys.exit(main())
