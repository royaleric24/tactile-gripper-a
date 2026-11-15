// Host-side deterministic test of the bit-banged ADS1220 driver.
// This is NOT hardware evidence; it validates command timing, register
// readback and signed 24-bit assembly against a simulated device.
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "ads1220.h"
#include "json_writer.h"
#include "sim_gpio.h"

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

void expectEqual(int actual, int expected, const char* message) {
  if (actual == expected) {
    std::printf("PASS %s (%d)\n", message, actual);
  } else {
    std::printf("FAIL %s: expected %d, got %d\n", message, expected, actual);
    ++failures;
  }
}

Ads1220Pins pinsFor(uint8_t cs, uint8_t miso) {
  return Ads1220Pins{18, 23, miso, cs};
}

int32_t readChannel(Ads1220& adc, uint8_t mux) {
  adc.setMux(mux);
  adc.startConversion();
  delayMicroseconds(4500);
  int32_t value = 0;
  if (!adc.readData(&value)) {
    std::printf("readData failed for mux %u\n", mux);
    return 0x7FFFFFFF;
  }
  return value;
}

void testDriver() {
  sim_reset();
  FakeAds1220* fake1 = sim_add_device(21, 34);
  FakeAds1220* fake2 = sim_add_device(22, 35);
  FakeAds1220* fake3 = sim_add_device(5, 26);
  fake1->setInput(0, 0.1);
  fake1->setInput(1, 0.2);
  fake1->setInput(2, 0.3);
  fake1->setInput(3, 0.4);
  fake2->setInput(0, 0.1);
  fake2->setInput(1, 0.2);
  fake2->setInput(2, 0.3);
  fake2->setInput(3, 0.4);
  fake3->setInput(0, 0.1);
  fake3->setInput(1, 0.2);
  fake3->setInput(2, 0.3);
  fake3->setInput(3, 0.4);

  Ads1220 adc1(0, pinsFor(21, 34));
  Ads1220 adc2(1, pinsFor(22, 35));
  Ads1220 adc3(2, pinsFor(5, 26));
  Ads1220* devices[3] = {&adc1, &adc2, &adc3};

  const uint8_t normal[4] = {0x81, 0x80, 0x00, 0x00};
  for (uint8_t i = 0; i < 3; ++i) {
    devices[i]->begin();
    uint8_t defaults[4] = {0xAA, 0xAA, 0xAA, 0xAA};
    expect(devices[i]->probe(defaults), "probe (reset + two config write/readback)");
    for (uint8_t r = 0; r < 4; ++r) {
      expectEqual(defaults[r], 0, "reset default register");
    }
    uint8_t readback[4] = {0, 0, 0, 0};
    expect(devices[i]->configure(normal, readback), "configure normal");
    expectEqual(readback[0], 0x81, "config reg0 readback");
    expectEqual(readback[1], 0x80, "config reg1 readback");
    expectEqual(readback[2], 0x00, "config reg2 readback");
    expectEqual(readback[3], 0x00, "config reg3 readback");
  }

  expectEqual(readChannel(adc1, 8), 409600, "AIN0 internal reference");
  expectEqual(readChannel(adc1, 9), 819200, "AIN1 internal reference");
  expectEqual(readChannel(adc1, 10), 1228800, "AIN2 internal reference");
  expectEqual(readChannel(adc1, 11), 1638400, "AIN3 internal reference");

  // AVDD reference: 0.1 V / 3.3 V * 2^23.
  uint8_t avdd_config[4] = {0x81, 0x80, 0x80, 0x00};
  uint8_t avdd_readback[4] = {0, 0, 0, 0};
  expect(adc1.configure(avdd_config, avdd_readback), "configure AVDD reference");
  expectEqual(readChannel(adc1, 8), static_cast<int>(std::llround(0.1 / 3.3 * 8388607.0)), "AIN0 AVDD reference");
  expectEqual(adc1.reference(), 2, "reference bits read as AVDD");

  // Restore internal reference and test sign extension with an input below AVSS.
  expect(adc1.configure(normal, avdd_readback), "restore internal reference");
  fake1->setInput(2, -0.1);
  const int32_t negative = readChannel(adc1, 10);
  expectEqual(negative, -409600, "negative raw value sign extension");

  // Internal offset and AVDD/4 monitor.
  uint8_t offset_config[4] = {0xE1, 0x80, 0x00, 0x00};
  expect(adc1.configure(offset_config, avdd_readback), "configure shorted-input offset test");
  expectEqual(readChannel(adc1, 0xE), 0, "shorted-input offset is zero");

  uint8_t monitor_config[4] = {0xD1, 0x80, 0x00, 0x00};
  expect(adc1.configure(monitor_config, avdd_readback), "configure AVDD/4 monitor");
  const int32_t avdd_monitor = readChannel(adc1, 0xD);
  expectEqual(avdd_monitor, static_cast<int>(std::llround((3.3 / 4.0) / 2.048 * 8388607.0)), "AVDD/4 monitor");

  // Temperature sensor: 14-bit result left justified; 25 C -> 800 counts.
  uint8_t temp_config[4] = {0x81, 0x82, 0x00, 0x00};
  expect(adc1.configure(temp_config, avdd_readback), "configure temperature sensor");
  expectEqual(readChannel(adc1, 8), 800 << 10, "temperature sensor raw");

  // Config restore and periodic readback.
  expect(adc1.configure(normal, avdd_readback), "restore normal configuration");
  for (uint8_t i = 0; i < 3; ++i) {
    uint8_t actual[4] = {0, 0, 0, 0};
    expect(devices[i]->readRegisters(0, actual, 4), "read register file");
    expectEqual(actual[0], 0x81, "final config reg0");
  }
}

void testAbsentDevice() {
  sim_reset();
  FakeAds1220* absent = sim_add_device(21, 34);
  absent->setPresent(false);
  absent->setStuckHigh(false);
  Ads1220 adc(0, pinsFor(21, 34));
  adc.begin();
  uint8_t defaults[4] = {0, 0, 0, 0};
  expect(!adc.probe(defaults), "stuck-low MISO is rejected by probe");

  sim_reset();
  absent = sim_add_device(21, 34);
  absent->setPresent(false);
  absent->setStuckHigh(true);
  Ads1220 adc2(0, pinsFor(21, 34));
  adc2.begin();
  expect(!adc2.probe(defaults), "stuck-high MISO is rejected by probe");
}

void testJsonWriter() {
  char buffer[128];
  JsonLineWriter writer(buffer, sizeof(buffer));
  writer.lit("{\"a\":");
  writer.i32(-8388608);
  writer.lit(",\"b\":");
  writer.centi(4761);
  writer.lit(",\"c\":");
  writer.boolean(true);
  writer.ch('}');
  writer.newline();
  expect(writer.ok(), "JsonLineWriter fits");
  expect(std::strcmp(buffer, "{\"a\":-8388608,\"b\":47.61,\"c\":true}\n") == 0, "JsonLineWriter output exact");

  JsonLineWriter small(buffer, 8);
  small.lit("12345678901234567890");
  expect(!small.ok(), "JsonLineWriter detects overflow");
}

}  // namespace

int main() {
  testDriver();
  testAbsentDevice();
  testJsonWriter();
  if (failures != 0) {
    std::printf("%d FAILURE(S)\n", failures);
    return 1;
  }
  std::printf("ALL HOST-SIMULATION TESTS PASSED\n");
  return 0;
}
