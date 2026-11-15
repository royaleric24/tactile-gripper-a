#include "ads1220_multi.h"

#include <Arduino.h>
#include <string.h>

namespace {

const uint8_t CMD_RESET = 0x06;
const uint8_t CMD_START = 0x08;
const uint8_t CMD_RDATA = 0x10;
const uint8_t CMD_RREG = 0x20;
const uint8_t CMD_WREG = 0x40;

}  // namespace

Ads1220Device::Ads1220Device()
    : index_(0),
      pins_{0, 0, 0, 0},
      config_{0, 0, 0, 0},
      transactions_(0),
      half_period_us_(1),
      sample_after_fall_(false) {}

void Ads1220Device::begin(Ads1220Pins pins, uint16_t half_period_us) {
  pins_ = pins;
  half_period_us_ = half_period_us == 0 ? 1 : half_period_us;
  // Drive CS high before enabling the output so a floating select line cannot
  // put the ADS1220 on the shared bus while the other three are talking.
  digitalWrite(pins_.cs, HIGH);
  pinMode(pins_.cs, OUTPUT);
  digitalWrite(pins_.cs, HIGH);
  pinMode(pins_.sclk, OUTPUT);
  digitalWrite(pins_.sclk, LOW);
  pinMode(pins_.mosi, OUTPUT);
  digitalWrite(pins_.mosi, LOW);
  pinMode(pins_.miso, INPUT);
  transactions_ = 0;
}

void Ads1220Device::setClockHalfPeriodUs(uint16_t value) {
  half_period_us_ = value == 0 ? 1 : value;
}

void Ads1220Device::select() {
  digitalWrite(pins_.cs, LOW);
  delayMicroseconds(1);
  ++transactions_;
}

void Ads1220Device::deselect() {
  digitalWrite(pins_.cs, HIGH);
  delayMicroseconds(1);
}

void Ads1220Device::settle(uint16_t microseconds) { delayMicroseconds(microseconds); }

uint8_t Ads1220Device::transferByte(uint8_t value) {
  uint8_t result = 0;
  for (int8_t bit = 7; bit >= 0; --bit) {
    digitalWrite(pins_.mosi, ((value >> bit) & 0x01) != 0 ? HIGH : LOW);
    delayMicroseconds(half_period_us_);
    digitalWrite(pins_.sclk, HIGH);
    delayMicroseconds(half_period_us_);
    if (!sample_after_fall_) {
      result = static_cast<uint8_t>((result << 1) | (digitalRead(pins_.miso) == HIGH ? 1 : 0));
    }
    digitalWrite(pins_.sclk, LOW);
    delayMicroseconds(half_period_us_);
    if (sample_after_fall_) {
      result = static_cast<uint8_t>((result << 1) | (digitalRead(pins_.miso) == HIGH ? 1 : 0));
    }
  }
  return result;
}

bool Ads1220Device::reset() {
  select();
  transferByte(CMD_RESET);
  deselect();
  delay(1);
  return true;
}

bool Ads1220Device::writeRegisters(uint8_t start, const uint8_t* values, uint8_t count) {
  if (values == nullptr || count == 0 || start > 3 || static_cast<uint16_t>(start) + count > 4) {
    return false;
  }
  select();
  transferByte(static_cast<uint8_t>(CMD_WREG | (start << 2) | (count - 1)));
  for (uint8_t index = 0; index < count; ++index) {
    transferByte(values[index]);
  }
  deselect();
  settle(50);
  for (uint8_t index = 0; index < count; ++index) {
    config_[start + index] = values[index];
  }
  return true;
}

bool Ads1220Device::readRegisters(uint8_t start, uint8_t* values, uint8_t count) {
  if (values == nullptr || count == 0 || start > 3 || static_cast<uint16_t>(start) + count > 4) {
    return false;
  }
  select();
  transferByte(static_cast<uint8_t>(CMD_RREG | (start << 2) | (count - 1)));
  for (uint8_t index = 0; index < count; ++index) {
    values[index] = transferByte(0x00);
  }
  deselect();
  settle(50);
  return true;
}

bool Ads1220Device::writeVerify(const uint8_t values[4], uint8_t readback[4]) {
  if (values == nullptr || readback == nullptr) return false;
  if (!writeRegisters(0, values, 4)) return false;
  if (!readRegisters(0, readback, 4)) return false;

  bool all_zero = true;
  bool all_ones = true;
  for (uint8_t index = 0; index < 4; ++index) {
    if (readback[index] != 0x00) all_zero = false;
    if (readback[index] != 0xFF) all_ones = false;
  }
  if (all_zero || all_ones) return false;
  return memcmp(readback, values, 4) == 0;
}

bool Ads1220Device::probe(uint8_t reset_defaults[4]) {
  if (reset_defaults == nullptr) return false;
  if (!reset()) return false;
  if (!readRegisters(0, reset_defaults, 4)) return false;

  static const uint8_t kPatternA[4] = {0x81, 0x80, 0x00, 0x00};
  static const uint8_t kPatternB[4] = {0x91, 0x80, 0x80, 0x00};
  uint8_t readback_a[4] = {0, 0, 0, 0};
  uint8_t readback_b[4] = {0, 0, 0, 0};
  if (!writeVerify(kPatternA, readback_a)) return false;
  if (!writeVerify(kPatternB, readback_b)) return false;
  if (memcmp(readback_a, readback_b, 4) == 0) return false;
  return true;
}

bool Ads1220Device::configure(const uint8_t values[4], uint8_t readback[4]) {
  if (values == nullptr || readback == nullptr) return false;
  if (!writeVerify(values, readback)) return false;
  memcpy(config_, values, 4);
  return true;
}

bool Ads1220Device::startConversion() {
  select();
  transferByte(CMD_START);
  deselect();
  return true;
}

bool Ads1220Device::readDataRaw(uint8_t raw[3], int32_t* value, bool extra_clock,
                                bool* restored_before_cs) {
  if (raw == nullptr || value == nullptr) return false;
  select();
  transferByte(CMD_RDATA);
  raw[0] = transferByte(0x00);
  raw[1] = transferByte(0x00);
  raw[2] = transferByte(0x00);
  bool high_after_clock = false;
  if (extra_clock) {
    transferByte(0x00);
    high_after_clock = digitalRead(pins_.miso) == HIGH;
  }
  deselect();
  if (restored_before_cs != nullptr) *restored_before_cs = high_after_clock;

  const uint32_t bits = (static_cast<uint32_t>(raw[0]) << 16) |
                        (static_cast<uint32_t>(raw[1]) << 8) | static_cast<uint32_t>(raw[2]);
  int32_t signed_value = static_cast<int32_t>(bits);
  if ((bits & 0x00800000UL) != 0) {
    signed_value |= static_cast<int32_t>(0xFF000000UL);
  }
  *value = signed_value;
  return true;
}

bool Ads1220Device::readData(int32_t* value) {
  uint8_t raw[3] = {0, 0, 0};
  return readDataRaw(raw, value, true, nullptr);
}

bool Ads1220Device::waitDataReady(uint16_t timeout_us, bool* high_seen, uint32_t* wait_us) {
  if (high_seen != nullptr) *high_seen = false;
  const uint32_t start = micros();
  select();
  while (static_cast<uint32_t>(micros() - start) < timeout_us) {
    if (digitalRead(pins_.miso) == LOW) {
      if (wait_us != nullptr) *wait_us = static_cast<uint32_t>(micros() - start);
      deselect();
      return true;
    }
    if (high_seen != nullptr) *high_seen = true;
  }
  if (wait_us != nullptr) *wait_us = static_cast<uint32_t>(micros() - start);
  deselect();
  return false;
}

void Ads1220Device::setMux(uint8_t mux_code) {
  const uint8_t updated = static_cast<uint8_t>(((mux_code & 0x0F) << 4) | (config_[0] & 0x0F));
  if (updated == config_[0]) return;
  config_[0] = updated;
  writeRegisters(0, config_, 1);
}

void Ads1220Device::setReference(uint8_t reference_code) {
  const uint8_t updated = static_cast<uint8_t>(((reference_code & 0x03) << 6) | (config_[2] & 0x3F));
  if (updated == config_[2]) return;
  config_[2] = updated;
  writeRegisters(2, config_ + 2, 1);
}
