"""Evaluate the firmware DIAG response and save machine-readable evidence."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .protocol import StatusMessage


def evaluate_diag(status: StatusMessage) -> Dict[str, Any]:
    if not status.diag:
        raise ValueError("STATUS message has no diag object")
    devices = status.diag.get("devices") or []
    checks: List[Dict[str, Any]] = []
    device_results: List[Dict[str, Any]] = []
    for expected, item in enumerate(devices, start=1):
        pattern_a = item.get("pattern_a") or {}
        pattern_b = item.get("pattern_b") or {}
        channels = item.get("channels") or []
        channel_values = [entry.get("raw") for entry in channels]
        channel_ok = all(bool(entry.get("ok")) for entry in channels) and len(channels) == 4
        result = {
            "adc": expected,
            "read_ok": bool(item.get("read_ok")),
            "current_config": item.get("current_config"),
            "pattern_a_ok": bool(pattern_a.get("ok")),
            "pattern_b_ok": bool(pattern_b.get("ok")),
            "patterns_differ": bool(item.get("patterns_differ")),
            "pattern_a_written": pattern_a.get("written"),
            "pattern_a_readback": pattern_a.get("readback"),
            "pattern_b_written": pattern_b.get("written"),
            "pattern_b_readback": pattern_b.get("readback"),
            "offset_raw": item.get("offset_raw"),
            "offset_ok": bool(item.get("offset_ok")),
            "avdd_mv": item.get("avdd_mv"),
            "avdd_plausible": bool(2500 <= int(item.get("avdd_mv") or 0) <= 3600),
            "temperature_centi_c": item.get("temperature_centi_c"),
            "temperature_ok": bool(item.get("temperature_ok")),
            "monitor_ok": bool(item.get("monitor_ok")),
            "channels_ok": channel_ok,
            "channel_raw": channel_values,
        }
        result["passed"] = all(
            [
                result["read_ok"],
                result["pattern_a_ok"],
                result["pattern_b_ok"],
                result["patterns_differ"],
                result["monitor_ok"],
                result["channels_ok"],
            ]
        )
        device_results.append(result)
        checks.append({"check": "ADC{} register read".format(expected), "result": "PASSED" if result["read_ok"] else "FAILED"})
        checks.append(
            {
                "check": "ADC{} two distinct config write/readback".format(expected),
                "result": "PASSED" if (result["pattern_a_ok"] and result["pattern_b_ok"] and result["patterns_differ"]) else "FAILED",
            }
        )
        checks.append(
            {
                "check": "ADC{} internal offset + AVDD monitor + temperature conversion".format(expected),
                "result": "PASSED" if result["monitor_ok"] else "FAILED",
            }
        )
        checks.append(
            {
                "check": "ADC{} AIN0..AIN3 conversion".format(expected),
                "result": "PASSED" if result["channels_ok"] else "FAILED",
            }
        )
    sample_ok = bool(status.diag.get("sample_ok"))
    checks.append({"check": "all 12 raw channels read in DIAG scan", "result": "PASSED" if sample_ok and all(item["channels_ok"] for item in device_results) else "FAILED"})
    passed = sample_ok and len(device_results) == 3 and all(item["passed"] for item in device_results)
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "device_id": status.device_id,
        "boot_id": status.boot_id,
        "firmware_version": status.firmware_version,
        "reference_mode": status.reference_mode,
        "overall": "PASSED" if passed else "FAILED",
        "sample_ok": sample_ok,
        "checks": checks,
        "devices": device_results,
        "raw_diag": status.diag,
    }


def format_diag_text(result: Dict[str, Any]) -> str:
    lines = []
    lines.append("ADS1220 HARDWARE DIAGNOSTIC")
    lines.append("  device   : {}".format(result["device_id"]))
    lines.append("  firmware : {}".format(result["firmware_version"]))
    lines.append("  overall  : {}".format(result["overall"]))
    lines.append("")
    lines.append("  ADC  read  patA  patB  differ  offset_raw  offset  avdd_mV  temp_C  monitor  AIN0..3")
    for item in result["devices"]:
        readback = item.get("pattern_a_readback") or []
        lines.append(
            "  {:>3}  {:<4}  {:<4}  {:<4}  {:<6}  {:>10}  {:<6}  {:>7}  {:>6}  {:<7}  {}".format(
                item["adc"],
                "OK" if item["read_ok"] else "FAIL",
                "OK" if item["pattern_a_ok"] else "FAIL",
                "OK" if item["pattern_b_ok"] else "FAIL",
                "YES" if item["patterns_differ"] else "NO",
                "-" if item["offset_raw"] is None else item["offset_raw"],
                "OK" if item["offset_ok"] else "FAIL",
                "-" if item["avdd_mv"] is None else item["avdd_mv"],
                "-" if item["temperature_centi_c"] is None else "{:.2f}".format(item["temperature_centi_c"] / 100.0),
                "OK" if item["monitor_ok"] else "FAIL",
                ", ".join("-" if value is None else str(value) for value in item["channel_raw"]),
            )
        )
        lines.append(
            "       pattern A written={} readback={}".format(item["pattern_a_written"], readback)
        )
        lines.append(
            "       pattern B written={} readback={}".format(item["pattern_b_written"], item["pattern_b_readback"])
        )
    lines.append("")
    for check in result["checks"]:
        lines.append("  [{}] {}".format(check["result"], check["check"]))
    return "\n".join(lines)


def save_diag(result: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
