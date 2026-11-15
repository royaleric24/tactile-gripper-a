// Host test for the exact SAMPLE JSON built by the firmware.
#include <cstdio>
#include <cstring>

#include "frame_builder.h"

int main() {
  int32_t raw[12] = {1234, -567, 0, 8388607, 0, 100, 200, 300, 400, 500, 600, 700};
  bool valid[12] = {true, true, true, true, false, true, true, true, true, true, true, true};
  uint32_t sample_us[12] = {1235000, 1235100, 1235200, 1235300, 0, 1235400, 1235600, 1235700, 1235800, 1235900, 1236000, 1236100};
  uint8_t flags[12] = {0, 0, 0, 1, 32, 0, 0, 0, 0, 0, 0, 0};
  FrameAdcStatus statuses[3] = {
      {"OK", 0, 0, 0, 0, nullptr},
      {"OK", 0, 0, 0, 0, nullptr},
      {"NO_RESPONSE", 2, 0, 4, 0, "PROBE_OR_CONFIG_READBACK_FAILED"},
  };
  FrameSample sample;
  sample.device_id = "tactile-esp32-01";
  sample.boot_id = "tactile-esp32-01-1a2b3c4d";
  sample.firmware_version = "tactile-sense-0.1.0";
  sample.frame_seq = 42;
  sample.timestamp_us = 1234567;
  sample.has_previous = true;
  sample.previous_frame_us = 1213167;
  sample.raw_adc = raw;
  sample.valid = valid;
  sample.sample_timestamp_us = sample_us;
  sample.channel_flags = flags;
  sample.reference_mode = "INTERNAL_2V048";
  sample.effective_frame_rate_centi_hz = 4673;
  sample.adc_status = statuses;

  char buffer[4096];
  if (!buildSampleFrame(buffer, sizeof(buffer), sample)) {
    std::fprintf(stderr, "builder failed\n");
    return 1;
  }
  char small[32];
  if (buildSampleFrame(small, sizeof(small), sample)) {
    std::fprintf(stderr, "builder did not detect overflow\n");
    return 2;
  }
  std::fputs(buffer, stdout);
  return 0;
}
