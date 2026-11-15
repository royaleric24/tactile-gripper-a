// Offline diagnostic firmware: fixed ADC2 AIN1, DRDY polling, raw RDATA bytes.
// NOT flashed by the build script.  Does not run the normal 12-channel scan.
#include <Arduino.h>

#include "../sensor/ads1220.cpp"

const char* VERSION = "tactile-sense-diag-ain1-0.1.3";
const uint8_t FIXED_ADC_INDEX = 1;  // ADC2
const uint8_t FIXED_MUX = 9;        // AIN1 vs AVSS
const uint8_t FIXED_REG0 = 0x91;    // AIN1, gain 1, PGA bypass
const uint8_t FIXED_REG2 = 0xC0;    // AVDD-AVSS, no IDAC/PSW
const uint8_t FIXED_REG3 = 0x02;    // DRDYM=1: DOUT/DRDY data-ready indication
char line[640];
uint32_t seq = 0;
uint32_t last_hello_ms = 0;
bool adc2_ok = false;
uint8_t adc2_config[4] = {FIXED_REG0, 0x80, FIXED_REG2, FIXED_REG3};

Ads1220Pins makePins(uint8_t index) {
  return Ads1220Pins{SENSOR_SCLK_PIN, SENSOR_MOSI_PIN, SENSOR_MISO_PINS[index], SENSOR_CS_PINS[index]};
}
Ads1220 devices[3] = {
    Ads1220(0, makePins(0)),
    Ads1220(1, makePins(1)),
    Ads1220(2, makePins(2)),
};

void appendRegs(char* out, size_t out_size, const uint8_t regs[4]) {
  snprintf(out, out_size, "[%u,%u,%u,%u]", regs[0], regs[1], regs[2], regs[3]);
}

void sendHello() {
  uint8_t r1[4] = {0}, r2[4] = {0}, r3[4] = {0};
  devices[0].readRegisters(0, r1, 4);
  devices[1].readRegisters(0, r2, 4);
  devices[2].readRegisters(0, r3, 4);
  char a1[32], a2[32], a3[32];
  appendRegs(a1, sizeof(a1), r1);
  appendRegs(a2, sizeof(a2), r2);
  appendRegs(a3, sizeof(a3), r3);
  snprintf(line, sizeof(line),
           "{\"type\":\"DIAG_HELLO\",\"firmware\":\"%s\",\"target\":\"ADC2_AIN1_FIXED\","
           "\"adc2_ok\":%s,\"adc1_regs\":%s,\"adc2_regs\":%s,\"adc3_regs\":%s,"
           "\"fixed_mux\":%u,\"fixed_reg0\":%u,\"fixed_reg2\":%u,\"fixed_reg3\":%u,"
           "\"drdym\":1,\"drdy_pin\":%u}\n",
           VERSION, adc2_ok ? "true" : "false", a1, a2, a3,
           FIXED_MUX, FIXED_REG0, FIXED_REG2, FIXED_REG3, SENSOR_MISO_PINS[1]);
  Serial.print(line);
}

void setup() {
  Serial.begin(921600);
  delay(100);
  for (uint8_t i = 0; i < 3; ++i) {
    devices[i].begin();
    devices[i].reset();
  }
  uint8_t readback[4];
  uint8_t aux[4] = {0x81, 0x80, 0xC0, 0x00};  // ADC1/ADC3 basic AIN0, no conversion
  devices[0].configure(aux, readback);
  devices[2].configure(aux, readback);
  adc2_ok = devices[FIXED_ADC_INDEX].configure(adc2_config, readback);
  sendHello();
  last_hello_ms = millis();
}

void loop() {
  // Handshake: HELLO on request or every second, so a host connecting after
  // boot can always recover identity without a reset.
  if (Serial.available()) {
    while (Serial.available()) {
      const int c = Serial.read();
      if (c == 'H' || c == 'h') {
        sendHello();
        last_hello_ms = millis();
      }
    }
  }
  if (millis() - last_hello_ms >= 1000) {
    sendHello();
    last_hello_ms = millis();
  }
  uint8_t before[4] = {0}, after[4] = {0};
  devices[FIXED_ADC_INDEX].readRegisters(0, before, 4);
  bool reconfigured = false;
  if (before[0] != FIXED_REG0 || before[2] != FIXED_REG2 || before[3] != FIXED_REG3) {
    uint8_t readback[4];
    adc2_ok = devices[FIXED_ADC_INDEX].configure(adc2_config, readback);
    devices[FIXED_ADC_INDEX].readRegisters(0, before, 4);
    reconfigured = true;
  }
  const uint8_t drdy_pin = devices[FIXED_ADC_INDEX].pins().miso;
  devices[FIXED_ADC_INDEX].startConversion();
  delayMicroseconds(250);
  bool high_seen = false;
  uint32_t wait_us = 0;
  // DRDYM=1: CS is held low by waitDataReady; it stays low when ready so the
  // following RDATA is in the same CS transaction.  On timeout CS is raised.
  const bool ready = devices[FIXED_ADC_INDEX].waitDataReady(12000, &high_seen, &wait_us);
  bool read_ok = false;
  bool restored_before_cs = false;
  uint8_t raw[3] = {0, 0, 0};
  int32_t counts = 0;
  if (ready) {
    // 24 data bits + 8 extra SCLK (DIN low), then CS high.  The helper reports
    // DOUT/DRDY high immediately before CS is raised.
    read_ok = devices[FIXED_ADC_INDEX].readDataRaw(raw, &counts, true, &restored_before_cs);
  }
  delayMicroseconds(2);
  const bool post_cs_high = digitalRead(drdy_pin) == HIGH;
  devices[FIXED_ADC_INDEX].readRegisters(0, after, 4);
  char b[32], a[32];
  appendRegs(b, sizeof(b), before);
  appendRegs(a, sizeof(a), after);
  char raw_text[12] = "null";
  char counts_text[16] = "null";
  char volts_text[16] = "null";
  if (read_ok) {
    snprintf(raw_text, sizeof(raw_text), "\"%02X%02X%02X\"", raw[0], raw[1], raw[2]);
    snprintf(counts_text, sizeof(counts_text), "%ld", static_cast<long>(counts));
    snprintf(volts_text, sizeof(volts_text), "%.4f", static_cast<double>(counts) * 3.3 / 8388607.0);
  }
  snprintf(line, sizeof(line),
           "{\"type\":\"DIAG_SAMPLE\",\"seq\":%lu,\"ms\":%lu,\"ready\":%s,\"high_seen\":%s,"
           "\"read_ok\":%s,\"wait_us\":%lu,\"before\":%s,\"after\":%s,"
           "\"mux_before\":%u,\"mux_after\":%u,\"vref_before\":%u,\"vref_after\":%u,"
           "\"reg3_before\":%u,\"reg3_after\":%u,\"restored_before_cs\":%s,"
           "\"post_cs_high\":%s,\"extra_clocks\":8,"
           "\"raw\":%s,\"counts\":%s,\"volts_nominal\":%s,\"reconfigured\":%s}\n",
           static_cast<unsigned long>(seq++), static_cast<unsigned long>(millis()),
           ready ? "true" : "false", high_seen ? "true" : "false",
           read_ok ? "true" : "false", static_cast<unsigned long>(wait_us), b, a,
           (before[0] >> 4) & 0x0F, (after[0] >> 4) & 0x0F,
           (before[2] >> 6) & 0x03, (after[2] >> 6) & 0x03,
           before[3], after[3], restored_before_cs ? "true" : "false",
           post_cs_high ? "true" : "false",
           raw_text, counts_text, volts_text, reconfigured ? "true" : "false");
  Serial.print(line);
  delay(30);
}
