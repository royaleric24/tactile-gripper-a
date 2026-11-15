#!/usr/bin/env python3
"""Hold ADC1's CS/SCLK/MOSI at three static levels, then probe ADC1 only.

The firmware command GPIO_DIAG stops acquisition, forces ADC2/ADC3 CS high and
holds ADC1 at:
  A: CS1=HIGH, SCLK=LOW,  MOSI=LOW
  B: CS1=LOW,  SCLK=LOW,  MOSI=LOW
  C: CS1=LOW,  SCLK=HIGH, MOSI=HIGH
for 5 s per state, repeated for --cycles.  It prints each state over serial so a
multimeter can be used on the ADC1 module pads.  After the states it restores
CS high / SCLK low and performs a minimal ADC1-only RESET + two-pattern register
write/readback at 20 kHz, reporting the raw bytes.

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


def true_pass(result):
    return bool(
        result.get("reset_ok")
        and result.get("read_a_return")
        and list(result.get("read_a") or []) == PATTERN_A
        and result.get("read_b_return")
        and list(result.get("read_b") or []) == PATTERN_B
    )


def format_result(payload):
    item = payload["adc1_min"]
    result = item["result"]
    pins = item.get("pins", {})
    lines = [
        "",
        "ADC1 MINIMAL REGISTER TEST (20 kHz, MISO sampled after rising edge)",
        "  CS/SCLK/MOSI/MISO : GPIO{}/GPIO{}/GPIO{}/GPIO{}".format(
            pins.get("cs"), pins.get("sclk"), pins.get("mosi"), pins.get("miso")
        ),
        "  cycles            : {}".format(item.get("cycles")),
        "  RESET             : 0x06 -> reset bytes [{}]".format(hex_bytes(result.get("reset"))),
        "  WREG A            : 0x43 [{}]".format(hex_bytes(PATTERN_A)),
        "  RREG A readback   : [{}]  {}".format(
            hex_bytes(result.get("read_a")), "OK" if list(result.get("read_a") or []) == PATTERN_A else "MISMATCH"
        ),
        "  WREG B            : 0x43 [{}]".format(hex_bytes(PATTERN_B)),
        "  RREG B readback   : [{}]  {}".format(
            hex_bytes(result.get("read_b")), "OK" if list(result.get("read_b") or []) == PATTERN_B else "MISMATCH"
        ),
        "  verdict           : {}".format("PASS" if true_pass(result) else "FAIL"),
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--cycles", type=int, default=3, help="A/B/C cycles; each cycle is 15 s")
    parser.add_argument("--timeout", type=float, default=0.0, help="override total response timeout")
    parser.add_argument("--out-dir", default=str(ROOT / "evidence/sensor"))
    args = parser.parse_args(argv)
    if not 1 <= args.cycles <= 100:
        parser.error("--cycles must be 1..100")
    timeout = args.timeout or (args.cycles * 15.0 + 20.0)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    txt_path = out_dir / "gpio_diag_{}.txt".format(stamp)
    json_path = out_dir / "gpio_diag_{}.json".format(stamp)
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
        request_id = "gpio-" + uuid.uuid4().hex[:12]
        print("GPIO_DIAG on {} ({}), cycles={} ({} s of static states)".format(
            identity.device_id, identity.port, args.cycles, args.cycles * 15), flush=True)
        print("Measure ADC1 module pads during states A/B/C; expected 0 V or 3.3 V as printed.", flush=True)
        session.send_command("GPIO_DIAG", target_id=args.cycles, request_id=request_id)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for raw in session.read_available():
                text = raw.decode("utf-8", errors="replace").rstrip("\r")
                if not text:
                    continue
                raw_lines.append(text)
                print(text, flush=True)
                if "adc1_min" in text:
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
            raise RuntimeError("no ADC1 minimum-test response within {:.0f}s".format(timeout))
        result = final["adc1_min"]["result"]
        print(format_result(final), flush=True)
        txt_path.write_text("\n".join(raw_lines) + "\n")
        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "kind": "REAL_HARDWARE_SERIAL",
            "port": args.port,
            "device_id": identity.device_id,
            "firmware_version": identity.firmware_version,
            "boot_id": identity.boot_id,
            "cycles": args.cycles,
            "states": [
                line for line in raw_lines if line.startswith("GPIO_DIAG state=")
            ],
            "adc1_min": final["adc1_min"],
            "pass": true_pass(result),
            "raw_log": str(txt_path),
        }
        json_path.write_text(json.dumps(payload, indent=2) + "\n")
        print("\nGPIO DIAG saved to {}".format(json_path), flush=True)
        return 0 if payload["pass"] else 1
    except (SerialTransportError, DeviceIdentityError, RuntimeError) as exc:
        print("GPIO DIAG FAILED: {}".format(exc), file=sys.stderr)
        return 2
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":
    sys.exit(main())
