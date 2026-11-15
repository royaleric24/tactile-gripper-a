#pragma once

#include <Arduino.h>

// ADS1220 driver for the old ESP32 tactile board.
//
// SCLK and MOSI are shared by all three devices.  Each device has its own MISO
// and CS, so this driver uses bit-banged SPI instead of the single-MISO ESP32
// SPI peripheral.  SPI mode 1 (CPOL=0, CPHA=1) is implemented explicitly:
// DIN is changed while SCLK is low and the ADS1220 latches DIN on the falling
// edge; DOUT is shifted out by the ADS1220 on the rising edge and sampled here
// after that edge.  See the ADS1220 datasheet, sections 8.5.1 and 8.5.3.

struct Ads1220Pins {
  uint8_t sclk;
  uint8_t mosi;
  uint8_t miso;
  uint8_t cs;
};

class Ads1220 {
 public:
  Ads1220(uint8_t index, Ads1220Pins pins);

  void begin();
  bool reset();
  bool writeRegisters(uint8_t start, const uint8_t* values, uint8_t count);
  bool readRegisters(uint8_t start, uint8_t* values, uint8_t count);
  bool startConversion();
  bool readData(int32_t* value);
  // Diagnostic-only raw RDATA capture: returns the three actual SPI bytes.
  bool readDataRaw(uint8_t raw[3], int32_t* value, bool extra_clock = false,
                   bool* restored_before_cs = nullptr);
  // DRDYM=1: keep CS low and wait for DOUT/DRDY HIGH -> LOW.  Leaves CS low
  // when ready so the following RDATA stays in the same transaction; raises CS
  // on timeout.  high_seen distinguishes "never asserted" from "ready".
  bool waitDataReady(uint16_t timeout_us, bool* high_seen, uint32_t* wait_us);

  // Writes four configuration registers, reads them back and compares.  Returns
  // false on a mismatch (including a fixed 0x00/0xFF bus response).
  bool writeVerify(const uint8_t values[4], uint8_t readback[4]);

  // Resets, verifies the reset defaults, then writes and reads back two valid
  // but different configurations.  This rejects a MISO line stuck low or high.
  bool probe(uint8_t reset_defaults[4]);

  // Writes the validated normal configuration and verifies it.
  bool configure(const uint8_t values[4], uint8_t readback[4]);

  void setMux(uint8_t mux_code);
  void setReference(uint8_t reference_code);

  // Diagnostic controls.  The production timing stays at the configured
  // SENSOR_SPI_HALF_PERIOD_US and samples DOUT after the rising edge; the
  // slow-clock diagnostic can override both to separate a wiring fault from a
  // clock-edge/CPHA mismatch.
  void setClockHalfPeriodUs(uint16_t us);
  void setSampleAfterFallingEdge(bool enabled);
  void setMisoPin(uint8_t pin);
  uint16_t clockHalfPeriodUs() const { return half_period_us_; }
  bool sampleAfterFallingEdge() const { return sample_after_fall_; }
  Ads1220Pins pins() const { return pins_; }

  uint8_t mux() const { return (config_[0] >> 4) & 0x0F; }
  uint8_t reference() const { return (config_[2] >> 6) & 0x03; }
  const uint8_t* config() const { return config_; }
  uint8_t index() const { return index_; }

  // Number of complete SPI transactions performed, for diagnostics only.
  uint32_t transactions() const { return transactions_; }

 private:
  void select();
  void deselect();
  uint8_t transferByte(uint8_t value);
  void settle();

  uint8_t index_;
  Ads1220Pins pins_;
  uint8_t config_[4];
  uint32_t transactions_;
  uint16_t half_period_us_;
  bool sample_after_fall_;
};
