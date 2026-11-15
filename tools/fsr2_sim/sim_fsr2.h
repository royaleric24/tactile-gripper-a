// Deterministic four-device ADS1220 simulation for host tests only.
//
// This exercises the bit-bang transaction decoding, register readback and the
// single-ended conversion math of the V2 firmware.  It is NOT hardware: a PASS
// from these tests means "the C++ logic is self-consistent", never "the board
// measures the dividers correctly".
#pragma once

#include <cstdint>

class FakeAds1220V2 {
 public:
  FakeAds1220V2(uint8_t cs, uint8_t miso);

  uint8_t csPin() const { return cs_; }
  uint8_t misoPin() const { return miso_; }

  void setCS(bool low);
  void onClockRising(bool mosi);
  void onClockFalling();
  int dout() const;
  void advance(uint64_t delta_us);

  void setInput(uint8_t ain, double volts) { inputs_[ain] = volts; }
  void setAVDD(double volts) { avdd_ = volts; }
  void setPresent(bool present);
  bool present() const { return present_; }

  const uint8_t* registers() const { return regs_; }
  uint32_t conversionCount() const { return conversions_; }
  uint32_t lastResult() const { return result_; }
  uint64_t conversionDoneUs() const { return conversion_done_us_; }

 private:
  enum State { IDLE, COMMAND, WREG_BYTES, RREG_BYTES, RDATA_BYTES };
  enum Task { TASK_NONE, TASK_TX, TASK_RX_WREG };

  void beginCommand();
  void finishCommand();
  void enterTask(Task task, const uint8_t* payload, uint8_t count);
  void computeResult();
  double referenceVolts() const;

  uint8_t cs_;
  uint8_t miso_;
  bool selected_ = false;
  bool present_ = true;

  uint8_t regs_[4] = {0x80, 0x00, 0x00, 0x00};
  double inputs_[4] = {0.0, 0.0, 0.0, 0.0};
  double avdd_ = 3.3;

  State state_ = IDLE;
  Task task_ = TASK_NONE;
  uint8_t command_ = 0;
  uint8_t bit_count_ = 0;
  uint8_t shift_ = 0;
  uint8_t rx_payload_[4] = {0, 0, 0, 0};
  uint8_t rx_count_ = 0;
  uint8_t rx_index_ = 0;
  uint8_t tx_payload_[8] = {0, 0, 0, 0, 0, 0, 0, 0};
  uint8_t tx_count_ = 0;
  uint8_t tx_index_ = 0;
  int tx_bit_ = 7;
  bool skip_next_fall_ = false;

  uint32_t result_ = 0;
  uint32_t conversions_ = 0;
  uint64_t conversion_done_us_ = 0;
  uint64_t now_us_ = 0;
};

// Global registry used by the Arduino.h GPIO shims.
void simReset();
FakeAds1220V2* simAddDevice(uint8_t cs, uint8_t miso);
FakeAds1220V2* simDevice(uint8_t cs);
void simSetPresent(uint8_t cs, bool present);
uint64_t simNowUs();
