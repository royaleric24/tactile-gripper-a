// Bit-banged ADS1220 driver for the V2 four-ADC board.
//
// A trimmed continuation of firmware/sensor/ads1220.{h,cpp}: same SPI mode 1
// bit-bang, same command set, same probe/configure/verify sequence, so the
// host simulation and the field wiring behave the way the frozen 12-channel
// firmware did.  Differences are deliberate and documented in
// docs/hardware/FSR_ONLY_INTERFACE_V2.md:
//   * default constructible, pins supplied by the generated profile,
//   * no dependency on any generated_config.h from the historical firmware,
//   * four instances instead of three.
#pragma once

#include <stdint.h>

struct Ads1220Pins {
  uint8_t sclk;
  uint8_t mosi;
  uint8_t miso;
  uint8_t cs;
};

class Ads1220Device {
 public:
  Ads1220Device();

  void begin(Ads1220Pins pins, uint16_t half_period_us = 1);
  void setIndex(uint8_t index) { index_ = index; }
  void setClockHalfPeriodUs(uint16_t value);
  uint16_t clockHalfPeriodUs() const { return half_period_us_; }
  void setSampleAfterFallingEdge(bool value) { sample_after_fall_ = value; }
  Ads1220Pins pins() const { return pins_; }
  uint8_t index() const { return index_; }
  uint32_t transactions() const { return transactions_; }

  bool reset();
  bool writeRegisters(uint8_t start, const uint8_t* values, uint8_t count);
  bool readRegisters(uint8_t start, uint8_t* values, uint8_t count);
  bool writeVerify(const uint8_t values[4], uint8_t readback[4]);
  bool probe(uint8_t reset_defaults[4]);
  bool configure(const uint8_t values[4], uint8_t readback[4]);

  bool startConversion();
  bool readData(int32_t* value);
  bool readDataRaw(uint8_t raw[3], int32_t* value, bool extra_clock = false,
                   bool* restored_before_cs = nullptr);
  bool waitDataReady(uint16_t timeout_us, bool* high_seen = nullptr, uint32_t* wait_us = nullptr);

  void setMux(uint8_t mux_code);
  void setReference(uint8_t reference_code);
  uint8_t mux() const { return static_cast<uint8_t>((config_[0] >> 4) & 0x0F); }
  uint8_t reference() const { return static_cast<uint8_t>((config_[2] >> 6) & 0x03); }
  const uint8_t* config() const { return config_; }

 private:
  void select();
  void deselect();
  uint8_t transferByte(uint8_t value);
  void settle(uint16_t microseconds);

  uint8_t index_;
  Ads1220Pins pins_;
  uint8_t config_[4];
  uint32_t transactions_;
  uint16_t half_period_us_;
  bool sample_after_fall_;
};
