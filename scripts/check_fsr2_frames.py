#!/usr/bin/env python3
"""Check the V2 firmware JSONL output and refresh the committed fixtures.

The firmware code is compiled against tools/fsr2_sim and asked to emit HELLO and
SAMPLE lines for both sensor profiles.  Every line is parsed with the strict
reference parser in tools/fsr2/protocol_v2.py, then copied into
tests/fixtures/fsr2 so software-group tests can parse the real structure without
a board.

The fixtures are SIMULATED.  They demonstrate the wire format, the null/NO_DATA
semantics and the profile channel tables; they are not measurements and must not
be presented as hardware evidence.
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
    ("test_fsr2_sampler", "FSR_ONLY"),
    ("test_fsr2_sampler_hybrid", "HYBRID_6X6_FSR2"),
]

FIXTURE_NAMES = {
    ("FSR_ONLY", 0): "hello_fsr_only.json",
    ("FSR_ONLY", 1): "sample_fsr_only_valid.json",
    ("FSR_ONLY", 2): "sample_fsr_only_no_adc4.json",
    ("HYBRID_6X6_FSR2", 0): "hello_hybrid.json",
    ("HYBRID_6X6_FSR2", 1): "sample_hybrid_valid.json",
    ("HYBRID_6X6_FSR2", 2): "sample_hybrid_no_adc4.json",
}


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
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return lines


def describe(message) -> str:
    if isinstance(message, proto.SampleFrame):
        return "SAMPLE %s seq=%d" % (message.profile, message.frame_seq)
    return "%s %s" % (message["type"], message["sensor_profile"])


def validate_fsr_only(frames: list, profile: str) -> None:
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
    check(valid.channels[0] is not None and valid.channels[1] is not None, "healthy FSR channels carry counts")
    check(valid.fsr_values["FSR_A"] < valid.fsr_values["FSR_B"], "injected divider order is preserved")
    check(all(entry["state"] == "OK" for entry in valid.adc_status), "healthy frame reports four OK converters")
    check(valid.frame_period_us == 10000, "frame period is reported once a previous frame exists")
    check(valid.effective_frame_rate_hz > 0, "frame rate is derived from the window")

    check(missing.frame_seq == 3, "the missing-converter frame keeps the sequence")
    for channel in (0, 1):
        check(missing.channels[channel] is None, "absent ADC4 channel %d is null, not zero" % (channel,))
        check(missing.valid[channel] is False, "absent ADC4 channel %d is invalid" % (channel,))
        check(proto.FLAG_NO_DATA in [bit for bit in proto.CHANNEL_FLAGS if missing.channel_flags[channel] & bit],
              "absent ADC4 channel %d carries NO_DATA" % (channel,))
    check(missing.adc_status[3]["state"] != "OK", "absent ADC4 is reported as not OK")


def validate_hybrid(frames: list, profile: str) -> None:
    hello, valid, missing = frames
    check(hello["sensor_profile"] == "HYBRID_6X6_FSR2" and hello["channel_count"] == 38,
          "HYBRID HELLO declares 38 channels")
    check(hello["channel_config"]["matrix_rows"] == 6 and hello["channel_config"]["matrix_cols"] == 6,
          "HYBRID channel_config declares a 6x6 matrix")
    check(hello["pins"]["matrix_columns"] == [4, 13, 14, 25, 27, 19],
          "HYBRID HELLO carries the six column GPIOs")
    kinds = [entry["sensor_kind"] for entry in hello["channel_config"]["channels"]]
    check(kinds[:36] == ["MATRIX_CELL"] * 36 and kinds[36:] == ["FSR", "FSR"],
          "HYBRID channel kinds are 36 matrix cells followed by two FSR channels")
    check(hello["channel_config"]["channels"][0]["matrix_row"] == 0
          and hello["channel_config"]["channels"][0]["matrix_col"] == 0, "HYBRID starts at R1C1")
    check(hello["channel_config"]["channels"][35]["matrix_row"] == 5
          and hello["channel_config"]["channels"][35]["matrix_col"] == 5, "HYBRID ends at R6C6")

    check(valid.channel_count == 38 and all(valid.valid), "HYBRID frame marks all 38 channels valid")
    check(all(value is not None for value in valid.channels), "HYBRID frame carries every count")
    check(missing.valid[36] is False and missing.valid[37] is False,
          "HYBRID missing ADC4 invalidates only the two FSR channels")
    check(missing.valid[0] and missing.valid[35], "HYBRID matrix cells stay valid when ADC4 is absent")


VALIDATORS = {"FSR_ONLY": validate_fsr_only, "HYBRID_6X6_FSR2": validate_hybrid}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE))
    parser.add_argument("--fixture-dir", default=str(FIXTURE_DIR))
    args = parser.parse_args(argv)

    evidence = Path(args.evidence_dir).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    fixture_dir = Path(args.fixture_dir).resolve()
    fixture_dir.mkdir(parents=True, exist_ok=True)

    cxx = host.find_cxx()
    binaries: dict[str, Path] = {}
    for name, _profile in EMITTERS:
        source = "tools/fsr2_sim/%s.cpp" % (name,)
        binary = evidence / name
        log = evidence / (name + ".compile.log")
        if not host.compile_test(cxx, source, binary, log):
            print("cannot build emitter %s" % (name,))
            return 1
        binaries[name] = binary

    summary = {"kind": "HOST_SIMULATION_NOT_HARDWARE", "profiles": [], "fixtures": {}}
    try:
        for name, profile in EMITTERS:
            lines = emit_lines(binaries[name])
            check(len(lines) == 3, "%s emitted HELLO plus two SAMPLE frames" % (profile,))
            parsed = [proto.parse_message(line) for line in lines]
            types = [describe(frame) for frame in parsed]
            print("  frames:", "; ".join(types))
            VALIDATORS[profile](parsed, profile)

            for index, line in enumerate(lines):
                fixture_name = FIXTURE_NAMES[(profile, index)]
                (fixture_dir / fixture_name).write_text(line.strip() + "\n")
                summary["fixtures"][fixture_name] = hashlib.sha256(
                    (line.strip() + "\n").encode("utf-8")
                ).hexdigest()
            summary["profiles"].append({"profile": profile, "frames": types, "result": "PASS"})
    except CheckFailure as failure:
        summary["result"] = "FAIL"
        summary["failure"] = str(failure)
        (evidence / "frames_check.json").write_text(json.dumps(summary, indent=2) + "\n")
        print("frame check: FAIL")
        return 1

    # The emitters are deterministic; a second run must reproduce the fixtures.
    for name, _profile in EMITTERS:
        first = emit_lines(binaries[name])
        second = emit_lines(binaries[name])
        check(first == second, "%s emitter is deterministic across runs" % (name,))

    summary["result"] = "PASS"
    summary["note"] = (
        "Emitted by this firmware compiled against the four-device host simulation. "
        "Fixture data for parser tests; not hardware measurements."
    )
    (evidence / "frames_check.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("frame check: PASS")
    print("fixtures: %s" % (fixture_dir,))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
