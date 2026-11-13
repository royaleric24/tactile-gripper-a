"""Single-point contact/release validation summary and register check."""
from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Sequence

MIN_SNR = 3.0
MAX_SATURATION = 0.05
VREF_ENCODINGS = {
    0: ("INTERNAL_2V048", 0x00),
    1: ("EXTERNAL_REFP0_REFN0", 0x40),
    2: ("EXTERNAL_REFP1_REFN1", 0x80),
    3: ("AVDD_AVSS", 0xC0),
}
EXPECTED_AVDD_REGISTERS = (0x81, 0x80, 0xC0, 0x00)
SCAN_MUX_VALUES = (0x81, 0x91, 0xA1, 0xB1)
MUX_NAMES = {0x81: "AIN0_AVSS", 0x91: "AIN1_AVSS", 0xA1: "AIN2_AVSS", 0xB1: "AIN3_AVSS"}


def _channel_map_evidence(channel_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    channels = (channel_config or {}).get("channels") or []
    expected = []
    for channel in range(12):
        expected.append({
            "channel_id": channel,
            "mux_channel": 8 + channel % 4,
            "adc_input": channel % 4,
            "ads1220_id": channel // 4 + 1,
        })
    issues = []
    if len(channels) != 12:
        issues.append("channel_config must contain 12 channels")
    for index, item in enumerate(channels[:12]):
        want = expected[index]
        for key in ("channel_id", "mux_channel", "adc_input", "ads1220_id"):
            if item.get(key) != want[key]:
                issues.append("channel {} {}={} expected {}".format(index, key, item.get(key), want[key]))
    return {"passed": not issues, "issues": issues, "expected": expected,
            "actual": channels[:12]}


def _frame_evidence(frame: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    frame = frame or {}
    valid0 = frame.get("valid0") is True
    raw0 = frame.get("raw0")
    frame_seq = frame.get("frame_seq")
    sample_us0 = frame.get("sample_timestamp_us0")
    issues = []
    if not valid0:
        issues.append("ch0 valid=false")
    if type(raw0) is not int:
        issues.append("ch0 raw value missing")
    if type(frame_seq) is not int or frame_seq <= 0:
        issues.append("frame_seq missing/zero")
    if type(sample_us0) is not int or sample_us0 <= 0:
        issues.append("ch0 sample_timestamp_us missing/zero")
    return {"passed": not issues, "issues": issues, "frame": frame}


def validate_config_report(report: Dict[str, Any], expected: Sequence[int] = EXPECTED_AVDD_REGISTERS,
                           *, mode: str = "scan", channel_config: Optional[Dict[str, Any]] = None,
                           frame: Optional[Dict[str, Any]] = None,
                           require_scan_evidence: bool = True) -> Dict[str, Any]:
    """Validate actual ADS1220 readback.

    scan: Reg0 must be one of the four legal AIN0..AIN3 single-ended MUX values;
    fixed: Reg0 must be exactly AIN0.  Scan mode additionally requires the
    reported channel map and a fresh ch0 valid frame, so accepting 0xB1 alone is
    never a PASS.
    """
    devices = (report or {}).get("devices") or []
    if mode not in ("scan", "fixed"):
        raise ValueError("mode must be scan or fixed")
    checks = []
    ok = len(devices) == 3
    for item in devices:
        registers = list(item.get("registers") or [])
        reg0 = registers[0] if len(registers) == 4 else None
        if mode == "scan":
            reg0_ok = reg0 in SCAN_MUX_VALUES
        else:
            reg0_ok = reg0 == 0x81
        device_ok = (
            bool(item.get("read_ok"))
            and len(registers) == 4
            and reg0_ok
            and registers[1:] == list(expected[1:])
            and item.get("mux") == ((reg0 >> 4) & 0x0F if reg0 is not None else None)
            and item.get("gain_code") == 0
            and item.get("pga_bypass") is True
            and item.get("vref_code") == 3
            and item.get("vref") == "AVDD_AVSS"
            and item.get("psw") == 0
            and item.get("idac_code") == 0
        )
        ok = ok and device_ok
        checks.append({
            "id": item.get("id"),
            "read_ok": item.get("read_ok"),
            "registers": registers,
            "reg0": reg0,
            "reg0_mode": "scan_legal" if reg0 in SCAN_MUX_VALUES else "illegal",
            "mux_name": MUX_NAMES.get(reg0, "UNKNOWN"),
            "expected_non_mux_registers": list(expected[1:]),
            "mux": item.get("mux"),
            "gain_code": item.get("gain_code"),
            "pga_bypass": item.get("pga_bypass"),
            "vref_code": item.get("vref_code"),
            "vref": item.get("vref"),
            "psw": item.get("psw"),
            "idac_code": item.get("idac_code"),
            "passed": device_ok,
        })
    channel_evidence = _channel_map_evidence(channel_config) if mode == "scan" else {
        "passed": True, "issues": [], "note": "fixed mode uses channel 0 only"}
    frame_evidence = _frame_evidence(frame) if mode == "scan" else {
        "passed": True, "issues": [], "note": "fixed mode evidence not evaluated"}
    evidence_ok = channel_evidence["passed"] and frame_evidence["passed"]
    if mode == "scan" and require_scan_evidence and not evidence_ok:
        ok = False
    return {
        "passed": ok,
        "mode": mode,
        "expected_non_mux_registers": list(expected[1:]),
        "devices": checks,
        "channel_evidence": channel_evidence,
        "frame_evidence": frame_evidence,
        "note": ("Scan mode accepts AIN0..AIN3 residue but requires channel map and fresh ch0 frame; "
                 "fixed mode requires AIN0 and is not inferred from a scan."),
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
