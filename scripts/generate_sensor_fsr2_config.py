#!/usr/bin/env python3
"""Generate the V2 four-ADS1220 firmware header from a board JSON file.

The V2 board keeps ADC1/ADC2/ADC3 as the 6x6 matrix row inputs and adds ADC4
for the two FSR dividers.  Two profiles are supported:

  FSR_ONLY          two channels, ADC4 AIN0/AIN1, matrix scanning disabled
  HYBRID_6X6_FSR2   38 channels, 0..35 row-major R1C1..R6C6, 36=FSR_A, 37=FSR_B

The generator validates pin assignments, the ADS1220 configuration and the
channel ordering before writing anything, so a stale or historical pin map can
never silently produce a V2 firmware header.  The historical ``[35, 26, 34]``
MISO order is rejected on purpose: on the V2 board MISO is 34/35/26/33.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_OUTPUT = ROOT / "firmware" / "sensor_fsr2" / "fsr2_config.h"

FLASH_PINS = {6, 7, 8, 9, 10, 11}
INPUT_ONLY_PINS = set(range(34, 40))
STRAPPING_PINS = {0, 2, 5, 12, 15}

# ADS1220 data rate: SPS -> DR[2:0]
DR_CODES = {20: 0, 45: 1, 90: 2, 175: 3, 330: 4, 600: 5, 1000: 6}
# Gain[2:0]
GAIN_CODES = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4, 32: 5, 64: 6, 128: 7}
# Reference: name -> (VREF[1:0], register bits)
REFERENCE_CODES = {
    "INTERNAL_2V048": (0, 0x00),
    "EXTERNAL_REFP0_REFN0": (1, 0x40),
    "EXTERNAL_REFP1_REFN1": (2, 0x80),
    "AVDD_AVSS": (3, 0xC0),
}

PROFILES = ("FSR_ONLY", "HYBRID_6X6_FSR2")
FSR_PROFILES = ("FSR_ONLY", "HYBRID_6X6_FSR2")
SERIAL_BAUDS = (115200, 230400, 460800, 921600, 1500000, 2000000)

MAX_FIRMWARE_LINE_BYTES = 8192
MAX_FIRMWARE_COMMAND_BYTES = 512
NAME_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_")


def load_json(path):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise SystemExit("cannot read %s: %s" % (path, exc))
    except json.JSONDecodeError as exc:
        raise SystemExit("%s is not valid JSON: %s" % (path, exc))


def require_int(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int):
        raise SystemExit("%s must be an integer" % name)
    if value < minimum or value > maximum:
        raise SystemExit("%s must be between %d and %d" % (name, minimum, maximum))
    return value


def require_bool(value, name):
    if not isinstance(value, bool):
        raise SystemExit("%s must be a boolean" % name)
    return value


def require_str(value, name):
    if not isinstance(value, str) or not value:
        raise SystemExit("%s must be a non-empty string" % name)
    return value


def require_name(value, name):
    text = require_str(value, name)
    if not set(text) <= NAME_CHARS:
        raise SystemExit("%s may only use letters, digits and underscore" % name)
    return text


def validate_pins(pins, adc_count):
    if not isinstance(pins, dict):
        raise SystemExit("pins must be an object")
    sclk = require_int(pins.get("sclk"), "pins.sclk", 0, 39)
    mosi = require_int(pins.get("mosi"), "pins.mosi", 0, 39)
    miso = pins.get("miso")
    cs = pins.get("cs")
    for key, value in (("miso", miso), ("cs", cs)):
        if not isinstance(value, list) or len(value) != adc_count:
            raise SystemExit("pins.%s must contain exactly %d GPIO numbers" % (key, adc_count))

    miso = [require_int(pin, "pins.miso[%d]" % i, 0, 39) for i, pin in enumerate(miso)]
    cs = [require_int(pin, "pins.cs[%d]" % i, 0, 39) for i, pin in enumerate(cs)]

    driven = [("pins.sclk", sclk), ("pins.mosi", mosi)]
    driven += [("pins.cs[%d]" % i, pin) for i, pin in enumerate(cs)]
    for label, pin in driven:
        if pin in FLASH_PINS:
            raise SystemExit("%s uses flash pin GPIO%d" % (label, pin))
        if pin in INPUT_ONLY_PINS:
            raise SystemExit("%s uses input-only GPIO%d, which cannot drive the bus" % (label, pin))
    for index, pin in enumerate(miso):
        if pin in FLASH_PINS:
            raise SystemExit("pins.miso[%d] uses flash pin GPIO%d" % (index, pin))

    driven_pins = [sclk, mosi] + cs
    if len(set(driven_pins)) != len(driven_pins):
        raise SystemExit("pins.sclk, pins.mosi and pins.cs share a GPIO")
    if len(set(miso)) != len(miso):
        raise SystemExit("pins.miso contains duplicate GPIOs")
    if set(miso) & set(driven_pins):
        raise SystemExit("pins.miso overlaps a driven pin")
    return sclk, mosi, miso, cs


def validate_ads1220(ads, profile):
    if not isinstance(ads, dict):
        raise SystemExit("ads1220 must be an object")

    half_period = require_int(ads.get("spi_half_period_us"), "ads1220.spi_half_period_us", 1, 100)
    data_rate_sps = require_int(ads.get("data_rate_sps"), "ads1220.data_rate_sps", 1, 2000)
    if data_rate_sps not in DR_CODES:
        raise SystemExit(
            "ads1220.data_rate_sps %d is not an ADS1220 rate; choose one of %s"
            % (data_rate_sps, sorted(DR_CODES))
        )
    gain = require_int(ads.get("gain"), "ads1220.gain", 1, 128)
    if gain not in GAIN_CODES:
        raise SystemExit(
            "ads1220.gain %d is not an ADS1220 gain; choose one of %s" % (gain, sorted(GAIN_CODES))
        )
    pga_bypass = require_bool(ads.get("pga_bypass"), "ads1220.pga_bypass")
    reference_name = require_str(ads.get("reference_mode"), "ads1220.reference_mode")
    if reference_name not in REFERENCE_CODES:
        raise SystemExit(
            "ads1220.reference_mode %r is unknown; choose one of %s"
            % (reference_name, sorted(REFERENCE_CODES))
        )
    allowed = ads.get("reference_modes_allowed")
    if not isinstance(allowed, list) or not allowed or not all(isinstance(item, str) for item in allowed):
        raise SystemExit("ads1220.reference_modes_allowed must be a non-empty list of names")
    if reference_name not in allowed:
        raise SystemExit("ads1220.reference_mode must appear in ads1220.reference_modes_allowed")
    for name in allowed:
        if name not in REFERENCE_CODES:
            raise SystemExit("ads1220.reference_modes_allowed contains unknown mode %r" % name)

    conversion_wait_us = require_int(
        ads.get("conversion_wait_us"), "ads1220.conversion_wait_us", 100, 40000
    )
    minimum_wait = 900000 // data_rate_sps
    if conversion_wait_us < minimum_wait:
        raise SystemExit(
            "ads1220.conversion_wait_us %d is shorter than one %d SPS conversion (%d us)"
            % (conversion_wait_us, data_rate_sps, minimum_wait)
        )
    if ads.get("operating_mode") != "NORMAL":
        raise SystemExit("ads1220.operating_mode must be NORMAL")
    if ads.get("conversion_mode") != "SINGLE_SHOT":
        raise SystemExit("ads1220.conversion_mode must be SINGLE_SHOT")
    require_bool(ads.get("idac_enabled"), "ads1220.idac_enabled")
    mux_codes = ads.get("mux_codes")
    if not isinstance(mux_codes, list) or len(mux_codes) != 4:
        raise SystemExit("ads1220.mux_codes must list the four AIN single-ended MUX codes")
    for code in mux_codes:
        require_int(code, "ads1220.mux_codes[]", 8, 11)

    if profile in FSR_PROFILES:
        if reference_name != "AVDD_AVSS":
            raise SystemExit(
                "profile %s requires ads1220.reference_mode AVDD_AVSS: the FSR divider sits near "
                "3.3 V and the internal 2.048 V reference would clip it" % profile
            )
        if gain != 1:
            raise SystemExit(
                "profile %s requires ads1220.gain 1 (no PGA gain on the 3.3 V divider)" % profile
            )
        if not pga_bypass:
            raise SystemExit("profile %s requires ads1220.pga_bypass true" % profile)
        if ads.get("idac_enabled"):
            raise SystemExit(
                "profile %s requires ads1220.idac_enabled false (no sensor excitation)" % profile
            )

    return {
        "spi_half_period_us": half_period,
        "data_rate_sps": data_rate_sps,
        "data_rate_code": DR_CODES[data_rate_sps],
        "conversion_wait_us": conversion_wait_us,
        "gain": gain,
        "gain_code": GAIN_CODES[gain],
        "pga_bypass": pga_bypass,
        "reference_name": reference_name,
        "reference_code": REFERENCE_CODES[reference_name][0],
        "reference_bits": REFERENCE_CODES[reference_name][1],
        "reference_modes_allowed": list(allowed),
        "mux_codes": list(mux_codes),
    }


def validate_matrix(matrix, sclk, mosi, miso, cs):
    if not isinstance(matrix, dict):
        raise SystemExit("matrix must be an object for HYBRID_6X6_FSR2")
    rows = require_int(matrix.get("rows"), "matrix.rows", 1, 6)
    cols = require_int(matrix.get("cols"), "matrix.cols", 1, 6)
    if rows != 6 or cols != 6:
        raise SystemExit("HYBRID_6X6_FSR2 requires matrix.rows 6 and matrix.cols 6")

    column_pins = matrix.get("column_pins")
    if not isinstance(column_pins, list) or len(column_pins) != cols:
        raise SystemExit("matrix.column_pins must list one GPIO per column")
    column_pins = [
        require_int(pin, "matrix.column_pins[%d]" % index, 0, 39)
        for index, pin in enumerate(column_pins)
    ]
    reserved = {sclk, mosi} | set(miso) | set(cs)
    for index, pin in enumerate(column_pins):
        if pin in FLASH_PINS:
            raise SystemExit("matrix.column_pins[%d] uses flash pin GPIO%d" % (index, pin))
        if pin in INPUT_ONLY_PINS:
            raise SystemExit("matrix.column_pins[%d] uses input-only GPIO%d" % (index, pin))
        if pin in reserved:
            raise SystemExit("matrix.column_pins[%d] GPIO%d collides with an SPI pin" % (index, pin))
    if len(set(column_pins)) != len(column_pins):
        raise SystemExit("matrix.column_pins contains duplicate GPIOs")

    row_inputs = matrix.get("row_inputs")
    if not isinstance(row_inputs, list) or len(row_inputs) != rows:
        raise SystemExit("matrix.row_inputs must list one entry per row")
    expected = [(index // 2 + 1, index % 2) for index in range(rows)]
    mapped = []
    for index, entry in enumerate(row_inputs):
        if not isinstance(entry, dict):
            raise SystemExit("matrix.row_inputs[%d] must be an object" % index)
        adc_id = require_int(entry.get("adc_id"), "matrix.row_inputs[%d].adc_id" % index, 1, 3)
        adc_input = require_int(
            entry.get("adc_input"), "matrix.row_inputs[%d].adc_input" % index, 0, 1
        )
        require_int(
            entry.get("pulldown_resistor_ohm", 10000),
            "matrix.row_inputs[%d].pulldown_resistor_ohm" % index,
            100,
            1000000,
        )
        mapped.append((adc_id, adc_input))
    if mapped != expected:
        raise SystemExit(
            "matrix.row_inputs must map row n to ADC(n//2+1) AIN(n%%2), i.e. %s; the column scan "
            "firmware assumes that order" % expected
        )

    if matrix.get("inactive_column_mode") != "HI_Z":
        raise SystemExit("matrix.inactive_column_mode must be HI_Z")
    settle_us = require_int(matrix.get("settle_us", 1000), "matrix.settle_us", 10, 50000)
    pre_discharge_us = require_int(
        matrix.get("pre_discharge_us", 200), "matrix.pre_discharge_us", 0, 20000
    )
    return {
        "rows": rows,
        "cols": cols,
        "column_pins": column_pins,
        "settle_us": settle_us,
        "pre_discharge_us": pre_discharge_us,
        "scan_mode": require_str(matrix.get("scan_mode", "COLUMN_SCAN_6X6"), "matrix.scan_mode"),
    }


def validate_stream(stream):
    if not isinstance(stream, dict):
        raise SystemExit("stream must be an object")
    max_line_bytes = require_int(stream.get("max_line_bytes"), "stream.max_line_bytes", 1024, 65536)
    if max_line_bytes > MAX_FIRMWARE_LINE_BYTES:
        raise SystemExit(
            "stream.max_line_bytes %d exceeds the firmware output buffer (%d bytes); the sketch "
            "allocates one fixed buffer, raise the sketch buffer deliberately if a bigger line is "
            "really needed" % (max_line_bytes, MAX_FIRMWARE_LINE_BYTES)
        )
    max_command_bytes = require_int(
        stream.get("max_command_bytes"), "stream.max_command_bytes", 64, 4096
    )
    if max_command_bytes > MAX_FIRMWARE_COMMAND_BYTES:
        raise SystemExit(
            "stream.max_command_bytes %d exceeds the firmware command buffer (%d bytes)"
            % (max_command_bytes, MAX_FIRMWARE_COMMAND_BYTES)
        )
    return {
        "max_line_bytes": max_line_bytes,
        "max_command_bytes": max_command_bytes,
        "command_partial_timeout_ms": require_int(
            stream.get("command_partial_timeout_ms"), "stream.command_partial_timeout_ms", 10, 60000
        ),
        "frame_rate_window": require_int(
            stream.get("frame_rate_window"), "stream.frame_rate_window", 2, 256
        ),
        "reinit_after_consecutive_errors": require_int(
            stream.get("reinit_after_consecutive_errors"),
            "stream.reinit_after_consecutive_errors",
            1,
            100,
        ),
        "reinit_retry_interval_ms": require_int(
            stream.get("reinit_retry_interval_ms"), "stream.reinit_retry_interval_ms", 10, 60000
        ),
    }


def validate_fsr(fsr, pins, adc_count, channel_count):
    if not isinstance(fsr, dict):
        raise SystemExit("fsr must be an object")
    adc_id = require_int(fsr.get("adc_id"), "fsr.adc_id", 1, adc_count)
    if adc_id != adc_count:
        raise SystemExit(
            "fsr.adc_id must be %d on the V2 board (ADC4 is the FSR ADC)" % adc_count
        )
    cs4 = require_int(fsr.get("adc4_cs_gpio"), "fsr.adc4_cs_gpio", 0, 39)
    miso4 = require_int(fsr.get("adc4_miso_gpio"), "fsr.adc4_miso_gpio", 0, 39)
    if cs4 != pins[3][3]:
        raise SystemExit(
            "fsr.adc4_cs_gpio %d must match pins.cs[3] %d, the fourth chip select"
            % (cs4, pins[3][3])
        )
    if miso4 != pins[2][3]:
        raise SystemExit(
            "fsr.adc4_miso_gpio %d must match pins.miso[3] %d" % (miso4, pins[2][3])
        )

    channels = fsr.get("channels")
    if not isinstance(channels, list) or len(channels) != 2:
        raise SystemExit("fsr.channels must describe exactly the two FSR dividers")
    entries = []
    for index, entry in enumerate(channels):
        if not isinstance(entry, dict):
            raise SystemExit("fsr.channels[%d] must be an object" % index)
        channel_id = require_int(entry.get("channel_id"), "fsr.channels[%d].channel_id" % index, 0, 255)
        name = require_name(entry.get("name"), "fsr.channels[%d].name" % index)
        adc_input = require_int(entry.get("adc_input"), "fsr.channels[%d].adc_input" % index, 0, 1)
        mux_code = require_int(entry.get("mux_code"), "fsr.channels[%d].mux_code" % index, 8, 11)
        if mux_code != 8 + adc_input:
            raise SystemExit(
                "fsr.channels[%d].mux_code %d must be the single-ended MUX code for AIN%d (%d)"
                % (index, mux_code, adc_input, 8 + adc_input)
            )
        entries.append(
            {
                "channel_id": channel_id,
                "name": name,
                "adc_input": adc_input,
                "mux_code": mux_code,
            }
        )
    entries.sort(key=lambda item: item["channel_id"])
    expected_ids = list(range(channel_count - len(entries), channel_count))
    actual_ids = [item["channel_id"] for item in entries]
    if actual_ids != expected_ids:
        raise SystemExit(
            "fsr.channels must carry the last channel ids %s in order, got %s"
            % (expected_ids, actual_ids)
        )
    if len({item["adc_input"] for item in entries}) != len(entries):
        raise SystemExit("the two FSR channels must use different ADC4 inputs")
    if len({item["name"] for item in entries}) != len(entries):
        raise SystemExit("the two FSR channels must have different names")

    divider_ohm = require_int(
        fsr.get("divider_resistor_ohm"), "fsr.divider_resistor_ohm", 100, 1000000
    )
    excitation_mv = require_int(fsr.get("excitation_mv"), "fsr.excitation_mv", 1000, 5000)
    if fsr.get("independent_pulldowns_required") is not True:
        raise SystemExit(
            "fsr.independent_pulldowns_required must be true: FSR_A and FSR_B share no node, "
            "each needs its own resistor to GND"
        )
    unit = require_str(fsr.get("unit", "ADC_COUNTS"), "fsr.unit")
    if unit != "ADC_COUNTS":
        raise SystemExit("fsr.unit must be ADC_COUNTS; the firmware reports raw counts only")
    polarity = require_str(
        fsr.get("response_polarity", "VOLTAGE_RISES_WITH_FORCE"), "fsr.response_polarity"
    )
    if polarity != "VOLTAGE_RISES_WITH_FORCE":
        raise SystemExit(
            "fsr.response_polarity must be VOLTAGE_RISES_WITH_FORCE for the divider-to-GND wiring"
        )
    return {
        "channels": entries,
        "divider_ohm": divider_ohm,
        "excitation_mv": excitation_mv,
    }


def build_channels(config, fsr, matrix):
    profile = config["sensor_profile"]
    channels = []
    if profile == "HYBRID_6X6_FSR2":
        for row in range(matrix["rows"]):
            for col in range(matrix["cols"]):
                channels.append(
                    {
                        "channel_id": row * matrix["cols"] + col,
                        "adc_index": row // 2,
                        "adc_input": row % 2,
                        "mux_code": 8 + (row % 2),
                        "kind": "MATRIX_CELL",
                        "matrix_row": row,
                        "matrix_col": col,
                        "name": "R%dC%d" % (row + 1, col + 1),
                    }
                )
    for entry in fsr["channels"]:
        channels.append(
            {
                "channel_id": entry["channel_id"],
                "adc_index": config["pins"]["cs"].index(config["fsr"]["adc4_cs_gpio"]),
                "adc_input": entry["adc_input"],
                "mux_code": entry["mux_code"],
                "kind": "FSR",
                "matrix_row": -1,
                "matrix_col": -1,
                "name": entry["name"],
            }
        )
    channels.sort(key=lambda item: item["channel_id"])
    for index, channel in enumerate(channels):
        if channel["channel_id"] != index:
            raise SystemExit("channel table must be dense and ordered by channel id")
    return channels


def display_path(path):
    """Repo-relative path when possible, so temp-file runs still render a header."""
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return Path(path).name


def render_header(config, config_path, profile, ads, pins, fsr, matrix, stream, channels):
    def cstr(value):
        return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'

    miso = [str(pin) for pin in pins[2]]
    cs = [str(pin) for pin in pins[3]]
    column_pins = [str(pin) for pin in (matrix["column_pins"] if matrix else [0])]
    fsr_ids = [str(item["channel_id"]) for item in fsr["channels"]]
    fsr_ids.sort(key=int)

    digest = hashlib.sha256(config_path.read_bytes()).hexdigest()
    channel_count = len(channels)
    matrix_rows = matrix["rows"] if matrix else 0
    matrix_cols = matrix["cols"] if matrix else 0
    matrix_adcs = 3 if matrix else 0
    rounds = 2 if matrix else 0
    column_count = matrix["cols"] if matrix else 0
    settle_us = matrix["settle_us"] if matrix else 0
    discharge_us = matrix["pre_discharge_us"] if matrix else 0

    lines = []
    lines.append("// AUTO-GENERATED FILE - do not edit by hand.")
    lines.append("// Source: %s (sha256 %s)" % (display_path(config_path), digest))
    lines.append("// Regenerate: python3 scripts/generate_sensor_fsr2_config.py --config %s"
                 % display_path(config_path))
    lines.append("//")
    lines.append("// V2 board: four ADS1220 share SCLK/MOSI; ADC1/ADC2/ADC3 carry the 6x6 matrix")
    lines.append("// rows, ADC4 carries the two FSR dividers.  Channel order is the protocol order.")
    lines.append("#pragma once")
    lines.append("")
    lines.append('#include "fsr2.h"')
    lines.append("")
    lines.append("// MISO/CS are ordered by ADS1220 index: ADC1..ADC%d." % len(cs))
    lines.append("static const uint8_t FSR2_MISO_PINS[%d] = {%s};" % (len(miso), ", ".join(miso)))
    lines.append("static const uint8_t FSR2_CS_PINS[%d] = {%s};" % (len(cs), ", ".join(cs)))
    if matrix:
        lines.append("static const uint8_t FSR2_COLUMN_PINS[%d] = {%s};"
                     % (len(column_pins), ", ".join(column_pins)))
    else:
        lines.append("// FSR_ONLY drives no matrix columns; the placeholder keeps the array non-empty.")
        lines.append("static const uint8_t FSR2_COLUMN_PINS[1] = {0};")
    if fsr_ids:
        lines.append("static const uint8_t FSR2_FSR_CHANNEL_INDICES[%d] = {%s};"
                     % (len(fsr_ids), ", ".join(fsr_ids)))
    lines.append("")
    lines.append("// Buffer sizes the sketch must provide; confirmed against struct Fsr2Profile.")
    lines.append("static const uint16_t FSR2_MAX_LINE_BYTES = %d;" % stream["max_line_bytes"])
    lines.append("static const uint16_t FSR2_COMMAND_BUFFER_BYTES = %d;"
                 % stream["max_command_bytes"])
    lines.append("")
    lines.append("static const Fsr2ChannelConfig FSR2_CHANNELS[%d] = {" % channel_count)
    for channel in channels:
        lines.append(
            "    {%d, %d, %d, %s, %d, %d, %s},  // channel %d"
            % (
                channel["adc_index"],
                channel["adc_input"],
                channel["mux_code"],
                "FSR2_KIND_MATRIX_CELL" if channel["kind"] == "MATRIX_CELL" else "FSR2_KIND_FSR",
                channel["matrix_row"],
                channel["matrix_col"],
                cstr(channel["name"]),
                channel["channel_id"],
            )
        )
    lines.append("};")
    lines.append("")
    lines.append("// Field order must match struct Fsr2Profile in fsr2.h.")
    lines.append("static const Fsr2Profile FSR2_PROFILE = {")
    lines.append("    %s,  // device_id" % cstr(config["device_id"]))
    lines.append("    %s,  // firmware_version" % cstr(config["firmware_version"]))
    lines.append("    %s,  // sensor_profile" % cstr(profile))
    lines.append(
        "    %s,  // scan_mode" % cstr(matrix["scan_mode"] if matrix else "FSR_ONLY_2CH")
    )
    lines.append("    %s,  // reference_mode_name" % cstr(ads["reference_name"]))
    lines.append("    %dUL,  // serial_baud" % config["serial_baud"])
    lines.append("    %d,  // sclk_pin" % pins[0])
    lines.append("    %d,  // mosi_pin" % pins[1])
    lines.append("    %d,  // adc_count" % len(cs))
    lines.append("    %d,  // channel_count" % channel_count)
    lines.append("    FSR2_MISO_PINS,  // miso_pins")
    lines.append("    FSR2_CS_PINS,  // cs_pins")
    lines.append("    %d,  // matrix_rows" % matrix_rows)
    lines.append("    %d,  // matrix_cols" % matrix_cols)
    lines.append("    %d,  // matrix_adc_count" % matrix_adcs)
    lines.append("    %d,  // matrix_rounds" % rounds)
    lines.append("    %d,  // column_count" % column_count)
    lines.append("    %s,  // column_pins" % ("FSR2_COLUMN_PINS" if matrix else "nullptr"))
    lines.append("    %d,  // matrix_settle_us" % settle_us)
    lines.append("    %d,  // matrix_pre_discharge_us" % discharge_us)
    lines.append("    %d,  // fsr_count" % len(fsr["channels"]))
    lines.append("    FSR2_FSR_CHANNEL_INDICES,  // fsr_channel_indices")
    lines.append("    %d,  // fsr_divider_ohm" % fsr["divider_ohm"])
    lines.append("    %d,  // fsr_excitation_mv" % fsr["excitation_mv"])
    lines.append("    FSR2_CHANNELS,  // channels")
    lines.append("    %d,  // reference_mode_code" % ads["reference_code"])
    lines.append("    %d,  // data_rate_code" % ads["data_rate_code"])
    lines.append("    %d,  // data_rate_sps" % ads["data_rate_sps"])
    lines.append("    %d,  // conversion_wait_us" % ads["conversion_wait_us"])
    lines.append("    %d,  // spi_half_period_us" % ads["spi_half_period_us"])
    lines.append("    %d,  // gain_code" % ads["gain_code"])
    lines.append("    %d,  // pga_bypass" % (1 if ads["pga_bypass"] else 0))
    lines.append("    %d,  // max_line_bytes" % stream["max_line_bytes"])
    lines.append("    %d,  // max_command_bytes" % stream["max_command_bytes"])
    lines.append("    %d,  // command_partial_timeout_ms" % stream["command_partial_timeout_ms"])
    lines.append("    %d,  // frame_rate_window" % stream["frame_rate_window"])
    lines.append("    %d,  // reinit_after_errors" % stream["reinit_after_consecutive_errors"])
    lines.append("    %d,  // reinit_retry_interval_ms" % stream["reinit_retry_interval_ms"])
    lines.append("};")
    lines.append("")
    return "\n".join(lines) + "\n"


def generate(config_path, output_path):
    config = load_json(config_path)
    if not isinstance(config, dict):
        raise SystemExit("%s must contain a JSON object" % config_path)

    profile = require_str(config.get("sensor_profile"), "sensor_profile")
    if profile not in PROFILES:
        raise SystemExit("sensor_profile %r is not one of %s" % (profile, list(PROFILES)))
    require_str(config.get("device_id"), "device_id")
    require_str(config.get("firmware_version"), "firmware_version")
    serial_baud = require_int(config.get("serial_baud"), "serial_baud", 9600, 2000000)
    if serial_baud not in SERIAL_BAUDS:
        raise SystemExit("serial_baud %d is not one of %s" % (serial_baud, list(SERIAL_BAUDS)))

    adc_count = 4
    pins = validate_pins(config.get("pins"), adc_count)
    ads = validate_ads1220(config.get("ads1220"), profile)
    stream = validate_stream(config.get("stream"))

    matrix = None
    if profile == "HYBRID_6X6_FSR2":
        matrix = validate_matrix(config.get("matrix"), pins[0], pins[1], pins[2], pins[3])
    elif config.get("matrix") is not None:
        raise SystemExit("FSR_ONLY must set matrix to null: no column is driven in this profile")

    fsr_channel_count = 2
    channel_count = (matrix["rows"] * matrix["cols"] if matrix else 0) + fsr_channel_count
    fsr = validate_fsr(config.get("fsr"), pins, adc_count, channel_count)
    channels = build_channels(config, fsr, matrix)

    text = render_header(
        config, config_path, profile, ads, pins, fsr, matrix, stream, channels
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return {
        "profile": profile,
        "channel_count": channel_count,
        "output": str(output_path),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(ROOT / "config" / "sensor_esp32_fsr2.json"),
        help="board configuration JSON (default: config/sensor_esp32_fsr2.json)",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="generated C++ header (default: firmware/sensor_fsr2/fsr2_config.h)",
    )
    args = parser.parse_args(argv)
    result = generate(Path(args.config).resolve(), Path(args.output).resolve())
    print(
        "wrote %s (%s profile, %d channels, header sha256 %s)"
        % (result["output"], result["profile"], result["channel_count"], result["sha256"][:16])
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
