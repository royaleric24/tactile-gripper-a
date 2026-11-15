// Shared sampler test cases for every V2 profile.
//
// Included by test_fsr2_sampler.cpp (FSR_ONLY generated header),
// test_fsr2_sampler_electrodes.cpp (production 14-channel electrode header) and
// test_fsr2_sampler_mapped.cpp (synthetic mapped electrode table).  Exactly one
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

// Same ramp the harness injects: 0.3 V + 50 mV per channel id.
inline double expectedCounts(uint8_t channel_id) {
  const double volts = 0.3 + 0.05 * static_cast<double>(channel_id);
  return volts / 3.3 * 8388607.0;
}

inline bool channelMapped(const Fsr2ChannelConfig& channel) {
  return channel.adc_index != FSR2_UNMAPPED && channel.adc_input != FSR2_UNMAPPED;
}

inline void injectVoltages(const Fsr2Profile& profile) {
  for (uint8_t channel = 0; channel < profile.channel_count; ++channel) {
    const Fsr2ChannelConfig& config = profile.channels[channel];
    if (!channelMapped(config)) continue;
    FakeAds1220V2* device = simDevice(profile.cs_pins[config.adc_index]);
    if (device != nullptr) {
      device->setInput(config.adc_input, 0.3 + 0.05 * static_cast<double>(channel));
      device->setAVDD(3.3);
    }
  }
}

inline void emitLine(const char* buffer) { std::printf("%s\n", buffer); }

inline bool isElectrode(const Fsr2Profile& profile, uint8_t channel) {
  return profile.channels[channel].kind == FSR2_KIND_ELECTRODE;
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
  const bool mapped_electrodes = fsr2ElectrodesMapped(profile);
  const bool has_electrodes = profile.electrode_count > 0;
  const bool has_fsr = profile.fsr_count > 0;

  simReset();
  for (uint8_t index = 0; index < profile.adc_count; ++index) {
    expect(simAddDevice(profile.cs_pins[index], profile.miso_pins[index]) != nullptr,
           "simulated ADS1220 registers");
  }

  Fsr2Sampler sampler(profile);
  const bool started = sampler.begin(boot_id, 100);
  expect(started, "sampler.begin succeeds for a consistent layout");
  if (!started) {
    std::printf("FSR2_SAMPLER_TESTS_FAILED %d (layout: %s)\n", failureCount(),
                sampler.lastError() == nullptr ? "unknown" : sampler.lastError());
    return 1;
  }
  expect(sampler.adcStatusCount() == profile.adc_count, "status count matches the ADC count");
  for (uint8_t index = 0; index < profile.adc_count; ++index) {
    expect(sampler.adcStatus(index).state == FSR2_ADC_OK, "device reports OK after init");
  }
  expect(!sampler.streaming(), "sampler starts stopped");
  if (has_electrodes) {
    expect(fsr2ElectrodesMapped(profile) == mapped_electrodes,
           "electrode mapping status is reported consistently");
  }

  injectVoltages(profile);
  sampler.setStreaming(true);

  expect(sampler.scanFrame(100000, 100), "first scanFrame completes");
  const Fsr2SampleFrame& first = sampler.frame();
  expect(first.profile == &profile, "frame carries the compiled profile");
  expect(first.frame_seq == 1, "first frame increments frame_seq");
  expect(first.timestamp_us == 100000, "frame timestamp is the scan start");
  expect(!first.has_previous, "the first frame has no previous frame");
  expect(sampler.frameSeq() == 1, "sampler frame_seq agrees with the frame");

  for (uint8_t channel = 0; channel < profile.channel_count; ++channel) {
    const Fsr2ChannelConfig& config = profile.channels[channel];
    if (config.kind == FSR2_KIND_ELECTRODE && !mapped_electrodes) {
      expect(!first.valid[channel], "unmapped electrode is invalid, not fabricated");
      expect(first.channel_flags[channel] == FSR2_FLAG_NO_DATA,
             "unmapped electrode carries NO_DATA");
      expect(first.sample_timestamp_us[channel] == 0,
             "unmapped electrode has no sample time");
      continue;
    }
    expect(first.valid[channel], "mapped channel is valid on a healthy frame");
    expect(near(first.raw_adc[channel], expectedCounts(channel), 3),
           "mapped channel raw count matches the injected voltage");
    expect(first.sample_timestamp_us[channel] > 0, "mapped channel carries a timestamp");
  }
  if (has_fsr) {
    for (uint8_t index = 0; index < profile.fsr_count; ++index) {
      expect(first.valid[profile.fsr_channel_indices[index]],
             "FSR channel stays valid independently of the electrode mapping");
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

  // Degraded frame: disconnect the converter that carries the most interesting
  // channel group (FSR ADC when present, otherwise the first electrode ADC).
  const uint8_t victim = has_fsr ? static_cast<uint8_t>(profile.adc_count - 1) : 0;
  simSetPresent(profile.cs_pins[victim], false);
  expect(!sampler.reinitDevice(victim, 120), "reinitDevice fails when the converter is absent");
  expect(sampler.adcStatus(victim).state != FSR2_ADC_OK,
         "the absent converter is not reported as OK");

  sampler.setStreaming(true);
  expect(sampler.scanFrame(140000, 140), "scanFrame still completes with one absent converter");
  const Fsr2SampleFrame& degraded = sampler.frame();
  for (uint8_t channel = 0; channel < profile.channel_count; ++channel) {
    const Fsr2ChannelConfig& config = profile.channels[channel];
    if (config.kind == FSR2_KIND_ELECTRODE && !mapped_electrodes) continue;
    if (config.adc_index != victim) continue;
    expect(!degraded.valid[channel], "channel on the absent converter is invalid");
    expect(degraded.channel_flags[channel] == FSR2_FLAG_NO_DATA,
           "channel on the absent converter is NO_DATA, not zero");
    expect(degraded.sample_timestamp_us[channel] == 0,
           "channel on the absent converter has no sample time");
  }

  if (emit) {
    if (fsr2BuildSampleFrame(out_buffer, sizeof(out_buffer), degraded)) {
      emitLine(out_buffer);
    }
    Fsr2AdcStatusSnapshot status[4];
    for (uint8_t index = 0; index < sampler.adcStatusCount(); ++index) {
      status[index] = sampler.adcStatus(index);
    }
    Fsr2StatusFrame report{};
    report.profile = &profile;
    report.boot_id = boot_id;
    report.uptime_ms = 140;
    report.streaming = sampler.streaming();
    report.frame_rate_centi_hz = sampler.frameRateCentiHz();
    report.last_frame_seq = sampler.frameSeq();
    report.last_error = sampler.lastError();
    report.adc_status = status;
    report.adc_status_count = sampler.adcStatusCount();
    report.request_id = "fixture-status-1";
    const bool status_built = fsr2BuildStatusFrame(out_buffer, sizeof(out_buffer), report);
    expect(status_built, "STATUS fits in the firmware line buffer");
    if (status_built) emitLine(out_buffer);
  }

  // Recovery path: the converter answers again and the next frame is clean.
  simSetPresent(profile.cs_pins[victim], true);
  expect(sampler.reinitDevice(victim, 150), "reinitDevice succeeds once the converter answers");
  expect(sampler.adcStatus(victim).state == FSR2_ADC_OK, "the recovered converter reports OK");
  expect(sampler.scanFrame(160000, 160), "scanFrame completes after recovery");
  for (uint8_t channel = 0; channel < profile.channel_count; ++channel) {
    const Fsr2ChannelConfig& config = profile.channels[channel];
    if (config.kind == FSR2_KIND_ELECTRODE && !mapped_electrodes) continue;
    if (config.adc_index != victim) continue;
    expect(sampler.frame().valid[channel], "channel on the recovered converter is valid again");
  }

  char report[2048];
  expect(sampler.buildConfigReport(report, sizeof(report)), "VERIFY_CONFIG report builds");
  expect(std::strstr(report, "readback") != nullptr, "config report carries the readback bytes");

  if (failureCount() == 0) {
    if (!emit) std::printf("FSR2_SAMPLER_TESTS_OK\n");
    return 0;
  }
  std::printf("FSR2_SAMPLER_TESTS_FAILED %d\n", failureCount());
  return 1;
}
