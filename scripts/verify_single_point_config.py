#!/usr/bin/env python3
"""Read back ADS1220 registers and verify the single-point AIN0/AVDD config."""
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

from tools.cup_grasp.single_point import validate_config_report  # noqa: E402
from tools.tactile_acq.protocol import StatusMessage  # noqa: E402
from tools.tactile_acq.transport import SerialSession  # noqa: E402

EVIDENCE = ROOT / "evidence/sensor"


def wait_config_report(session, timeout_s=5.0):
    request_id = "cfg-" + uuid.uuid4().hex[:10]
    session.send_command("VERIFY_CONFIG", request_id=request_id)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for item in session.messages(0.05):
            if isinstance(item, StatusMessage) and item.request_id == request_id:
                report = item.raw.get("config_report")
                if isinstance(report, dict):
                    return report
        time.sleep(0.005)
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/cu.usbserial-EXAMPLE_ESP32")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--skip-set-ref", action="store_true")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    session = SerialSession(args.port, baud=args.baud)
    session.open()
    try:
        identity = session.identify(timeout_s=8.0)
        print("identified {} (firmware {})".format(identity.device_id, identity.firmware_version))
        if not args.skip_set_ref:
            session.send_command("SET_REF", value="AVDD_AVSS", request_id="setref-" + uuid.uuid4().hex[:8])
            time.sleep(0.3)
        report = wait_config_report(session)
        if report is None:
            print("VERIFY_CONFIG response missing", file=sys.stderr)
            return 2
        result = validate_config_report(report)
        print(json.dumps(result, indent=2))
        out = Path(args.out) if args.out else EVIDENCE / ("single_point_config_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"timestamp_utc": datetime.now(timezone.utc).isoformat(),
                                   "device_id": identity.device_id,
                                   "firmware_version": identity.firmware_version,
                                   "config_report": report, "validation": result}, indent=2) + "\n")
        print("saved: {}".format(out))
        print("CONFIG {}".format("PASS" if result["passed"] else "FAIL"))
        return 0 if result["passed"] else 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
