// AUTO-GENERATED FILE - do not edit by hand.
// Source: config/sensor_esp32_electrodes12_fsr2.json (sha256 9937489dbceb14c513aeba5cde201ad0bcd1bace1249d88a471c218e0d2c1951)
// Regenerate: python3 scripts/generate_sensor_fsr2_config.py --config config/sensor_esp32_electrodes12_fsr2.json
//
// V2 board: four ADS1220 share SCLK/MOSI.  Every electrode and every FSR
// divider is read on its own single-ended AIN; no GPIO drives a column.
//
// WIRING NOT RECORDED: electrode channels are emitted with sentinel
// 0xFF (unmapped) and the firmware reports null + NO_DATA for them.
// Fill electrodes.map in the JSON once the harness is documented.
#pragma once

#include "fsr2.h"

// MISO/CS are ordered by ADS1220 index: ADC1..ADC4.
static const uint8_t FSR2_MISO_PINS[4] = {34, 35, 26, 33};
static const uint8_t FSR2_CS_PINS[4] = {21, 22, 5, 32};
static const uint8_t FSR2_FSR_CHANNEL_INDICES[2] = {12, 13};

static const char FSR2_ELECTRODE_MAPPING[] = "PENDING_REAL_WIRING";
static const char FSR2_ROW_BIAS[] = "PULLDOWN_10K_TO_GND";
static const char FSR2_COLUMN_BIAS[] = "PULLUP_1K_TO_3V3";

// Buffer sizes the sketch must provide; confirmed against struct Fsr2Profile.
static const uint16_t FSR2_MAX_LINE_BYTES = 8192;
static const uint16_t FSR2_COMMAND_BUFFER_BYTES = 512;

static const Fsr2ChannelConfig FSR2_CHANNELS[14] = {
    {255, 255, 255, FSR2_KIND_ELECTRODE, FSR2_ROLE_ROW, 1, "R1"},  // channel 0
    {255, 255, 255, FSR2_KIND_ELECTRODE, FSR2_ROLE_ROW, 2, "R2"},  // channel 1
    {255, 255, 255, FSR2_KIND_ELECTRODE, FSR2_ROLE_ROW, 3, "R3"},  // channel 2
    {255, 255, 255, FSR2_KIND_ELECTRODE, FSR2_ROLE_ROW, 4, "R4"},  // channel 3
    {255, 255, 255, FSR2_KIND_ELECTRODE, FSR2_ROLE_ROW, 5, "R5"},  // channel 4
    {255, 255, 255, FSR2_KIND_ELECTRODE, FSR2_ROLE_ROW, 6, "R6"},  // channel 5
    {255, 255, 255, FSR2_KIND_ELECTRODE, FSR2_ROLE_COLUMN, 1, "C1"},  // channel 6
    {255, 255, 255, FSR2_KIND_ELECTRODE, FSR2_ROLE_COLUMN, 2, "C2"},  // channel 7
    {255, 255, 255, FSR2_KIND_ELECTRODE, FSR2_ROLE_COLUMN, 3, "C3"},  // channel 8
    {255, 255, 255, FSR2_KIND_ELECTRODE, FSR2_ROLE_COLUMN, 4, "C4"},  // channel 9
    {255, 255, 255, FSR2_KIND_ELECTRODE, FSR2_ROLE_COLUMN, 5, "C5"},  // channel 10
    {255, 255, 255, FSR2_KIND_ELECTRODE, FSR2_ROLE_COLUMN, 6, "C6"},  // channel 11
    {3, 0, 8, FSR2_KIND_FSR, FSR2_ROLE_NONE, 0, "FSR_A"},  // channel 12
    {3, 1, 9, FSR2_KIND_FSR, FSR2_ROLE_NONE, 0, "FSR_B"},  // channel 13
};

// Field order must match struct Fsr2Profile in fsr2.h.
static const Fsr2Profile FSR2_PROFILE = {
    "tactile-esp32-01",  // device_id
    "tactile-electrodes12fsr2-0.3.0",  // firmware_version
    "MATRIX_ELECTRODES_12",  // sensor_profile
    "OFFLINE_ELECTRODE_READ",  // scan_mode
    "AVDD_AVSS",  // reference_mode_name
    921600UL,  // serial_baud
    18,  // sclk_pin
    23,  // mosi_pin
    4,  // adc_count
    14,  // channel_count
    FSR2_MISO_PINS,  // miso_pins
    FSR2_CS_PINS,  // cs_pins
    12,  // electrode_count
    6,  // electrode_rows
    6,  // electrode_columns
    FSR2_ELECTRODE_MAPPING,  // electrode_mapping
    FSR2_ROW_BIAS,  // row_bias
    FSR2_COLUMN_BIAS,  // column_bias
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

