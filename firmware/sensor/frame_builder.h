#pragma once

#include <stddef.h>
#include <stdint.h>

// Plain views of the runtime state used to build one SAMPLE line.  Keeping this
// separate from the Arduino sketch lets the exact wire JSON be compiled and
// parsed in host tests without a board.
struct FrameAdcStatus {
  const char* state;
  uint8_t code;
  uint8_t consecutive_errors;
  uint16_t total_errors;
  uint16_t recovered;
  const char* last_error;
};

struct FrameSample {
  const char* device_id;
  const char* boot_id;
  const char* firmware_version;
  uint32_t frame_seq;
  uint32_t timestamp_us;
  bool has_previous;
  uint32_t previous_frame_us;
  const int32_t* raw_adc;
  const bool* valid;
  const uint32_t* sample_timestamp_us;
  const uint8_t* channel_flags;
  const char* reference_mode;
  uint32_t effective_frame_rate_centi_hz;
  const FrameAdcStatus* adc_status;
};

// Writes exactly one JSON line (including the trailing newline).  Returns false
// if the fixed buffer is too small; the caller must not send a partial line.
bool buildSampleFrame(char* buffer, size_t capacity, const FrameSample& sample);
