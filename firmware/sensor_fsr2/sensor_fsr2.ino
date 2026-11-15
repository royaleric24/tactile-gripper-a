// V2 tactile gripper acquisition firmware: four ADS1220.
//
//   default                            FSR_ONLY (FSR_A, ADC4 AIN0)
//   -DFSR2_PROFILE_ELECTRODES12_FSR1   twelve passive electrodes plus FSR_A
//   -DFSR2_PROFILE_ELECTRODES12        twelve passive electrodes (ADC1..ADC3)
//   -DFSR2_PROFILE_LEGACY_FSR2         historical dual-FSR build
//   -DFSR2_PROFILE_ELECTRODES12_FSR2   historical twelve electrodes plus dual FSR
//
// The electrode profile carries no GPIO column drive: R1..R6 are pulled to GND
// through 10 kOhm and C1..C6 to 3.3 V through 1 kOhm, each on its own AIN.
//
// The heavy lifting lives in the sibling translation units so the host tests
// can compile them without the Arduino runtime:
//   ads1220_multi.*       bit-banged driver, four instances
//   fsr2.*                channel table validation and lookup
//   frame_builder_fsr2.*  HELLO/SAMPLE/STATUS/ERROR/PONG JSON lines
//   sampler_fsr2.*        the acquisition loop
//   fsr2_config.h         generated from config/sensor_esp32_fsr2*.json
//
// This file only owns Serial, the command parser, the boot id and the loop.
// It never claims PASS: the firmware reports channel_config.status as
// IMPLEMENTED_UNVERIFIED until a real wiring and sampling session is recorded.

#include <Arduino.h>
#include <ArduinoJson.h>

#if defined(ARDUINO_ARCH_ESP32)
#include <driver/gpio.h>
#include <esp_system.h>
#endif

#include "fsr2.h"
#if defined(FSR2_PROFILE_ELECTRODES12_FSR1)
#include "fsr2_config_electrodes12_fsr1.h"
static_assert(sizeof(FSR2_CHANNELS) / sizeof(FSR2_CHANNELS[0]) == 13, "expected 12 electrodes plus FSR_A");
#elif defined(FSR2_PROFILE_ELECTRODES12_FSR2)
#include "fsr2_config_electrodes12_fsr2.h"
#elif defined(FSR2_PROFILE_ELECTRODES12)
#include "fsr2_config_electrodes12.h"
#elif defined(FSR2_PROFILE_LEGACY_FSR2)
#include "fsr2_config.h"
#else
#include "fsr2_config_fsr1.h"
static_assert(sizeof(FSR2_CHANNELS) / sizeof(FSR2_CHANNELS[0]) == 1, "expected only FSR_A");
#endif
#include "frame_builder_fsr2.h"
#include "sampler_fsr2.h"

namespace {

const size_t kOutBufferSize = 8192;
const size_t kCommandBufferSize = FSR2_COMMAND_BUFFER_BYTES + 1;
const size_t kReportBufferSize = 2048;
const uint8_t kReadChunkBytes = 64;
const uint8_t kMaxCommandLength = 15;
const uint8_t kMaxRequestIdLength = 64;

char out_buffer[kOutBufferSize];
char report_buffer[kReportBufferSize];
char command_buffer[kCommandBufferSize];
size_t command_length = 0;
uint32_t command_last_byte_ms = 0;
char boot_id[48];
bool wrote_hello = false;

Fsr2Sampler sampler(FSR2_PROFILE);

void sendRaw(const char* data, size_t length) {
  if (data == nullptr || length == 0) return;
  Serial.write(reinterpret_cast<const uint8_t*>(data), length);
}

void sendFramed(const char* data, size_t length) {
  sendRaw(data, length);
}

void sendError(const char* code, const char* message, const char* request_id) {
  if (fsr2BuildErrorFrame(out_buffer, kOutBufferSize, code, message, request_id)) {
    sendFramed(out_buffer, strlen(out_buffer));
    return;
  }
  static const char kFallback[] =
      "{\"protocol_version\":1,\"type\":\"ERROR\",\"code\":\"FRAME_BUILD_FAILED\","
      "\"message\":\"\",\"fatal\":false}\n";
  sendRaw(kFallback, sizeof(kFallback) - 1);
}

void sendHello() {
  Fsr2AdcStatusSnapshot status[4];
  for (uint8_t index = 0; index < sampler.adcStatusCount(); ++index) {
    status[index] = sampler.adcStatus(index);
  }
  if (!fsr2BuildHelloFrame(out_buffer, kOutBufferSize, FSR2_PROFILE, boot_id, status,
                           sampler.adcStatusCount())) {
    sendError("FRAME_TOO_LARGE", "HELLO does not fit in the output buffer", nullptr);
    return;
  }
  wrote_hello = true;
  sendFramed(out_buffer, strlen(out_buffer));
}

void sendStatus(const char* request_id, const char* config_report) {
  Fsr2AdcStatusSnapshot status[4];
  for (uint8_t index = 0; index < sampler.adcStatusCount(); ++index) {
    status[index] = sampler.adcStatus(index);
  }
  Fsr2StatusFrame frame;
  frame.profile = &FSR2_PROFILE;
  frame.boot_id = boot_id;
  frame.uptime_ms = millis();
  frame.streaming = sampler.streaming();
  frame.frame_rate_centi_hz = sampler.frameRateCentiHz();
  frame.last_frame_seq = sampler.frameSeq();
  frame.last_error = sampler.lastError();
  frame.adc_status = status;
  frame.adc_status_count = sampler.adcStatusCount();
  frame.request_id = request_id;
  frame.config_report = config_report;
  if (!fsr2BuildStatusFrame(out_buffer, kOutBufferSize, frame)) {
    sendError("FRAME_TOO_LARGE", "STATUS does not fit in the output buffer", request_id);
    return;
  }
  sendFramed(out_buffer, strlen(out_buffer));
}

void sendPong(const char* request_id) {
  if (!fsr2BuildPongFrame(out_buffer, kOutBufferSize, FSR2_PROFILE, boot_id, request_id)) {
    sendError("FRAME_TOO_LARGE", "PONG does not fit in the output buffer", request_id);
    return;
  }
  sendFramed(out_buffer, strlen(out_buffer));
}

void sendSampleFrame() {
  if (!fsr2BuildSampleFrame(out_buffer, kOutBufferSize, sampler.frame())) {
    sendError("FRAME_TOO_LARGE", "SAMPLE does not fit in the output buffer", nullptr);
    return;
  }
  sendFramed(out_buffer, strlen(out_buffer));
}

bool equalsIgnoreCase(const char* left, const char* right) {
  if (left == nullptr || right == nullptr) return false;
  while (*left != '\0' && *right != '\0') {
    char a = *left;
    char b = *right;
    if (a >= 'a' && a <= 'z') a = static_cast<char>(a - 'a' + 'A');
    if (b >= 'a' && b <= 'z') b = static_cast<char>(b - 'a' + 'A');
    if (a != b) return false;
    ++left;
    ++right;
  }
  return *left == '\0' && *right == '\0';
}

bool parseStreamValue(const char* value, bool* on) {
  if (value == nullptr) return false;
  if (equalsIgnoreCase(value, "on") || equalsIgnoreCase(value, "1") ||
      equalsIgnoreCase(value, "start") || equalsIgnoreCase(value, "true")) {
    *on = true;
    return true;
  }
  if (equalsIgnoreCase(value, "off") || equalsIgnoreCase(value, "0") ||
      equalsIgnoreCase(value, "stop") || equalsIgnoreCase(value, "false")) {
    *on = false;
    return true;
  }
  return false;
}

void handleLine(const char* line) {
  if (line == nullptr || line[0] == '\0') return;

  JsonDocument document;
  const DeserializationError error = deserializeJson(document, line);
  if (error) {
    sendError("INVALID_JSON", error.c_str(), nullptr);
    return;
  }
  if (!document.is<JsonObject>()) {
    sendError("INVALID_COMMAND", "command line must be a JSON object", nullptr);
    return;
  }

  const char* command = document["cmd"] | "";
  const char* request_id = nullptr;
  if (document["request_id"].is<const char*>()) {
    request_id = document["request_id"].as<const char*>();
    if (request_id != nullptr && strlen(request_id) > kMaxRequestIdLength) {
      sendError("INVALID_REQUEST_ID", "request_id is longer than 64 characters", nullptr);
      return;
    }
  }
  const char* value = document["value"] | "";
  const int numeric_id = document["id"] | 0;

  if (equalsIgnoreCase(command, "PING")) {
    sendPong(request_id);
    return;
  }
  if (equalsIgnoreCase(command, "HELLO")) {
    sendHello();
    return;
  }
  if (equalsIgnoreCase(command, "STATUS")) {
    sendStatus(request_id, nullptr);
    return;
  }
  if (equalsIgnoreCase(command, "STREAM") || equalsIgnoreCase(command, "STOP")) {
    bool on = false;
    if (equalsIgnoreCase(command, "STOP")) {
      on = false;
    } else if (!parseStreamValue(value, &on)) {
      sendError("INVALID_VALUE", "STREAM expects on|off|start|stop", request_id);
      return;
    }
    sampler.setStreaming(on);
    sendStatus(request_id, nullptr);
    return;
  }
  if (equalsIgnoreCase(command, "RESET_ADC")) {
    const uint32_t now_ms = millis();
    if (numeric_id >= 1 && numeric_id <= sampler.adcStatusCount()) {
      sampler.reinitDevice(static_cast<uint8_t>(numeric_id - 1), now_ms);
    } else if (numeric_id == 0) {
      for (uint8_t index = 0; index < sampler.adcStatusCount(); ++index) {
        sampler.reinitDevice(index, now_ms);
      }
    } else {
      sendError("INVALID_ID", "RESET_ADC id must be 0 or an existing ADS1220 id", request_id);
      return;
    }
    sendStatus(request_id, nullptr);
    return;
  }
  if (equalsIgnoreCase(command, "VERIFY_CONFIG")) {
    const bool report_ok = sampler.buildConfigReport(report_buffer, kReportBufferSize);
    sendStatus(request_id, report_ok ? report_buffer : nullptr);
    if (!report_ok) {
      sendError("VERIFY_CONFIG_FAILED", "register readback did not build", request_id);
    }
    return;
  }

  static const char kSupported[] =
      "PING, STATUS, HELLO, STREAM, STOP, RESET_ADC, VERIFY_CONFIG";
  char message[160];
  snprintf(message, sizeof(message), "supported commands: %s", kSupported);
  sendError("UNKNOWN_COMMAND", message, request_id);
}

}  // namespace

void serviceSerialInput() {
  uint8_t budget = kReadChunkBytes;
  while (budget-- > 0 && Serial.available() > 0) {
    const int incoming = Serial.read();
    if (incoming < 0) break;
    const char value = static_cast<char>(incoming);
    command_last_byte_ms = millis();
    if (value == '\n' || value == '\r') {
      if (command_length == 0) continue;
      command_buffer[command_length] = '\0';
      handleLine(command_buffer);
      command_length = 0;
      continue;
    }
    if (command_length >= kCommandBufferSize - 1) {
      command_length = 0;
      sendError("COMMAND_TOO_LONG", "command line exceeds the buffer", nullptr);
      continue;
    }
    command_buffer[command_length++] = value;
  }

  if (command_length > 0 &&
      (millis() - command_last_byte_ms) > FSR2_PROFILE.command_partial_timeout_ms) {
    command_length = 0;
    sendError("INCOMPLETE_COMMAND", "command line timed out", nullptr);
  }
}

void setup() {
  // Keep GPIO5 (ADC3 chip select, also an ESP32 strapping pin) high before the
  // output driver is enabled so the converter is never selected during boot.
#if defined(ARDUINO_ARCH_ESP32)
  gpio_set_level(static_cast<gpio_num_t>(FSR2_CS_PINS[2]), 1);
#endif

  Serial.begin(FSR2_PROFILE.serial_baud, SERIAL_8N1);
  delay(50);

  command_length = 0;
  command_last_byte_ms = millis();
#if defined(ARDUINO_ARCH_ESP32)
  const uint64_t mac = ESP.getEfuseMac();
  snprintf(boot_id, sizeof(boot_id), "%04x%08x-%08x", static_cast<uint16_t>(mac >> 32),
           static_cast<uint32_t>(mac), static_cast<uint32_t>(esp_random()));
#else
  snprintf(boot_id, sizeof(boot_id), "sim-%08x", static_cast<uint32_t>(millis()));
#endif

  sampler.setPollHook(serviceSerialInput);
  if (!sampler.begin(boot_id, millis())) {
    sendError("UNSUPPORTED_CHANNEL_LAYOUT", sampler.lastError(), nullptr);
  }
  sendHello();
}

void loop() {
  serviceSerialInput();
  if (sampler.streaming()) {
    if (sampler.scanFrame(static_cast<uint32_t>(micros()), millis())) {
      sendSampleFrame();
    }
  } else {
    delay(1);
  }
}
