#include "ads1220.h"

#include "generated_config.h"

namespace {
constexpr uint8_t CMD_RESET = 0x06;
constexpr uint8_t CMD_START = 0x08;
constexpr uint8_t CMD_RDATA = 0x10;
constexpr uint8_t CMD_RREG = 0x20;
constexpr uint8_t CMD_WREG = 0x40;
}  // namespace

Ads1220::Ads1220(uint8_t index, Ads1220Pins pins)
    : index_(index),
      pins_(pins),
      config_{0, 0, 0, 0},
      transactions_(0),
      half_period_us_(SENSOR_SPI_HALF_PERIOD_US),
      sample_after_fall_(false) {}

void Ads1220::setClockHalfPeriodUs(uint16_t us) {
  half_period_us_ = us < 1 ? 1 : (us > 1000 ? 1000 : us);
}

void Ads1220::setSampleAfterFallingEdge(bool enabled) {
  sample_after_fall_ = enabled;
}

void Ads1220::setMisoPin(uint8_t pin) {
  // Diagnostic-only remap: keep the old pin as an input (it is not driven by
  // this firmware) and make the candidate MISO an input before clocking.
  pinMode(pin, INPUT);
  pins_.miso = pin;
}

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
    // CPOL=0: SCLK idles low.  DIN is changed while SCLK is low.  In SPI mode 1
    // (CPHA=1) the ADS1220 latches DIN on the falling edge and shifts DOUT on
    // the rising edge, so the production build samples just after the rising
    // edge.  The diagnostic can instead sample after the falling edge.
    digitalWrite(pins_.mosi, (value & (1u << bit)) ? HIGH : LOW);
    delayMicroseconds(half_period_us_);
    digitalWrite(pins_.sclk, HIGH);
    delayMicroseconds(half_period_us_);
    if (!sample_after_fall_) {
      in = static_cast<uint8_t>((in << 1) | (digitalRead(pins_.miso) == HIGH ? 1 : 0));
    }
    digitalWrite(pins_.sclk, LOW);
    delayMicroseconds(half_period_us_);
    if (sample_after_fall_) {
      in = static_cast<uint8_t>((in << 1) | (digitalRead(pins_.miso) == HIGH ? 1 : 0));
    }
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

bool Ads1220::readDataRaw(uint8_t raw[3], int32_t* value, bool extra_clock) {
  if (raw == nullptr || value == nullptr) {
    return false;
  }
  select();
  transferByte(CMD_RDATA);
  raw[0] = transferByte(0x00);
  raw[1] = transferByte(0x00);
  raw[2] = transferByte(0x00);
  if (extra_clock) {
    // DRDYM=1 state restore: one extra SCLK after the 24 data bits returns
    // DOUT/DRDY high before CS is raised.  Normal readData() does not use it.
    digitalWrite(pins_.sclk, HIGH);
    delayMicroseconds(half_period_us_);
    digitalWrite(pins_.sclk, LOW);
    delayMicroseconds(half_period_us_);
  }
  deselect();
  uint32_t bits = (static_cast<uint32_t>(raw[0]) << 16) |
                  (static_cast<uint32_t>(raw[1]) << 8) |
                  static_cast<uint32_t>(raw[2]);
  if (bits & 0x00800000UL) {
    bits |= 0xFF000000UL;  // sign-extend the 24-bit two's complement value
  }
  *value = static_cast<int32_t>(bits);
  return true;
}

bool Ads1220::waitDataReady(uint16_t timeout_us, bool* high_seen, uint32_t* wait_us) {
  if (high_seen == nullptr || wait_us == nullptr) {
    return false;
  }
  *high_seen = false;
  *wait_us = 0;
  const uint32_t start = micros();
  select();
  while (static_cast<uint32_t>(micros() - start) < timeout_us) {
    const int level = digitalRead(pins_.miso);
    if (!*high_seen && level == HIGH) {
      *high_seen = true;
    } else if (*high_seen && level == LOW) {
      *wait_us = static_cast<uint32_t>(micros() - start);
      return true;  // CS stays low for RDATA
    }
  }
  *wait_us = static_cast<uint32_t>(micros() - start);
  deselect();
  return false;
}

bool Ads1220::readData(int32_t* value) {
  uint8_t raw[3] = {0, 0, 0};
  return readDataRaw(raw, value);
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
