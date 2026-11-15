#!/usr/bin/env python3
"""Check the V2 firmware JSONL output and refresh the committed fixtures.

The firmware code is compiled against tools/fsr2_sim and asked to emit HELLO and
SAMPLE lines for the FSR-only profile, the production 14-channel electrode
profile (real mapping still missing) and a synthetic fully-mapped electrode
table.  Every line is parsed with the strict reference parser in
tools/fsr2/protocol_v2.py, then copied into tests/fixtures/fsr2 so software tests
can parse the real structure without a board.

The fixtures are SIMULATED.  They demonstrate the wire format, the null/NO_DATA
semantics and the electrode tables; they are not measurements and must not be
presented as hardware evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import run_fsr2_host_tests as host  # noqa: E402
from tools.fsr2 import protocol_v2 as proto  # noqa: E402

FIXTURE_DIR = ROOT / "tests" / "fixtures" / "fsr2"
DEFAULT_EVIDENCE = ROOT / "evidence" / "fsr2" / "frames"

EMITTERS = [
    ("test_fsr2_sampler", "fsr"),
    ("test_fsr2_sampler_electrodes", "electrodes_unmapped"),
    ("test_fsr2_sampler_mapped", "electrodes_mapped"),
]

FIXTURE_NAMES = {
    ("fsr", 0): "hello_fsr_only.json",
    ("fsr", 1): "sample_fsr_only_valid.json",
    ("fsr", 2): "sample_fsr_only_no_adc4.json",
    ("fsr", 3): "status_fsr_only_no_adc4.json",
    ("electrodes_unmapped", 0): "hello_electrodes12_fsr2_unmapped.json",
    ("electrodes_unmapped", 1): "sample_electrodes12_fsr2_unmapped.json",
    ("electrodes_unmapped", 2): "sample_electrodes12_fsr2_fsr_absent.json",
    ("electrodes_unmapped", 3): "status_electrodes12_fsr2_fsr_absent.json",
    ("electrodes_mapped", 0): "hello_electrodes12_mapped_synthetic.json",
    ("electrodes_mapped", 1): "sample_electrodes12_mapped_synthetic.json",
    ("electrodes_mapped", 2): "sample_electrodes12_mapped_adc_absent.json",
    ("electrodes_mapped", 3): "status_electrodes12_mapped_adc_absent.json",
}
RETIRED_FIXTURES = (
    "hello_hybrid.json",
    "sample_hybrid_valid.json",
    "sample_hybrid_no_adc4.json",
)

ELECTRODE_NAMES = ["R%d" % index for index in range(1, 7)] + [
    "C%d" % index for index in range(1, 7)
]


class CheckFailure(Exception):
    pass


def check(condition: bool, message: str) -> None:
    if condition:
        print("PASS %s" % message)
    else:
        print("FAIL %s" % message)
        raise CheckFailure(message)


def emit_lines(binary: Path) -> list[str]:
    result = subprocess.run([str(binary), "--emit"], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise CheckFailure("emitter failed: %s" % (result.stdout[-2000:],))
    return [line for line in result.stdout.splitlines() if line.strip()]


def describe(message) -> str:
    if isinstance(message, proto.SampleFrame):
        return "SAMPLE %s seq=%d" % (message.profile, message.frame_seq)
    return "%s %s" % (message["type"], message["sensor_profile"])


def validate_fsr_only(frames: list) -> None:
    hello, valid, missing = frames
    check(hello["type"] == "HELLO" and hello["sensor_profile"] == "FSR_ONLY", "FSR_ONLY HELLO parses")
    check(hello["channel_count"] == 2, "FSR_ONLY declares two channels")
    check(hello["pins"]["miso"] == [34, 35, 26, 33], "FSR_ONLY HELLO carries the V2 MISO mapping")
    check(hello["pins"]["cs"] == [21, 22, 5, 32], "FSR_ONLY HELLO carries the V2 CS mapping including ADC4=32")
    check(hello["pins"]["sclk"] == 18 and hello["pins"]["mosi"] == 23, "FSR_ONLY HELLO shares SCLK/MOSI")
    check(hello["channel_config"]["status"] == "IMPLEMENTED_UNVERIFIED",
          "channel_config.status is honest about the offline stage")
    check(hello["channel_config"]["matrix_rows"] is None, "FSR_ONLY matrix_rows is null")
    check(hello["fsr_layout"]["adc_id"] == 4, "FSR layout is on ADC4")
    check(hello["fsr_layout"]["divider_resistor_ohm"] == 10000, "FSR layout documents the 10k divider")
    check(hello["fsr_layout"]["validated"] is False, "fsr_layout.validated is false")
    check(hello["reference_mode"] == "AVDD_AVSS", "HELLO uses the AVDD/AVSS reference")

    check(valid.frame_seq == 2 and valid.channel_count == 2, "FSR_ONLY SAMPLE has two channels")
    check(all(valid.valid), "healthy frame marks both FSR channels valid")
    check(valid.fsr_values["FSR_A"] < valid.fsr_values["FSR_B"], "injected divider order is preserved")
    check(all(entry["state"] == "OK" for entry in valid.adc_status),
          "healthy frame reports four OK converters")
    check(valid.frame_period_us == 10000, "frame period is reported once a previous frame exists")

    check(missing.frame_seq == 3, "the missing-converter frame keeps the sequence")
    for channel in (0, 1):
        check(missing.channels[channel] is None, "absent ADC4 channel %d is null, not zero" % (channel,))
        check(missing.valid[channel] is False, "absent ADC4 channel %d is invalid" % (channel,))
        check(missing.channel_flags[channel] == proto.FLAG_NO_DATA,
              "absent ADC4 channel %d carries NO_DATA" % (channel,))
    check(missing.adc_status[3]["state"] != "OK", "absent ADC4 is reported as not OK")


def validate_electrodes_unmapped(frames: list) -> None:
    hello, sample, degraded = frames
    check(hello["sensor_profile"] == "MATRIX_ELECTRODES_12", "electrode HELLO declares the electrode profile")
    check(hello["scan_mode"] == "OFFLINE_ELECTRODE_READ", "electrode profile uses a passive read scan mode")
    check(hello["channel_count"] == 14, "electrode+FSR HELLO declares 14 logical channels")
    check(hello["channel_config"]["matrix_rows"] is None and hello["channel_config"]["matrix_cols"] is None,
          "electrode channel_config keeps matrix_rows/cols null")
    check("matrix_columns" not in hello["pins"], "HELLO has no GPIO matrix column list")
    layout = hello["electrode_layout"]
    check(layout["count"] == 12 and layout["rows"] == 6 and layout["columns"] == 6,
          "electrode_layout describes twelve nodes in a 6x6 grid")
    check(layout["row_bias"] == "PULLDOWN_10K_TO_GND", "row bias is a 10k pulldown to GND")
    check(layout["column_bias"] == "PULLUP_1K_TO_3V3", "column bias is a 1k pullup to 3.3 V")
    check(layout["mapping_status"] == "PENDING_REAL_WIRING",
          "the real R/C to ADC/AIN map is still missing")
    check(layout["validated"] is False, "electrode_layout.validated is false")
    check(layout["gpio_excitation"] is False, "electrode_layout declares no GPIO excitation")
    check(all(entry["adc_id"] is None and entry["adc_input"] is None for entry in layout["channels"]),
          "no electrode invents an ADC/AIN while the harness is unknown")
    kinds = [entry["sensor_kind"] for entry in hello["channel_config"]["channels"]]
    check(kinds == ["ELECTRODE"] * 12 + ["FSR", "FSR"],
          "channel kinds are twelve ELECTRODE then two FSR")

    for index in range(12):
        check(sample.valid[index] is False, "electrode channel %d is invalid" % (index,))
        check(sample.channels[index] is None, "electrode channel %d is null, not zero" % (index,))
        check(sample.channel_flags[index] == proto.FLAG_NO_DATA,
              "electrode channel %d carries NO_DATA" % (index,))
    check(sample.valid[12] and sample.valid[13], "FSR channels stay valid without an electrode map")
    check(sample.fsr_values["FSR_A"] < sample.fsr_values["FSR_B"],
          "FSR divider order is preserved alongside electrodes")

    check(degraded.valid[12] is False and degraded.valid[13] is False,
          "FSR channels go invalid when ADC4 is absent")
    check(degraded.channels[12] is None, "absent ADC4 leaves a null FSR channel")
    check(degraded.adc_status[3]["state"] != "OK", "absent ADC4 is reported as not OK")


def validate_electrodes_mapped(frames: list) -> None:
    hello, sample, degraded = frames
    check(hello["channel_count"] == 12, "synthetic mapped HELLO declares twelve electrodes")
    layout = hello["electrode_layout"]
    check(layout["mapping_status"] == "SIM_SYNTHETIC_MAPPING",
          "the synthetic table is labelled as synthetic, not real wiring")
    mapped = [entry for entry in layout["channels"] if entry["adc_id"] is not None]
    check(len(mapped) == 12, "every synthetic electrode has an ADC/AIN")
    pairs = {(entry["adc_id"], entry["adc_input"]) for entry in mapped}
    check(len(pairs) == 12, "synthetic ADC/AIN pairs are unique")
    check("fsr_layout" not in hello, "the twelve-electrode variant has no FSR layout")
    check([entry["role"] for entry in layout["channels"]] == ["ROW"] * 6 + ["COLUMN"] * 6,
          "electrode roles are six rows then six columns")

    check(all(sample.valid), "every mapped electrode is valid")
    values = sample.electrode_values
    check(sorted(values) == sorted(ELECTRODE_NAMES), "electrode values are addressable by name")
    check(len(set(values.values())) == 12, "each electrode reports a distinct injected voltage")
    check(sample.electrode_values["R1"] < sample.electrode_values["C6"],
          "injected ramp order is preserved")

    for index in range(4):
        check(degraded.valid[index] is False, "electrode on the absent ADC1 is invalid (%d)" % (index,))
    check(degraded.valid[4], "electrodes on other converters stay valid")


VALIDATORS = {
    "fsr": validate_fsr_only,
    "electrodes_unmapped": validate_electrodes_unmapped,
    "electrodes_mapped": validate_electrodes_mapped,
}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE))
    parser.add_argument("--fixture-dir", default=str(FIXTURE_DIR))
    args = parser.parse_args(argv)

    evidence = Path(args.evidence_dir).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    fixture_dir = Path(args.fixture_dir).resolve()
    fixture_dir.mkdir(parents=True, exist_ok=True)
    for name in RETIRED_FIXTURES:
        retired = fixture_dir / name
        if retired.is_file():
            retired.unlink()

    cxx = host.find_cxx()
    binaries: dict[str, Path] = {}
    for name, _key in EMITTERS:
        source = "tools/fsr2_sim/%s.cpp" % (name,)
        binary = evidence / name
        log = evidence / (name + ".compile.log")
        if not host.compile_test(cxx, source, binary, log):
            print("cannot build emitter %s" % (name,))
            return 1
        binaries[name] = binary

    summary = {"kind": "HOST_SIMULATION_NOT_HARDWARE", "profiles": [], "fixtures": {}}
    try:
        for name, key in EMITTERS:
            lines = emit_lines(binaries[name])
            check(len(lines) == 4, "%s emitted HELLO, two SAMPLE frames and STATUS" % (key,))
            parsed = [proto.parse_message(line) for line in lines]
            types = [describe(frame) for frame in parsed]
            print("  frames:", "; ".join(types))
            VALIDATORS[key](parsed[:3])
            status = parsed[3]
            check(status["type"] == "STATUS" and status["request_id"] == "fixture-status-1"
                  and status["last_frame_seq"] == parsed[2].frame_seq
                  and status["adc_status"] == parsed[2].adc_status,
                  "%s STATUS matches sample identity and ADC faults" % key)

            for index, line in enumerate(lines):
                fixture_name = FIXTURE_NAMES[(key, index)]
                (fixture_dir / fixture_name).write_text(line.strip() + "\n")
                summary["fixtures"][fixture_name] = hashlib.sha256(
                    (line.strip() + "\n").encode("utf-8")
                ).hexdigest()
            summary["profiles"].append({"case": key, "frames": types, "result": "PASS"})
    except CheckFailure as failure:
        summary["result"] = "FAIL"
        summary["failure"] = str(failure)
        (evidence / "frames_check.json").write_text(json.dumps(summary, indent=2) + "\n")
        print("frame check: FAIL")
        return 1

    for name, _key in EMITTERS:
        first = emit_lines(binaries[name])
        second = emit_lines(binaries[name])
        check(first == second, "%s emitter is deterministic across runs" % (name,))

    summary["result"] = "PASS"
    summary["note"] = (
        "Emitted by this firmware compiled against the four-device host simulation. Fixture data "
        "for parser tests; not hardware measurements. The mapped electrodes use a SYNTHETIC table, "
        "not the real harness record (which is still missing)."
    )
    (evidence / "frames_check.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("frame check: PASS")
    print("fixtures: %s" % (fixture_dir,))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
