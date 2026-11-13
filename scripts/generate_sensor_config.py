#!/usr/bin/env python3
"""Generate the ADS1220 tactile-acquisition firmware header from JSON.

The generator refuses configurations that are electrically impossible or that
would enable an unverified IDAC excitation source.  It performs no serial
access and no upload.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ESP32 (original) pins.  GPIO 6..11 are attached to the SPI flash and must not
# be used.  GPIO 34..39 are input-only.  GPIO 0/2/12/15 are strapping pins but
# are not used by this build; GPIO 5 is a strapping pin and is allowed only as a
# chip select because the firmware drives it high immediately at boot.
FLASH_PINS = {6, 7, 8, 9, 10, 11}
INPUT_ONLY_PINS = set(range(34, 40))
STRAPPING_PINS = {0, 2, 5, 12, 15}

DR_CODES = {20: 0, 45: 1, 90: 2, 175: 3, 330: 4, 600: 5, 1000: 6}
REFERENCE_CODES = {"INTERNAL_2V048": 0, "AVDD_AVSS": 1}


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise SystemExit(f"cannot read {path}: {exc}")


def require_int(value, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise SystemExit(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def validate_pins(pins: dict) -> tuple[int, int, list[int], list[int]]:
    sclk = require_int(pins.get("sclk"), "pins.sclk", 0, 39)
    mosi = require_int(pins.get("mosi"), "pins.mosi", 0, 39)
    miso = pins.get("miso")
    cs = pins.get("cs")
    if not isinstance(miso, list) or len(miso) != 3:
        raise SystemExit("pins.miso must contain exactly 3 GPIO numbers")
    if not isinstance(cs, list) or len(cs) != 3:
        raise SystemExit("pins.cs must contain exactly 3 GPIO numbers")
    miso = [require_int(item, f"pins.miso[{index}]", 0, 39) for index, item in enumerate(miso)]
    cs = [require_int(item, f"pins.cs[{index}]", 0, 39) for index, item in enumerate(cs)]

    all_pins = [sclk, mosi, *miso, *cs]
    if len(set(all_pins)) != len(all_pins):
        raise SystemExit("pin map contains duplicate GPIO assignments")
    for name, pin in (("sclk", sclk), ("mosi", mosi), *[(f"cs[{i}]", p) for i, p in enumerate(cs)]):
        if pin in FLASH_PINS:
            raise SystemExit(f"{name}=GPIO{pin} is connected to the SPI flash")
        if pin in INPUT_ONLY_PINS:
            raise SystemExit(f"{name}=GPIO{pin} is input-only and cannot be an output")
    for index, pin in enumerate(miso):
        if pin in FLASH_PINS:
            raise SystemExit(f"miso[{index}]=GPIO{pin} is connected to the SPI flash")
    if len(set(miso)) != 3:
        raise SystemExit("the three ADS1220 MISO pins must be independent")
    if len(set(cs)) != 3:
        raise SystemExit("the three ADS1220 CS pins must be independent")
    return sclk, mosi, miso, cs


def validate_reference(mode: str, allowed: list) -> int:
    if mode not in REFERENCE_CODES:
        raise SystemExit(f"unsupported reference_mode: {mode}")
    if not isinstance(allowed, list) or mode not in allowed:
        raise SystemExit(f"reference_mode {mode} is not listed in reference_modes_allowed")
    for item in allowed:
        if item not in REFERENCE_CODES:
            raise SystemExit(f"unsupported reference mode in allowed list: {item}")
    return REFERENCE_CODES[mode]


def validate_ads(ads: dict) -> dict:
    half = require_int(ads.get("spi_half_period_us"), "ads1220.spi_half_period_us", 1, 25)
    diag_half = require_int(ads.get("diag_half_period_us"), "ads1220.diag_half_period_us", 5, 200)
    sps = ads.get("data_rate_sps")
    if sps not in DR_CODES:
        raise SystemExit(f"ads1220.data_rate_sps must be one of {sorted(DR_CODES)}")
    wait = require_int(ads.get("conversion_wait_us"), "ads1220.conversion_wait_us", 1000, 200000)
    # Datasheet single-shot conversion time (12562 tCLK for 330 SPS) plus the
    # internal-oscillator wake-up and tolerance.  Require >= 10% + 150 us margin
    # over the nominal conversion period so a stale result is not read.
    minimum_wait = math.ceil(1_000_000 / sps * 1.10 + 150)
    if wait < minimum_wait:
        raise SystemExit(
            f"conversion_wait_us={wait} is too short for {sps} SPS; use >= {minimum_wait}"
        )
    if ads.get("operating_mode") != "NORMAL":
        raise SystemExit("only NORMAL operating mode is supported")
    if ads.get("conversion_mode") != "SINGLE_SHOT":
        raise SystemExit("only SINGLE_SHOT conversion mode is supported")
    if ads.get("gain") != 1:
        raise SystemExit("only gain 1 is supported for the validated build")
    if ads.get("pga_bypass") is not True:
        raise SystemExit("pga_bypass must be true for single-ended AINx/AVSS measurements")
    if ads.get("idac_enabled") is not False:
        raise SystemExit("IDAC excitation is not confirmed and must remain disabled")
    if ads.get("mux_codes") != [8, 9, 10, 11]:
        raise SystemExit("mux_codes must be [8,9,10,11] for AIN0..AIN3 versus AVSS")
    mode = ads.get("reference_mode")
    allowed = ads.get("reference_modes_allowed")
    reference_code = validate_reference(mode, allowed)
    return {
        "half": half,
        "diag_half": diag_half,
        "sps": sps,
        "dr_code": DR_CODES[sps],
        "wait": wait,
        "reference_mode": mode,
        "reference_code": reference_code,
    }


def c_string(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise SystemExit("device_id/firmware_version must be non-empty strings <= 64 chars")
    if not all(32 <= ord(ch) < 127 for ch in value):
        raise SystemExit("device_id/firmware_version must be printable ASCII")
    return value.replace("\\", "\\\\").replace('"', '\\"')


def generate(config: dict) -> str:
    device_id = c_string(config.get("device_id"))
    firmware_version = c_string(config.get("firmware_version"))
    baud = require_int(config.get("serial_baud"), "serial_baud", 230400, 2000000)
    if baud not in (230400, 460800, 921600, 1000000, 1500000, 2000000):
        raise SystemExit("serial_baud should be one of 230400/460800/921600/1000000/1500000/2000000")
    pins = config.get("pins") or {}
    sclk, mosi, miso, cs = validate_pins(pins)
    ads = validate_ads(config.get("ads1220") or {})
    stream = config.get("stream") or {}
    max_line = require_int(stream.get("max_line_bytes"), "stream.max_line_bytes", 512, 8192)
    max_cmd = require_int(stream.get("max_command_bytes"), "stream.max_command_bytes", 32, 2048)
    partial = require_int(stream.get("command_partial_timeout_ms"), "stream.command_partial_timeout_ms", 50, 60000)
    window = require_int(stream.get("frame_rate_window"), "stream.frame_rate_window", 2, 256)
    errors = require_int(stream.get("reinit_after_consecutive_errors"), "stream.reinit_after_consecutive_errors", 1, 100)
    retry = require_int(stream.get("reinit_retry_interval_ms"), "stream.reinit_retry_interval_ms", 50, 60000)

    lines = [
        "// AUTO-GENERATED by scripts/generate_sensor_config.py. Do not edit by hand.",
        "#pragma once",
        "",
        "#include <stdint.h>",
        "",
        f'static const char SENSOR_DEVICE_ID[] = "{device_id}";',
        f'static const char SENSOR_FIRMWARE_VERSION[] = "{firmware_version}";',
        f"static const uint32_t SENSOR_SERIAL_BAUD = {baud}UL;",
        f"static const uint8_t SENSOR_ADC_COUNT = 3;",
        f"static const uint8_t SENSOR_CHANNEL_COUNT = 12;",
        "",
        f"static const uint8_t SENSOR_SCLK_PIN = {sclk};",
        f"static const uint8_t SENSOR_MOSI_PIN = {mosi};",
        "static const uint8_t SENSOR_MISO_PINS[SENSOR_ADC_COUNT] = {"
        + ", ".join(str(pin) for pin in miso)
        + "};",
        "static const uint8_t SENSOR_CS_PINS[SENSOR_ADC_COUNT] = {"
        + ", ".join(str(pin) for pin in cs)
        + "};",
        "",
        f"static const uint8_t SENSOR_SPI_HALF_PERIOD_US = {ads['half']};",
        f"static const uint16_t SENSOR_DIAG_SPI_HALF_PERIOD_US = {ads['diag_half']};",
        f"static const uint8_t SENSOR_DATA_RATE_CODE = {ads['dr_code']};",
        f"static const uint16_t SENSOR_CONVERSION_WAIT_US = {ads['wait']};",
        f"static const uint8_t SENSOR_REFERENCE_MODE_INITIAL = {ads['reference_code']};",
        "static const uint8_t SENSOR_MUX_CODES[4] = {8, 9, 10, 11};",
        "static const uint8_t SENSOR_ADC_INPUTS[4] = {0, 1, 2, 3};",
        "",
        f"static const uint16_t SENSOR_MAX_LINE_BYTES = {max_line};",
        f"static const uint16_t SENSOR_MAX_COMMAND_BYTES = {max_cmd};",
        f"static const uint16_t SENSOR_COMMAND_PARTIAL_TIMEOUT_MS = {partial};",
        f"static const uint8_t SENSOR_FRAME_RATE_WINDOW = {window};",
        f"static const uint8_t SENSOR_REINIT_AFTER_ERRORS = {errors};",
        f"static const uint16_t SENSOR_REINIT_RETRY_INTERVAL_MS = {retry};",
        "",
        "// Channel order: ADC1 AIN0..AIN3 -> CH0..CH3, ADC2 -> CH4..CH7, ADC3 -> CH8..CH11.",
        "",
    ]
    if any(pin in STRAPPING_PINS for pin in [sclk, mosi, *miso, *cs]):
        used = sorted({pin for pin in [sclk, mosi, *miso, *cs] if pin in STRAPPING_PINS})
        lines.insert(2, f"// NOTE: strapping GPIO(s) used: {used}; CS lines are driven high at boot.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "config/sensor_esp32.json"))
    parser.add_argument("--output", default=str(ROOT / "firmware/sensor/generated_config.h"))
    args = parser.parse_args()
    config = load_json(Path(args.config))
    header = generate(config)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(header)
    print(header)
    return 0


if __name__ == "__main__":
    sys.exit(main())
