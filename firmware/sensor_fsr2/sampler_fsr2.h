// Acquisition loop for the V2 four-ADS1220 board.
//
// The sampler owns the ADS1220 instances and the channel buffer, but it never
// touches Serial: the sketch passes a poll hook so command bytes are drained
// during conversion waits, and it takes now_ms as an argument so the same code
// compiles against the host simulation (whose Arduino.h has no millis()).
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "ads1220_multi.h"
#include "frame_builder_fsr2.h"
#include "fsr2.h"

class Fsr2Sampler {
 public:
  explicit Fsr2Sampler(const Fsr2Profile& profile);

  // Validates the channel table, brings up all four ADS1220s and probes them.
  // Returns false (and records last_error()) when the profile is inconsistent;
  // the sketch must then refuse to stream instead of emitting wrong frames.
  bool begin(const char* boot_id, uint32_t now_ms);

  // Runs one full acquisition frame.  Returns false when the frame was aborted
  // (streaming disabled mid-wait) or the sampler never started.
  bool scanFrame(uint32_t now_us, uint32_t now_ms);

  // Timeout, configuration-drift and reinit supervision; called once per frame.
  void maintain(uint32_t now_ms);

  void setPollHook(void (*hook)()) { poll_hook_ = hook; }
  void setStreaming(bool on) { streaming_ = on; }
  bool streaming() const { return streaming_; }

  uint32_t frameSeq() const { return frame_seq_; }
  uint32_t frameRateCentiHz() const { return frame_rate_centi_hz_; }
  const char* lastError() const { return last_error_; }
  const Fsr2Profile& profile() const { return *profile_; }
  const Fsr2SampleFrame& frame() const { return sample_; }
  const Fsr2AdcStatusSnapshot& adcStatus(uint8_t index) const { return status_[index]; }
  uint8_t adcStatusCount() const { return profile_->adc_count; }

  bool reinitDevice(uint8_t index, uint32_t now_ms);
  bool buildConfigReport(char* buffer, size_t capacity);
  bool deviceRegisterReadback(uint8_t index, uint8_t out[4]);

 private:
  bool initDevice(uint8_t index, bool recovery, uint32_t now_ms);
  void markDeviceError(uint8_t index, const char* code);
  void invalidateChannel(uint8_t channel_id);
  void invalidateDeviceChannels(uint8_t index);
  void recordChannel(uint8_t channel_id, int32_t value, uint32_t sample_us, uint32_t now_ms);
  void recordFrameStart(uint32_t now_us);
  bool waitConversion(uint16_t wait_us);
  void driveColumn(uint8_t column);
  void parkColumns();
  void poll();
  void buildExpectedConfig(uint8_t index, uint8_t mux_code, uint8_t out[4]) const;
  uint8_t firstChannelOfDevice(uint8_t index) const;

  const Fsr2Profile* profile_;
  Ads1220Device devices_[4];
  Fsr2AdcStatusSnapshot status_[4];
  uint32_t last_success_ms_[4];
  uint32_t last_reinit_ms_[4];
  uint16_t config_checks_[4];
  uint8_t last_mux_code_[4];

  int32_t channel_raw_[64];
  bool channel_valid_[64];
  uint32_t channel_sample_us_[64];
  uint8_t channel_flags_[64];
  uint8_t stuck_frames_[64];

  Fsr2SampleFrame sample_;
  const char* boot_id_;
  const char* last_error_;
  uint32_t frame_seq_;
  uint32_t frame_rate_centi_hz_;
  uint32_t last_frame_us_;
  uint32_t previous_frame_us_;
  uint32_t frame_start_us_[64];
  uint8_t frame_start_index_;
  uint8_t frame_start_count_;
  uint8_t window_;
  bool streaming_;
  bool started_;
  void (*poll_hook_)();
};
