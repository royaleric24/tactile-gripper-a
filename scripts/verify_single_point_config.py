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
from tools.tactile_acq.protocol import ErrorMessage, SampleFrame, StatusMessage, parse_message  # noqa: E402
from tools.tactile_acq.transport import SerialSession  # noqa: E402

EVIDENCE = ROOT / "evidence/sensor"


class ConfigResponseError(RuntimeError):
    def __init__(self, message, raw_lines=None, parse_errors=None):
        super().__init__(message)
        self.raw_lines = list(raw_lines or [])
        self.parse_errors = list(parse_errors or [])


def wait_sample(session, timeout_s=3.0):
    """Return one fresh SAMPLE frame; interleaved STATUS/ERROR lines are skipped."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for line in session.read_available():
            try:
                item = parse_message(line)
            except Exception:
                continue
            if isinstance(item, SampleFrame) and len(item.raw_adc) == 12:
                return item
        time.sleep(0.003)
    return None


def frame_evidence(frame):
    return {
        "frame_seq": frame.frame_seq,
        "valid0": bool(frame.valid[0]) if len(frame.valid) else False,
        "raw0": frame.raw_adc[0] if len(frame.raw_adc) else None,
        "sample_timestamp_us0": frame.sample_timestamp_us[0] if len(frame.sample_timestamp_us) else None,
        "reference_mode": frame.reference_mode,
    }


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
        if not identity.streaming:
            session.set_streaming(True)
            time.sleep(0.2)
        frame = wait_sample(session)
        if frame is None:
            print("NO SAMPLE FRAME: cannot verify ch0 conversion mapping", file=sys.stderr)
            return 2
        channel_config = identity.raw.get("channel_config")
        print("ch0 map {} frame_seq={} raw0={} valid0={}".format(
            (channel_config or {}).get("channels", [{}])[0].get("mux_channel"),
            frame.frame_seq, frame.raw_adc[0], frame.valid[0]))
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
        result = validate_config_report(report, mode="scan", channel_config=channel_config,
                                        frame=frame_evidence(frame), require_scan_evidence=True)
        print(json.dumps(result, indent=2))
        out = Path(args.out) if args.out else EVIDENCE / ("single_point_config_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"timestamp_utc": datetime.now(timezone.utc).isoformat(),
                                   "device_id": identity.device_id,
                                   "firmware_version": identity.firmware_version,
                                   "set_ref": setref, "config_report": report,
                                   "channel_config": channel_config,
                                   "frame_evidence": frame_evidence(frame),
                                   "diagnostics": diagnostics, "validation": result}, indent=2) + "\n")
        print("saved: {}".format(out))
        if result["passed"]:
            print("SCAN_MODE_PASS (fixed mode not evaluated; ch0 map and fresh frame checked)")
        else:
            print("SCAN_MODE_FAIL")
        return 0 if result["passed"] else 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
