#!/usr/bin/env python3
"""Old-ESP32-only raw serial diagnostic for SET_REF/VERIFY_CONFIG.

Prints every raw line and parse result for ~6 s. No S3, no gripper, no motion.
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.tactile_acq.protocol import ErrorMessage, StatusMessage, parse_message  # noqa: E402
from tools.tactile_acq.transport import SerialSession  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/cu.usbserial-EXAMPLE_ESP32")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--no-set-ref", action="store_true")
    args = parser.parse_args()
    session = SerialSession(args.port, baud=args.baud)
    lines = []
    session.open()
    try:
        identity = session.identify(timeout_s=8.0)
        print("identified {} firmware={}".format(identity.device_id, identity.firmware_version))
        if not args.no_set_ref:
            session.send_command("SET_REF", value="AVDD_AVSS", request_id="diag-setref-" + uuid.uuid4().hex[:8])
            print("TX SET_REF AVDD_AVSS")
        session.send_command("VERIFY_CONFIG", request_id="diag-cfg-" + uuid.uuid4().hex[:8])
        print("TX VERIFY_CONFIG")
        session.send_command("PING", request_id="diag-ping-" + uuid.uuid4().hex[:8])
        print("TX PING")
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            for raw in session.read_available():
                text = raw.decode("utf-8", errors="replace")
                lines.append(text)
                try:
                    item = parse_message(raw)
                    kind = type(item).__name__
                    rid = getattr(item, "request_id", None)
                    print("RAW {} | PARSED {} request_id={}".format(text, kind, rid))
                    if isinstance(item, ErrorMessage):
                        print("  ERROR {}: {}".format(item.code, item.message))
                    if isinstance(item, StatusMessage) and item.raw.get("config_report"):
                        print("  CONFIG_REPORT {}".format(item.raw["config_report"]))
                except Exception as exc:
                    print("RAW {} | PARSE_ERROR {}: {}".format(text, type(exc).__name__, exc))
            time.sleep(0.003)
    finally:
        session.close()
    out = ROOT / "evidence/sensor" / ("verify_config_raw_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".log")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print("RAW LOG: {}".format(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
