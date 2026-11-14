#include "sampler_fsr2.h"

#include <Arduino.h>

namespace {

const uint32_t kDataTimeoutMs = 2000;
const uint16_t kConfigCheckInterval = 256;
const int32_t kPositiveFullScale = 8388607;   // 2^23 - 1
const int32_t kNegativeFullScale = -8388608;  // -2^23
const int32_t kNearRail = 8220834;            // 98 % of the positive full scale
const uint8_t kMaxChannels = 64;
const uint8_t kMaxAdcs = 4;
const uint8_t kMaxColumns = 16;
const uint8_t kMaxWindow = 64;

uint8_t clampWindow(uint8_t requested) {
  if (requested < 2) return 2;
  if (requested > kMaxWindow) return kMaxWindow;
  return requested;
}

}  // namespace

Fsr2Sampler::Fsr2Sampler(const Fsr2Profile& profile)
    : profile_(&profile),
      devices_{},
      status_{},
      last_success_ms_{0, 0, 0, 0},
      last_reinit_ms_{0, 0, 0, 0},
      config_checks_{0, 0, 0, 0},
      last_mux_code_{8, 8, 8, 8},
      channel_raw_{0},
      channel_valid_{false},
      channel_sample_us_{0},
      channel_flags_{0},
      stuck_frames_{0},
      sample_{},
      boot_id_("unknown"),
      last_error_(nullptr),
      frame_seq_(0),
      frame_rate_centi_hz_(0),
      last_frame_us_(0),
      previous_frame_us_(0),
      frame_start_us_{0},
      frame_start_index_(0),
      frame_start_count_(0),
      window_(32),
      streaming_(false),
      started_(false),
      poll_hook_(nullptr) {}

uint8_t Fsr2Sampler::firstChannelOfDevice(uint8_t index) const {
  for (uint8_t channel_id = 0; channel_id < profile_->channel_count; ++channel_id) {
    if (profile_->channels[channel_id].adc_index == index) return channel_id;
  }
  return 0;
}

void Fsr2Sampler::buildExpectedConfig(uint8_t index, uint8_t mux_code, uint8_t out[4]) const {
  (void)index;
  out[0] = static_cast<uint8_t>((mux_code << 4) | (profile_->gain_code << 1) |
                                (profile_->pga_bypass != 0 ? 1 : 0));
  // Single-shot conversion, normal operating mode: TS = 0, CM = 0.
  out[1] = static_cast<uint8_t>(profile_->data_rate_code << 5);
  out[2] = static_cast<uint8_t>(profile_->reference_mode_code << 6);
  out[3] = 0x00;
}

bool Fsr2Sampler::begin(const char* boot_id, uint32_t now_ms) {
  boot_id_ = (boot_id == nullptr) ? "unknown" : boot_id;
  started_ = false;
  if (!fsr2ValidateLayout(*profile_)) {
    last_error_ = "UNSUPPORTED_CHANNEL_LAYOUT";
    return false;
  }
  if (profile_->channel_count > kMaxChannels || profile_->adc_count > kMaxAdcs ||
      profile_->column_count > kMaxColumns) {
    last_error_ = "PROFILE_EXCEEDS_FIRMWARE_LIMITS";
    return false;
  }

  window_ = clampWindow(profile_->frame_rate_window);
  frame_start_index_ = 0;
  frame_start_count_ = 0;
  frame_seq_ = 0;
  frame_rate_centi_hz_ = 0;
  last_frame_us_ = 0;
  previous_frame_us_ = 0;

  for (uint8_t index = 0; index < profile_->adc_count; ++index) {
    Ads1220Pins pins;
    pins.sclk = profile_->sclk_pin;
    pins.mosi = profile_->mosi_pin;
    pins.miso = profile_->miso_pins[index];
    pins.cs = profile_->cs_pins[index];
    devices_[index].setIndex(index);
    devices_[index].begin(pins, profile_->spi_half_period_us);
    status_[index].state = FSR2_ADC_RECOVERING;
    status_[index].consecutive_errors = 0;
    status_[index].total_errors = 0;
    status_[index].recovered = 0;
    status_[index].last_error = nullptr;
    last_success_ms_[index] = 0;
    last_reinit_ms_[index] = 0;
    config_checks_[index] = 0;
    last_mux_code_[index] = profile_->channels[firstChannelOfDevice(index)].mux_code;
  }
  for (uint8_t channel_id = 0; channel_id < kMaxChannels; ++channel_id) {
    invalidateChannel(channel_id);
  }
  for (uint8_t index = 0; index < profile_->adc_count; ++index) {
    last_mux_code_[index] = profile_->channels[firstChannelOfDevice(index)].mux_code;
  }

  delay(20);  // let the four converters finish their power-on reset
  for (uint8_t index = 0; index < profile_->adc_count; ++index) {
    initDevice(index, false, now_ms);
  }
  started_ = true;
  return true;
}

bool Fsr2Sampler::initDevice(uint8_t index, bool recovery, uint32_t now_ms) {
  if (index >= profile_->adc_count) return false;
  last_reinit_ms_[index] = now_ms;
  config_checks_[index] = 0;
  status_[index].state = FSR2_ADC_RECOVERING;

  uint8_t reset_defaults[4] = {0, 0, 0, 0};
  bool ok = devices_[index].probe(reset_defaults);
  if (ok) {
    const uint8_t mux = profile_->channels[firstChannelOfDevice(index)].mux_code;
    uint8_t expected[4];
    buildExpectedConfig(index, mux, expected);
    uint8_t readback[4] = {0, 0, 0, 0};
    ok = devices_[index].configure(expected, readback);
    if (ok) last_mux_code_[index] = mux;
  }

  if (ok) {
    status_[index].state = FSR2_ADC_OK;
    status_[index].consecutive_errors = 0;
    status_[index].last_error = nullptr;
    if (recovery && status_[index].recovered < 0xFFFF) {
      ++status_[index].recovered;
    }
    last_success_ms_[index] = now_ms;
    last_error_ = nullptr;
    return true;
  }

  status_[index].state = FSR2_ADC_NO_RESPONSE;
  status_[index].last_error = "PROBE_OR_CONFIG_READBACK_FAILED";
  if (status_[index].consecutive_errors < 0xFF) ++status_[index].consecutive_errors;
  if (status_[index].total_errors < 0xFFFF) ++status_[index].total_errors;
  last_error_ = "PROBE_OR_CONFIG_READBACK_FAILED";
  return false;
}

bool Fsr2Sampler::reinitDevice(uint8_t index, uint32_t now_ms) {
  return initDevice(index, true, now_ms);
}

void Fsr2Sampler::markDeviceError(uint8_t index, const char* code) {
  if (index >= profile_->adc_count) return;
  if (status_[index].consecutive_errors < 0xFF) ++status_[index].consecutive_errors;
  if (status_[index].total_errors < 0xFFFF) ++status_[index].total_errors;
  status_[index].last_error = code;
  last_error_ = code;
  if (status_[index].consecutive_errors >= profile_->reinit_after_errors) {
    status_[index].state = FSR2_ADC_FAILED;
  }
}

void Fsr2Sampler::invalidateChannel(uint8_t channel_id) {
  if (channel_id >= kMaxChannels) return;
  channel_raw_[channel_id] = 0;
  channel_valid_[channel_id] = false;
  channel_sample_us_[channel_id] = 0;
  channel_flags_[channel_id] = FSR2_FLAG_NO_DATA;
  stuck_frames_[channel_id] = 0;
}

void Fsr2Sampler::invalidateDeviceChannels(uint8_t index) {
  for (uint8_t channel_id = 0; channel_id < profile_->channel_count; ++channel_id) {
    if (profile_->channels[channel_id].adc_index == index) invalidateChannel(channel_id);
  }
}

void Fsr2Sampler::recordChannel(uint8_t channel_id, int32_t value, uint32_t sample_us,
                                uint32_t now_ms) {
  if (channel_id >= kMaxChannels) return;
  const Fsr2ChannelConfig& channel = profile_->channels[channel_id];

  uint8_t flags = 0;
  if (value >= kPositiveFullScale) flags |= FSR2_FLAG_SAT_HIGH;
  if (value <= kNegativeFullScale) flags |= FSR2_FLAG_SAT_LOW;
  // A single-ended AIN versus AVSS conversion cannot legitimately go negative.
  if (value < 0) flags |= FSR2_FLAG_NEGATIVE_SINGLE_ENDED;
  const int32_t magnitude = value < 0 ? -value : value;
  if (magnitude >= kNearRail) flags |= FSR2_FLAG_NEAR_RAIL;
  if (flags != 0) {
    if (stuck_frames_[channel_id] < 0xFF) ++stuck_frames_[channel_id];
  } else {
    stuck_frames_[channel_id] = 0;
  }
  if (stuck_frames_[channel_id] >= 16) flags |= FSR2_FLAG_STUCK_EXTREME;

  channel_raw_[channel_id] = value;
  channel_valid_[channel_id] = true;
  channel_sample_us_[channel_id] = sample_us;
  channel_flags_[channel_id] = flags;

  const uint8_t adc_index = channel.adc_index;
  if (adc_index < kMaxAdcs) {
    last_success_ms_[adc_index] = now_ms;
    status_[adc_index].consecutive_errors = 0;
  }
}

void Fsr2Sampler::recordFrameStart(uint32_t now_us) {
  frame_start_us_[frame_start_index_] = now_us;
  frame_start_index_ = static_cast<uint8_t>((frame_start_index_ + 1) % window_);
  if (frame_start_count_ < window_) ++frame_start_count_;
  if (frame_start_count_ < 2) return;

  const uint8_t oldest = (frame_start_count_ < window_) ? 0 : frame_start_index_;
  const uint32_t elapsed = now_us - frame_start_us_[oldest];
  if (elapsed == 0) return;
  const uint32_t intervals = static_cast<uint32_t>(frame_start_count_) - 1;
  frame_rate_centi_hz_ = static_cast<uint32_t>(
      (static_cast<uint64_t>(intervals) * 100000000ULL) / static_cast<uint64_t>(elapsed));
}

void Fsr2Sampler::poll() {
  if (poll_hook_ != nullptr) poll_hook_();
}

bool Fsr2Sampler::waitConversion(uint16_t wait_us) {
  const uint32_t start = micros();
  while (static_cast<uint32_t>(micros() - start) < wait_us) {
    poll();
    if (!streaming_) return false;
    delay(1);
  }
  return true;
}

void Fsr2Sampler::driveColumn(uint8_t column) {
  for (uint8_t index = 0; index < profile_->column_count; ++index) {
    const uint8_t pin = profile_->column_pins[index];
    if (!streaming_) return;
    if (index == column) {
      pinMode(pin, OUTPUT);
      digitalWrite(pin, HIGH);
    } else {
      // Inactive columns stay high impedance; the row pulldowns define the
      // node so an unselected column cannot drive current into the matrix.
      pinMode(pin, INPUT);
    }
  }
}

void Fsr2Sampler::parkColumns() {
  for (uint8_t index = 0; index < profile_->column_count; ++index) {
    pinMode(profile_->column_pins[index], INPUT);
  }
}

bool Fsr2Sampler::scanFrame(uint32_t now_us, uint32_t now_ms) {
  if (!started_ || !streaming_) return false;
  const uint32_t frame_start = now_us;

  if (profile_->matrix_rows > 0) {
    for (uint8_t column = 0; column < profile_->column_count; ++column) {
      parkColumns();
      if (profile_->matrix_pre_discharge_us > 0) {
        delayMicroseconds(profile_->matrix_pre_discharge_us);
      }
      driveColumn(column);
      if (profile_->matrix_settle_us > 0) {
        delayMicroseconds(profile_->matrix_settle_us);
      }
      for (uint8_t round = 0; round < profile_->matrix_rounds; ++round) {
        bool conversion_started = false;
        for (uint8_t adc = 0; adc < profile_->matrix_adc_count; ++adc) {
          if (status_[adc].state != FSR2_ADC_OK) continue;
          uint8_t channel_id = 0;
          if (!fsr2MatrixChannelIndex(*profile_, adc, round, column, &channel_id)) continue;
          devices_[adc].setMux(profile_->channels[channel_id].mux_code);
          last_mux_code_[adc] = profile_->channels[channel_id].mux_code;
          devices_[adc].startConversion();
          conversion_started = true;
        }
        if (!conversion_started) {
          for (uint8_t adc = 0; adc < profile_->matrix_adc_count; ++adc) {
            uint8_t channel_id = 0;
            if (fsr2MatrixChannelIndex(*profile_, adc, round, column, &channel_id)) {
              invalidateChannel(channel_id);
            }
          }
          continue;
        }
        if (!waitConversion(profile_->conversion_wait_us)) {
          // Streaming stopped mid-conversion: never leave a column energised.
          parkColumns();
          return false;
        }
        for (uint8_t adc = 0; adc < profile_->matrix_adc_count; ++adc) {
          uint8_t channel_id = 0;
          if (!fsr2MatrixChannelIndex(*profile_, adc, round, column, &channel_id)) continue;
          if (status_[adc].state != FSR2_ADC_OK) {
            invalidateChannel(channel_id);
            continue;
          }
          int32_t value = 0;
          if (devices_[adc].readData(&value)) {
            recordChannel(channel_id, value, static_cast<uint32_t>(micros()), now_ms);
          } else {
            markDeviceError(adc, "READ_FAILED");
            invalidateDeviceChannels(adc);
          }
        }
      }
    }
    parkColumns();
  }

  const uint8_t fsr_adc = static_cast<uint8_t>(profile_->adc_count - 1);
  for (uint8_t index = 0; index < profile_->fsr_count; ++index) {
    const uint8_t channel_id = profile_->fsr_channel_indices[index];
    if (status_[fsr_adc].state != FSR2_ADC_OK) {
      invalidateChannel(channel_id);
      continue;
    }
    devices_[fsr_adc].setMux(profile_->channels[channel_id].mux_code);
    last_mux_code_[fsr_adc] = profile_->channels[channel_id].mux_code;
    devices_[fsr_adc].startConversion();
    if (!waitConversion(profile_->conversion_wait_us)) {
      if (profile_->matrix_rows > 0) parkColumns();
      return false;
    }
    int32_t value = 0;
    if (devices_[fsr_adc].readData(&value)) {
      recordChannel(channel_id, value, static_cast<uint32_t>(micros()), now_ms);
    } else {
      markDeviceError(fsr_adc, "READ_FAILED");
      invalidateDeviceChannels(fsr_adc);
    }
  }

  ++frame_seq_;
  last_frame_us_ = frame_start;
  recordFrameStart(frame_start);

  sample_.profile = profile_;
  sample_.boot_id = boot_id_;
  sample_.frame_seq = frame_seq_;
  sample_.timestamp_us = frame_start;
  sample_.has_previous = previous_frame_us_ != 0;
  sample_.previous_frame_us = previous_frame_us_;
  sample_.raw_adc = channel_raw_;
  sample_.valid = channel_valid_;
  sample_.sample_timestamp_us = channel_sample_us_;
  sample_.channel_flags = channel_flags_;
  sample_.effective_frame_rate_centi_hz = frame_rate_centi_hz_;
  sample_.adc_status = status_;
  sample_.adc_status_count = profile_->adc_count;
  previous_frame_us_ = frame_start;

  maintain(now_ms);
  return true;
}

void Fsr2Sampler::maintain(uint32_t now_ms) {
  for (uint8_t index = 0; index < profile_->adc_count; ++index) {
    if (status_[index].state == FSR2_ADC_OK) {
      if (last_success_ms_[index] != 0 && (now_ms - last_success_ms_[index]) > kDataTimeoutMs) {
        markDeviceError(index, "DATA_TIMEOUT");
        status_[index].state = FSR2_ADC_CONFIG_ERROR;
      } else if (++config_checks_[index] >= kConfigCheckInterval) {
        config_checks_[index] = 0;
        uint8_t readback[4] = {0, 0, 0, 0};
        if (!devices_[index].readRegisters(0, readback, 4)) {
          markDeviceError(index, "REGISTER_READ_FAILED");
        } else {
          uint8_t expected[4];
          buildExpectedConfig(index, last_mux_code_[index], expected);
          if (readback[0] != expected[0] || readback[1] != expected[1] ||
              readback[2] != expected[2] || readback[3] != expected[3]) {
            // The MUX nibble is expected to match last_mux_code_ because that is
            // the last value written; a mismatch means the converter lost its
            // configuration (brown-out or an incomplete SPI write).
            status_[index].state = FSR2_ADC_CONFIG_ERROR;
            markDeviceError(index, "CONFIG_LOST");
          }
        }
      }
    }

    if (status_[index].state != FSR2_ADC_OK) {
      if ((now_ms - last_reinit_ms_[index]) >= profile_->reinit_retry_interval_ms) {
        initDevice(index, true, now_ms);
      }
    }
  }
}

bool Fsr2Sampler::deviceRegisterReadback(uint8_t index, uint8_t out[4]) {
  if (index >= profile_->adc_count || out == nullptr) return false;
  return devices_[index].readRegisters(0, out, 4);
}

bool Fsr2Sampler::buildConfigReport(char* buffer, size_t capacity) {
  uint8_t readback[kMaxAdcs * 4] = {0};
  uint8_t expected[kMaxAdcs * 4] = {0};
  bool read_ok[kMaxAdcs] = {false, false, false, false};
  uint8_t muxes[kMaxAdcs] = {0};
  for (uint8_t index = 0; index < profile_->adc_count; ++index) {
    muxes[index] = last_mux_code_[index];
    buildExpectedConfig(index, muxes[index], expected + index * 4);
    read_ok[index] = devices_[index].readRegisters(0, readback + index * 4, 4);
  }
  return fsr2BuildConfigReport(buffer, capacity, *profile_, readback, expected, read_ok, muxes,
                               profile_->adc_count);
}
