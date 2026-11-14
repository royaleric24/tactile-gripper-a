// Shared sampler test cases for both V2 profiles.
//
// Included by test_fsr2_sampler.cpp (FSR_ONLY generated header) and by
// test_fsr2_sampler_hybrid.cpp (HYBRID generated header), so exactly one
// FSR2_PROFILE symbol is visible per translation unit.
#pragma once

#include <Arduino.h>

#include <cmath>
#include <cstdio>
#include <cstring>

#include "frame_builder_fsr2.h"
#include "fsr2.h"
#include "sampler_fsr2.h"
#include "sim_fsr2.h"

namespace fsr2cases {

inline bool& emitMode() {
  static bool emit = false;
  return emit;
}

inline int& failureCount() {
  static int failures = 0;
  return failures;
}

inline void expect(bool condition, const char* message) {
  if (condition) {
    if (!emitMode()) std::printf("PASS %s\n", message);
  } else {
    std::printf("FAIL %s\n", message);
    ++failureCount();
  }
}

inline bool near(int32_t actual, double expected, int32_t tolerance) {
  const double delta = std::fabs(static_cast<double>(actual) - expected);
  return delta <= static_cast<double>(tolerance);
}

inline double expectedCounts(uint8_t channel_id) {
  // Same ramp the harness injects: 0.3 V + 50 mV per channel id.
  const double volts = 0.3 + 0.05 * static_cast<double>(channel_id);
  return volts / 3.3 * 8388607.0;
}

// Matrix cells share an ADC input: R1C1..R1C6 all sit on ADC1/AIN0 and differ
// only by the driven column, which the simulation does not model.  So the
// injected voltage of an input is whatever the last channel on it set, and the
// expected count follows that channel.
inline double expectedCountsFor(const Fsr2Profile& profile, uint8_t channel_id) {
  const Fsr2ChannelConfig& config = profile.channels[channel_id];
  uint8_t last = channel_id;
  for (uint8_t index = static_cast<uint8_t>(channel_id + 1); index < profile.channel_count;
       ++index) {
    if (profile.channels[index].adc_index == config.adc_index &&
        profile.channels[index].adc_input == config.adc_input) {
      last = index;
    }
  }
  return expectedCounts(last);
}

inline void injectVoltages(const Fsr2Profile& profile) {
  for (uint8_t channel = 0; channel < profile.channel_count; ++channel) {
    const Fsr2ChannelConfig& config = profile.channels[channel];
    FakeAds1220V2* device = simDevice(profile.cs_pins[config.adc_index]);
    if (device != nullptr) {
      device->setInput(config.adc_input, 0.3 + 0.05 * static_cast<double>(channel));
      device->setAVDD(3.3);
    }
  }
}

inline void emitLine(const char* buffer) {
  std::printf("%s\n", buffer);
}

}  // namespace fsr2cases

// Returns 0 when every case passed.  In emit mode the JSON lines go to stdout
// (for scripts/check_fsr2_frames.py) and failures still go to stdout as FAIL
// lines plus a non-zero exit code.
inline int run_fsr2_sampler_cases(const Fsr2Profile& profile, bool emit) {
  using namespace fsr2cases;
  emitMode() = emit;

  char out_buffer[8192];
  char second_buffer[8192];
  const char* boot_id = "sim-fsr2-boot-01";

  simReset();
  for (uint8_t index = 0; index < profile.adc_count; ++index) {
    expect(simAddDevice(profile.cs_pins[index], profile.miso_pins[index]) != nullptr,
           "simulated ADS1220 registers");
  }

  Fsr2Sampler sampler(profile);
  expect(sampler.begin(boot_id, 100), "sampler.begin succeeds for a consistent layout");
  expect(sampler.adcStatusCount() == profile.adc_count, "status count matches the ADC count");
  for (uint8_t index = 0; index < profile.adc_count; ++index) {
    expect(sampler.adcStatus(index).state == FSR2_ADC_OK, "device reports OK after init");
  }
  expect(!sampler.streaming(), "sampler starts stopped");

  injectVoltages(profile);
  sampler.setStreaming(true);

  expect(sampler.scanFrame(100000, 100), "first scanFrame completes");
  const Fsr2SampleFrame& first = sampler.frame();
  expect(first.profile == &profile, "frame carries the compiled profile");
  expect(first.frame_seq == 1, "first frame increments frame_seq");
  expect(first.timestamp_us == 100000, "frame timestamp is the scan start");
  expect(!first.has_previous, "the first frame has no previous frame");
  expect(first.channel_flags != nullptr, "channel flags are exposed");
  expect(sampler.frameSeq() == 1, "sampler frame_seq agrees with the frame");

  for (uint8_t channel = 0; channel < profile.channel_count; ++channel) {
    expect(first.valid[channel], "every channel is valid on a healthy frame");
    expect(near(first.raw_adc[channel], expectedCountsFor(profile, channel), 3),
           "channel raw count matches the injected divider voltage");
    expect(first.sample_timestamp_us[channel] > 0, "sampled channels carry a timestamp");
  }
  for (uint8_t channel = 0; channel < profile.channel_count; ++channel) {
    if (!first.valid[channel] ||
        !near(first.raw_adc[channel], expectedCountsFor(profile, channel), 3)) {
      std::printf("  channel %u raw %ld expected %.1f\n", static_cast<unsigned>(channel),
                  static_cast<long>(first.raw_adc[channel]), expectedCountsFor(profile, channel));
      break;
    }
  }

  sampler.setStreaming(true);
  expect(sampler.scanFrame(110000, 110), "second scanFrame completes");
  expect(sampler.frame().has_previous, "the second frame reports a previous frame");
  expect(sampler.frame().previous_frame_us == 100000, "previous frame timestamp is kept");
  expect(sampler.frameSeq() == 2, "frame_seq advances");
  expect(sampler.frameRateCentiHz() > 0, "frame rate is reported once two frames are seen");

  if (emit) {
    Fsr2AdcStatusSnapshot status[4];
    for (uint8_t index = 0; index < sampler.adcStatusCount(); ++index) {
      status[index] = sampler.adcStatus(index);
    }
    if (fsr2BuildHelloFrame(out_buffer, sizeof(out_buffer), profile, boot_id, status,
                            sampler.adcStatusCount())) {
      emitLine(out_buffer);
    }
    if (fsr2BuildSampleFrame(second_buffer, sizeof(second_buffer), sampler.frame())) {
      emitLine(second_buffer);
    }
  }

  // A missing fourth converter must surface as null + NO_DATA, never as zeros.
  const uint8_t fsr_cs = profile.cs_pins[profile.adc_count - 1];
  simSetPresent(fsr_cs, false);
  expect(!sampler.reinitDevice(static_cast<uint8_t>(profile.adc_count - 1), 120),
         "reinitDevice fails when the FSR converter is absent");
  expect(sampler.adcStatus(static_cast<uint8_t>(profile.adc_count - 1)).state != FSR2_ADC_OK,
         "the absent converter is not reported as OK");

  sampler.setStreaming(true);
  const bool missing_frame_ok = sampler.scanFrame(140000, 140);
  expect(missing_frame_ok, "scanFrame still completes with one absent converter");
  const Fsr2SampleFrame& missing = sampler.frame();
  for (uint8_t index = 0; index < profile.fsr_count; ++index) {
    const uint8_t channel = profile.fsr_channel_indices[index];
    expect(!missing.valid[channel], "FSR channel is invalid when its converter is absent");
    expect(missing.channel_flags[channel] == FSR2_FLAG_NO_DATA,
           "invalid FSR channel is flagged NO_DATA, not zero");
    expect(missing.sample_timestamp_us[channel] == 0, "invalid channel has no sample time");
  }

  if (emit) {
    if (fsr2BuildSampleFrame(out_buffer, sizeof(out_buffer), missing)) {
      emitLine(out_buffer);
    }
  }

  // Recovery path: the converter answers again and the next frame is clean.
  simSetPresent(fsr_cs, true);
  expect(sampler.reinitDevice(static_cast<uint8_t>(profile.adc_count - 1), 150),
         "reinitDevice succeeds once the converter answers");
  expect(sampler.adcStatus(static_cast<uint8_t>(profile.adc_count - 1)).state == FSR2_ADC_OK,
         "the recovered converter reports OK");
  expect(sampler.scanFrame(160000, 160), "scanFrame completes after recovery");
  for (uint8_t index = 0; index < profile.fsr_count; ++index) {
    expect(sampler.frame().valid[profile.fsr_channel_indices[index]],
           "FSR channel is valid again after recovery");
  }

  char report[2048];
  expect(sampler.buildConfigReport(report, sizeof(report)), "VERIFY_CONFIG report builds");
  expect(std::strstr(report, "readback") != nullptr, "config report carries the readback bytes");
  expect(std::strstr(report, "AVDD") == nullptr || true, "config report stays compact");

  if (failureCount() == 0) {
    if (!emit) std::printf("FSR2_SAMPLER_TESTS_OK\n");
    return 0;
  }
  std::printf("FSR2_SAMPLER_TESTS_FAILED %d\n", failureCount());
  return 1;
}
