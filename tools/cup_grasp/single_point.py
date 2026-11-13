"""Single-point contact/release validation summary (pure analysis)."""
from __future__ import annotations

import statistics
from typing import Any, Dict, List, Sequence

MIN_SNR = 3.0
MAX_SATURATION = 0.05


def summarize_single_point(records: Sequence[Dict[str, Any]], cycles: Sequence[Dict[str, int]]) -> Dict[str, Any]:
    rows = sorted(records, key=lambda item: item["host_monotonic_ns"])
    def window(start, end):
        return [r for r in rows if start <= r["host_monotonic_ns"] < end and r.get("delta") is not None]
    results = []
    for index, cycle in enumerate(cycles, start=1):
        press = cycle["press_ns"]; release = cycle["release_ns"]
        baseline = window(press - 1_500_000_000, press)
        contact = window(press, release)
        post = window(release, release + 1_500_000_000)
        base_deltas = [r["delta"] for r in baseline if r["delta"] is not None]
        contact_deltas = [r["delta"] for r in contact if r["delta"] is not None]
        post_deltas = [r["delta"] for r in post if r["delta"] is not None]
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
        passed = (response is not None and noise > 0 and snr is not None and snr >= MIN_SNR
                  and saturation is not None and saturation <= MAX_SATURATION)
        results.append({
            "cycle": index,
            "baseline_samples": len(baseline),
            "contact_samples": len(contact),
            "noise_counts": noise,
            "response_mean_counts": response,
            "snr": snr,
            "saturation_fraction": saturation,
            "latency_ms": latency_ms,
            "recovery_mean_counts": recovery,
            "passed": passed,
        })
    passed_cycles = sum(1 for item in results if item["passed"])
    return {
        "cycles": results,
        "passed_cycles": passed_cycles,
        "total_cycles": len(results),
        "pass": passed_cycles >= max(4, len(results) - 1) if len(results) >= 5 else False,
        "criteria": {"min_snr": MIN_SNR, "max_saturation_fraction": MAX_SATURATION,
                     "note": "ADC counts only; no pressure/force calibration."},
    }
