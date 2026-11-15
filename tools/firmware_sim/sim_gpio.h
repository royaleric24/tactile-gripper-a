#pragma once
#include <cstdint>

// Deterministic ADS1220 + GPIO simulation for host tests only.  This is not a
// substitute for real hardware; it exercises the bit-bang transaction logic.
class FakeAds1220 {
 public:
  FakeAds1220(uint8_t cs, uint8_t miso);
  void setCS(bool low);
  void onSclk(bool high, bool mosi);
  int dout() const;
  void tick(uint64_t now_us);
  void setInput(uint8_t ain, double volts);
  void setAVDD(double volts) { avdd_ = volts; }
  void setPresent(bool present) { present_ = present; }
  void setStuckHigh(bool value) { stuck_high_ = value; }
  const uint8_t* registers() const { return regs_; }
  uint32_t transactions() const { return transactions_; }
  uint32_t lastResult() const { return result_; }

 private:
  void decodeCommand(uint8_t command);
  void loadOutputByte(uint8_t value);
  void computeResult();
  uint8_t sampleVoltage(uint8_t mux) const;

  uint8_t cs_;
  uint8_t miso_;
  bool selected_ = false;
  bool present_ = true;
  bool stuck_high_ = false;
  uint8_t regs_[4] = {0, 0, 0, 0};
  double inputs_[4] = {0.1, 0.2, 0.3, 0.4};
  double avdd_ = 3.3;

  enum State { IDLE, CMD, WREG_DATA, RREG_DATA, RDATA };
  State state_ = IDLE;
  uint8_t command_shift_ = 0;
  uint8_t bit_count_ = 0;
  uint8_t din_shift_ = 0;
  uint8_t data_start_ = 0;
  uint8_t data_count_ = 0;
  uint8_t data_index_ = 0;
  uint8_t out_byte_ = 0;
  int out_bit_ = 7;
  bool dout_level_ = false;
  uint32_t result_ = 0;
  uint32_t conversions_ = 0;
  uint32_t transactions_ = 0;
  uint64_t conversion_done_us_ = 0;
  uint64_t now_us_ = 0;
};

FakeAds1220* sim_add_device(uint8_t cs, uint8_t miso);
void sim_reset();
uint64_t sim_now_us();
