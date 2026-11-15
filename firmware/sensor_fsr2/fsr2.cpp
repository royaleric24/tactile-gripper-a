#include "fsr2.h"

#include <string.h>

namespace {

bool channelMapped(const Fsr2ChannelConfig& channel) {
  return channel.adc_index != FSR2_UNMAPPED && channel.adc_input != FSR2_UNMAPPED &&
         channel.mux_code != FSR2_UNMAPPED;
}

// Only an explicitly pending/missing mapping may leave electrodes unmapped.
// "PENDING_REAL_WIRING" is the protocol status; "MISSING_REAL_WIRING" is the
// older spelling kept so an older generated header still validates.
bool mappingAllowsUnmapped(const char* status) {
  if (status == nullptr) return false;
  return strncmp(status, "PENDING", 7) == 0 || strncmp(status, "MISSING", 7) == 0;
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
    case FSR2_KIND_ELECTRODE: return "ELECTRODE";
    case FSR2_KIND_FSR: return "FSR";
    default: return "UNKNOWN";
  }
}

const char* fsr2ElectrodeRoleName(uint8_t role) {
  switch (role) {
    case FSR2_ROLE_ROW: return "ROW";
    case FSR2_ROLE_COLUMN: return "COLUMN";
    default: return "NONE";
  }
}

bool fsr2ElectrodesMapped(const Fsr2Profile& profile) {
  if (profile.electrode_count == 0) return true;
  for (uint8_t channel_id = 0; channel_id < profile.channel_count; ++channel_id) {
    const Fsr2ChannelConfig& channel = profile.channels[channel_id];
    if (channel.kind != FSR2_KIND_ELECTRODE) continue;
    if (!channelMapped(channel)) return false;
  }
  return true;
}

bool fsr2ValidateLayout(const Fsr2Profile& profile) {
  if (profile.device_id == nullptr || profile.firmware_version == nullptr) return false;
  if (profile.sensor_profile == nullptr || profile.scan_mode == nullptr) return false;
  if (profile.reference_mode_name == nullptr) return false;
  if (profile.electrode_count > 0) {
    // These describe the cloth; a profile without electrodes leaves them null.
    if (profile.electrode_mapping == nullptr) return false;
    if (profile.row_bias == nullptr || profile.column_bias == nullptr) return false;
  }
  if (profile.adc_count == 0 || profile.adc_count > 4) return false;
  if (profile.channel_count == 0) return false;
  if (profile.channels == nullptr) return false;
  if (profile.miso_pins == nullptr || profile.cs_pins == nullptr) return false;
  if (profile.fsr_count > 2 || profile.fsr_count > profile.channel_count) return false;
  if (profile.fsr_count > 0 && profile.fsr_channel_indices == nullptr) return false;

  const uint8_t electrode_count = profile.electrode_count;
  if (electrode_count > 0) {
    if (profile.electrode_rows == 0 || profile.electrode_columns == 0) return false;
    // A 6x6 cloth exposes six row and six column electrodes: 12 nodes, not 36
    // cells.  rows + columns is the electrode count the table must contain.
    if (static_cast<uint16_t>(profile.electrode_rows) +
            static_cast<uint16_t>(profile.electrode_columns) !=
        electrode_count) {
      return false;
    }
    if (static_cast<uint16_t>(electrode_count) + profile.fsr_count != profile.channel_count) {
      return false;
    }
  } else {
    if (profile.electrode_rows != 0 || profile.electrode_columns != 0) return false;
    if (profile.channel_count != profile.fsr_count) return false;
  }

  bool any_mapped = false;
  bool any_unmapped = false;
  for (uint8_t channel_id = 0; channel_id < profile.channel_count; ++channel_id) {
    const Fsr2ChannelConfig& channel = profile.channels[channel_id];
    if (channel.name == nullptr) return false;
    if (channel.kind == FSR2_KIND_ELECTRODE) {
      if (channel_id >= electrode_count) return false;
      const uint8_t row_or_column =
          channel_id < profile.electrode_rows ? FSR2_ROLE_ROW : FSR2_ROLE_COLUMN;
      if (channel.role != row_or_column) return false;
      const uint8_t expected_position =
          static_cast<uint8_t>(channel_id % profile.electrode_rows + 1);
      if (channel.position != expected_position) return false;
      if (channelMapped(channel)) {
        any_mapped = true;
        if (channel.adc_index == profile.adc_count - 1) {
          // The last ADS1220 is reserved for the FSR dividers.
          return false;
        }
        if (channel.adc_input > 3) return false;
        if (channel.mux_code != static_cast<uint8_t>(8 + channel.adc_input)) return false;
      } else {
        any_unmapped = true;
        if (!mappingAllowsUnmapped(profile.electrode_mapping)) return false;
      }
    } else if (channel.kind == FSR2_KIND_FSR) {
      if (channel_id < electrode_count) return false;
      if (!channelMapped(channel)) return false;
      if (channel.adc_input > 3) return false;
      if (channel.mux_code != static_cast<uint8_t>(8 + channel.adc_input)) return false;
      if (channel.adc_index != static_cast<uint8_t>(profile.adc_count - 1)) return false;
      if (profile.fsr_count == 1 && (channel.adc_input != 0 || strcmp(channel.name, "FSR_A") != 0)) {
        return false;
      }
    } else {
      return false;
    }
  }
  if (any_mapped && any_unmapped) return false;  // partial tables are a wiring bug

  for (uint8_t index = 0; index < profile.fsr_count; ++index) {
    if (profile.fsr_channel_indices[index] != electrode_count + index) return false;
  }
  return true;
}
