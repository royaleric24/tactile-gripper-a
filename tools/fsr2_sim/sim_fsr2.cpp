#include "sim_fsr2.h"

#include <Arduino.h>

#include <cmath>
#include <cstdlib>

namespace {

const uint8_t kPinCount = 40;
const uint8_t kMaxDevices = 4;
const uint64_t kConversionUs330Sps = 3030;  // one sample period at 330 SPS

struct PinState {
  uint8_t mode;
  uint8_t level;
};

PinState g_pins[kPinCount];
FakeAds1220V2* g_devices[kMaxDevices];
uint8_t g_device_count = 0;
uint64_t g_now_us = 0;
uint8_t g_sclk_pin = 18;
uint8_t g_mosi_pin = 23;

void resetPins() {
  for (uint8_t pin = 0; pin < kPinCount; ++pin) {
    g_pins[pin].mode = INPUT;
    g_pins[pin].level = LOW;
  }
}

FakeAds1220V2* deviceByCS(uint8_t pin) {
  for (uint8_t index = 0; index < g_device_count; ++index) {
    if (g_devices[index]->csPin() == pin) return g_devices[index];
  }
  return nullptr;
}

FakeAds1220V2* deviceByMiso(uint8_t pin) {
  for (uint8_t index = 0; index < g_device_count; ++index) {
    if (g_devices[index]->misoPin() == pin) return g_devices[index];
  }
  return nullptr;
}

int32_t voltsToCounts(double volts, double reference) {
  if (reference <= 0.0) return 0;
  if (volts < 0.0) volts = 0.0;
  if (volts > reference) volts = reference;
  const double scaled = volts / reference * 8388607.0;
  return static_cast<int32_t>(scaled < 0 ? scaled - 0.5 : scaled + 0.5);
}

}  // namespace

FakeAds1220V2::FakeAds1220V2(uint8_t cs, uint8_t miso) : cs_(cs), miso_(miso) {}

void FakeAds1220V2::setPresent(bool present) {
  present_ = present;
  if (!present_) {
    selected_ = false;
    state_ = IDLE;
    task_ = TASK_NONE;
  }
}

void FakeAds1220V2::setCS(bool low) {
  if (!present_) return;
  selected_ = low;
  if (low) {
    state_ = COMMAND;
    task_ = TASK_NONE;
    bit_count_ = 0;
    shift_ = 0;
  } else {
    state_ = IDLE;
    task_ = TASK_NONE;
    skip_next_fall_ = false;
  }
}

void FakeAds1220V2::beginCommand() {
  const uint8_t command = command_;
  state_ = IDLE;
  switch (command) {
    case 0x06:  // RESET
      regs_[0] = 0x80;
      regs_[1] = 0x00;
      regs_[2] = 0x00;
      regs_[3] = 0x00;
      conversion_done_us_ = 0;
      break;
    case 0x08:  // START/SYNC: single-shot conversion
      computeResult();
      ++conversions_;
      conversion_done_us_ = simNowUs() + kConversionUs330Sps;
      break;
    case 0x10: {  // RDATA
      computeResult();
      tx_payload_[0] = static_cast<uint8_t>((result_ >> 16) & 0xFF);
      tx_payload_[1] = static_cast<uint8_t>((result_ >> 8) & 0xFF);
      tx_payload_[2] = static_cast<uint8_t>(result_ & 0xFF);
      conversion_done_us_ = 0;
      enterTask(TASK_TX, tx_payload_, 3);
      state_ = RDATA_BYTES;
      break;
    }
    default:
      break;
  }

  if ((command & 0xF0) == 0x20) {  // RREG
    const uint8_t start = static_cast<uint8_t>((command >> 2) & 0x03);
    const uint8_t count = static_cast<uint8_t>((command & 0x03) + 1);
    for (uint8_t index = 0; index < count; ++index) {
      tx_payload_[index] = regs_[start + index];
    }
    enterTask(TASK_TX, tx_payload_, count);
    state_ = RREG_BYTES;
  } else if ((command & 0xF0) == 0x40) {  // WREG
    rx_count_ = static_cast<uint8_t>((command & 0x03) + 1);
    rx_index_ = 0;
    rx_payload_[0] = 0;
    rx_payload_[1] = 0;
    rx_payload_[2] = 0;
    rx_payload_[3] = 0;
    state_ = WREG_BYTES;
  }
}

void FakeAds1220V2::enterTask(Task task, const uint8_t* payload, uint8_t count) {
  // The trailing falling edge of the command byte belongs to the command
  // transfer, not to the data phase: ignore it or every byte reads one bit early.
  skip_next_fall_ = true;
  task_ = task;
  tx_count_ = count;
  tx_index_ = 0;
  tx_bit_ = 7;
  for (uint8_t index = 0; index < count && index < 8; ++index) {
    tx_payload_[index] = payload[index];
  }
}

void FakeAds1220V2::onClockRising(bool mosi) {
  if (!selected_ || !present_) return;
  const bool level = mosi;

  switch (state_) {
    case COMMAND:
      shift_ = static_cast<uint8_t>((shift_ << 1) | (level ? 1 : 0));
      if (++bit_count_ == 8) {
        command_ = shift_;
        bit_count_ = 0;
        shift_ = 0;
        beginCommand();
      }
      break;
    case WREG_BYTES:
      shift_ = static_cast<uint8_t>((shift_ << 1) | (level ? 1 : 0));
      if (++bit_count_ == 8) {
        bit_count_ = 0;
        if (rx_index_ < 4) rx_payload_[rx_index_++] = shift_;
        shift_ = 0;
        if (rx_index_ >= rx_count_) {
          const uint8_t start = static_cast<uint8_t>((command_ >> 2) & 0x03);
          for (uint8_t index = 0; index < rx_count_ && index < 4; ++index) {
            regs_[start + index] = rx_payload_[index];
          }
          state_ = IDLE;
        }
      }
      break;
    default:
      break;
  }
}

void FakeAds1220V2::onClockFalling() {
  if (!selected_ || !present_) return;
  if (skip_next_fall_) {
    skip_next_fall_ = false;
    return;
  }
  if (state_ != RREG_BYTES && state_ != RDATA_BYTES) return;
  if (task_ != TASK_TX) return;

  --tx_bit_;
  if (tx_bit_ < 0) {
    ++tx_index_;
    tx_bit_ = 7;
    if (tx_index_ >= tx_count_) {
      task_ = TASK_NONE;
      state_ = IDLE;
    }
  }
}

int FakeAds1220V2::dout() const {
  if (!present_ || !selected_) return HIGH;
  if (task_ == TASK_TX) {
    if (tx_index_ >= tx_count_) return HIGH;
    const uint8_t value = tx_payload_[tx_index_];
    return ((value >> (tx_bit_ < 0 ? 0 : tx_bit_)) & 0x01) != 0 ? HIGH : LOW;
  }
  if (conversion_done_us_ != 0 && simNowUs() >= conversion_done_us_) return LOW;
  return HIGH;
}

void FakeAds1220V2::advance(uint64_t delta_us) { (void)delta_us; }

void FakeAds1220V2::computeResult() {
  const uint8_t mux = static_cast<uint8_t>((regs_[0] >> 4) & 0x0F);
  int32_t counts = 0;
  if (mux >= 8 && mux <= 11) {
    counts = voltsToCounts(inputs_[mux - 8], referenceVolts());
  }
  result_ = static_cast<uint32_t>(counts);
}

double FakeAds1220V2::referenceVolts() const {
  // AVDD/AVSS is VREF[1:0] == 3 (bits 0xC0).  Internal 2.048 V is 0.
  const uint8_t code = static_cast<uint8_t>((regs_[2] >> 6) & 0x03);
  if (code == 3) return avdd_;
  return 2.048;
}

// ---------------------------------------------------------------------------
// GPIO shims declared by tools/firmware_sim/Arduino.h
// ---------------------------------------------------------------------------

void pinMode(uint8_t pin, uint8_t mode) {
  if (pin >= kPinCount) return;
  g_pins[pin].mode = mode;
}

void digitalWrite(uint8_t pin, uint8_t value) {
  if (pin >= kPinCount) return;
  const uint8_t level = value == LOW ? LOW : HIGH;
  g_pins[pin].level = level;

  FakeAds1220V2* by_cs = deviceByCS(pin);
  if (by_cs != nullptr) {
    by_cs->setCS(level == LOW);
    return;
  }

  if (pin == g_sclk_pin) {
    for (uint8_t index = 0; index < g_device_count; ++index) {
      if (level == HIGH) {
        g_devices[index]->onClockRising(g_pins[g_mosi_pin].level == HIGH);
      } else {
        g_devices[index]->onClockFalling();
      }
    }
  }
}

int digitalRead(uint8_t pin) {
  // Each poll costs the virtual bus 1 us, so a DRDY spin loop (which never
  // calls delay) still reaches the end of the conversion window.
  g_now_us += 1;
  FakeAds1220V2* device = deviceByMiso(pin);
  if (device != nullptr) return device->dout();
  if (pin < kPinCount) return g_pins[pin].level;
  return HIGH;
}

void delay(unsigned long ms) { g_now_us += static_cast<uint64_t>(ms) * 1000ULL; }

void delayMicroseconds(unsigned int us) { g_now_us += us; }

unsigned long micros() { return static_cast<unsigned long>(g_now_us); }

// ---------------------------------------------------------------------------
// Registry helpers used by the tests
// ---------------------------------------------------------------------------

void simReset() {
  for (uint8_t index = 0; index < kMaxDevices; ++index) {
    g_devices[index] = nullptr;
  }
  g_device_count = 0;
  g_now_us = 0;
  resetPins();
}

FakeAds1220V2* simAddDevice(uint8_t cs, uint8_t miso) {
  if (g_device_count >= kMaxDevices) return nullptr;
  g_devices[g_device_count] = new FakeAds1220V2(cs, miso);
  return g_devices[g_device_count++];
}

FakeAds1220V2* simDevice(uint8_t cs) { return deviceByCS(cs); }

void simSetPresent(uint8_t cs, bool present) {
  FakeAds1220V2* device = deviceByCS(cs);
  if (device != nullptr) device->setPresent(present);
}

uint64_t simNowUs() { return g_now_us; }
