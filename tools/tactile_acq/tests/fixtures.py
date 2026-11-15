"""Deterministic protocol fixtures for tests.  Not real sensor data."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


def make_adc_status(states: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    states = list(states or ["OK", "OK", "OK"])
    return [
        {
            "id": index + 1,
            "state": state,
            "code": 0 if state == "OK" else 1,
            "consecutive_errors": 0,
            "total_errors": 0,
            "recovered": 0,
            "last_error": None,
        }
        for index, state in enumerate(states)
    ]


def make_sample(
    seq: int = 0,
    timestamp_us: int = 1000000,
    values: Optional[Sequence[Optional[int]]] = None,
    valid: Optional[Sequence[bool]] = None,
    flags: Optional[Sequence[int]] = None,
    reference_mode: str = "INTERNAL_2V048",
    rate: float = 47.5,
    boot_id: str = "tactile-esp32-01-00000001",
    adc_states: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    if values is None:
        values = [1000 * index - 5000 for index in range(12)]
    if valid is None:
        valid = [True] * 12
    if flags is None:
        flags = [0 if item else 0x20 for item in valid]
    values = list(values)
    valid = list(valid)
    flags = list(flags)
    timestamps = [timestamp_us + index * 10 if valid[index] else None for index in range(12)]
    return {
        "protocol_version": 1,
        "type": "SAMPLE",
        "device_id": "tactile-esp32-01",
        "boot_id": boot_id,
        "firmware_version": "tactile-sense-0.1.0",
        "frame_seq": seq,
        "timestamp_us": timestamp_us,
        "mcu_time_us": timestamp_us,
        "frame_period_us": 21000,
        "channel_ids": list(range(12)),
        "channel_count": 12,
        "raw_adc": values,
        "channels": values,
        "valid": valid,
        "valid_mask": valid,
        "sample_timestamp_us": timestamps,
        "channel_flags": flags,
        "reference_mode": reference_mode,
        "effective_frame_rate_hz": rate,
        "adc_status": make_adc_status(adc_states),
    }
