// Host-side deterministic test of the V2 four-device ADS1220 driver.
//
// This is NOT hardware evidence: it validates the bit-bang command timing,
// register readback, reference selection and 24-bit assembly against a
// simulated converter.  A failure here means the firmware logic is wrong; a
// pass says nothing about the real dividers.
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include <Arduino.h>

#include "ads1220_multi.h"
#include "sim_fsr2.h"

namespace {

int failures = 0;

void expect(bool condition, const char* message) {
  if (condition) {
    std::printf("PASS %s\n", message);
  } else {
    std::printf("FAIL %s\n", message);
    ++failures;
  }
}

void expectNear(int32_t actual, int32_t expected, int32_t tolerance, const char* message) {
  const int32_t delta = actual > expected ? actual - expected : expected - actual;
  if (delta <= tolerance) {
    std::printf("PASS %s (%ld)\n", message, static_cast<long>(actual));
  } else {
    std::printf("FAIL %s: expected %ld +/- %ld, got %ld\n", message,
                static_cast<long>(expected), static_cast<long>(tolerance),
                static_cast<long>(actual));
    ++failures;
  }
}

Ads1220Pins pinsFor(uint8_t cs, uint8_t miso) {
  return Ads1220Pins{18, 23, miso, cs};
}

// Single-ended, gain 1, PGA bypass, AVDD/AVSS reference: the configuration the
// V2 FSR dividers need so a 3.3 V node is never clipped by the 2.048 V internal
// reference.
const uint8_t kAvddConfig[4] = {0x81, 0x80, 0xC0, 0x00};

}  // namespace

int main() {
  simReset();
  FakeAds1220V2* adc1 = simAddDevice(21, 34);
  FakeAds1220V2* adc2 = simAddDevice(22, 35);
  FakeAds1220V2* adc3 = simAddDevice(5, 26);
  FakeAds1220V2* adc4 = simAddDevice(32, 33);
  expect(adc1 != nullptr && adc2 != nullptr && adc3 != nullptr && adc4 != nullptr,
         "four simulated ADS1220 devices register");

  Ads1220Device device;
  device.setIndex(3);
  device.begin(pinsFor(32, 33));

  expect(device.clockHalfPeriodUs() == 1, "default SPI half period is 1 us");

  uint8_t defaults[4] = {0, 0, 0, 0};
  expect(device.probe(defaults), "probe succeeds against a present device");
  expect(defaults[0] != 0xFF && defaults[1] != 0xFF, "probe rejects an all-0xFF readback");

  uint8_t readback[4] = {0, 0, 0, 0};
  expect(device.configure(kAvddConfig, readback), "configure writes and verifies 4 registers");
  expect(readback[0] == 0x81, "register 0 keeps MUX AIN0 / gain 1 / PGA bypass");
  expect(readback[1] == 0x80, "register 1 selects 330 SPS");
  expect(readback[2] == 0xC0, "register 2 selects the AVDD/AVSS reference");
  expect(readback[3] == 0x00, "register 3 keeps continuous conversion off and no IDAC");
  expect(device.reference() == 3, "driver reports reference code 3 (AVDD/AVSS)");
  expect(device.reference() != 2, "driver never selects the internal 2.048 V reference");

  device.setMux(9);
  uint8_t mux_readback[4] = {0, 0, 0, 0};
  expect(device.readRegisters(0, mux_readback, 4), "register readback works after setMux");
  expect(mux_readback[0] == 0x91, "setMux rewrites only the high nibble of register 0");
  device.setMux(8);

  adc4->setAVDD(3.3);
  adc4->setInput(0, 1.65);
  adc4->setInput(1, 0.5);

  expect(device.startConversion(), "startConversion returns true");
  delayMicroseconds(4000);
  int32_t value = 0;
  expect(device.readData(&value), "readData returns a signed 24-bit result");
  expectNear(value, 4194304, 2, "1.65 V at AVDD/AVSS reference is half scale");

  device.setMux(9);
  expect(device.startConversion(), "second conversion starts");
  delayMicroseconds(4000);
  expect(device.readData(&value), "second readData returns");
  expectNear(value, 1271001, 2, "0.5 V on AIN1 converts with AVDD scaling");

  device.setMux(8);
  adc4->setInput(0, 0.0);
  device.startConversion();
  delayMicroseconds(4000);
  device.readData(&value);
  expect(value == 0, "0 V converts to 0 counts");

  adc4->setInput(0, 3.3);
  device.startConversion();
  delayMicroseconds(4000);
  device.readData(&value);
  expect(value >= 8388600, "3.3 V converts close to full scale, not clipped by 2.048 V");

  // DRDY: a present device raises DRDY (DOUT low) once the conversion window
  // elapses, and the driver can wait for it without reading stale data.
  adc4->setInput(0, 1.65);
  device.startConversion();
  bool high_seen = false;
  uint32_t waited_us = 0;
  const bool ready = device.waitDataReady(20000, &high_seen, &waited_us);
  expect(ready, "waitDataReady observes DRDY going low");
  expect(high_seen, "waitDataReady saw DOUT high before the conversion finished");
  expect(waited_us > 0, "waitDataReady reports a non-zero wait");
  uint8_t raw[3] = {0, 0, 0};
  bool restored = false;
  expect(device.readDataRaw(raw, &value, true, &restored), "readDataRaw with the extra clock");
  expect(restored, "the extra clock restores DOUT high after a read");
  expectNear(value, 4194304, 2, "DRDY path returns the same half-scale count");

  expect(device.transactions() > 0, "transaction counter advances");

  // An absent converter must be reported, not silently converted to zeros.
  simSetPresent(32, false);
  uint8_t absent_defaults[4] = {0, 0, 0, 0};
  expect(!device.probe(absent_defaults), "probe fails when the converter is absent");
  expect(!device.configure(kAvddConfig, readback), "configure fails when the converter is absent");

  simSetPresent(32, true);
  expect(device.probe(absent_defaults), "probe recovers once the converter answers again");

  if (failures == 0) {
    std::printf("FSR2_DRIVER_TESTS_OK\n");
    return 0;
  }
  std::printf("FSR2_DRIVER_TESTS_FAILED %d\n", failures);
  return 1;
}
