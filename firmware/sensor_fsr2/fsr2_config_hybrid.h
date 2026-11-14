// AUTO-GENERATED FILE - do not edit by hand.
// Source: config/sensor_esp32_fsr2_hybrid.json (sha256 3d134fe83b6be0f41a1299c13af046252bed6ebd4af2d4b2a6a791eae23aa5cc)
// Regenerate: python3 scripts/generate_sensor_fsr2_config.py --config config/sensor_esp32_fsr2_hybrid.json
//
// V2 board: four ADS1220 share SCLK/MOSI; ADC1/ADC2/ADC3 carry the 6x6 matrix
// rows, ADC4 carries the two FSR dividers.  Channel order is the protocol order.
#pragma once

#include "fsr2.h"

// MISO/CS are ordered by ADS1220 index: ADC1..ADC4.
static const uint8_t FSR2_MISO_PINS[4] = {34, 35, 26, 33};
static const uint8_t FSR2_CS_PINS[4] = {21, 22, 5, 32};
static const uint8_t FSR2_COLUMN_PINS[6] = {4, 13, 14, 25, 27, 19};
static const uint8_t FSR2_FSR_CHANNEL_INDICES[2] = {36, 37};

// Buffer sizes the sketch must provide; confirmed against struct Fsr2Profile.
static const uint16_t FSR2_MAX_LINE_BYTES = 8192;
static const uint16_t FSR2_COMMAND_BUFFER_BYTES = 512;

static const Fsr2ChannelConfig FSR2_CHANNELS[38] = {
    {0, 0, 8, FSR2_KIND_MATRIX_CELL, 0, 0, "R1C1"},  // channel 0
    {0, 0, 8, FSR2_KIND_MATRIX_CELL, 0, 1, "R1C2"},  // channel 1
    {0, 0, 8, FSR2_KIND_MATRIX_CELL, 0, 2, "R1C3"},  // channel 2
    {0, 0, 8, FSR2_KIND_MATRIX_CELL, 0, 3, "R1C4"},  // channel 3
    {0, 0, 8, FSR2_KIND_MATRIX_CELL, 0, 4, "R1C5"},  // channel 4
    {0, 0, 8, FSR2_KIND_MATRIX_CELL, 0, 5, "R1C6"},  // channel 5
    {0, 1, 9, FSR2_KIND_MATRIX_CELL, 1, 0, "R2C1"},  // channel 6
    {0, 1, 9, FSR2_KIND_MATRIX_CELL, 1, 1, "R2C2"},  // channel 7
    {0, 1, 9, FSR2_KIND_MATRIX_CELL, 1, 2, "R2C3"},  // channel 8
    {0, 1, 9, FSR2_KIND_MATRIX_CELL, 1, 3, "R2C4"},  // channel 9
    {0, 1, 9, FSR2_KIND_MATRIX_CELL, 1, 4, "R2C5"},  // channel 10
    {0, 1, 9, FSR2_KIND_MATRIX_CELL, 1, 5, "R2C6"},  // channel 11
    {1, 0, 8, FSR2_KIND_MATRIX_CELL, 2, 0, "R3C1"},  // channel 12
    {1, 0, 8, FSR2_KIND_MATRIX_CELL, 2, 1, "R3C2"},  // channel 13
    {1, 0, 8, FSR2_KIND_MATRIX_CELL, 2, 2, "R3C3"},  // channel 14
    {1, 0, 8, FSR2_KIND_MATRIX_CELL, 2, 3, "R3C4"},  // channel 15
    {1, 0, 8, FSR2_KIND_MATRIX_CELL, 2, 4, "R3C5"},  // channel 16
    {1, 0, 8, FSR2_KIND_MATRIX_CELL, 2, 5, "R3C6"},  // channel 17
    {1, 1, 9, FSR2_KIND_MATRIX_CELL, 3, 0, "R4C1"},  // channel 18
    {1, 1, 9, FSR2_KIND_MATRIX_CELL, 3, 1, "R4C2"},  // channel 19
    {1, 1, 9, FSR2_KIND_MATRIX_CELL, 3, 2, "R4C3"},  // channel 20
    {1, 1, 9, FSR2_KIND_MATRIX_CELL, 3, 3, "R4C4"},  // channel 21
    {1, 1, 9, FSR2_KIND_MATRIX_CELL, 3, 4, "R4C5"},  // channel 22
    {1, 1, 9, FSR2_KIND_MATRIX_CELL, 3, 5, "R4C6"},  // channel 23
    {2, 0, 8, FSR2_KIND_MATRIX_CELL, 4, 0, "R5C1"},  // channel 24
    {2, 0, 8, FSR2_KIND_MATRIX_CELL, 4, 1, "R5C2"},  // channel 25
    {2, 0, 8, FSR2_KIND_MATRIX_CELL, 4, 2, "R5C3"},  // channel 26
    {2, 0, 8, FSR2_KIND_MATRIX_CELL, 4, 3, "R5C4"},  // channel 27
    {2, 0, 8, FSR2_KIND_MATRIX_CELL, 4, 4, "R5C5"},  // channel 28
    {2, 0, 8, FSR2_KIND_MATRIX_CELL, 4, 5, "R5C6"},  // channel 29
    {2, 1, 9, FSR2_KIND_MATRIX_CELL, 5, 0, "R6C1"},  // channel 30
    {2, 1, 9, FSR2_KIND_MATRIX_CELL, 5, 1, "R6C2"},  // channel 31
    {2, 1, 9, FSR2_KIND_MATRIX_CELL, 5, 2, "R6C3"},  // channel 32
    {2, 1, 9, FSR2_KIND_MATRIX_CELL, 5, 3, "R6C4"},  // channel 33
    {2, 1, 9, FSR2_KIND_MATRIX_CELL, 5, 4, "R6C5"},  // channel 34
    {2, 1, 9, FSR2_KIND_MATRIX_CELL, 5, 5, "R6C6"},  // channel 35
    {3, 0, 8, FSR2_KIND_FSR, -1, -1, "FSR_A"},  // channel 36
    {3, 1, 9, FSR2_KIND_FSR, -1, -1, "FSR_B"},  // channel 37
};

// Field order must match struct Fsr2Profile in fsr2.h.
static const Fsr2Profile FSR2_PROFILE = {
    "tactile-esp32-01",  // device_id
    "tactile-fsr2hybrid-0.2.0",  // firmware_version
    "HYBRID_6X6_FSR2",  // sensor_profile
    "COLUMN_SCAN_6X6",  // scan_mode
    "AVDD_AVSS",  // reference_mode_name
    921600UL,  // serial_baud
    18,  // sclk_pin
    23,  // mosi_pin
    4,  // adc_count
    38,  // channel_count
    FSR2_MISO_PINS,  // miso_pins
    FSR2_CS_PINS,  // cs_pins
    6,  // matrix_rows
    6,  // matrix_cols
    3,  // matrix_adc_count
    2,  // matrix_rounds
    6,  // column_count
    FSR2_COLUMN_PINS,  // column_pins
    1000,  // matrix_settle_us
    200,  // matrix_pre_discharge_us
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

