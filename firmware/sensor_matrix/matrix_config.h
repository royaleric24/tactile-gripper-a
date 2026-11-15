#pragma once
// Offline 6x6 row-scan prototype configuration.
// This file is NOT flashed by the current 12-channel firmware.
#include <stdint.h>

static const char MATRIX_FIRMWARE_VERSION[] = "tactile-matrix-0.1.0";
static const char MATRIX_DEVICE_ID[] = "tactile-esp32-01";
static const uint8_t MATRIX_ROWS = 6;
static const uint8_t MATRIX_COLS = 6;
static const uint8_t MATRIX_CELL_COUNT = 36;

// R1..R6: output-capable GPIOs, each through a 1k series resistor.
static const uint8_t MATRIX_ROW_PINS[MATRIX_ROWS] = {4, 13, 14, 25, 27, 32};

// Two columns per ADC; ADS1220 index 0..2, AIN 0..3.
static const uint8_t MATRIX_COLUMN_ADC[MATRIX_COLS] = {0, 0, 1, 1, 2, 2};
static const uint8_t MATRIX_COLUMN_AIN[MATRIX_COLS] = {0, 1, 0, 1, 0, 1};

static const uint16_t MATRIX_PRE_DISCHARGE_US = 200;
static const uint16_t MATRIX_SETTLE_US = 1000;
static const uint16_t MATRIX_CONVERSION_WAIT_US = 4500;
static const uint16_t MATRIX_READ_OVERHEAD_US = 100;

// AVDD-AVSS: the row driver and ADC reference share the same 3.3 V rail.
static const uint8_t MATRIX_REFERENCE_CONFIG = 0x80;
static const uint8_t MATRIX_MUX_BASE = 8;
