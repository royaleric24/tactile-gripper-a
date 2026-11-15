#include "Arduino.h"
#include "sim_gpio.h"

#include <cmath>
#include <cstring>

namespace {
constexpr uint8_t SLOT_COUNT = 3;
bool g_outputs[40] = {false};
uint8_t g_modes[40] = {INPUT};
bool g_mosi = false;
uint64_t g_now_us = 0;
struct Association {
  FakeAds1220* device;
  uint8_t cs;
  uint8_t miso;
};
Association g_assoc[SLOT_COUNT] = {{nullptr, 0, 0}, {nullptr, 0, 0}, {nullptr, 0, 0}};
}  // namespace

FakeAds1220* sim_add_device(uint8_t cs, uint8_t miso) {
  for (uint8_t i = 0; i < SLOT_COUNT; ++i) {
    if (g_assoc[i].device == nullptr) {
      g_assoc[i].device = new FakeAds1220(cs, miso);
      g_assoc[i].cs = cs;
      g_assoc[i].miso = miso;
      return g_assoc[i].device;
    }
  }
  return nullptr;
}

void sim_reset() {
  for (uint8_t i = 0; i < SLOT_COUNT; ++i) {
    delete g_assoc[i].device;
    g_assoc[i] = {nullptr, 0, 0};
  }
  for (uint8_t i = 0; i < 40; ++i) {
    g_outputs[i] = false;
    g_modes[i] = INPUT;
  }
  g_mosi = false;
  g_now_us = 0;
}

uint64_t sim_now_us() { return g_now_us; }

void pinMode(uint8_t pin, uint8_t mode) {
  if (pin < 40) {
    g_modes[pin] = mode;
  }
}

void digitalWrite(uint8_t pin, uint8_t value) {
  if (pin < 40) {
    g_outputs[pin] = value != 0;
  }
  if (pin == 23) {
    g_mosi = value != 0;
  }
  for (uint8_t i = 0; i < SLOT_COUNT; ++i) {
    FakeAds1220* device = g_assoc[i].device;
    if (device == nullptr) {
      continue;
    }
    if (pin == g_assoc[i].cs) {
      device->setCS(value == LOW);
    }
  }
  // SCLK must be delivered to the selected device(s).  Use a second pass so
  // the CS change above is already applied.
  if (pin == 18) {
    for (uint8_t i = 0; i < SLOT_COUNT; ++i) {
      if (g_assoc[i].device != nullptr) {
        g_assoc[i].device->onSclk(value != 0, g_mosi);
      }
    }
  }
}

int digitalRead(uint8_t pin) {
  for (uint8_t i = 0; i < SLOT_COUNT; ++i) {
    if (g_assoc[i].device != nullptr && g_assoc[i].miso == pin) {
      return g_assoc[i].device->dout();
    }
  }
  return g_outputs[pin] ? 1 : 0;
}

void delayMicroseconds(unsigned int us) {
  g_now_us += us;
  for (uint8_t i = 0; i < SLOT_COUNT; ++i) {
    if (g_assoc[i].device != nullptr) {
      g_assoc[i].device->tick(g_now_us);
    }
  }
}

void delay(unsigned long ms) { delayMicroseconds(static_cast<unsigned int>(ms * 1000UL)); }

unsigned long micros() { return static_cast<unsigned long>(g_now_us); }

FakeAds1220::FakeAds1220(uint8_t cs, uint8_t miso) : cs_(cs), miso_(miso) {}

void FakeAds1220::setCS(bool low) {
  selected_ = low;
  if (low) {
    state_ = CMD;
    command_shift_ = 0;
    bit_count_ = 0;
    din_shift_ = 0;
    out_byte_ = 0;
    out_bit_ = 7;
    dout_level_ = false;
  } else {
    state_ = IDLE;
    dout_level_ = false;
  }
}

int FakeAds1220::dout() const {
  if (!present_) {
    return stuck_high_ ? 1 : 0;
  }
  if (!selected_) {
    return 0;
  }
  return dout_level_ ? 1 : 0;
}

void FakeAds1220::onSclk(bool high, bool mosi) {
  if (!selected_) {
    return;
  }
  if (high) {
    if (state_ == RREG_DATA || state_ == RDATA) {
      dout_level_ = ((out_byte_ >> out_bit_) & 1) != 0;
      --out_bit_;
      if (out_bit_ < 0) {
        ++data_index_;
        if (data_index_ < data_count_) {
          uint8_t value = 0;
          if (state_ == RREG_DATA) {
            value = regs_[data_start_ + data_index_];
          } else {
            const uint8_t shift = static_cast<uint8_t>(16 - 8 * data_index_);
            value = static_cast<uint8_t>((result_ >> shift) & 0xFF);
          }
          loadOutputByte(value);
        } else {
          out_bit_ = 7;
          out_byte_ = 0;
        }
      }
    } else {
      dout_level_ = false;
    }
    return;
  }

  if (state_ == CMD) {
    command_shift_ = static_cast<uint8_t>((command_shift_ << 1) | (mosi ? 1 : 0));
    ++bit_count_;
    if (bit_count_ == 8) {
      ++transactions_;
      decodeCommand(command_shift_);
      bit_count_ = 0;
    }
  } else if (state_ == WREG_DATA) {
    din_shift_ = static_cast<uint8_t>((din_shift_ << 1) | (mosi ? 1 : 0));
    ++bit_count_;
    if (bit_count_ == 8) {
      regs_[data_start_ + data_index_] = din_shift_;
      ++data_index_;
      bit_count_ = 0;
      din_shift_ = 0;
      if (data_index_ >= data_count_) {
        state_ = IDLE;
      }
    }
  }
}

void FakeAds1220::loadOutputByte(uint8_t value) {
  out_byte_ = value;
  out_bit_ = 7;
}

void FakeAds1220::decodeCommand(uint8_t command) {
  if ((command & 0xFE) == 0x06) {
    for (uint8_t i = 0; i < 4; ++i) {
      regs_[i] = 0;
    }
    state_ = IDLE;
    result_ = 0;
    return;
  }
  if ((command & 0xFE) == 0x08) {
    conversion_done_us_ = now_us_ + 3067;
    state_ = IDLE;
    return;
  }
  if ((command & 0xF0) == 0x10) {
    state_ = RDATA;
    data_start_ = 0;
    data_count_ = 3;
    data_index_ = 0;
    loadOutputByte(static_cast<uint8_t>((result_ >> 16) & 0xFF));
    return;
  }
  if ((command & 0xF0) == 0x20) {
    state_ = RREG_DATA;
    data_start_ = static_cast<uint8_t>((command >> 2) & 0x03);
    data_count_ = static_cast<uint8_t>((command & 0x03) + 1);
    data_index_ = 0;
    loadOutputByte(regs_[data_start_]);
    return;
  }
  if ((command & 0xF0) == 0x40) {
    state_ = WREG_DATA;
    data_start_ = static_cast<uint8_t>((command >> 2) & 0x03);
    data_count_ = static_cast<uint8_t>((command & 0x03) + 1);
    data_index_ = 0;
    bit_count_ = 0;
    din_shift_ = 0;
    return;
  }
  state_ = IDLE;
}

void FakeAds1220::tick(uint64_t now_us) {
  now_us_ = now_us;
  if (conversion_done_us_ != 0 && now_us_ >= conversion_done_us_) {
    computeResult();
    conversion_done_us_ = 0;
    ++conversions_;
  }
}

void FakeAds1220::setInput(uint8_t ain, double volts) {
  if (ain < 4) {
    inputs_[ain] = volts;
  }
}

void FakeAds1220::computeResult() {
  if ((regs_[1] & 0x02) != 0) {  // TS=1, 14-bit left justified, 25 C
    result_ = static_cast<uint32_t>(800u << 10);
    return;
  }
  const uint8_t mux = static_cast<uint8_t>((regs_[0] >> 4) & 0x0F);
  double value = 0.0;
  if (mux == 0x0E) {
    value = 0.0;
  } else if (mux == 0x0D) {
    value = (avdd_ / 4.0) / 2.048 * 8388607.0;
  } else if (mux >= 8 && mux <= 11) {
    const double vref = ((regs_[2] >> 6) == 2) ? avdd_ : 2.048;
    value = inputs_[mux - 8] / vref * 8388607.0;
  }
  if (value > 8388607.0) value = 8388607.0;
  if (value < -8388608.0) value = -8388608.0;
  result_ = static_cast<uint32_t>(static_cast<int32_t>(std::llround(value))) & 0xFFFFFFu;
}
