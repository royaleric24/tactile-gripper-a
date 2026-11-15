#include "frame_builder_fsr2.h"

#include "json_writer.h"

namespace {

const char* kChannelConfigStatus = "IMPLEMENTED_UNVERIFIED";

void writeKey(JsonLineWriter& writer, const char* name) { writer.key(name); }

void appendPins(JsonLineWriter& writer, const Fsr2Profile& profile) {
  writer.ch('{');
  writeKey(writer, "sclk");
  writer.u32(profile.sclk_pin);
  writeKey(writer, "mosi");
  writer.u32(profile.mosi_pin);
  writeKey(writer, "miso");
  writer.ch('[');
  for (uint8_t index = 0; index < profile.adc_count; ++index) {
    if (index > 0) writer.ch(',');
    writer.u32(profile.miso_pins[index]);
  }
  writer.ch(']');
  writeKey(writer, "cs");
  writer.ch('[');
  for (uint8_t index = 0; index < profile.adc_count; ++index) {
    if (index > 0) writer.ch(',');
    writer.u32(profile.cs_pins[index]);
  }
  writer.ch(']');
  writer.ch('}');
}

void appendAdcStatus(JsonLineWriter& writer, const Fsr2AdcStatusSnapshot* status, uint8_t count) {
  writer.ch('[');
  for (uint8_t index = 0; index < count; ++index) {
    if (index > 0) writer.ch(',');
    writer.ch('{');
    writeKey(writer, "id");
    writer.u32(index + 1);
    writeKey(writer, "state");
    writer.str(fsr2AdcStateName(status[index].state));
    writeKey(writer, "code");
    writer.u32(status[index].state);
    writeKey(writer, "consecutive_errors");
    writer.u32(status[index].consecutive_errors);
    writeKey(writer, "total_errors");
    writer.u32(status[index].total_errors);
    writeKey(writer, "recovered");
    writer.u32(status[index].recovered);
    writeKey(writer, "last_error");
    if (status[index].last_error == nullptr) {
      writer.nul();
    } else {
      writer.str(status[index].last_error);
    }
    writer.ch('}');
  }
  writer.ch(']');
}

void appendChannelConfig(JsonLineWriter& writer, const Fsr2Profile& profile) {
  writer.ch('{');
  writeKey(writer, "status");
  writer.str(kChannelConfigStatus);
  // The cloth has no scanned matrix; these stay null so an old consumer cannot
  // mistake the electrode list for a 6x6 cell map.
  writeKey(writer, "matrix_rows");
  writer.nul();
  writeKey(writer, "matrix_cols");
  writer.nul();
  writeKey(writer, "adc_count");
  writer.u32(profile.adc_count);
  writeKey(writer, "scan_mode");
  writer.str(profile.scan_mode);
  writeKey(writer, "unit");
  writer.str("ADC_COUNTS");
  writeKey(writer, "channels");
  writer.ch('[');
  for (uint8_t index = 0; index < profile.channel_count; ++index) {
    const Fsr2ChannelConfig& channel = profile.channels[index];
    const bool mapped = channel.adc_index != FSR2_UNMAPPED;
    if (index > 0) writer.ch(',');
    writer.ch('{');
    writeKey(writer, "channel_id");
    writer.u32(index);
    writeKey(writer, "name");
    writer.str(channel.name);
    writeKey(writer, "sensor_kind");
    writer.str(fsr2SensorKindName(channel.kind));
    writeKey(writer, "ads1220_id");
    if (mapped) {
      writer.u32(static_cast<uint8_t>(channel.adc_index + 1));
    } else {
      writer.nul();
    }
    writeKey(writer, "adc_input");
    if (mapped) {
      writer.u32(channel.adc_input);
    } else {
      writer.nul();
    }
    writeKey(writer, "mux_channel");
    if (mapped) {
      writer.u32(channel.mux_code);
    } else {
      writer.nul();
    }
    writeKey(writer, "matrix_row");
    writer.nul();
    writeKey(writer, "matrix_col");
    writer.nul();
    writeKey(writer, "electrode_role");
    writer.str(fsr2ElectrodeRoleName(channel.role));
    writeKey(writer, "electrode_position");
    if (channel.kind == FSR2_KIND_ELECTRODE) {
      writer.u32(channel.position);
    } else {
      writer.nul();
    }
    writer.ch('}');
  }
  writer.ch(']');
  writer.ch('}');
}

void appendElectrodeLayout(JsonLineWriter& writer, const Fsr2Profile& profile) {
  writer.ch('{');
  writeKey(writer, "count");
  writer.u32(profile.electrode_count);
  writeKey(writer, "rows");
  writer.u32(profile.electrode_rows);
  writeKey(writer, "columns");
  writer.u32(profile.electrode_columns);
  writeKey(writer, "mapping_status");
  writer.str(profile.electrode_mapping);
  writeKey(writer, "row_bias");
  writer.str(profile.row_bias);
  writeKey(writer, "column_bias");
  writer.str(profile.column_bias);
  writeKey(writer, "protocol_order");
  writer.str("R1..R6 THEN C1..C6");
  writeKey(writer, "gpio_excitation");
  writer.boolean(false);
  // Twelve electrode voltages are not 36 pressure cells and the firmware never
  // claims the harness itself is validated.
  writeKey(writer, "validated");
  writer.boolean(false);
  writeKey(writer, "channels");
  writer.ch('[');
  uint16_t channels_written = 0;
  for (uint8_t index = 0; index < profile.channel_count; ++index) {
    const Fsr2ChannelConfig& channel = profile.channels[index];
    if (channel.kind != FSR2_KIND_ELECTRODE) continue;
    const bool mapped = channel.adc_index != FSR2_UNMAPPED;
    if (channels_written > 0) writer.ch(',');
    ++channels_written;
    writer.ch('{');
    writeKey(writer, "channel_id");
    writer.u32(index);
    writeKey(writer, "name");
    writer.str(channel.name);
    writeKey(writer, "role");
    writer.str(fsr2ElectrodeRoleName(channel.role));
    writeKey(writer, "position");
    writer.u32(channel.position);
    writeKey(writer, "bias");
    writer.str(channel.role == FSR2_ROLE_ROW ? profile.row_bias : profile.column_bias);
    writeKey(writer, "adc_id");
    if (mapped) {
      writer.u32(static_cast<uint8_t>(channel.adc_index + 1));
    } else {
      writer.nul();
    }
    writeKey(writer, "adc_input");
    if (mapped) {
      writer.u32(channel.adc_input);
    } else {
      writer.nul();
    }
    writeKey(writer, "mux_channel");
    if (mapped) {
      writer.u32(channel.mux_code);
    } else {
      writer.nul();
    }
    writer.ch('}');
  }
  writer.ch(']');
  writer.ch('}');
}

void appendFsrLayout(JsonLineWriter& writer, const Fsr2Profile& profile) {
  writer.ch('{');
  writeKey(writer, "adc_id");
  writer.u32(profile.adc_count);
  writeKey(writer, "independent_pulldowns");
  writer.boolean(true);
  writeKey(writer, "divider_resistor_ohm");
  writer.u32(profile.fsr_divider_ohm);
  writeKey(writer, "excitation_mv");
  writer.u32(profile.fsr_excitation_mv);
  writeKey(writer, "unit");
  writer.str("ADC_COUNTS");
  writeKey(writer, "response_polarity");
  writer.str("VOLTAGE_RISES_WITH_FORCE");
  // The firmware cannot know whether the dividers are actually wired, so it
  // never claims validated hardware here.
  writeKey(writer, "validated");
  writer.boolean(false);
  writeKey(writer, "channels");
  writer.ch('[');
  for (uint8_t index = 0; index < profile.fsr_count; ++index) {
    const uint8_t channel_id = profile.fsr_channel_indices[index];
    const Fsr2ChannelConfig& channel = profile.channels[channel_id];
    if (index > 0) writer.ch(',');
    writer.ch('{');
    writeKey(writer, "channel_id");
    writer.u32(channel_id);
    writeKey(writer, "name");
    writer.str(channel.name);
    writeKey(writer, "adc_input");
    writer.u32(channel.adc_input);
    writeKey(writer, "mux_channel");
    writer.u32(channel.mux_code);
    writer.ch('}');
  }
  writer.ch(']');
  writer.ch('}');
}

void appendRequestId(JsonLineWriter& writer, const char* request_id) {
  if (request_id == nullptr) return;
  writeKey(writer, "request_id");
  writer.str(request_id);
}

}  // namespace

bool fsr2BuildSampleFrame(char* buffer, size_t capacity, const Fsr2SampleFrame& frame) {
  if (buffer == nullptr || capacity == 0 || frame.profile == nullptr) return false;
  if (frame.raw_adc == nullptr || frame.valid == nullptr) return false;
  if (frame.sample_timestamp_us == nullptr || frame.channel_flags == nullptr) return false;

  const Fsr2Profile& profile = *frame.profile;
  JsonLineWriter writer(buffer, capacity);
  writer.ch('{');
  writeKey(writer, "protocol_version");
  writer.u32(1);
  writeKey(writer, "type");
  writer.str("SAMPLE");
  writeKey(writer, "sensor_profile");
  writer.str(profile.sensor_profile);
  writeKey(writer, "device_id");
  writer.str(profile.device_id);
  writeKey(writer, "boot_id");
  writer.str(frame.boot_id == nullptr ? "unknown" : frame.boot_id);
  writeKey(writer, "firmware_version");
  writer.str(profile.firmware_version);
  writeKey(writer, "frame_seq");
  writer.u32(frame.frame_seq);
  writeKey(writer, "timestamp_us");
  writer.u32(frame.timestamp_us);
  writeKey(writer, "mcu_time_us");
  writer.u32(frame.timestamp_us);
  writeKey(writer, "frame_period_us");
  if (frame.has_previous && frame.timestamp_us >= frame.previous_frame_us) {
    writer.u32(frame.timestamp_us - frame.previous_frame_us);
  } else {
    writer.nul();
  }

  writeKey(writer, "channel_ids");
  writer.ch('[');
  for (uint8_t index = 0; index < profile.channel_count; ++index) {
    if (index > 0) writer.ch(',');
    writer.u32(index);
  }
  writer.ch(']');
  writeKey(writer, "channel_count");
  writer.u32(profile.channel_count);

  writeKey(writer, "raw_adc");
  writer.ch('[');
  for (uint8_t index = 0; index < profile.channel_count; ++index) {
    if (index > 0) writer.ch(',');
    if (frame.valid[index]) {
      writer.i32(frame.raw_adc[index]);
    } else {
      writer.nul();
    }
  }
  writer.ch(']');
  writeKey(writer, "channels");
  writer.ch('[');
  for (uint8_t index = 0; index < profile.channel_count; ++index) {
    if (index > 0) writer.ch(',');
    if (frame.valid[index]) {
      writer.i32(frame.raw_adc[index]);
    } else {
      writer.nul();
    }
  }
  writer.ch(']');
  writeKey(writer, "valid");
  writer.ch('[');
  for (uint8_t index = 0; index < profile.channel_count; ++index) {
    if (index > 0) writer.ch(',');
    writer.boolean(frame.valid[index]);
  }
  writer.ch(']');
  writeKey(writer, "valid_mask");
  writer.ch('[');
  for (uint8_t index = 0; index < profile.channel_count; ++index) {
    if (index > 0) writer.ch(',');
    writer.boolean(frame.valid[index]);
  }
  writer.ch(']');
  writeKey(writer, "sample_timestamp_us");
  writer.ch('[');
  for (uint8_t index = 0; index < profile.channel_count; ++index) {
    if (index > 0) writer.ch(',');
    if (frame.valid[index]) {
      writer.u32(frame.sample_timestamp_us[index]);
    } else {
      writer.nul();
    }
  }
  writer.ch(']');
  writeKey(writer, "channel_flags");
  writer.ch('[');
  for (uint8_t index = 0; index < profile.channel_count; ++index) {
    if (index > 0) writer.ch(',');
    writer.u32(frame.channel_flags[index]);
  }
  writer.ch(']');

  writeKey(writer, "reference_mode");
  writer.str(profile.reference_mode_name);
  writeKey(writer, "effective_frame_rate_hz");
  writer.centi(frame.effective_frame_rate_centi_hz);
  writeKey(writer, "adc_status");
  appendAdcStatus(writer, frame.adc_status, frame.adc_status_count);
  writer.ch('}');
  writer.newline();
  return writer.ok();
}

bool fsr2BuildHelloFrame(char* buffer, size_t capacity, const Fsr2Profile& profile,
                         const char* boot_id, const Fsr2AdcStatusSnapshot* adc_status,
                         uint8_t adc_status_count) {
  if (buffer == nullptr || capacity == 0) return false;
  JsonLineWriter writer(buffer, capacity);
  writer.ch('{');
  writeKey(writer, "protocol_version");
  writer.u32(1);
  writeKey(writer, "type");
  writer.str("HELLO");
  writeKey(writer, "sensor_profile");
  writer.str(profile.sensor_profile);
  writeKey(writer, "device_id");
  writer.str(profile.device_id);
  writeKey(writer, "boot_id");
  writer.str(boot_id == nullptr ? "unknown" : boot_id);
  writeKey(writer, "firmware_version");
  writer.str(profile.firmware_version);
  writeKey(writer, "scan_mode");
  writer.str(profile.scan_mode);
  writeKey(writer, "sample_rate_hz");
  writer.nul();
  writeKey(writer, "channel_count");
  writer.u32(profile.channel_count);
  writeKey(writer, "spi_mode");
  writer.str("MODE1_BITBANG");
  writeKey(writer, "data_rate_sps");
  writer.u32(profile.data_rate_sps);
  writeKey(writer, "conversion_wait_us");
  writer.u32(profile.conversion_wait_us);
  writeKey(writer, "reference_mode");
  writer.str(profile.reference_mode_name);
  writeKey(writer, "reference_modes_allowed");
  writer.ch('[');
  writer.str(profile.reference_mode_name);
  writer.ch(']');
  writeKey(writer, "pins");
  appendPins(writer, profile);
  writeKey(writer, "channel_config");
  appendChannelConfig(writer, profile);
  if (profile.electrode_count > 0) {
    writeKey(writer, "electrode_layout");
    appendElectrodeLayout(writer, profile);
  }
  if (profile.fsr_count > 0) {
    writeKey(writer, "fsr_layout");
    appendFsrLayout(writer, profile);
  }
  writeKey(writer, "max_line_bytes");
  writer.u32(profile.max_line_bytes);
  writeKey(writer, "adc_status");
  appendAdcStatus(writer, adc_status, adc_status_count);
  writer.ch('}');
  writer.newline();
  return writer.ok();
}

bool fsr2BuildStatusFrame(char* buffer, size_t capacity, const Fsr2StatusFrame& frame) {
  if (buffer == nullptr || capacity == 0 || frame.profile == nullptr) return false;
  const Fsr2Profile& profile = *frame.profile;
  JsonLineWriter writer(buffer, capacity);
  writer.ch('{');
  writeKey(writer, "protocol_version");
  writer.u32(1);
  writeKey(writer, "type");
  writer.str("STATUS");
  writeKey(writer, "sensor_profile");
  writer.str(profile.sensor_profile);
  writeKey(writer, "device_id");
  writer.str(profile.device_id);
  writeKey(writer, "boot_id");
  writer.str(frame.boot_id == nullptr ? "unknown" : frame.boot_id);
  writeKey(writer, "firmware_version");
  writer.str(profile.firmware_version);
  writeKey(writer, "uptime_ms");
  writer.u32(frame.uptime_ms);
  writeKey(writer, "sensor_state");
  writer.str(frame.streaming ? "STREAMING" : "STOPPED");
  writeKey(writer, "streaming");
  writer.boolean(frame.streaming);
  writeKey(writer, "channel_count");
  writer.u32(profile.channel_count);
  writeKey(writer, "scan_mode");
  writer.str(profile.scan_mode);
  writeKey(writer, "sample_rate_hz");
  writer.nul();
  writeKey(writer, "effective_frame_rate_hz");
  writer.centi(frame.frame_rate_centi_hz);
  writeKey(writer, "last_frame_seq");
  writer.u32(frame.last_frame_seq);
  writeKey(writer, "last_error");
  if (frame.last_error == nullptr) {
    writer.nul();
  } else {
    writer.str(frame.last_error);
  }
  writeKey(writer, "reference_mode");
  writer.str(profile.reference_mode_name);
  writeKey(writer, "reference_modes_allowed");
  writer.ch('[');
  writer.str(profile.reference_mode_name);
  writer.ch(']');
  writeKey(writer, "pins");
  appendPins(writer, profile);
  writeKey(writer, "channel_config");
  appendChannelConfig(writer, profile);
  if (profile.electrode_count > 0) {
    writeKey(writer, "electrode_layout");
    appendElectrodeLayout(writer, profile);
  }
  if (profile.fsr_count > 0) {
    writeKey(writer, "fsr_layout");
    appendFsrLayout(writer, profile);
  }
  writeKey(writer, "max_line_bytes");
  writer.u32(profile.max_line_bytes);
  writeKey(writer, "adc_status");
  appendAdcStatus(writer, frame.adc_status, frame.adc_status_count);
  if (frame.config_report != nullptr) {
    writeKey(writer, "config_report");
    writer.lit(frame.config_report);
  }
  if (frame.request_id != nullptr) {
    writeKey(writer, "request_id");
    writer.str(frame.request_id);
  }
  writer.ch('}');
  writer.newline();
  return writer.ok();
}

bool fsr2BuildPongFrame(char* buffer, size_t capacity, const Fsr2Profile& profile,
                        const char* boot_id, const char* request_id) {
  if (buffer == nullptr || capacity == 0) return false;
  JsonLineWriter writer(buffer, capacity);
  writer.ch('{');
  writeKey(writer, "protocol_version");
  writer.u32(1);
  writeKey(writer, "type");
  writer.str("PONG");
  writeKey(writer, "sensor_profile");
  writer.str(profile.sensor_profile);
  writeKey(writer, "device_id");
  writer.str(profile.device_id);
  writeKey(writer, "boot_id");
  writer.str(boot_id == nullptr ? "unknown" : boot_id);
  writeKey(writer, "firmware_version");
  writer.str(profile.firmware_version);
  appendRequestId(writer, request_id);
  writer.ch('}');
  writer.newline();
  return writer.ok();
}

bool fsr2BuildErrorFrame(char* buffer, size_t capacity, const char* code, const char* message,
                         const char* request_id) {
  if (buffer == nullptr || capacity == 0) return false;
  JsonLineWriter writer(buffer, capacity);
  writer.ch('{');
  writeKey(writer, "protocol_version");
  writer.u32(1);
  writeKey(writer, "type");
  writer.str("ERROR");
  writeKey(writer, "code");
  writer.str(code == nullptr ? "UNKNOWN" : code);
  writeKey(writer, "message");
  writer.str(message == nullptr ? "" : message);
  writeKey(writer, "fatal");
  writer.boolean(false);
  appendRequestId(writer, request_id);
  writer.ch('}');
  writer.newline();
  return writer.ok();
}

bool fsr2BuildConfigReport(char* buffer, size_t capacity, const Fsr2Profile& profile,
                           const uint8_t* readback, const uint8_t* expected, const bool* read_ok,
                           const uint8_t* mux_codes, uint8_t count) {
  if (buffer == nullptr || capacity == 0) return false;
  if (readback == nullptr || expected == nullptr || read_ok == nullptr || mux_codes == nullptr) {
    return false;
  }
  if (count > profile.adc_count) return false;

  JsonLineWriter writer(buffer, capacity);
  writer.ch('{');
  writeKey(writer, "adc_count");
  writer.u32(profile.adc_count);
  writeKey(writer, "expected_registers");
  writer.str("REG0=GAIN/PGA/MUX, REG1=DR/MODE, REG2=VREF/IDAC, REG3=SYSTEM");
  writeKey(writer, "devices");
  writer.ch('[');
  for (uint8_t index = 0; index < count; ++index) {
    if (index > 0) writer.ch(',');
    writer.ch('{');
    writeKey(writer, "id");
    writer.u32(static_cast<uint8_t>(index + 1));
    writeKey(writer, "read_ok");
    writer.boolean(read_ok[index]);
    writeKey(writer, "mux_channel");
    writer.u32(mux_codes[index]);
    writeKey(writer, "expected");
    writer.ch('[');
    for (uint8_t byte = 0; byte < 4; ++byte) {
      if (byte > 0) writer.ch(',');
      writer.u32(expected[index * 4 + byte]);
    }
    writer.ch(']');
    writeKey(writer, "readback");
    writer.ch('[');
    for (uint8_t byte = 0; byte < 4; ++byte) {
      if (byte > 0) writer.ch(',');
      writer.u32(readback[index * 4 + byte]);
    }
    writer.ch(']');
    writeKey(writer, "match");
    if (!read_ok[index]) {
      writer.boolean(false);
    } else {
      bool match = true;
      for (uint8_t byte = 0; byte < 4; ++byte) {
        if (readback[index * 4 + byte] != expected[index * 4 + byte]) match = false;
      }
      writer.boolean(match);
    }
    writer.ch('}');
  }
  writer.ch(']');
  writer.ch('}');
  return writer.ok();
}
