// JSONL frame builders for the V2 FSR firmware.
//
// The wire format is protocol_version 1 JSON lines, as before.  The V2
// additions are additive and optional for an old consumer:
//   * "sensor_profile"      FSR_ONLY or HYBRID_6X6_FSR2
//   * "sensor_kind"         MATRIX_CELL or FSR, per channel in channel_config
//   * "fsr_layout"          FSR divider description in HELLO/STATUS
//   * "channel_config.status" carries the verification state honestly
//
// The builders take the profile by reference, so the same compiled code emits
// both profiles and the host tests can build either one.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "fsr2.h"

struct Fsr2SampleFrame {
  const Fsr2Profile* profile;
  const char* boot_id;
  uint32_t frame_seq;
  uint32_t timestamp_us;
  bool has_previous;
  uint32_t previous_frame_us;
  const int32_t* raw_adc;
  const bool* valid;
  const uint32_t* sample_timestamp_us;
  const uint8_t* channel_flags;
  uint32_t effective_frame_rate_centi_hz;
  const Fsr2AdcStatusSnapshot* adc_status;
  uint8_t adc_status_count;
};

struct Fsr2StatusFrame {
  const Fsr2Profile* profile;
  const char* boot_id;
  uint32_t uptime_ms;
  bool streaming;
  uint32_t frame_rate_centi_hz;
  uint32_t last_frame_seq;
  const char* last_error;  // nullptr when no error is recorded
  const Fsr2AdcStatusSnapshot* adc_status;
  uint8_t adc_status_count;
  const char* request_id;     // nullptr when the frame is unsolicited
  const char* config_report;  // optional prebuilt JSON object, nullptr when absent
};

bool fsr2BuildSampleFrame(char* buffer, size_t capacity, const Fsr2SampleFrame& frame);
bool fsr2BuildHelloFrame(char* buffer, size_t capacity, const Fsr2Profile& profile,
                         const char* boot_id, const Fsr2AdcStatusSnapshot* adc_status,
                         uint8_t adc_status_count);
bool fsr2BuildStatusFrame(char* buffer, size_t capacity, const Fsr2StatusFrame& frame);
bool fsr2BuildPongFrame(char* buffer, size_t capacity, const Fsr2Profile& profile,
                        const char* boot_id, const char* request_id);
bool fsr2BuildErrorFrame(char* buffer, size_t capacity, const char* code, const char* message,
                         const char* request_id);

// VERIFY_CONFIG payload.  readback and expected are count*4 register bytes;
// mux_codes is the last MUX code written to each device, so expected[0] can be
// rebuilt exactly instead of assuming a fixed MUX.
bool fsr2BuildConfigReport(char* buffer, size_t capacity, const Fsr2Profile& profile,
                           const uint8_t* readback, const uint8_t* expected, const bool* read_ok,
                           const uint8_t* mux_codes, uint8_t count);
