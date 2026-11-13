"""Single-point contact/release validation summary and register check."""
from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Sequence

MIN_SNR = 3.0
MAX_SATURATION = 0.05
EXPECTED_AVDD_REGISTERS = (0x81, 0x80, 0x80, 0x00)


def validate_config_report(report: Dict[str, Any], expected: Sequence[int] = EXPECTED_AVDD_REGISTERS) -> Dict[str, Any]:
    """Validate raw ADS1220 register readback for AIN0/AVDD/gain1/PGA-bypass."""
    devices = (report or {}).get("devices") or []
    checks = []
    ok = len(devices) == 3
    for item in devices:
        registers = item.get("registers") or []
        device_ok = (
            bool(item.get("read_ok"))
            and list(registers) == list(expected)
            and item.get("mux") == 8
            and item.get("gain_code") == 0
            and item.get("pga_bypass") is True
            and item.get("vref_code") == 2
            and item.get("psw") == 0
            and item.get("idac_code") == 0
        )
        ok = ok and device_ok
        checks.append({
            "id": item.get("id"),
            "read_ok": item.get("read_ok"),
            "registers": registers,
            "expected_registers": list(expected),
            "mux": item.get("mux"),
            "gain_code": item.get("gain_code"),
            "pga_bypass": item.get("pga_bypass"),
            "vref_code": item.get("vref_code"),
            "vref": item.get("vref"),
            "psw": item.get("psw"),
            "idac_code": item.get("idac_code"),
            "passed": device_ok,
        })
    return {
        "passed": ok,
        "expected_registers": list(expected),
        "devices": checks,
        "note": "VREF[1:0]=10 (0x80) is AVDD-AVSS; 0x40 is external REF0 and 0xC0 is external REF1.",
    }


def _raw_mean(rows):
    values = [r["raw"] for r in rows if r.get("raw") is not None]
    return statistics.mean(values) if values else None


def summarize_single_point(records: Sequence[Dict[str, Any]], cycles: Sequence[Dict[str, int]],
                           avdd_mv: Optional[float] = None, r_ref_ohm: Optional[float] = None,
                           r_row_ohm: Optional[float] = None, v_exc: float = 3.3) -> Dict[str, Any]:
    rows = sorted(records, key=lambda item: item["host_monotonic_ns"])
    def window(start, end):
        return [r for r in rows if start <= r["host_monotonic_ns"] < end]
    results = []
    for index, cycle in enumerate(cycles, start=1):
        press = cycle["press_ns"]; release = cycle["release_ns"]
        baseline = window(press - 1_500_000_000, press)
        contact = window(press, release)
        post = window(release, release + 1_500_000_000)
        base_deltas = [r["delta"] for r in baseline if r.get("delta") is not None]
        contact_deltas = [r["delta"] for r in contact if r.get("delta") is not None]
        post_deltas = [r["delta"] for r in post if r.get("delta") is not None]
        noise = statistics.pstdev(base_deltas) if len(base_deltas) >= 2 else 0.0
        response = statistics.mean(contact_deltas) if contact_deltas else None
        snr = (response / noise) if response is not None and noise > 0 else None
        saturation = (sum(1 for r in contact if r.get("saturated")) / len(contact)) if contact else None
        recovery = statistics.mean(post_deltas) if post_deltas else None
        latency_ms = None
        threshold = max(MIN_SNR * noise, 1.0)
        for r in contact:
            if r.get("delta") is not None and r["delta"] > threshold:
                latency_ms = (r["host_monotonic_ns"] - press) / 1e6
                break
        base_raw = _raw_mean(baseline)
        contact_raw = _raw_mean(contact)
        approx_volts = (contact_raw / 8388607.0 * avdd_mv / 1000.0) if contact_raw is not None and avdd_mv else None
        inferred_r = None
        if approx_volts and approx_volts > 0 and r_ref_ohm and r_row_ohm is not None:
            inferred_r = r_ref_ohm * (v_exc - approx_volts) / approx_volts - r_row_ohm
        passed = (response is not None and noise > 0 and snr is not None and snr >= MIN_SNR
                  and saturation is not None and saturation <= MAX_SATURATION)
        results.append({
            "cycle": index,
            "baseline_samples": len(baseline),
            "contact_samples": len(contact),
            "noise_counts": noise,
            "baseline_raw_mean": base_raw,
            "contact_raw_mean": contact_raw,
            "response_mean_counts": response,
            "snr": snr,
            "saturation_fraction": saturation,
            "latency_ms": latency_ms,
            "recovery_mean_counts": recovery,
            "approx_contact_volts": approx_volts,
            "inferred_r_cell_ohm": inferred_r,
            "passed": passed,
        })
    passed_cycles = sum(1 for item in results if item["passed"])
    return {
        "cycles": results,
        "passed_cycles": passed_cycles,
        "total_cycles": len(results),
        "pass": passed_cycles >= max(4, len(results) - 1) if len(results) >= 5 else False,
        "criteria": {"min_snr": MIN_SNR, "max_saturation_fraction": MAX_SATURATION,
                     "note": "ADC counts only; inferred resistance assumes an ideal 3.3 V/1k/10k divider."},
        "conversion": {"avdd_mv": avdd_mv, "r_ref_ohm": r_ref_ohm, "r_row_ohm": r_row_ohm,
                       "v_exc": v_exc},
    }
