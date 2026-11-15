// Shared types for the V2 four-ADS1220 firmware.
//
// This header is hand written.  fsr2_config.h is generated from
// config/sensor_esp32_fsr2*.json / config/sensor_esp32_electrodes12*.json and
// fills one Fsr2Profile instance; nothing here depends on a particular profile.
//
// Topology note (2026-11-15 correction): the pressure cloth exposes twelve
// independent electrodes.  R1..R6 are each pulled to GND through 10 kOhm and
// C1..C6 are each pulled to 3.3 V through 1 kOhm; every electrode is read on
// its own ADS1220 single-ended AIN.  There is no GPIO column excitation and no
// 6x6 scan.  Which electrode lands on which ADC/AIN is not known yet, so a
// profile may carry an explicitly UNMAPPED channel table instead of invented
// pins.
#pragma once

#include <stdint.h>

// Sentinel for "this electrode has no assigned ADC/AIN yet".
static const uint8_t FSR2_UNMAPPED = 0xFF;

// Channel identity, reported as "sensor_kind" in the protocol.
enum Fsr2SensorKind : uint8_t {
  FSR2_KIND_ELECTRODE = 0,
  FSR2_KIND_FSR = 1,
};

// Electrode role inside the cloth; reported as "role" in electrode_layout.
enum Fsr2ElectrodeRole : uint8_t {
  FSR2_ROLE_NONE = 0,
  FSR2_ROLE_ROW = 1,     // R1..R6, 10 kOhm to GND
  FSR2_ROLE_COLUMN = 2,  // C1..C6, 1 kOhm to 3.3 V
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
// firmware reports, so channel order in the generated header is protocol order.
struct Fsr2ChannelConfig {
  uint8_t adc_index;  // 0-based ADS1220 index; reported as ads1220_id = index + 1
  uint8_t adc_input;  // AIN number on that ADS1220, or FSR2_UNMAPPED
  uint8_t mux_code;   // ADS1220 MUX[3:0] for single-ended AIN versus AVSS
  uint8_t kind;       // Fsr2SensorKind
  uint8_t role;       // Fsr2ElectrodeRole; FSR2_ROLE_NONE for FSR channels
  uint8_t position;   // 1..6 for R1..C6, 0 for FSR channels
  const char* name;   // stable label, e.g. "R3", "C5", "FSR_A"
};

// Everything the firmware needs to know about one board profile.  The field
// order is fixed: the generated header initialises this struct positionally.
struct Fsr2Profile {
  const char* device_id;
  const char* firmware_version;
  const char* sensor_profile;       // "FSR_ONLY" or "MATRIX_ELECTRODES_12"
  const char* scan_mode;            // e.g. "FSR_ONLY_2CH" or "STATIC_ELECTRODE_READ"
  const char* reference_mode_name;  // e.g. "AVDD_AVSS"

  uint32_t serial_baud;

  uint8_t sclk_pin;
  uint8_t mosi_pin;
  uint8_t adc_count;
  uint8_t channel_count;
  const uint8_t* miso_pins;  // one per ADS1220, ordered ADC1..ADC4
  const uint8_t* cs_pins;    // one per ADS1220, ordered ADC1..ADC4

  uint8_t electrode_count;    // 12 for the real cloth, 0 for FSR-only
  uint8_t electrode_rows;     // 6
  uint8_t electrode_columns;  // 6
  const char* electrode_mapping;  // "PENDING_REAL_WIRING" or "TABLE_PROVIDED"
  const char* row_bias;           // "PULLDOWN_10K_TO_GND"
  const char* column_bias;        // "PULLUP_1K_TO_3V3"

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
const char* fsr2ElectrodeRoleName(uint8_t role);

// True when every electrode channel has an assigned ADC/AIN.  The firmware
// streams the 12 channels as null + NO_DATA while this is false, instead of
// pretending an unknown wiring is measuring something.
bool fsr2ElectrodesMapped(const Fsr2Profile& profile);

// Checks that the generated channel table is internally consistent with the
// profile: dense channel ids, electrode block first (R1..Rn then C1..Cm) and
// FSR block last on the last ADS1220, mapping either complete and unique or
// explicitly absent.  The firmware refuses to stream when this fails instead
// of emitting a frame whose channels and metadata disagree.
bool fsr2ValidateLayout(const Fsr2Profile& profile);
