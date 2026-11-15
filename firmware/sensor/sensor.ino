// Tactile acquisition firmware for the old ESP32 (NodeMCU ESP-32S V1.1).
//
// Three ADS1220 devices share SCLK/MOSI and have independent MISO/CS.  The
// firmware uses bit-banged SPI mode 1, measures AIN0..AIN3 single-ended versus
// AVSS on every device (12 channels total), sign-extends the 24-bit results and
// streams JSON Lines over USB serial.  It never starts a servo, PWM or any
// gripper-control output.
//
// This sketch targets the OLD ESP32 only.  Do not build or flash it for the
// ESP32-S3 controller.

#include <Arduino.h>
#include <ArduinoJson.h>
#include <esp_system.h>
#include <string.h>

#include "ads1220.h"
#include "frame_builder.h"
#include "generated_config.h"
#include "json_writer.h"

namespace {

enum AdcStateCode : uint8_t {
  ADC_STATE_OK = 0,
  ADC_STATE_CONFIG_ERROR = 1,
  ADC_STATE_NO_RESPONSE = 2,
  ADC_STATE_RECOVERING = 3,
  ADC_STATE_FAILED = 4,
};

enum ChannelFlag : uint8_t {
  CH_FLAG_SAT_HIGH = 0x01,
  CH_FLAG_SAT_LOW = 0x02,
  CH_FLAG_NEGATIVE_SINGLE_ENDED = 0x04,
  CH_FLAG_NEAR_RAIL = 0x08,
  CH_FLAG_STUCK_EXTREME = 0x10,
  CH_FLAG_NO_DATA = 0x20,
};

struct AdcRuntime {
  uint8_t state;
  uint8_t consecutive_errors;
  uint16_t total_errors;
  uint16_t recovered;
  const char* last_error;
  uint32_t last_reinit_ms;
  uint32_t last_success_ms;
  uint16_t config_check_counter;
};

struct PendingCommand {
  char cmd[16];
  char value[48];
  int32_t id;
  bool has_id;
  char request_id[65];
};

void serviceSerialInput();
void processCommands();

struct DiagDevice {
  bool read_ok;
  uint8_t current_config[4];
  uint8_t pattern_a_written[4];
  uint8_t pattern_a_readback[4];
  uint8_t pattern_b_written[4];
  uint8_t pattern_b_readback[4];
  bool pattern_a_ok;
  bool pattern_b_ok;
  bool patterns_differ;
  bool monitor_ok;
  int32_t offset_raw;
  bool offset_ok;
  int32_t avdd_raw;
  int32_t avdd_mv;
  int32_t temperature_raw;
  int32_t temperature_centi_c;
  bool temperature_ok;
  int32_t channel_raw[4];
  bool channel_ok[4];
};

// Raw, low-speed SPI probe result for one ADC and one MISO sampling edge.
struct SpiEdgeResult {
  bool reset_ok;
  uint8_t reset_bytes[4];
  bool write_a_return;
  bool read_a_return;
  uint8_t read_a[4];
  bool read_a_ok;
  bool write_b_return;
  bool read_b_return;
  uint8_t read_b[4];
  bool read_b_ok;
  bool pass;
};

struct SpiProbeResult {
  uint8_t adc;
  uint8_t cs;
  uint8_t miso;
  uint8_t idle_miso;
  uint8_t after_miso;
  SpiEdgeResult after_rising;
  SpiEdgeResult after_falling;
};

struct MisoMapResult {
  uint8_t adc;
  uint8_t cs;
  uint8_t miso;
  SpiEdgeResult result;
};

constexpr int32_t ADC_FULL_SCALE = 8388607;   // 2^23 - 1
constexpr int32_t ADC_MIN_SCALE = -8388608;   // -2^23
constexpr uint32_t FRAME_RATE_SCALE = 100000000UL;  // hundredths of a hertz

Ads1220Pins makePins(uint8_t index) {
  return Ads1220Pins{SENSOR_SCLK_PIN, SENSOR_MOSI_PIN, SENSOR_MISO_PINS[index], SENSOR_CS_PINS[index]};
}

Ads1220 devices[3] = {
    Ads1220(0, makePins(0)),
    Ads1220(1, makePins(1)),
    Ads1220(2, makePins(2)),
};

AdcRuntime runtime_state[3];

int32_t channel_raw[SENSOR_CHANNEL_COUNT];
bool channel_valid[SENSOR_CHANNEL_COUNT];
uint32_t channel_sample_us[SENSOR_CHANNEL_COUNT];
uint8_t channel_flags[SENSOR_CHANNEL_COUNT];
uint8_t channel_stuck_frames[SENSOR_CHANNEL_COUNT];
int32_t channel_last_extreme[SENSOR_CHANNEL_COUNT];

uint32_t frame_seq = 0;
uint32_t frame_start_history[SENSOR_FRAME_RATE_WINDOW];
uint8_t frame_history_count = 0;
uint8_t frame_history_index = 0;
uint32_t last_frame_start_us = 0;
uint32_t frame_rate_centi_hz = 0;
uint8_t reference_mode = SENSOR_REFERENCE_MODE_INITIAL;
bool streaming = true;

char boot_id[48];
char out_buffer[SENSOR_MAX_LINE_BYTES];
const char* last_global_error = nullptr;

char command_buffer[SENSOR_MAX_COMMAND_BYTES + 1];
size_t command_length = 0;
bool command_overflow = false;
uint32_t last_command_byte_ms = 0;

PendingCommand command_queue[4];
uint8_t queue_head = 0;
uint8_t queue_tail = 0;
uint8_t queue_count = 0;

const char* stateName(uint8_t state) {
  switch (state) {
    case ADC_STATE_OK: return "OK";
    case ADC_STATE_CONFIG_ERROR: return "CONFIG_ERROR";
    case ADC_STATE_NO_RESPONSE: return "NO_RESPONSE";
    case ADC_STATE_RECOVERING: return "RECOVERING";
    default: return "FAILED";
  }
}

const char* referenceName(uint8_t mode) {
  // ADS1220 Rev.D Table 8-13: 00 internal, 01 REFP0/REFN0, 10 REFP1/REFN1,
  // 11 AVDD/AVSS.  Only 0 and 3 are allowed by this firmware.
  if (mode == 0) return "INTERNAL_2V048";
  if (mode == 3) return "AVDD_AVSS";
  return "UNKNOWN_REFERENCE";
}

void buildNormalConfig(uint8_t config[4]) {
  // Register 0: MUX[7:4], gain 1, PGA bypassed.  Register 1: 330 SPS, normal
  // mode, single-shot, temperature sensor off, burn-out current off.  Register
  // 2: selected reference, no 50/60 rejection, low-side switch open, IDAC off.
  config[0] = static_cast<uint8_t>((SENSOR_MUX_CODES[0] << 4) | 0x01);
  config[1] = static_cast<uint8_t>(SENSOR_DATA_RATE_CODE << 5);
  config[2] = static_cast<uint8_t>(reference_mode << 6);
  config[3] = 0x00;
}

void appendAdcStatus(JsonLineWriter& writer) {
  writer.lit("[");
  for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
    if (i > 0) writer.ch(',');
    writer.lit("{\"id\":");
    writer.u32(i + 1);
    writer.lit(",\"state\":");
    writer.str(stateName(runtime_state[i].state));
    writer.lit(",\"code\":");
    writer.u32(runtime_state[i].state);
    writer.lit(",\"consecutive_errors\":");
    writer.u32(runtime_state[i].consecutive_errors);
    writer.lit(",\"total_errors\":");
    writer.u32(runtime_state[i].total_errors);
    writer.lit(",\"recovered\":");
    writer.u32(runtime_state[i].recovered);
    writer.lit(",\"last_error\":");
    if (runtime_state[i].last_error == nullptr) {
      writer.nul();
    } else {
      writer.str(runtime_state[i].last_error);
    }
    writer.ch('}');
  }
  writer.lit("]");
}

void appendPins(JsonLineWriter& writer) {
  writer.lit("\"pins\":{\"sclk\":");
  writer.u32(SENSOR_SCLK_PIN);
  writer.lit(",\"mosi\":");
  writer.u32(SENSOR_MOSI_PIN);
  writer.lit(",\"miso\":[");
  for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
    if (i > 0) writer.ch(',');
    writer.u32(SENSOR_MISO_PINS[i]);
  }
  writer.lit("],\"cs\":[");
  for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
    if (i > 0) writer.ch(',');
    writer.u32(SENSOR_CS_PINS[i]);
  }
  writer.lit("]}");
}

void appendChannelConfig(JsonLineWriter& writer) {
  writer.lit("\"channel_config\":{\"status\":\"IMPLEMENTED\",\"matrix_rows\":null,\"matrix_cols\":null,");
  writer.lit("\"adc_count\":3,\"scan_mode\":\"SINGLE_SHOT_3X4\",\"channels\":[");
  for (uint8_t channel = 0; channel < SENSOR_CHANNEL_COUNT; ++channel) {
    if (channel > 0) writer.ch(',');
    writer.lit("{\"channel_id\":");
    writer.u32(channel);
    writer.lit(",\"adc_input\":");
    writer.u32(channel % 4);
    writer.lit(",\"ads1220_id\":");
    writer.u32(channel / 4 + 1);
    writer.lit(",\"mux_channel\":");
    writer.u32(SENSOR_MUX_CODES[channel % 4]);
    writer.lit(",\"matrix_row\":null,\"matrix_col\":null,\"enabled\":true,\"unit\":\"ADC_COUNTS\"}");
  }
  writer.lit("]}");
}

void sendWriter(JsonLineWriter& writer) {
  if (!writer.ok()) {
    last_global_error = "FRAME_BUFFER_OVERFLOW";
    JsonLineWriter error(out_buffer, sizeof(out_buffer));
    error.lit("{\"protocol_version\":1,\"type\":\"ERROR\",\"device_id\":");
    error.str(SENSOR_DEVICE_ID);
    error.lit(",\"code\":\"FRAME_BUFFER_OVERFLOW\",\"message\":\"output line exceeded buffer\"}");
    error.newline();
    Serial.write(reinterpret_cast<const uint8_t*>(error.data()), error.length());
    return;
  }
  writer.newline();
  Serial.write(reinterpret_cast<const uint8_t*>(writer.data()), writer.length());
}

void sendHello() {
  JsonLineWriter writer(out_buffer, sizeof(out_buffer));
  writer.lit("{\"protocol_version\":1,\"type\":\"HELLO\",\"device_id\":");
  writer.str(SENSOR_DEVICE_ID);
  writer.lit(",\"boot_id\":");
  writer.str(boot_id);
  writer.lit(",\"firmware_version\":");
  writer.str(SENSOR_FIRMWARE_VERSION);
  writer.lit(",\"scan_mode\":\"SINGLE_SHOT_3X4\",\"sample_rate_hz\":null,");
  writer.lit("\"channel_count\":12,\"spi_mode\":\"MODE1_BITBANG\",\"data_rate_sps\":330,");
  writer.lit("\"conversion_wait_us\":");
  writer.u32(SENSOR_CONVERSION_WAIT_US);
  writer.lit(",\"reference_mode\":");
  writer.str(referenceName(reference_mode));
  writer.lit(",\"reference_modes_allowed\":[\"INTERNAL_2V048\",\"AVDD_AVSS\"],");
  appendPins(writer);
  writer.ch(',');
  appendChannelConfig(writer);
  writer.lit(",\"adc_status\":");
  appendAdcStatus(writer);
  writer.ch('}');
  sendWriter(writer);
}

void sendPong(const char* request_id) {
  JsonLineWriter writer(out_buffer, sizeof(out_buffer));
  writer.lit("{\"protocol_version\":1,\"type\":\"PONG\",\"device_id\":");
  writer.str(SENSOR_DEVICE_ID);
  writer.lit(",\"boot_id\":");
  writer.str(boot_id);
  writer.lit(",\"firmware_version\":");
  writer.str(SENSOR_FIRMWARE_VERSION);
  if (request_id != nullptr) {
    writer.lit(",\"request_id\":");
    writer.str(request_id);
  }
  writer.ch('}');
  sendWriter(writer);
}

void appendDiag(JsonLineWriter& writer, const DiagDevice* diag, bool sample_ok) {
  writer.lit("\"diag\":{\"devices\":[");
  for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
    if (i > 0) writer.ch(',');
    const DiagDevice& item = diag[i];
    writer.lit("{\"id\":");
    writer.u32(i + 1);
    writer.lit(",\"read_ok\":");
    writer.boolean(item.read_ok);
    writer.lit(",\"current_config\":[");
    for (uint8_t r = 0; r < 4; ++r) {
      if (r > 0) writer.ch(',');
      writer.u32(item.current_config[r]);
    }
    writer.lit("],\"pattern_a\":{\"written\":[");
    for (uint8_t r = 0; r < 4; ++r) {
      if (r > 0) writer.ch(',');
      writer.u32(item.pattern_a_written[r]);
    }
    writer.lit("],\"readback\":[");
    for (uint8_t r = 0; r < 4; ++r) {
      if (r > 0) writer.ch(',');
      writer.u32(item.pattern_a_readback[r]);
    }
    writer.lit("],\"ok\":");
    writer.boolean(item.pattern_a_ok);
    writer.lit("},\"pattern_b\":{\"written\":[");
    for (uint8_t r = 0; r < 4; ++r) {
      if (r > 0) writer.ch(',');
      writer.u32(item.pattern_b_written[r]);
    }
    writer.lit("],\"readback\":[");
    for (uint8_t r = 0; r < 4; ++r) {
      if (r > 0) writer.ch(',');
      writer.u32(item.pattern_b_readback[r]);
    }
    writer.lit("],\"ok\":");
    writer.boolean(item.pattern_b_ok);
    writer.lit("},\"patterns_differ\":");
    writer.boolean(item.patterns_differ);
    writer.lit(",\"monitor_ok\":");
    writer.boolean(item.monitor_ok);
    writer.lit(",\"offset_raw\":");
    writer.i32(item.offset_raw);
    writer.lit(",\"offset_ok\":");
    writer.boolean(item.offset_ok);
    writer.lit(",\"avdd_raw\":");
    writer.i32(item.avdd_raw);
    writer.lit(",\"avdd_mv\":");
    writer.i32(item.avdd_mv);
    writer.lit(",\"temperature_raw\":");
    writer.i32(item.temperature_raw);
    writer.lit(",\"temperature_centi_c\":");
    writer.i32(item.temperature_centi_c);
    writer.lit(",\"temperature_ok\":");
    writer.boolean(item.temperature_ok);
    writer.lit(",\"channels\":[");
    for (uint8_t c = 0; c < 4; ++c) {
      if (c > 0) writer.ch(',');
      writer.lit("{\"input\":");
      writer.u32(c);
      writer.lit(",\"raw\":");
      if (item.channel_ok[c]) {
        writer.i32(item.channel_raw[c]);
      } else {
        writer.nul();
      }
      writer.lit(",\"ok\":");
      writer.boolean(item.channel_ok[c]);
      writer.ch('}');
    }
    writer.lit("]}");
  }
  writer.lit("],\"sample_ok\":");
  writer.boolean(sample_ok);
  writer.ch('}');
}

void sendStatus(const char* request_id, const DiagDevice* diag, bool sample_ok) {
  JsonLineWriter writer(out_buffer, sizeof(out_buffer));
  writer.lit("{\"protocol_version\":1,\"type\":\"STATUS\",\"device_id\":");
  writer.str(SENSOR_DEVICE_ID);
  writer.lit(",\"boot_id\":");
  writer.str(boot_id);
  writer.lit(",\"firmware_version\":");
  writer.str(SENSOR_FIRMWARE_VERSION);
  writer.lit(",\"uptime_ms\":");
  writer.u32(millis());
  writer.lit(",\"sensor_state\":");
  writer.str(streaming ? "STREAMING" : "STOPPED");
  writer.lit(",\"streaming\":");
  writer.boolean(streaming);
  writer.lit(",\"channel_count\":12,\"scan_mode\":\"SINGLE_SHOT_3X4\",\"sample_rate_hz\":");
  writer.centi(frame_rate_centi_hz);
  writer.lit(",\"effective_frame_rate_hz\":");
  writer.centi(frame_rate_centi_hz);
  writer.lit(",\"last_frame_seq\":");
  writer.u32(frame_seq);
  writer.lit(",\"last_error\":");
  if (last_global_error == nullptr) {
    writer.nul();
  } else {
    writer.str(last_global_error);
  }
  writer.lit(",\"reference_mode\":");
  writer.str(referenceName(reference_mode));
  writer.lit(",\"reference_modes_allowed\":[\"INTERNAL_2V048\",\"AVDD_AVSS\"],");
  appendPins(writer);
  writer.ch(',');
  writer.lit("\"adc_status\":");
  appendAdcStatus(writer);
  if (diag != nullptr) {
    writer.ch(',');
    appendDiag(writer, diag, sample_ok);
  }
  if (request_id != nullptr) {
    writer.lit(",\"request_id\":");
    writer.str(request_id);
  }
  writer.ch('}');
  sendWriter(writer);
}

void appendByteArray(JsonLineWriter& writer, const uint8_t* values, uint8_t count) {
  writer.ch('[');
  for (uint8_t i = 0; i < count; ++i) {
    if (i > 0) writer.ch(',');
    writer.u32(values[i]);
  }
  writer.ch(']');
}

void appendSpiEdge(JsonLineWriter& writer, const SpiEdgeResult& edge) {
  writer.lit("{\"reset_ok\":");
  writer.boolean(edge.reset_ok);
  writer.lit(",\"reset\":");
  appendByteArray(writer, edge.reset_bytes, 4);
  writer.lit(",\"write_a_return\":");
  writer.boolean(edge.write_a_return);
  writer.lit(",\"read_a_return\":");
  writer.boolean(edge.read_a_return);
  writer.lit(",\"read_a\":");
  appendByteArray(writer, edge.read_a, 4);
  writer.lit(",\"read_a_ok\":");
  writer.boolean(edge.read_a_ok);
  writer.lit(",\"write_b_return\":");
  writer.boolean(edge.write_b_return);
  writer.lit(",\"read_b_return\":");
  writer.boolean(edge.read_b_return);
  writer.lit(",\"read_b\":");
  appendByteArray(writer, edge.read_b, 4);
  writer.lit(",\"read_b_ok\":");
  writer.boolean(edge.read_b_ok);
  writer.lit(",\"pass\":");
  writer.boolean(edge.pass);
  writer.ch('}');
}

void sendSpiDiag(const char* request_id, uint16_t slow_half_us, const SpiProbeResult* results) {
  JsonLineWriter writer(out_buffer, sizeof(out_buffer));
  writer.lit("{\"protocol_version\":1,\"type\":\"STATUS\",\"device_id\":");
  writer.str(SENSOR_DEVICE_ID);
  writer.lit(",\"boot_id\":");
  writer.str(boot_id);
  writer.lit(",\"firmware_version\":");
  writer.str(SENSOR_FIRMWARE_VERSION);
  writer.lit(",\"sensor_state\":\"STOPPED\",\"streaming\":false,\"channel_count\":12");
  writer.lit(",\"spi_diag\":{\"slow_half_period_us\":");
  writer.u32(slow_half_us);
  writer.lit(",\"pins\":{\"sclk\":");
  writer.u32(SENSOR_SCLK_PIN);
  writer.lit(",\"mosi\":");
  writer.u32(SENSOR_MOSI_PIN);
  writer.lit("},\"commands\":{\"reset\":6,\"wreg\":67,\"rreg\":35,\"start\":8,\"rdata\":16}");
  writer.lit(",\"devices\":[");
  for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
    if (i > 0) writer.ch(',');
    const SpiProbeResult& item = results[i];
    writer.lit("{\"adc\":");
    writer.u32(item.adc);
    writer.lit(",\"cs\":");
    writer.u32(item.cs);
    writer.lit(",\"miso\":");
    writer.u32(item.miso);
    writer.lit(",\"idle_miso\":");
    writer.u32(item.idle_miso);
    writer.lit(",\"after_miso\":");
    writer.u32(item.after_miso);
    writer.lit(",\"edges\":{\"after_rising\":");
    appendSpiEdge(writer, item.after_rising);
    writer.lit(",\"after_falling\":");
    appendSpiEdge(writer, item.after_falling);
    writer.lit("}}");
  }
  writer.lit("]}");
  if (request_id != nullptr) {
    writer.lit(",\"request_id\":");
    writer.str(request_id);
  }
  writer.ch('}');
  sendWriter(writer);
}

void sendAdc1Min(const char* request_id, uint8_t cycles, const SpiEdgeResult& result) {
  JsonLineWriter writer(out_buffer, sizeof(out_buffer));
  writer.lit("{\"protocol_version\":1,\"type\":\"STATUS\",\"device_id\":");
  writer.str(SENSOR_DEVICE_ID);
  writer.lit(",\"boot_id\":");
  writer.str(boot_id);
  writer.lit(",\"firmware_version\":");
  writer.str(SENSOR_FIRMWARE_VERSION);
  writer.lit(",\"sensor_state\":\"STOPPED\",\"streaming\":false,\"channel_count\":12");
  writer.lit(",\"adc1_min\":{\"cycles\":");
  writer.u32(cycles);
  writer.lit(",\"pins\":{\"cs\":");
  writer.u32(SENSOR_CS_PINS[0]);
  writer.lit(",\"sclk\":");
  writer.u32(SENSOR_SCLK_PIN);
  writer.lit(",\"mosi\":");
  writer.u32(SENSOR_MOSI_PIN);
  writer.lit(",\"miso\":");
  writer.u32(SENSOR_MISO_PINS[0]);
  writer.lit("},\"slow_half_period_us\":");
  writer.u32(SENSOR_DIAG_SPI_HALF_PERIOD_US);
  writer.lit(",\"result\":");
  appendSpiEdge(writer, result);
  writer.lit("}");
  if (request_id != nullptr) {
    writer.lit(",\"request_id\":");
    writer.str(request_id);
  }
  writer.ch('}');
  sendWriter(writer);
}

void sendMisoMap(const char* request_id, uint16_t slow_half_us, const MisoMapResult* results,
                 uint8_t result_count) {
  JsonLineWriter writer(out_buffer, sizeof(out_buffer));
  writer.lit("{\"protocol_version\":1,\"type\":\"STATUS\",\"device_id\":");
  writer.str(SENSOR_DEVICE_ID);
  writer.lit(",\"boot_id\":");
  writer.str(boot_id);
  writer.lit(",\"firmware_version\":");
  writer.str(SENSOR_FIRMWARE_VERSION);
  writer.lit(",\"sensor_state\":\"STOPPED\",\"streaming\":false,\"channel_count\":12");
  writer.lit(",\"miso_map\":{\"slow_half_period_us\":");
  writer.u32(slow_half_us);
  writer.lit(",\"results\":[");
  for (uint8_t i = 0; i < result_count; ++i) {
    if (i > 0) writer.ch(',');
    const MisoMapResult& item = results[i];
    writer.lit("{\"adc\":");
    writer.u32(item.adc);
    writer.lit(",\"cs\":");
    writer.u32(item.cs);
    writer.lit(",\"miso\":");
    writer.u32(item.miso);
    writer.lit(",\"result\":");
    appendSpiEdge(writer, item.result);
    writer.ch('}');
  }
  writer.lit("]}");
  if (request_id != nullptr) {
    writer.lit(",\"request_id\":");
    writer.str(request_id);
  }
  writer.ch('}');
  sendWriter(writer);
}

void sendConfigReport(const char* request_id) {
  JsonLineWriter writer(out_buffer, sizeof(out_buffer));
  writer.lit("{\"protocol_version\":1,\"type\":\"STATUS\",\"device_id\":");
  writer.str(SENSOR_DEVICE_ID);
  writer.lit(",\"boot_id\":");
  writer.str(boot_id);
  writer.lit(",\"firmware_version\":");
  writer.str(SENSOR_FIRMWARE_VERSION);
  writer.lit(",\"config_report\":{\"devices\":[");
  for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
    if (i > 0) writer.ch(',');
    uint8_t regs[4] = {0, 0, 0, 0};
    const bool read_ok = devices[i].readRegisters(0, regs, 4);
    const uint8_t vref = static_cast<uint8_t>((regs[2] >> 6) & 0x03);
    writer.lit("{\"id\":");
    writer.u32(i + 1);
    writer.lit(",\"read_ok\":");
    writer.boolean(read_ok);
    writer.lit(",\"registers\":");
    appendByteArray(writer, regs, 4);
    writer.lit(",\"mux\":");
    writer.u32((regs[0] >> 4) & 0x0F);
    writer.lit(",\"gain_code\":");
    writer.u32((regs[0] >> 1) & 0x07);
    writer.lit(",\"pga_bypass\":");
    writer.boolean((regs[0] & 0x01) != 0);
    writer.lit(",\"vref_code\":");
    writer.u32(vref);
    writer.lit(",\"vref\":");
    if (vref == 0) {
      writer.str("INTERNAL_2V048");
    } else if (vref == 1) {
      writer.str("EXTERNAL_REFP0_REFN0");
    } else if (vref == 2) {
      writer.str("EXTERNAL_REFP1_REFN1");
    } else {
      writer.str("AVDD_AVSS");
    }
    writer.lit(",\"psw\":");
    writer.u32((regs[2] >> 3) & 0x01);
    writer.lit(",\"idac_code\":");
    writer.u32(regs[2] & 0x07);
    writer.lit(",\"data_rate_code\":");
    writer.u32((regs[1] >> 5) & 0x07);
    writer.lit(",\"config1_raw\":");
    writer.u32(regs[1]);
    writer.ch('}');
  }
  writer.lit("]}");  // close devices array and config_report object; root closes below
  if (request_id != nullptr) {
    writer.lit(",\"request_id\":");
    writer.str(request_id);
  }
  writer.ch('}');
  sendWriter(writer);
}

void sendError(const char* code, const char* message, const char* request_id) {
  last_global_error = code;
  JsonLineWriter writer(out_buffer, sizeof(out_buffer));
  writer.lit("{\"protocol_version\":1,\"type\":\"ERROR\",\"device_id\":");
  writer.str(SENSOR_DEVICE_ID);
  writer.lit(",\"code\":");
  writer.str(code);
  writer.lit(",\"message\":");
  writer.str(message);
  writer.lit(",\"fatal\":false");
  if (request_id != nullptr) {
    writer.lit(",\"request_id\":");
    writer.str(request_id);
  }
  writer.ch('}');
  sendWriter(writer);
}

void recordFrameStart(uint32_t timestamp_us) {
  frame_start_history[frame_history_index] = timestamp_us;
  frame_history_index = static_cast<uint8_t>((frame_history_index + 1) % SENSOR_FRAME_RATE_WINDOW);
  if (frame_history_count < SENSOR_FRAME_RATE_WINDOW) {
    ++frame_history_count;
  }
  if (frame_history_count < 2) {
    frame_rate_centi_hz = 0;
    return;
  }
  const uint8_t oldest_index =
      static_cast<uint8_t>((frame_history_index + SENSOR_FRAME_RATE_WINDOW - frame_history_count) %
                           SENSOR_FRAME_RATE_WINDOW);
  const uint8_t newest_index =
      static_cast<uint8_t>((frame_history_index + SENSOR_FRAME_RATE_WINDOW - 1) % SENSOR_FRAME_RATE_WINDOW);
  const uint32_t elapsed = frame_start_history[newest_index] - frame_start_history[oldest_index];
  if (elapsed == 0) {
    return;
  }
  const uint64_t value =
      (static_cast<uint64_t>(frame_history_count - 1) * FRAME_RATE_SCALE) / elapsed;
  frame_rate_centi_hz = static_cast<uint32_t>(value);
}

uint8_t classifyChannel(int32_t value) {
  uint8_t flags = 0;
  if (value >= ADC_FULL_SCALE) flags |= CH_FLAG_SAT_HIGH;
  if (value <= ADC_MIN_SCALE) flags |= CH_FLAG_SAT_LOW;
  if (value < 0) flags |= CH_FLAG_NEGATIVE_SINGLE_ENDED;
  const int32_t rail = static_cast<int32_t>(ADC_FULL_SCALE * 0.98);
  if (value > rail || value < -rail) flags |= CH_FLAG_NEAR_RAIL;
  return flags;
}

void recordChannel(uint8_t channel, int32_t value, uint32_t timestamp_us) {
  channel_raw[channel] = value;
  channel_valid[channel] = true;
  channel_sample_us[channel] = timestamp_us;
  uint8_t flags = classifyChannel(value);
  const bool extreme = (value >= ADC_FULL_SCALE || value <= ADC_MIN_SCALE || value == 0);
  if (extreme && channel_last_extreme[channel] == value) {
    if (channel_stuck_frames[channel] < 0xFF) ++channel_stuck_frames[channel];
  } else {
    channel_stuck_frames[channel] = 0;
  }
  channel_last_extreme[channel] = value;
  if (extreme && channel_stuck_frames[channel] >= 16) flags |= CH_FLAG_STUCK_EXTREME;
  channel_flags[channel] = flags;
}

void invalidateChannel(uint8_t channel) {
  channel_raw[channel] = 0;
  channel_valid[channel] = false;
  channel_sample_us[channel] = 0;
  channel_flags[channel] = CH_FLAG_NO_DATA;
  channel_stuck_frames[channel] = 0;
  channel_last_extreme[channel] = 0;
}

void sendSample(uint32_t frame_start_us) {
  FrameAdcStatus statuses[SENSOR_ADC_COUNT];
  for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
    statuses[i].state = stateName(runtime_state[i].state);
    statuses[i].code = runtime_state[i].state;
    statuses[i].consecutive_errors = runtime_state[i].consecutive_errors;
    statuses[i].total_errors = runtime_state[i].total_errors;
    statuses[i].recovered = runtime_state[i].recovered;
    statuses[i].last_error = runtime_state[i].last_error;
  }
  FrameSample sample;
  sample.device_id = SENSOR_DEVICE_ID;
  sample.boot_id = boot_id;
  sample.firmware_version = SENSOR_FIRMWARE_VERSION;
  sample.frame_seq = frame_seq;
  sample.timestamp_us = frame_start_us;
  sample.has_previous = (last_frame_start_us != 0);
  sample.previous_frame_us = last_frame_start_us;
  sample.raw_adc = channel_raw;
  sample.valid = channel_valid;
  sample.sample_timestamp_us = channel_sample_us;
  sample.channel_flags = channel_flags;
  sample.reference_mode = referenceName(reference_mode);
  sample.effective_frame_rate_centi_hz = frame_rate_centi_hz;
  sample.adc_status = statuses;
  if (!buildSampleFrame(out_buffer, sizeof(out_buffer), sample)) {
    last_global_error = "FRAME_BUFFER_OVERFLOW";
    JsonLineWriter error(out_buffer, sizeof(out_buffer));
    error.lit("{\"protocol_version\":1,\"type\":\"ERROR\",\"device_id\":");
    error.str(SENSOR_DEVICE_ID);
    error.lit(",\"code\":\"FRAME_BUFFER_OVERFLOW\",\"message\":\"sample line exceeded buffer\"}");
    error.newline();
    Serial.write(reinterpret_cast<const uint8_t*>(error.data()), error.length());
    return;
  }
  Serial.write(reinterpret_cast<const uint8_t*>(out_buffer), strlen(out_buffer));
}

bool readRegisterFile(uint8_t index, uint8_t values[4]) {
  return devices[index].readRegisters(0, values, 4);
}

void markDeviceError(uint8_t index, const char* code) {
  AdcRuntime& rt = runtime_state[index];
  if (rt.consecutive_errors < 0xFF) ++rt.consecutive_errors;
  if (rt.total_errors < 0xFFFF) ++rt.total_errors;
  rt.last_error = code;
  last_global_error = code;
  if (rt.consecutive_errors >= SENSOR_REINIT_AFTER_ERRORS) {
    rt.state = ADC_STATE_FAILED;
  }
}

bool initDevice(uint8_t index, bool recovery) {
  AdcRuntime& rt = runtime_state[index];
  const uint8_t old_state = rt.state;
  rt.state = ADC_STATE_RECOVERING;
  uint8_t defaults[4] = {0, 0, 0, 0};
  bool ok = devices[index].probe(defaults);
  if (ok) {
    uint8_t config[4];
    uint8_t readback[4];
    buildNormalConfig(config);
    ok = devices[index].configure(config, readback);
  }
  rt.last_reinit_ms = millis();
  if (ok) {
    rt.state = ADC_STATE_OK;
    rt.last_success_ms = millis();
    rt.consecutive_errors = 0;
    rt.last_error = nullptr;
    if (recovery && old_state != ADC_STATE_OK) {
      if (rt.recovered < 0xFFFF) ++rt.recovered;
    }
    return true;
  }
  rt.state = ADC_STATE_NO_RESPONSE;
  rt.last_error = "PROBE_OR_CONFIG_READBACK_FAILED";
  last_global_error = rt.last_error;
  if (rt.total_errors < 0xFFFF) ++rt.total_errors;
  return false;
}

void maintainDevices() {
  const uint32_t now = millis();
  for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
    AdcRuntime& rt = runtime_state[i];
    if (rt.state == ADC_STATE_OK) {
      if (millis() - rt.last_success_ms > 2000UL) {
        rt.state = ADC_STATE_CONFIG_ERROR;
        markDeviceError(i, "DATA_TIMEOUT");
        continue;
      }
      ++rt.config_check_counter;
      if (rt.config_check_counter >= 256) {
        rt.config_check_counter = 0;
        uint8_t expected[4];
        uint8_t actual[4];
        buildNormalConfig(expected);
        if (!readRegisterFile(i, actual)) {
          rt.state = ADC_STATE_CONFIG_ERROR;
          markDeviceError(i, "CONFIG_READ_FAILED");
          continue;
        }
        for (uint8_t r = 0; r < 4; ++r) {
          if (actual[r] != expected[r]) {
            rt.state = ADC_STATE_CONFIG_ERROR;
            markDeviceError(i, "CONFIG_LOST");
            break;
          }
        }
      }
    } else if (now - rt.last_reinit_ms >= SENSOR_REINIT_RETRY_INTERVAL_MS) {
      initDevice(i, true);
    }
  }
}

void scanFrame() {
  const uint32_t frame_start = micros();
  bool started[3] = {false, false, false};

  for (uint8_t step = 0; step < 4; ++step) {
    for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
      if (runtime_state[i].state != ADC_STATE_OK) {
        continue;
      }
      devices[i].setMux(SENSOR_MUX_CODES[step]);
      devices[i].startConversion();
      started[i] = true;
    }

    const uint32_t wait_start = micros();
    while (static_cast<uint32_t>(micros() - wait_start) < SENSOR_CONVERSION_WAIT_US) {
      serviceSerialInput();
      if (!streaming) {
        return;
      }
      delay(1);
    }

    for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
      const uint8_t channel = static_cast<uint8_t>(i * 4 + step);
      if (!started[i]) {
        invalidateChannel(channel);
        continue;
      }
      int32_t value = 0;
      if (devices[i].readData(&value)) {
        recordChannel(channel, value, micros());
        runtime_state[i].last_success_ms = millis();
      } else {
        invalidateChannel(channel);
        markDeviceError(i, "RDATA_FAILED");
      }
    }
    serviceSerialInput();
  }

  ++frame_seq;
  recordFrameStart(frame_start);
  sendSample(frame_start);
  last_frame_start_us = frame_start;

  maintainDevices();
  serviceSerialInput();
  processCommands();
}

void runDiagnostics(const char* request_id) {
  DiagDevice diag[SENSOR_ADC_COUNT];
  memset(diag, 0, sizeof(diag));
  static const uint8_t pattern_a[4] = {0x81, 0x80, 0x00, 0x00};
  static const uint8_t pattern_b[4] = {0x91, 0x80, 0x80, 0x00};

  for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
    DiagDevice& item = diag[i];
    memcpy(item.pattern_a_written, pattern_a, 4);
    memcpy(item.pattern_b_written, pattern_b, 4);
    item.read_ok = devices[i].readRegisters(0, item.current_config, 4);
    uint8_t readback[4];
    item.pattern_a_ok = devices[i].writeVerify(pattern_a, readback);
    if (item.pattern_a_ok) {
      memcpy(item.pattern_a_readback, readback, 4);
    }
    item.pattern_b_ok = devices[i].writeVerify(pattern_b, readback);
    if (item.pattern_b_ok) {
      memcpy(item.pattern_b_readback, readback, 4);
    }
    item.patterns_differ = false;
    for (uint8_t r = 0; r < 4; ++r) {
      if (item.pattern_a_readback[r] != item.pattern_b_readback[r]) {
        item.patterns_differ = true;
        break;
      }
    }
    const bool uniform_a = (item.pattern_a_readback[0] == 0x00 && item.pattern_a_readback[1] == 0x00 &&
                            item.pattern_a_readback[2] == 0x00 && item.pattern_a_readback[3] == 0x00) ||
                           (item.pattern_a_readback[0] == 0xFF && item.pattern_a_readback[1] == 0xFF &&
                            item.pattern_a_readback[2] == 0xFF && item.pattern_a_readback[3] == 0xFF);
    const bool uniform_b = (item.pattern_b_readback[0] == 0x00 && item.pattern_b_readback[1] == 0x00 &&
                            item.pattern_b_readback[2] == 0x00 && item.pattern_b_readback[3] == 0x00) ||
                           (item.pattern_b_readback[0] == 0xFF && item.pattern_b_readback[1] == 0xFF &&
                            item.pattern_b_readback[2] == 0xFF && item.pattern_b_readback[3] == 0xFF);
    item.pattern_a_ok = item.pattern_a_ok && !uniform_a && item.patterns_differ;
    item.pattern_b_ok = item.pattern_b_ok && !uniform_b && item.patterns_differ;
  }

  // Internal self-tests: shorted inputs (offset), AVDD/4 monitor, temperature.
  for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
    DiagDevice& item = diag[i];
    uint8_t config[4] = {0, 0, 0, 0};
    uint8_t readback[4];
    bool ok = item.pattern_a_ok && item.pattern_b_ok;

    if (ok) {
      config[0] = 0xE1;  // MUX=1110, inputs shorted to (AVDD+AVSS)/2
      config[1] = 0x80;  // 330 SPS, normal, single-shot
      config[2] = 0x00;  // internal reference
      config[3] = 0x00;
      ok = devices[i].configure(config, readback);
      if (ok) {
        devices[i].startConversion();
        delayMicroseconds(SENSOR_CONVERSION_WAIT_US);
        ok = devices[i].readData(&item.offset_raw);
      }
    }
    item.offset_ok = ok && (item.offset_raw > -200000L) && (item.offset_raw < 200000L);

    if (ok) {
      config[0] = 0xD1;  // MUX=1101, (AVDD-AVSS)/4 monitor
      config[1] = 0x80;
      config[2] = 0x00;
      config[3] = 0x00;
      ok = devices[i].configure(config, readback);
      if (ok) {
        devices[i].startConversion();
        delayMicroseconds(SENSOR_CONVERSION_WAIT_US);
        ok = devices[i].readData(&item.avdd_raw);
      }
    }
    if (ok && item.avdd_raw > 0) {
      // (AVDD/4) / 2.048 * 2^23 counts  ->  AVDD in millivolts = raw / 1024.
      item.avdd_mv = item.avdd_raw / 1024;
    }

    if (ok) {
      config[0] = 0x81;
      config[1] = 0x82;  // TS=1, internal temperature sensor
      config[2] = 0x00;
      config[3] = 0x00;
      ok = devices[i].configure(config, readback);
      if (ok) {
        devices[i].startConversion();
        delayMicroseconds(SENSOR_CONVERSION_WAIT_US);
        ok = devices[i].readData(&item.temperature_raw);
      }
    }
    if (ok) {
      const int16_t temperature_14bit = static_cast<int16_t>(item.temperature_raw >> 10);
      item.temperature_centi_c = static_cast<int32_t>(temperature_14bit) * 3125L / 1000L;
      item.temperature_ok = item.temperature_centi_c > -4000L && item.temperature_centi_c < 12500L;
    }
    item.monitor_ok = item.offset_ok && item.temperature_ok && item.avdd_mv > 2000 && item.avdd_mv < 6000;

    // Restore the validated normal configuration for this device.
    buildNormalConfig(config);
    const bool restored = devices[i].configure(config, readback);
    if (!restored) {
      runtime_state[i].state = ADC_STATE_CONFIG_ERROR;
      markDeviceError(i, "DIAG_RESTORE_FAILED");
    }
  }

  // Read all 12 channels once with the normal configuration, overlapping the
  // three ADCs at each MUX step.
  bool sample_ok = true;
  for (uint8_t step = 0; step < 4; ++step) {
    bool started[3] = {false, false, false};
    for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
      if (runtime_state[i].state != ADC_STATE_OK) {
        continue;
      }
      devices[i].setMux(SENSOR_MUX_CODES[step]);
      devices[i].startConversion();
      started[i] = true;
    }
    delayMicroseconds(SENSOR_CONVERSION_WAIT_US);
    for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
      if (!started[i]) {
        diag[i].channel_ok[step] = false;
        sample_ok = false;
        continue;
      }
      int32_t value = 0;
      if (devices[i].readData(&value)) {
        diag[i].channel_raw[step] = value;
        diag[i].channel_ok[step] = true;
      } else {
        diag[i].channel_ok[step] = false;
        sample_ok = false;
      }
    }
  }
  sendStatus(request_id, diag, sample_ok);
}

void runSpiDiagnostics(const char* request_id) {
  const uint16_t slow_half_us = SENSOR_DIAG_SPI_HALF_PERIOD_US;
  static const uint8_t pattern_a[4] = {0x81, 0x80, 0x00, 0x00};
  static const uint8_t pattern_b[4] = {0x91, 0x80, 0x80, 0x00};
  SpiProbeResult results[SENSOR_ADC_COUNT];
  memset(results, 0, sizeof(results));

  // Stop the acquisition loop for the whole probe; commands are serviced by
  // this call, so no SAMPLE frame can interleave with the SPI transactions.
  streaming = false;

  for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
    SpiProbeResult& item = results[i];
    const Ads1220Pins pins = devices[i].pins();
    item.adc = static_cast<uint8_t>(i + 1);
    item.cs = pins.cs;
    item.miso = pins.miso;
    digitalWrite(pins.cs, HIGH);
    delayMicroseconds(10);
    item.idle_miso = digitalRead(pins.miso) == HIGH ? 1 : 0;

    for (uint8_t edge = 0; edge < 2; ++edge) {
      const bool after_fall = (edge == 1);
      SpiEdgeResult& result = after_fall ? item.after_falling : item.after_rising;
      devices[i].setClockHalfPeriodUs(slow_half_us);
      devices[i].setSampleAfterFallingEdge(after_fall);

      devices[i].reset();
      result.reset_ok = devices[i].readRegisters(0, result.reset_bytes, 4);

      result.write_a_return = devices[i].writeRegisters(0, pattern_a, 4);
      result.read_a_return = devices[i].readRegisters(0, result.read_a, 4);
      result.read_a_ok = result.read_a_return && memcmp(result.read_a, pattern_a, 4) == 0;

      result.write_b_return = devices[i].writeRegisters(0, pattern_b, 4);
      result.read_b_return = devices[i].readRegisters(0, result.read_b, 4);
      result.read_b_ok = result.read_b_return && memcmp(result.read_b, pattern_b, 4) == 0;

      result.pass = result.reset_ok && result.write_a_return && result.read_a_ok &&
                    result.write_b_return && result.read_b_ok;
      digitalWrite(pins.cs, HIGH);
    }
    item.after_miso = digitalRead(pins.miso) == HIGH ? 1 : 0;
  }

  // Restore production timing and try the normal init once, then report.  The
  // stream stays stopped so the host can inspect the result without SAMPLE
  // traffic; the operator can send STREAM with id=1 to resume.
  for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
    devices[i].setClockHalfPeriodUs(SENSOR_SPI_HALF_PERIOD_US);
    devices[i].setSampleAfterFallingEdge(false);
    initDevice(i, true);
  }
  sendSpiDiag(request_id, slow_half_us, results);
}

void applyGpioState(bool cs1_high, bool sclk_high, bool mosi_high) {
  // Never select ADC2/ADC3 while probing ADC1.
  digitalWrite(SENSOR_CS_PINS[1], HIGH);
  digitalWrite(SENSOR_CS_PINS[2], HIGH);
  digitalWrite(SENSOR_CS_PINS[0], cs1_high ? HIGH : LOW);
  digitalWrite(SENSOR_SCLK_PIN, sclk_high ? HIGH : LOW);
  digitalWrite(SENSOR_MOSI_PIN, mosi_high ? HIGH : LOW);
}

void printGpioState(const char* name, bool cs1_high, bool sclk_high, bool mosi_high) {
  Serial.print("GPIO_DIAG state=");
  Serial.print(name);
  Serial.print(" t_ms=");
  Serial.print(millis());
  Serial.print(" cs1=");
  Serial.print(cs1_high ? "HIGH" : "LOW");
  Serial.print(" sclk=");
  Serial.print(sclk_high ? "HIGH" : "LOW");
  Serial.print(" mosi=");
  Serial.print(mosi_high ? "HIGH" : "LOW");
  Serial.print(" hold_ms=5000 esp_read cs1=");
  Serial.print(digitalRead(SENSOR_CS_PINS[0]) == HIGH ? "HIGH" : "LOW");
  Serial.print(" sclk=");
  Serial.print(digitalRead(SENSOR_SCLK_PIN) == HIGH ? "HIGH" : "LOW");
  Serial.print(" mosi=");
  Serial.print(digitalRead(SENSOR_MOSI_PIN) == HIGH ? "HIGH" : "LOW");
  Serial.print(" cs2=");
  Serial.print(digitalRead(SENSOR_CS_PINS[1]) == HIGH ? "HIGH" : "LOW");
  Serial.print(" cs3=");
  Serial.print(digitalRead(SENSOR_CS_PINS[2]) == HIGH ? "HIGH" : "LOW");
  Serial.println();
  Serial.flush();
}

void holdGpioState(uint32_t hold_ms) {
  const uint32_t start = millis();
  while (millis() - start < hold_ms) {
    delay(10);
  }
}

void runGpioDiagnostics(uint8_t cycles, const char* request_id) {
  static const uint8_t pattern_a[4] = {0x81, 0x80, 0x00, 0x00};
  static const uint8_t pattern_b[4] = {0x91, 0x80, 0x80, 0x00};
  streaming = false;

  // Safe idle before the first measurement.
  applyGpioState(true, false, false);
  delay(20);

  for (uint8_t cycle = 0; cycle < cycles; ++cycle) {
    applyGpioState(true, false, false);  // A: CS1 high, SCLK low, MOSI low
    printGpioState("A", true, false, false);
    holdGpioState(5000);

    applyGpioState(false, false, false);  // B: CS1 low, SCLK low, MOSI low
    printGpioState("B", false, false, false);
    holdGpioState(5000);

    applyGpioState(false, true, true);  // C: CS1 low, SCLK high, MOSI high
    printGpioState("C", false, true, true);
    holdGpioState(5000);
  }

  // Restore safe levels before any SPI transaction.
  applyGpioState(true, false, false);
  delay(20);

  // Minimal ADC1-only register sequence, at the slow diagnostic clock.
  SpiEdgeResult result;
  memset(&result, 0, sizeof(result));
  devices[0].setClockHalfPeriodUs(SENSOR_DIAG_SPI_HALF_PERIOD_US);
  devices[0].setSampleAfterFallingEdge(false);
  devices[0].reset();
  result.reset_ok = devices[0].readRegisters(0, result.reset_bytes, 4);
  result.write_a_return = devices[0].writeRegisters(0, pattern_a, 4);
  result.read_a_return = devices[0].readRegisters(0, result.read_a, 4);
  result.read_a_ok = result.read_a_return && memcmp(result.read_a, pattern_a, 4) == 0;
  result.write_b_return = devices[0].writeRegisters(0, pattern_b, 4);
  result.read_b_return = devices[0].readRegisters(0, result.read_b, 4);
  result.read_b_ok = result.read_b_return && memcmp(result.read_b, pattern_b, 4) == 0;
  result.pass = result.reset_ok && result.read_a_ok && result.read_b_ok;

  devices[0].setClockHalfPeriodUs(SENSOR_SPI_HALF_PERIOD_US);
  devices[0].setSampleAfterFallingEdge(false);
  initDevice(0, true);
  sendAdc1Min(request_id, cycles, result);
}

void runMisoMap(const char* request_id) {
  static const uint8_t pattern_a[4] = {0x81, 0x80, 0x00, 0x00};
  static const uint8_t pattern_b[4] = {0x91, 0x80, 0x80, 0x00};
  // ADC1 is already confirmed on GPIO35.  Only the ADC2/ADC3 pair is ambiguous:
  // test GPIO34 and GPIO26 once for each, not all nine CS/MISO combinations.
  static const uint8_t candidates[3][2] = {{35, 35}, {34, 26}, {34, 26}};
  static const uint8_t candidate_count[3] = {1, 2, 2};
  MisoMapResult results[5];
  uint8_t result_count = 0;
  streaming = false;

  for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
    digitalWrite(SENSOR_CS_PINS[i], HIGH);
  }
  digitalWrite(SENSOR_SCLK_PIN, LOW);
  digitalWrite(SENSOR_MOSI_PIN, LOW);
  delay(10);

  for (uint8_t adc = 0; adc < SENSOR_ADC_COUNT; ++adc) {
    for (uint8_t c = 0; c < candidate_count[adc]; ++c) {
      const uint8_t miso = candidates[adc][c];
      for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
        digitalWrite(SENSOR_CS_PINS[i], HIGH);
      }
      devices[adc].setMisoPin(miso);
      devices[adc].setClockHalfPeriodUs(SENSOR_DIAG_SPI_HALF_PERIOD_US);
      devices[adc].setSampleAfterFallingEdge(false);

      MisoMapResult& item = results[result_count++];
      memset(&item, 0, sizeof(item));
      item.adc = static_cast<uint8_t>(adc + 1);
      item.cs = SENSOR_CS_PINS[adc];
      item.miso = miso;

      devices[adc].reset();
      item.result.reset_ok = devices[adc].readRegisters(0, item.result.reset_bytes, 4);
      item.result.write_a_return = devices[adc].writeRegisters(0, pattern_a, 4);
      item.result.read_a_return = devices[adc].readRegisters(0, item.result.read_a, 4);
      item.result.read_a_ok =
          item.result.read_a_return && memcmp(item.result.read_a, pattern_a, 4) == 0;
      item.result.write_b_return = devices[adc].writeRegisters(0, pattern_b, 4);
      item.result.read_b_return = devices[adc].readRegisters(0, item.result.read_b, 4);
      item.result.read_b_ok =
          item.result.read_b_return && memcmp(item.result.read_b, pattern_b, 4) == 0;
      item.result.pass =
          item.result.reset_ok && item.result.read_a_ok && item.result.read_b_ok;
      digitalWrite(SENSOR_CS_PINS[adc], HIGH);
    }
  }

  for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
    devices[i].setMisoPin(SENSOR_MISO_PINS[i]);
    devices[i].setClockHalfPeriodUs(SENSOR_SPI_HALF_PERIOD_US);
    devices[i].setSampleAfterFallingEdge(false);
    initDevice(i, true);
  }
  sendMisoMap(request_id, SENSOR_DIAG_SPI_HALF_PERIOD_US, results, result_count);
}

void handleCommand(const PendingCommand& command) {
  // request_id is independent of the numeric "id" field: PING/STATUS/DIAG carry
  // no id but still need their response correlated by the host.
  const char* request_id = command.request_id[0] != '\0' ? command.request_id : nullptr;
  if (strcmp(command.cmd, "PING") == 0) {
    sendPong(request_id);
    return;
  }
  if (strcmp(command.cmd, "STATUS") == 0) {
    sendStatus(request_id, nullptr, false);
    return;
  }
  if (strcmp(command.cmd, "DIAG") == 0) {
    runDiagnostics(request_id);
    return;
  }
  if (strcmp(command.cmd, "DIAG_SPI") == 0) {
    runSpiDiagnostics(request_id);
    return;
  }
  if (strcmp(command.cmd, "GPIO_DIAG") == 0) {
    uint8_t cycles = 1;
    if (command.has_id && command.id >= 1 && command.id <= 100) {
      cycles = static_cast<uint8_t>(command.id);
    }
    runGpioDiagnostics(cycles, request_id);
    return;
  }
  if (strcmp(command.cmd, "MISO_MAP") == 0) {
    runMisoMap(request_id);
    return;
  }
  if (strcmp(command.cmd, "VERIFY_CONFIG") == 0) {
    sendConfigReport(request_id);
    return;
  }
  if (strcmp(command.cmd, "SET_REF") == 0) {
    uint8_t new_mode = reference_mode;
    if (strcmp(command.value, "INTERNAL_2V048") == 0) {
      new_mode = 0;  // VREF[1:0] = 00
    } else if (strcmp(command.value, "AVDD_AVSS") == 0) {
      new_mode = 3;  // VREF[1:0] = 11 -> Reg2 bits 7:6 = 0xC0
    } else {
      sendError("INVALID_VALUE", "SET_REF value must be INTERNAL_2V048 or AVDD_AVSS", request_id);
      return;
    }
    const uint8_t old_mode = reference_mode;
    reference_mode = new_mode;
    bool ok = true;
    for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
      if (runtime_state[i].state != ADC_STATE_OK) {
        continue;
      }
      uint8_t config[4];
      uint8_t readback[4];
      buildNormalConfig(config);
      if (!devices[i].configure(config, readback)) {
        runtime_state[i].state = ADC_STATE_CONFIG_ERROR;
        markDeviceError(i, "SET_REF_FAILED");
        ok = false;
      }
    }
    if (!ok) {
      reference_mode = old_mode;
      for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
        if (runtime_state[i].state != ADC_STATE_OK) {
          continue;
        }
        uint8_t config[4];
        uint8_t readback[4];
        buildNormalConfig(config);
        devices[i].configure(config, readback);
      }
      sendError("SET_REF_FAILED", "one or more ADCs did not accept the reference change", request_id);
      return;
    }
    sendStatus(request_id, nullptr, false);
    return;
  }
  if (strcmp(command.cmd, "STREAM") == 0) {
    if (command.has_id && command.id >= 0) {
      streaming = (command.id != 0);
    }
    sendStatus(request_id, nullptr, false);
    return;
  }
  if (strcmp(command.cmd, "RESET_ADC") == 0) {
    const int32_t index = command.id;
    if (index < 1 || index > 3) {
      sendError("INVALID_VALUE", "RESET_ADC id must be 1..3", request_id);
      return;
    }
    initDevice(static_cast<uint8_t>(index - 1), true);
    sendStatus(request_id, nullptr, false);
    return;
  }
  sendError("UNKNOWN_COMMAND", "supported: PING, STATUS, DIAG, DIAG_SPI, GPIO_DIAG, MISO_MAP, VERIFY_CONFIG, SET_REF, STREAM, RESET_ADC", request_id);
}

void processCommands() {
  while (queue_count > 0) {
    PendingCommand command = command_queue[queue_head];
    queue_head = static_cast<uint8_t>((queue_head + 1) % 4);
    --queue_count;
    handleCommand(command);
  }
}

void enqueueCommand(const char* cmd, const char* value, int32_t id, bool has_id, const char* request_id) {
  if (queue_count >= 4) {
    sendError("BUSY", "command queue full", request_id);
    return;
  }
  PendingCommand& slot = command_queue[queue_tail];
  slot.cmd[0] = '\0';
  slot.value[0] = '\0';
  slot.request_id[0] = '\0';
  strncpy(slot.cmd, cmd, sizeof(slot.cmd) - 1);
  strncpy(slot.value, value != nullptr ? value : "", sizeof(slot.value) - 1);
  strncpy(slot.request_id, request_id != nullptr ? request_id : "", sizeof(slot.request_id) - 1);
  slot.id = id;
  slot.has_id = has_id;
  queue_tail = static_cast<uint8_t>((queue_tail + 1) % 4);
  ++queue_count;
}

void handleCommandLine() {
  JsonDocument doc;
  const DeserializationError error = deserializeJson(doc, command_buffer);
  if (error || !doc.is<JsonObject>()) {
    sendError("INVALID_JSON", "command must be one JSON object", nullptr);
    return;
  }
  const char* cmd = doc["cmd"];
  if (cmd == nullptr || cmd[0] == '\0' || strlen(cmd) > 15) {
    sendError("INVALID_COMMAND", "missing or too long cmd", nullptr);
    return;
  }
  const char* request_id = nullptr;
  char request_copy[65] = {0};
  if (doc["request_id"].is<const char*>()) {
    request_id = doc["request_id"];
    if (strlen(request_id) > 64) {
      sendError("INVALID_REQUEST_ID", "request_id exceeds 64 characters", nullptr);
      return;
    }
    strncpy(request_copy, request_id, sizeof(request_copy) - 1);
    request_id = request_copy;
  }
  const char* value = doc["value"].is<const char*>() ? doc["value"].as<const char*>() : "";
  int32_t id = -1;
  bool has_id = false;
  if (doc["id"].is<int32_t>()) {
    id = doc["id"].as<int32_t>();
    has_id = true;
  } else if (doc["value"].is<bool>()) {
    id = doc["value"].as<bool>() ? 1 : 0;
    has_id = true;
  }
  enqueueCommand(cmd, value, id, has_id, request_id);
}

void serviceSerialInput() {
  uint16_t budget = 64;
  while (Serial.available() > 0 && budget-- > 0) {
    const char value = static_cast<char>(Serial.read());
    last_command_byte_ms = millis();
    if (value == '\n' || value == '\r') {
      if (command_overflow) {
        sendError("COMMAND_TOO_LONG", "command line exceeded buffer", nullptr);
        command_length = 0;
        command_overflow = false;
      } else if (command_length > 0) {
        command_buffer[command_length] = '\0';
        handleCommandLine();
        command_length = 0;
      }
      continue;
    }
    if (command_overflow) {
      continue;
    }
    if (command_length < SENSOR_MAX_COMMAND_BYTES) {
      command_buffer[command_length++] = value;
    } else {
      command_overflow = true;
    }
  }
  if ((command_length > 0 || command_overflow) &&
      (millis() - last_command_byte_ms) > SENSOR_COMMAND_PARTIAL_TIMEOUT_MS) {
    sendError("INCOMPLETE_COMMAND", "command line timed out", nullptr);
    command_length = 0;
    command_overflow = false;
  }
}

}  // namespace

void setup() {
  // GPIO5 is CS3 and a boot strapping pin.  Set the output register high
  // before enabling the output driver, then keep every CS line high.
  gpio_set_level(static_cast<gpio_num_t>(SENSOR_CS_PINS[2]), 1);
  pinMode(SENSOR_CS_PINS[2], OUTPUT);
  digitalWrite(SENSOR_CS_PINS[2], HIGH);
  for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
    pinMode(SENSOR_CS_PINS[i], OUTPUT);
    digitalWrite(SENSOR_CS_PINS[i], HIGH);
  }

  Serial.begin(SENSOR_SERIAL_BAUD, SERIAL_8N1);
  delay(50);

  const uint64_t mac = ESP.getEfuseMac();
  const uint32_t random_part = esp_random();
  snprintf(boot_id, sizeof(boot_id), "%s-%04x%08x", SENSOR_DEVICE_ID,
           static_cast<unsigned>((mac >> 32) & 0xFFFFu), static_cast<unsigned>(random_part));

  for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
    runtime_state[i].state = ADC_STATE_RECOVERING;
    runtime_state[i].consecutive_errors = 0;
    runtime_state[i].total_errors = 0;
    runtime_state[i].recovered = 0;
    runtime_state[i].last_error = nullptr;
    runtime_state[i].last_reinit_ms = 0;
    runtime_state[i].last_success_ms = millis();
    runtime_state[i].config_check_counter = 0;
    devices[i].begin();
    invalidateChannel(static_cast<uint8_t>(i * 4 + 0));
    invalidateChannel(static_cast<uint8_t>(i * 4 + 1));
    invalidateChannel(static_cast<uint8_t>(i * 4 + 2));
    invalidateChannel(static_cast<uint8_t>(i * 4 + 3));
  }
  delay(20);  // ADS1220 power-on settling

  for (uint8_t i = 0; i < SENSOR_ADC_COUNT; ++i) {
    initDevice(i, false);
  }

  sendHello();
  last_command_byte_ms = millis();
}

void loop() {
  serviceSerialInput();
  if (streaming) {
    scanFrame();
  } else {
    processCommands();
    delay(1);
  }
}
