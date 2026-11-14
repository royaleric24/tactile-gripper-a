#include "fsr2.h"

namespace {

int8_t safeDivide(uint8_t value, uint8_t divisor) {
  if (divisor == 0) return -1;
  return static_cast<int8_t>(value / divisor);
}

}  // namespace

const char* fsr2AdcStateName(uint8_t state) {
  switch (state) {
    case FSR2_ADC_OK: return "OK";
    case FSR2_ADC_CONFIG_ERROR: return "CONFIG_ERROR";
    case FSR2_ADC_NO_RESPONSE: return "NO_RESPONSE";
    case FSR2_ADC_RECOVERING: return "RECOVERING";
    case FSR2_ADC_FAILED: return "FAILED";
    default: return "UNKNOWN";
  }
}

const char* fsr2SensorKindName(uint8_t kind) {
  switch (kind) {
    case FSR2_KIND_MATRIX_CELL: return "MATRIX_CELL";
    case FSR2_KIND_FSR: return "FSR";
    default: return "UNKNOWN";
  }
}

bool fsr2MatrixChannelIndex(const Fsr2Profile& profile, uint8_t adc_index, uint8_t round,
                            uint8_t column, uint8_t* out_channel) {
  if (out_channel == nullptr) return false;
  if (profile.matrix_rows == 0 || profile.matrix_cols == 0) return false;
  if (profile.matrix_rounds == 0) return false;
  if (adc_index >= profile.matrix_adc_count) return false;
  if (round >= profile.matrix_rounds) return false;
  if (column >= profile.matrix_cols) return false;
  const uint16_t row = static_cast<uint16_t>(adc_index) * profile.matrix_rounds + round;
  if (row >= profile.matrix_rows) return false;
  *out_channel = static_cast<uint8_t>(row * profile.matrix_cols + column);
  return true;
}

bool fsr2ValidateLayout(const Fsr2Profile& profile) {
  if (profile.device_id == nullptr || profile.firmware_version == nullptr) return false;
  if (profile.sensor_profile == nullptr || profile.scan_mode == nullptr) return false;
  if (profile.reference_mode_name == nullptr) return false;
  if (profile.adc_count == 0 || profile.adc_count > 4) return false;
  if (profile.channel_count == 0) return false;
  if (profile.channels == nullptr) return false;
  if (profile.miso_pins == nullptr || profile.cs_pins == nullptr) return false;
  if (profile.fsr_count == 0 || profile.fsr_channel_indices == nullptr) return false;
  if (profile.fsr_count > profile.channel_count) return false;
  if (profile.column_count > 0 && profile.column_pins == nullptr) return false;
  if (profile.matrix_cols > profile.column_count) return false;

  const uint16_t matrix_channels =
      static_cast<uint16_t>(profile.matrix_rows) * profile.matrix_cols;
  if (profile.matrix_rows == 0) {
    if (profile.matrix_cols != 0 || profile.column_count != 0) return false;
    if (profile.matrix_adc_count != 0 || profile.matrix_rounds != 0) return false;
    if (profile.channel_count != profile.fsr_count) return false;
  } else {
    if (profile.matrix_cols == 0) return false;
    if (profile.matrix_adc_count == 0 || profile.matrix_rounds == 0) return false;
    if (profile.column_count != profile.matrix_cols) return false;
    if (profile.matrix_rows !=
        static_cast<uint8_t>(profile.matrix_adc_count * profile.matrix_rounds)) {
      return false;
    }
    if (matrix_channels + profile.fsr_count != profile.channel_count) return false;
    // The FSR ADC is the last ADS1220, after the matrix row ADCs.
    if (profile.matrix_adc_count + 1 > profile.adc_count) return false;
  }

  for (uint8_t channel_id = 0; channel_id < profile.channel_count; ++channel_id) {
    const Fsr2ChannelConfig& channel = profile.channels[channel_id];
    if (channel.name == nullptr) return false;
    if (channel.adc_index >= profile.adc_count) return false;
    if (channel.adc_input > 3) return false;
    if (channel.mux_code != static_cast<uint8_t>(8 + channel.adc_input)) return false;
    if (channel_id < matrix_channels) {
      const int8_t row = safeDivide(channel_id, profile.matrix_cols);
      const int8_t col = static_cast<int8_t>(channel_id % profile.matrix_cols);
      if (row < 0) return false;
      if (channel.kind != FSR2_KIND_MATRIX_CELL) return false;
      if (channel.matrix_row != row || channel.matrix_col != col) return false;
      if (channel.adc_index >= profile.matrix_adc_count) return false;
      if (channel.adc_index != safeDivide(static_cast<uint8_t>(row), profile.matrix_rounds)) {
        return false;
      }
      if (channel.adc_input != static_cast<uint8_t>(row % profile.matrix_rounds)) return false;
    } else {
      if (channel.kind != FSR2_KIND_FSR) return false;
      if (channel.matrix_row != -1 || channel.matrix_col != -1) return false;
      if (channel.adc_index != static_cast<uint8_t>(profile.adc_count - 1)) return false;
    }
  }

  for (uint8_t index = 0; index < profile.fsr_count; ++index) {
    if (profile.fsr_channel_indices[index] != matrix_channels + index) return false;
  }
  return true;
}
