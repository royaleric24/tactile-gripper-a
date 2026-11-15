// AUTO-GENERATED FILE - do not edit by hand.
// Source: config/sensor_esp32_fsr2.json (sha256 e38792f6213369ff06a9b0caa055bb5eb8d37391e10136c548c3fe7e10c1c620)
// Regenerate: python3 scripts/generate_sensor_fsr2_config.py --config config/sensor_esp32_fsr2.json
//
// V2 board: four ADS1220 share SCLK/MOSI.  Every electrode and every FSR
// divider is read on its own single-ended AIN; no GPIO drives a column.
#pragma once

#include "fsr2.h"

// MISO/CS are ordered by ADS1220 index: ADC1..ADC4.
static const uint8_t FSR2_MISO_PINS[4] = {34, 35, 26, 33};
static const uint8_t FSR2_CS_PINS[4] = {21, 22, 5, 32};
static const uint8_t FSR2_FSR_CHANNEL_INDICES[2] = {0, 1};

static const char FSR2_ELECTRODE_MAPPING[] = "PENDING_REAL_WIRING";
static const char FSR2_ROW_BIAS[] = "PULLDOWN_10K_TO_GND";
static const char FSR2_COLUMN_BIAS[] = "PULLUP_1K_TO_3V3";

// Buffer sizes the sketch must provide; confirmed against struct Fsr2Profile.
static const uint16_t FSR2_MAX_LINE_BYTES = 8192;
static const uint16_t FSR2_COMMAND_BUFFER_BYTES = 512;

static const Fsr2ChannelConfig FSR2_CHANNELS[2] = {
    {3, 0, 8, FSR2_KIND_FSR, FSR2_ROLE_NONE, 0, "FSR_A"},  // channel 0
    {3, 1, 9, FSR2_KIND_FSR, FSR2_ROLE_NONE, 0, "FSR_B"},  // channel 1
};

// Field order must match struct Fsr2Profile in fsr2.h.
static const Fsr2Profile FSR2_PROFILE = {
    "tactile-esp32-01",  // device_id
    "tactile-fsr2-0.2.0",  // firmware_version
    "FSR_ONLY",  // sensor_profile
    "FSR_ONLY_2CH",  // scan_mode
    "AVDD_AVSS",  // reference_mode_name
    921600UL,  // serial_baud
    18,  // sclk_pin
    23,  // mosi_pin
    4,  // adc_count
    2,  // channel_count
    FSR2_MISO_PINS,  // miso_pins
    FSR2_CS_PINS,  // cs_pins
    0,  // electrode_count
    0,  // electrode_rows
    0,  // electrode_columns
    nullptr,  // electrode_mapping
    nullptr,  // row_bias
    nullptr,  // column_bias
    2,  // fsr_count
    FSR2_FSR_CHANNEL_INDICES,  // fsr_channel_indices
    10000,  // fsr_divider_ohm
    3300,  // fsr_excitation_mv
    FSR2_CHANNELS,  // channels
    3,  // reference_mode_code
    4,  // data_rate_code
    330,  // data_rate_sps
    4500,  // conversion_wait_us
    1,  // spi_half_period_us
    0,  // gain_code
    1,  // pga_bypass
    8192,  // max_line_bytes
    512,  // max_command_bytes
    1000,  // command_partial_timeout_ms
    32,  // frame_rate_window
    3,  // reinit_after_errors
    500,  // reinit_retry_interval_ms
};

