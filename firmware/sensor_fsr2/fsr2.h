// Shared types for the V2 four-ADS1220 firmware.
//
// This header is hand written.  fsr2_config.h is generated from
// config/sensor_esp32_fsr2*.json and fills one Fsr2Profile instance; nothing
// here depends on a particular profile, which is what lets the host tests and
// the serial frame builder exercise both the FSR_ONLY and HYBRID_6X6_FSR2
// channel tables with the same sources.
#pragma once

#include <stdint.h>

// Channel identity, reported as "sensor_kind" in the protocol.
enum Fsr2SensorKind : uint8_t {
  FSR2_KIND_MATRIX_CELL = 0,
  FSR2_KIND_FSR = 1,
};

// Per-channel quality flags.  Same bit values as the historical 12-channel
// firmware so a host that already understands the old flags keeps working.
enum Fsr2ChannelFlag : uint8_t {
  FSR2_FLAG_SAT_HIGH = 0x01,
  FSR2_FLAG_SAT_LOW = 0x02,
  FSR2_FLAG_NEGATIVE_SINGLE_ENDED = 0x04,
  FSR2_FLAG_NEAR_RAIL = 0x08,
  FSR2_FLAG_STUCK_EXTREME = 0x10,
  FSR2_FLAG_NO_DATA = 0x20,
};

// ADS1220 runtime state, reported as "adc_status[].state".
enum Fsr2AdcState : uint8_t {
  FSR2_ADC_OK = 0,
  FSR2_ADC_CONFIG_ERROR = 1,
  FSR2_ADC_NO_RESPONSE = 2,
  FSR2_ADC_RECOVERING = 3,
  FSR2_ADC_FAILED = 4,
};

// One entry of the channel table.  The table index is the channel_id that the
// firmware reports, so channel order in fsr2_config.h is the protocol order.
struct Fsr2ChannelConfig {
  uint8_t adc_index;   // 0-based ADS1220 index; reported as ads1220_id = adc_index + 1
  uint8_t adc_input;   // AIN number on that ADS1220
  uint8_t mux_code;    // ADS1220 MUX[3:0] for single-ended AIN versus AVSS
  uint8_t kind;        // Fsr2SensorKind
  int8_t matrix_row;   // -1 when the channel is not a matrix cell
  int8_t matrix_col;   // -1 when the channel is not a matrix cell
  const char* name;    // stable label, e.g. "R1C1" or "FSR_A"
};

// Everything the firmware needs to know about one board profile.  The field
// order is fixed: fsr2_config.h initialises this struct positionally.
struct Fsr2Profile {
  const char* device_id;
  const char* firmware_version;
  const char* sensor_profile;      // "FSR_ONLY" or "HYBRID_6X6_FSR2"
  const char* scan_mode;           // e.g. "FSR_ONLY_2CH"
  const char* reference_mode_name; // e.g. "AVDD_AVSS"

  uint32_t serial_baud;

  uint8_t sclk_pin;
  uint8_t mosi_pin;
  uint8_t adc_count;
  uint8_t channel_count;
  const uint8_t* miso_pins;  // one per ADS1220, ordered ADC1..ADC4
  const uint8_t* cs_pins;    // one per ADS1220, ordered ADC1..ADC4

  uint8_t matrix_rows;         // 0 when the profile has no matrix
  uint8_t matrix_cols;         // 0 when the profile has no matrix
  uint8_t matrix_adc_count;    // ADS1220s that carry matrix rows
  uint8_t matrix_rounds;       // AIN rounds per column (2 on the V2 board)
  uint8_t column_count;        // driven matrix columns
  const uint8_t* column_pins;  // may be nullptr when column_count is 0
  uint16_t matrix_settle_us;
  uint16_t matrix_pre_discharge_us;

  uint8_t fsr_count;
  const uint8_t* fsr_channel_indices;  // channel ids of the FSR entries, sorted
  uint16_t fsr_divider_ohm;            // nominal series resistor, for diagnostics only
  uint16_t fsr_excitation_mv;          // nominal supply across the divider

  const Fsr2ChannelConfig* channels;

  uint8_t reference_mode_code;  // VREF[1:0]
  uint8_t data_rate_code;       // DR[2:0]
  uint16_t data_rate_sps;
  uint16_t conversion_wait_us;
  uint16_t spi_half_period_us;
  uint8_t gain_code;   // GAIN[2:0]
  uint8_t pga_bypass;  // 1 when the PGA is bypassed

  uint16_t max_line_bytes;
  uint16_t max_command_bytes;
  uint16_t command_partial_timeout_ms;
  uint8_t frame_rate_window;
  uint8_t reinit_after_errors;
  uint16_t reinit_retry_interval_ms;
};

// Runtime status of one ADS1220, reported verbatim in "adc_status".
struct Fsr2AdcStatusSnapshot {
  uint8_t state;
  uint8_t consecutive_errors;
  uint16_t total_errors;
  uint16_t recovered;
  const char* last_error;  // nullptr when the device is healthy
};

const char* fsr2AdcStateName(uint8_t state);
const char* fsr2SensorKindName(uint8_t kind);

// Returns the channel index of matrix cell (adc_index, round, column), or
// false when the profile layout does not contain that cell.
bool fsr2MatrixChannelIndex(const Fsr2Profile& profile, uint8_t adc_index, uint8_t round,
                            uint8_t column, uint8_t* out_channel);

// Checks that the generated channel table is internally consistent with the
// profile: dense channel ids, row-major matrix layout (row n on ADC n/2,
// AIN n%2), FSR channels last and on the last ADS1220.  The firmware refuses
// to stream when this fails instead of emitting a frame whose channels and
// metadata disagree.
bool fsr2ValidateLayout(const Fsr2Profile& profile);
