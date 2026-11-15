#!/usr/bin/env python3
"""Minimal, dependency-free parser example for the software group.

Reads the hardware group's JSONL from stdin (for example a saved
``raw_frames.jsonl``) and prints one validated 12-channel record per SAMPLE.
This file intentionally contains no imports from the hardware package so it can
be copied into ``src/tactile_gripper/`` after interface review.

It never turns a raw ADC count into force, resistance, opening or a matrix
coordinate.  Invalid channels stay ``None``.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional

PROTOCOL_VERSION = 1
CHANNEL_COUNT = 12
ADC_MIN = -8388608
ADC_MAX = 8388607
REFERENCE_MODES = {"INTERNAL_2V048", "AVDD_AVSS"}


class InvalidFrame(ValueError):
    pass


def parse_sample(line: bytes) -> Dict[str, Any]:
    message = json.loads(line)
    if message.get("protocol_version") != PROTOCOL_VERSION:
        raise InvalidFrame("unsupported protocol_version")
    if message.get("type") != "SAMPLE":
        raise InvalidFrame("not a SAMPLE")
    raw = message.get("raw_adc")
    valid = message.get("valid")
    timestamps = message.get("sample_timestamp_us")
    if not isinstance(raw, list) or not isinstance(valid, list) or not isinstance(timestamps, list):
        raise InvalidFrame("raw_adc/valid/sample_timestamp_us must be arrays")
    if len(raw) != CHANNEL_COUNT or len(valid) != CHANNEL_COUNT or len(timestamps) != CHANNEL_COUNT:
        raise InvalidFrame("expected 12 channels")
    for index in range(CHANNEL_COUNT):
        if type(valid[index]) is not bool:
            raise InvalidFrame("valid[%d] must be boolean" % index)
        if valid[index]:
            value = raw[index]
            if type(value) is not int or not ADC_MIN <= value <= ADC_MAX:
                raise InvalidFrame("valid channel %d is not a signed 24-bit integer" % index)
        elif raw[index] is not None:
            raise InvalidFrame("invalid channel %d must be null, not a fabricated value" % index)
    if message.get("reference_mode") not in REFERENCE_MODES:
        raise InvalidFrame("unknown reference_mode")
    if not isinstance(message.get("frame_seq"), int) or message["frame_seq"] < 0:
        raise InvalidFrame("invalid frame_seq")
    return {
        "device_id": message.get("device_id"),
        "boot_id": message.get("boot_id"),
        "frame_seq": message["frame_seq"],
        "device_timestamp_us": message.get("timestamp_us"),
        "raw_adc": raw,
        "valid": valid,
        "sample_timestamp_us": timestamps,
        "channel_flags": message.get("channel_flags"),
        "reference_mode": message["reference_mode"],
        "effective_frame_rate_hz": message.get("effective_frame_rate_hz"),
        "adc_status": message.get("adc_status"),
    }


def main() -> int:
    count = 0
    for line in sys.stdin.buffer:
        line = line.strip()
        if not line:
            continue
        try:
            record = parse_sample(line)
        except (ValueError, KeyError) as exc:
            print("REJECT: %s" % exc, file=sys.stderr)
            continue
        count += 1
        if count <= 3:
            print(json.dumps(record, ensure_ascii=False))
    print("parsed %d SAMPLE frames" % count, file=sys.stderr)
    return 0 if count else 2


if __name__ == "__main__":
    sys.exit(main())
