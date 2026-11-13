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
from tools.tactile_acq.protocol import ErrorMessage, StatusMessage, parse_message  # noqa: E402
from tools.tactile_acq.transport import SerialSession  # noqa: E402

EVIDENCE = ROOT / "evidence/sensor"


class ConfigResponseError(RuntimeError):
    def __init__(self, message, raw_lines=None, parse_errors=None):
        super().__init__(message)
        self.raw_lines = list(raw_lines or [])
        self.parse_errors = list(parse_errors or [])


def _pump(session, raw_lines, parse_errors, parsed):
    for line in session.read_available():
        text = line.decode("utf-8", errors="replace")
        raw_lines.append(text)
        try:
            parsed.append(parse_message(line))
        except Exception as exc:
            parse_errors.append("{}: {}".format(type(exc).__name__, exc))


def _wait_for(session, request_id, timeout_s, want_config=False):
    raw_lines = []
    parse_errors = []
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        parsed = []
        _pump(session, raw_lines, parse_errors, parsed)
        for item in parsed:
            if isinstance(item, ErrorMessage) and item.request_id == request_id:
                raise ConfigResponseError("device ERROR {}: {}".format(item.code, item.message),
                                          raw_lines, parse_errors)
            if isinstance(item, StatusMessage) and item.request_id == request_id:
                if want_config and not isinstance(item.raw.get("config_report"), dict):
                    continue
                return item, raw_lines, parse_errors
        time.sleep(0.005)
    return None, raw_lines, parse_errors


def wait_config_report(session, timeout_s=8.0, attempts=2):
    """Send VERIFY_CONFIG, tolerate interleaved SAMPLE lines, return report + raw diagnostics."""
    raw_lines = []
    parse_errors = []
    for attempt in range(attempts):
        request_id = "cfg-" + uuid.uuid4().hex[:10]
        session.send_command("VERIFY_CONFIG", request_id=request_id)
        item, lines, errors = _wait_for(session, request_id, timeout_s / attempts, want_config=True)
        raw_lines.extend(lines)
        parse_errors.extend(errors)
        if item is not None:
            return item.raw["config_report"], {"request_id": request_id, "raw_lines": raw_lines,
                                               "parse_errors": parse_errors, "attempts": attempt + 1}
    raise ConfigResponseError("VERIFY_CONFIG response missing", raw_lines, parse_errors)


def wait_set_ref(session, timeout_s=4.0):
    request_id = "setref-" + uuid.uuid4().hex[:8]
    session.send_command("SET_REF", value="AVDD_AVSS", request_id=request_id)
    item, lines, errors = _wait_for(session, request_id, timeout_s)
    if item is None:
        raise ConfigResponseError("SET_REF response missing", lines, errors)
    return item, {"request_id": request_id, "raw_lines": lines, "parse_errors": errors}


def print_diagnostics(error):
    print("DIAGNOSTIC: {}".format(error), file=sys.stderr)
    if getattr(error, "parse_errors", None):
        print("PARSE ERRORS:", file=sys.stderr)
        for item in error.parse_errors[-20:]:
            print("  {}".format(item), file=sys.stderr)
    if getattr(error, "raw_lines", None):
        print("RAW LINES (last 40):", file=sys.stderr)
        for line in error.raw_lines[-40:]:
            print("  {}".format(line), file=sys.stderr)


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
        setref = None
        if not args.skip_set_ref:
            try:
                status, setref = wait_set_ref(session)
            except ConfigResponseError as exc:
                print_diagnostics(exc)
                return 2
            print("SET_REF -> reference_mode={}".format(status.reference_mode))
        try:
            report, diagnostics = wait_config_report(session)
        except ConfigResponseError as exc:
            print_diagnostics(exc)
            return 2
        result = validate_config_report(report)
        print(json.dumps(result, indent=2))
        out = Path(args.out) if args.out else EVIDENCE / ("single_point_config_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"timestamp_utc": datetime.now(timezone.utc).isoformat(),
                                   "device_id": identity.device_id,
                                   "firmware_version": identity.firmware_version,
                                   "set_ref": setref, "config_report": report,
                                   "diagnostics": diagnostics, "validation": result}, indent=2) + "\n")
        print("saved: {}".format(out))
        print("CONFIG {}".format("PASS" if result["passed"] else "FAIL"))
        return 0 if result["passed"] else 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
