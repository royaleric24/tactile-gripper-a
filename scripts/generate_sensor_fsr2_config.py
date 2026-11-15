#!/usr/bin/env python3
"""Generate the V2 four-ADS1220 firmware header from a board JSON file.

Board facts fixed by the 2026-11-15 wiring correction:

* ADC1..ADC4 share SCLK18/MOSI23 with CS 21/22/5/32 and MISO 34/35/26/33.
* The pressure cloth has twelve independent electrodes.  R1..R6 each sit on
  their own single-ended AIN with a 10 kOhm resistor to GND; C1..C6 each sit on
  their own single-ended AIN with a 1 kOhm resistor to 3.3 V.  Nothing drives a
  column from a GPIO, and twelve electrode voltages are *not* 36 pressure
  cells.
* Which electrode reaches which ADC/AIN is decided by the physical harness and
  has not been recorded yet.  A configuration may therefore declare
  ``PENDING_REAL_WIRING`` and the generator emits an unmapped channel table
  (sentinel 0xFF) instead of inventing pins.

Supported profiles:

  FSR_ONLY            two channels, ADC4 AIN0/AIN1 (the FSR dividers)
  MATRIX_ELECTRODES_12  twelve electrode channels, optionally followed by the
                      two FSR channels (14 logical channels)

``HYBRID_6X6_FSR2`` is withdrawn: it modelled 36 scanned cells that the real
cloth does not have.  It is kept only in git history and the generator refuses
to produce it again.
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

PROFILES = ("FSR_ONLY", "MATRIX_ELECTRODES_12")
HISTORICAL_PROFILES = ("HYBRID_6X6_FSR2",)
FSR_PROFILES = PROFILES  # both supported profiles read the 3.3 V divider domain
ELECTRODE_ROLES = {"R": "ROW", "C": "COLUMN"}
ELECTRODE_NAMES = ["R%d" % index for index in range(1, 7)] + [
    "C%d" % index for index in range(1, 7)
]
ROW_BIAS = "PULLDOWN_10K_TO_GND"
COLUMN_BIAS = "PULLUP_1K_TO_3V3"
MISSING_MAPPING = "PENDING_REAL_WIRING"
PROVIDED_MAPPING = "TABLE_PROVIDED"
UNMAPPED = 0xFF
ELECTRODE_COUNT = 12
ELECTRODE_ROWS = 6
ELECTRODE_COLUMNS = 6
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
                "profile %s requires ads1220.reference_mode AVDD_AVSS: the FSR divider and the "
                "electrode nodes sit near 3.3 V and the internal 2.048 V reference would clip them"
                % profile
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


def validate_electrodes(electrodes, adc_count, has_fsr):
    """Validate the twelve-electrode block and return (channels, mapping_status).

    An empty ``map`` means the physical harness is not documented yet.  That is
    the normal state today: the firmware must then expose twelve explicitly
    unmapped channels instead of guessing which AIN carries which electrode.
    """
    if not isinstance(electrodes, dict):
        raise SystemExit("electrodes must be an object for MATRIX_ELECTRODES_12")
    count = require_int(electrodes.get("count"), "electrodes.count", 1, 32)
    rows = require_int(electrodes.get("rows"), "electrodes.rows", 1, 16)
    columns = require_int(electrodes.get("columns"), "electrodes.columns", 1, 16)
    if count != ELECTRODE_COUNT or rows != ELECTRODE_ROWS or columns != ELECTRODE_COLUMNS:
        raise SystemExit(
            "the pressure cloth has %d electrodes in a %dx%d grid; electrodes.count/rows/columns "
            "must be %d/%d/%d"
            % (ELECTRODE_COUNT, ELECTRODE_ROWS, ELECTRODE_COLUMNS,
               ELECTRODE_COUNT, ELECTRODE_ROWS, ELECTRODE_COLUMNS)
        )
    if electrodes.get("row_bias", ROW_BIAS) != ROW_BIAS:
        raise SystemExit(
            "electrodes.row_bias must be %s: every row electrode has its own 10 kOhm resistor "
            "to GND" % ROW_BIAS
        )
    if electrodes.get("column_bias", COLUMN_BIAS) != COLUMN_BIAS:
        raise SystemExit(
            "electrodes.column_bias must be %s: every column electrode has its own 1 kOhm "
            "resistor to 3.3 V" % COLUMN_BIAS
        )
    if electrodes.get("gpio_excitation", False):
        raise SystemExit(
            "electrodes.gpio_excitation must be false: the cloth is not scanned by driving "
            "columns from GPIOs"
        )

    mapping = electrodes.get("map")
    if not isinstance(mapping, list):
        raise SystemExit("electrodes.map must be a list (empty while the harness is undocumented)")
    status = require_str(electrodes.get("mapping_status", MISSING_MAPPING), "electrodes.mapping_status")
    if status not in (MISSING_MAPPING, PROVIDED_MAPPING):
        raise SystemExit(
            "electrodes.mapping_status must be %s or %s" % (MISSING_MAPPING, PROVIDED_MAPPING)
        )

    entries = {name: None for name in ELECTRODE_NAMES}
    if not mapping:
        if status != MISSING_MAPPING:
            raise SystemExit(
                "electrodes.mapping_status %s needs a complete map of %d electrodes"
                % (PROVIDED_MAPPING, ELECTRODE_COUNT)
            )
    else:
        if status != PROVIDED_MAPPING:
            raise SystemExit(
                "electrodes.map is filled but mapping_status is %s; set %s once the harness is "
                "recorded" % (status, PROVIDED_MAPPING)
            )
        if len(mapping) != ELECTRODE_COUNT:
            raise SystemExit("electrodes.map must list all %d electrodes" % ELECTRODE_COUNT)
        occupied = set()
        for index, entry in enumerate(mapping):
            if not isinstance(entry, dict):
                raise SystemExit("electrodes.map[%d] must be an object" % index)
            name = require_str(entry.get("electrode"), "electrodes.map[%d].electrode" % index)
            if name not in entries:
                raise SystemExit(
                    "electrodes.map[%d].electrode %r is not one of %s"
                    % (index, name, ELECTRODE_NAMES)
                )
            if entries[name] is not None:
                raise SystemExit("electrodes.map lists %s more than once" % name)
            adc_id = require_int(entry.get("adc_id"), "electrodes.map[%d].adc_id" % index, 1, adc_count)
            if adc_id == adc_count:
                raise SystemExit(
                    "electrodes.map[%d] puts %s on ADC%d, which is the FSR ADC; electrode AINs are "
                    "wired to ADC1..ADC%d" % (index, name, adc_count, adc_count - 1)
                )
            adc_input = require_int(
                entry.get("adc_input"), "electrodes.map[%d].adc_input" % index, 0, 3
            )
            if (adc_id, adc_input) in occupied:
                raise SystemExit(
                    "electrodes.map[%d] assigns %s to ADC%d AIN%d, already taken by another "
                    "electrode" % (index, name, adc_id, adc_input)
                )
            occupied.add((adc_id, adc_input))
            entries[name] = (adc_id - 1, adc_input)

    channels = []
    for position, name in enumerate(ELECTRODE_NAMES, start=1):
        mapped = entries[name]
        channel_position = (position - 1) % ELECTRODE_ROWS + 1
        channels.append(
            {
                "channel_id": position - 1,
                "adc_index": mapped[0] if mapped else UNMAPPED,
                "adc_input": mapped[1] if mapped else UNMAPPED,
                "mux_code": 8 + mapped[1] if mapped else UNMAPPED,
                "kind": "ELECTRODE",
                "role": ELECTRODE_ROLES[name[0]],
                "position": channel_position,
                "name": name,
            }
        )
    return channels, status


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
        raise SystemExit("fsr must be an object or null")
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


def build_channels(electrode_channels, fsr):
    channels = list(electrode_channels)
    if fsr is not None:
        adc_index = 3  # validated: fsr.adc_id == 4 and pins.cs[3] selects ADC4
        for entry in fsr["channels"]:
            channels.append(
                {
                    "channel_id": entry["channel_id"],
                    "adc_index": adc_index,
                    "adc_input": entry["adc_input"],
                    "mux_code": entry["mux_code"],
                    "kind": "FSR",
                    "role": "NONE",
                    "position": 0,
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


def render_header(config, config_path, profile, ads, pins, fsr, electrodes, stream, channels):
    def cstr(value):
        return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'

    miso = [str(pin) for pin in pins[2]]
    cs = [str(pin) for pin in pins[3]]
    fsr_ids = [str(item["channel_id"]) for item in fsr["channels"]] if fsr else []
    fsr_ids.sort(key=int)

    digest = hashlib.sha256(config_path.read_bytes()).hexdigest()
    channel_count = len(channels)
    electrode_count = len(electrodes[0]) if electrodes else 0
    mapping_status = electrodes[1] if electrodes else MISSING_MAPPING
    row_bias = ROW_BIAS
    column_bias = COLUMN_BIAS
    divider_ohm = fsr["divider_ohm"] if fsr else 0
    excitation_mv = fsr["excitation_mv"] if fsr else 0
    scan_mode = config.get("scan_mode") or ("OFFLINE_ELECTRODE_READ" if electrodes else "FSR_ONLY_2CH")

    lines = []
    lines.append("// AUTO-GENERATED FILE - do not edit by hand.")
    lines.append("// Source: %s (sha256 %s)" % (display_path(config_path), digest))
    lines.append("// Regenerate: python3 scripts/generate_sensor_fsr2_config.py --config %s"
                 % display_path(config_path))
    lines.append("//")
    lines.append("// V2 board: four ADS1220 share SCLK/MOSI.  Every electrode and every FSR")
    lines.append("// divider is read on its own single-ended AIN; no GPIO drives a column.")
    if electrodes and mapping_status == MISSING_MAPPING:
        lines.append("//")
        lines.append("// WIRING NOT RECORDED: electrode channels are emitted with sentinel")
        lines.append("// 0xFF (unmapped) and the firmware reports null + NO_DATA for them.")
        lines.append("// Fill electrodes.map in the JSON once the harness is documented.")
    lines.append("#pragma once")
    lines.append("")
    lines.append('#include "fsr2.h"')
    lines.append("")
    lines.append("// MISO/CS are ordered by ADS1220 index: ADC1..ADC%d." % len(cs))
    lines.append("static const uint8_t FSR2_MISO_PINS[%d] = {%s};" % (len(miso), ", ".join(miso)))
    lines.append("static const uint8_t FSR2_CS_PINS[%d] = {%s};" % (len(cs), ", ".join(cs)))
    if fsr_ids:
        lines.append("static const uint8_t FSR2_FSR_CHANNEL_INDICES[%d] = {%s};"
                     % (len(fsr_ids), ", ".join(fsr_ids)))
    lines.append("")
    lines.append("static const char FSR2_ELECTRODE_MAPPING[] = %s;" % cstr(mapping_status))
    lines.append("static const char FSR2_ROW_BIAS[] = %s;" % cstr(row_bias))
    lines.append("static const char FSR2_COLUMN_BIAS[] = %s;" % cstr(column_bias))
    lines.append("")
    lines.append("// Buffer sizes the sketch must provide; confirmed against struct Fsr2Profile.")
    lines.append("static const uint16_t FSR2_MAX_LINE_BYTES = %d;" % stream["max_line_bytes"])
    lines.append("static const uint16_t FSR2_COMMAND_BUFFER_BYTES = %d;"
                 % stream["max_command_bytes"])
    lines.append("")
    lines.append("static const Fsr2ChannelConfig FSR2_CHANNELS[%d] = {" % channel_count)
    kind_names = {"ELECTRODE": "FSR2_KIND_ELECTRODE", "FSR": "FSR2_KIND_FSR"}
    role_names = {"NONE": "FSR2_ROLE_NONE", "ROW": "FSR2_ROLE_ROW", "COLUMN": "FSR2_ROLE_COLUMN"}
    for channel in channels:
        lines.append(
            "    {%d, %d, %d, %s, %s, %d, %s},  // channel %d"
            % (
                channel["adc_index"],
                channel["adc_input"],
                channel["mux_code"],
                kind_names[channel["kind"]],
                role_names[channel["role"]],
                channel["position"],
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
    lines.append("    %s,  // scan_mode" % cstr(scan_mode))
    lines.append("    %s,  // reference_mode_name" % cstr(ads["reference_name"]))
    lines.append("    %dUL,  // serial_baud" % config["serial_baud"])
    lines.append("    %d,  // sclk_pin" % pins[0])
    lines.append("    %d,  // mosi_pin" % pins[1])
    lines.append("    %d,  // adc_count" % len(cs))
    lines.append("    %d,  // channel_count" % channel_count)
    lines.append("    FSR2_MISO_PINS,  // miso_pins")
    lines.append("    FSR2_CS_PINS,  // cs_pins")
    lines.append("    %d,  // electrode_count" % electrode_count)
    lines.append("    %d,  // electrode_rows" % (ELECTRODE_ROWS if electrodes else 0))
    lines.append("    %d,  // electrode_columns" % (ELECTRODE_COLUMNS if electrodes else 0))
    lines.append("    %s,  // electrode_mapping" % ("FSR2_ELECTRODE_MAPPING" if electrodes else "nullptr"))
    lines.append("    %s,  // row_bias" % ("FSR2_ROW_BIAS" if electrodes else "nullptr"))
    lines.append("    %s,  // column_bias" % ("FSR2_COLUMN_BIAS" if electrodes else "nullptr"))
    lines.append("    %d,  // fsr_count" % (len(fsr["channels"]) if fsr else 0))
    lines.append("    %s,  // fsr_channel_indices" % ("FSR2_FSR_CHANNEL_INDICES" if fsr else "nullptr"))
    lines.append("    %d,  // fsr_divider_ohm" % divider_ohm)
    lines.append("    %d,  // fsr_excitation_mv" % excitation_mv)
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
    if profile in HISTORICAL_PROFILES:
        raise SystemExit(
            "sensor_profile %s is withdrawn: the pressure cloth has twelve independent electrodes "
            "and is not scanned as 6x6 cells.  Use MATRIX_ELECTRODES_12 (optionally with the two "
            "FSR channels) and record the real R/C to ADC/AIN harness mapping first." % profile
        )
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

    if config.get("matrix") is not None:
        raise SystemExit(
            "matrix must be null: the cloth has no scanned matrix; electrodes are described by "
            "the electrodes block"
        )

    electrodes = None
    fsr_config = config.get("fsr")
    if profile == "FSR_ONLY":
        if config.get("electrodes") is not None:
            raise SystemExit("FSR_ONLY must set electrodes to null; use MATRIX_ELECTRODES_12")
        if fsr_config is None:
            raise SystemExit("FSR_ONLY needs the fsr block")
        electrode_count = 0
    else:
        if fsr_config is not None and not isinstance(fsr_config, dict):
            raise SystemExit("fsr must be an object or null")
        electrodes = validate_electrodes(config.get("electrodes"), adc_count, fsr_config is not None)
        electrode_count = len(electrodes[0])

    fsr = None
    channel_count = electrode_count
    if fsr_config is not None:
        channel_count += 2
        fsr = validate_fsr(fsr_config, pins, adc_count, channel_count)

    channels = build_channels(electrodes[0] if electrodes else [], fsr)
    if len(channels) != channel_count:  # pragma: no cover - defensive
        raise SystemExit("internal channel count mismatch")

    text = render_header(
        config, config_path, profile, ads, pins, fsr, electrodes, stream, channels
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return {
        "profile": profile,
        "channel_count": channel_count,
        "mapping_status": electrodes[1] if electrodes else "NOT_APPLICABLE",
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
        "wrote %s (%s profile, %d channels, mapping %s, header sha256 %s)"
        % (
            result["output"],
            result["profile"],
            result["channel_count"],
            result["mapping_status"],
            result["sha256"][:16],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
