#include "ads1220.h"

#include "generated_config.h"

namespace {
constexpr uint8_t CMD_RESET = 0x06;
constexpr uint8_t CMD_START = 0x08;
constexpr uint8_t CMD_RDATA = 0x10;
constexpr uint8_t CMD_RREG = 0x20;
constexpr uint8_t CMD_WREG = 0x40;

inline void halfPeriod() {
  delayMicroseconds(SENSOR_SPI_HALF_PERIOD_US);
}
}  // namespace

Ads1220::Ads1220(uint8_t index, Ads1220Pins pins)
    : index_(index), pins_(pins), config_{0, 0, 0, 0}, transactions_(0) {}

void Ads1220::begin() {
  // Drive CS high before touching SCLK/MOSI.  GPIO5 is a strapping pin on the
  // old ESP32 and must not be left low while the board comes up.
  pinMode(pins_.cs, OUTPUT);
  digitalWrite(pins_.cs, HIGH);
  pinMode(pins_.sclk, OUTPUT);
  digitalWrite(pins_.sclk, LOW);
  pinMode(pins_.mosi, OUTPUT);
  digitalWrite(pins_.mosi, LOW);
  pinMode(pins_.miso, INPUT);
}

void Ads1220::select() {
  digitalWrite(pins_.cs, LOW);
  delayMicroseconds(1);
}

void Ads1220::deselect() {
  digitalWrite(pins_.cs, HIGH);
  delayMicroseconds(1);
}

uint8_t Ads1220::transferByte(uint8_t value) {
  uint8_t in = 0;
  for (int bit = 7; bit >= 0; --bit) {
    // CPHA=1: set DIN while SCLK is low; the ADS1220 latches DIN on the falling
    // edge.  DOUT changes on the rising edge and is sampled here after it.
    digitalWrite(pins_.mosi, (value & (1u << bit)) ? HIGH : LOW);
    halfPeriod();
    digitalWrite(pins_.sclk, HIGH);
    halfPeriod();
    in = static_cast<uint8_t>((in << 1) | (digitalRead(pins_.miso) == HIGH ? 1 : 0));
    digitalWrite(pins_.sclk, LOW);
    halfPeriod();
  }
  transactions_++;
  return in;
}

void Ads1220::settle() {
  delayMicroseconds(50);
}

bool Ads1220::reset() {
  select();
  transferByte(CMD_RESET);
  deselect();
  // Datasheet: wait at least 50 us + 32 x tCLK.  1 ms is a safe margin.
  delay(1);
  return true;
}

bool Ads1220::writeRegisters(uint8_t start, const uint8_t* values, uint8_t count) {
  if (count < 1 || count > 4 || start > 3 || start + count > 4) {
    return false;
  }
  select();
  transferByte(static_cast<uint8_t>(CMD_WREG | (start << 2) | (count - 1)));
  for (uint8_t i = 0; i < count; ++i) {
    transferByte(values[i]);
    config_[start + i] = values[i];
  }
  deselect();
  settle();
  return true;
}

bool Ads1220::readRegisters(uint8_t start, uint8_t* values, uint8_t count) {
  if (count < 1 || count > 4 || start > 3 || start + count > 4) {
    return false;
  }
  select();
  transferByte(static_cast<uint8_t>(CMD_RREG | (start << 2) | (count - 1)));
  for (uint8_t i = 0; i < count; ++i) {
    values[i] = transferByte(0x00);
  }
  deselect();
  return true;
}

bool Ads1220::startConversion() {
  select();
  transferByte(CMD_START);
  deselect();
  return true;
}

bool Ads1220::readData(int32_t* value) {
  if (value == nullptr) {
    return false;
  }
  select();
  transferByte(CMD_RDATA);
  uint32_t raw = 0;
  raw |= static_cast<uint32_t>(transferByte(0x00)) << 16;
  raw |= static_cast<uint32_t>(transferByte(0x00)) << 8;
  raw |= static_cast<uint32_t>(transferByte(0x00));
  deselect();
  if (raw & 0x00800000UL) {
    raw |= 0xFF000000UL;  // sign-extend the 24-bit two's complement value
  }
  *value = static_cast<int32_t>(raw);
  return true;
}

bool Ads1220::writeVerify(const uint8_t values[4], uint8_t readback[4]) {
  if (!writeRegisters(0, values, 4)) {
    return false;
  }
  if (!readRegisters(0, readback, 4)) {
    return false;
  }
  for (uint8_t i = 0; i < 4; ++i) {
    if (readback[i] != values[i]) {
      return false;
    }
  }
  // A valid 4-byte register file is never uniformly 0x00 or 0xFF for both test
  // patterns.  Rejecting these explicitly catches a stuck MISO even if the
  // compare happened to line up.
  if ((readback[0] == 0x00 && readback[1] == 0x00 && readback[2] == 0x00 && readback[3] == 0x00) ||
      (readback[0] == 0xFF && readback[1] == 0xFF && readback[2] == 0xFF && readback[3] == 0xFF)) {
    return false;
  }
  return true;
}

bool Ads1220::probe(uint8_t reset_defaults[4]) {
  reset();
  if (!readRegisters(0, reset_defaults, 4)) {
    return false;
  }

  static const uint8_t pattern_a[4] = {0x81, 0x80, 0x00, 0x00};  // AIN0/AVSS, 330 SPS, internal 2.048 V
  static const uint8_t pattern_b[4] = {0x91, 0x80, 0x80, 0x00};  // AIN1/AVSS, 330 SPS, AVDD reference
  uint8_t readback[4];
  if (!writeVerify(pattern_a, readback)) {
    return false;
  }
  bool saw_a = true;
  for (uint8_t i = 0; i < 4; ++i) {
    saw_a = saw_a && (readback[i] == pattern_a[i]);
  }
  if (!writeVerify(pattern_b, readback)) {
    return false;
  }
  bool saw_b = true;
  for (uint8_t i = 0; i < 4; ++i) {
    saw_b = saw_b && (readback[i] == pattern_b[i]);
  }
  // The two patterns must be genuinely different readbacks.
  if (!saw_a || !saw_b) {
    return false;
  }
  return true;
}

bool Ads1220::configure(const uint8_t values[4], uint8_t readback[4]) {
  if (!writeVerify(values, readback)) {
    return false;
  }
  for (uint8_t i = 0; i < 4; ++i) {
    config_[i] = values[i];
  }
  return true;
}

void Ads1220::setMux(uint8_t mux_code) {
  config_[0] = static_cast<uint8_t>((mux_code << 4) | (config_[0] & 0x0F));
  writeRegisters(0, &config_[0], 1);
  settle();
}

void Ads1220::setReference(uint8_t reference_code) {
  config_[2] = static_cast<uint8_t>((reference_code << 6) | (config_[2] & 0x3F));
  writeRegisters(2, &config_[2], 1);
  settle();
}
