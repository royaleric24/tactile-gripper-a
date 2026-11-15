// Offline 6x6 row-scan prototype for the old ESP32 + 3x ADS1220.
//
// This sketch is intentionally NOT flashed during the hardware design phase.
// It reuses the validated ADS1220 driver from ../sensor via include; the driver
// still reads its SPI pin constants from ../sensor/generated_config.h.
//
// Topology assumed here:
//   - 6 row electrodes on ESP32 GPIOs (through 1k), selected HIGH / others HIGH_Z
//   - 6 column electrodes on ADS1220 AIN0/AIN1 of all three ADCs
//   - one reference resistor per column to GND
//   - AVDD-AVSS reference, no IDAC
#include <Arduino.h>

#include "matrix_config.h"
#include "../sensor/json_writer.h"
#include "../sensor/ads1220.cpp"

namespace {

char out_buffer[8192];
uint32_t frame_seq = 0;
uint32_t last_frame_start_us = 0;
int32_t cells[MATRIX_CELL_COUNT];
bool cell_valid[MATRIX_CELL_COUNT];
uint8_t cell_flags[MATRIX_CELL_COUNT];
bool device_ok[3] = {false, false, false};

Ads1220Pins makePins(uint8_t index) {
  return Ads1220Pins{SENSOR_SCLK_PIN, SENSOR_MOSI_PIN, SENSOR_MISO_PINS[index], SENSOR_CS_PINS[index]};
}

Ads1220 devices[3] = {
    Ads1220(0, makePins(0)),
    Ads1220(1, makePins(1)),
    Ads1220(2, makePins(2)),
};

void setAllRowsLow() {
  for (uint8_t i = 0; i < MATRIX_ROWS; ++i) {
    digitalWrite(MATRIX_ROW_PINS[i], LOW);
    pinMode(MATRIX_ROW_PINS[i], OUTPUT);
  }
}

void setAllRowsHighZ() {
  for (uint8_t i = 0; i < MATRIX_ROWS; ++i) {
    pinMode(MATRIX_ROW_PINS[i], INPUT);  // no pull-up/pull-down
  }
}

void selectRow(uint8_t row) {
  // Preload the output register HIGH, then enable the driver; avoids a low glitch.
  digitalWrite(MATRIX_ROW_PINS[row], HIGH);
  pinMode(MATRIX_ROW_PINS[row], OUTPUT);
}

uint8_t classify(int32_t value, bool valid) {
  if (!valid) return 0x20;  // NO_DATA
  uint8_t flags = 0;
  if (value >= 8388607) flags |= 0x01;
  if (value <= -8388608) flags |= 0x02;
  if (value < 0) flags |= 0x04;
  if (value > 8000000 || value < -8000000) flags |= 0x08;
  return flags;
}

void sendWriter(JsonLineWriter& writer) {
  if (!writer.ok()) {
    Serial.println("{\"protocol_version\":1,\"type\":\"ERROR\",\"code\":\"FRAME_BUFFER_OVERFLOW\"}");
    return;
  }
  Serial.write(reinterpret_cast<const uint8_t*>(writer.data()), writer.length());
  Serial.write('\n');
}

void sendMatrixFrame(uint32_t frame_start_us) {
  const uint32_t period = last_frame_start_us == 0 ? 0 : (frame_start_us - last_frame_start_us);
  last_frame_start_us = frame_start_us;

  JsonLineWriter writer(out_buffer, sizeof(out_buffer));
  writer.lit("{\"protocol_version\":1,\"type\":\"MATRIX_FRAME\",\"device_id\":");
  writer.str(MATRIX_DEVICE_ID);
  writer.lit(",\"firmware_version\":");
  writer.str(MATRIX_FIRMWARE_VERSION);
  writer.lit(",\"scan_mode\":\"ROW_SCAN_6X6\",\"rows\":6,\"cols\":6,\"cell_order\":\"ROW_MAJOR_R1C1\"");
  writer.lit(",\"frame_seq\":");
  writer.u32(++frame_seq);
  writer.lit(",\"timestamp_us\":");
  writer.u32(frame_start_us);
  writer.lit(",\"frame_period_us\":");
  writer.u32(period);
  writer.lit(",\"reference_mode\":\"AVDD_AVSS\",\"row_pins\":[");
  for (uint8_t i = 0; i < MATRIX_ROWS; ++i) {
    if (i > 0) writer.ch(',');
    writer.u32(MATRIX_ROW_PINS[i]);
  }
  writer.lit("],\"column_ains\":[");
  for (uint8_t i = 0; i < MATRIX_COLS; ++i) {
    if (i > 0) writer.ch(',');
    writer.u32(MATRIX_COLUMN_AIN[i]);
  }
  writer.lit("],\"cells\":[");
  for (uint8_t i = 0; i < MATRIX_CELL_COUNT; ++i) {
    if (i > 0) writer.ch(',');
    if (cell_valid[i]) writer.i32(cells[i]);
    else writer.nul();
  }
  writer.lit("],\"valid\":[");
  for (uint8_t i = 0; i < MATRIX_CELL_COUNT; ++i) {
    if (i > 0) writer.ch(',');
    writer.boolean(cell_valid[i]);
  }
  writer.lit("],\"flags\":[");
  for (uint8_t i = 0; i < MATRIX_CELL_COUNT; ++i) {
    if (i > 0) writer.ch(',');
    writer.u32(cell_flags[i]);
  }
  writer.lit("]}");
  sendWriter(writer);
}

void scanFrame() {
  const uint32_t frame_start = micros();
  for (uint8_t row = 0; row < MATRIX_ROWS; ++row) {
    setAllRowsLow();
    delayMicroseconds(MATRIX_PRE_DISCHARGE_US);
    setAllRowsHighZ();
    selectRow(row);
    delayMicroseconds(MATRIX_SETTLE_US);

    for (uint8_t round = 0; round < 2; ++round) {
      for (uint8_t adc = 0; adc < 3; ++adc) {
        if (!device_ok[adc]) continue;
        // ADC1 owns C1/C2, ADC2 owns C3/C4, ADC3 owns C5/C6.
        // Round 0 uses AIN0 of each ADC; round 1 uses AIN1 of each ADC.
        const uint8_t column = static_cast<uint8_t>(adc * 2 + round);
        devices[adc].setMux(static_cast<uint8_t>(MATRIX_MUX_BASE + MATRIX_COLUMN_AIN[column]));
        devices[adc].startConversion();
      }
      delayMicroseconds(MATRIX_CONVERSION_WAIT_US);
      for (uint8_t adc = 0; adc < 3; ++adc) {
        const uint8_t column = static_cast<uint8_t>(adc * 2 + round);
        const uint8_t cell = static_cast<uint8_t>(row * MATRIX_COLS + column);
        if (!device_ok[adc]) {
          cells[cell] = 0;
          cell_valid[cell] = false;
          cell_flags[cell] = 0x20;
          continue;
        }
        int32_t value = 0;
        const bool ok = devices[adc].readData(&value);
        cells[cell] = value;
        cell_valid[cell] = ok;
        cell_flags[cell] = classify(value, ok);
      }
      delayMicroseconds(MATRIX_READ_OVERHEAD_US);
    }
    pinMode(MATRIX_ROW_PINS[row], INPUT);
  }
  sendMatrixFrame(frame_start);
}

}  // namespace

void setup() {
  // All rows high-Z before any drive; no excitation during boot.
  for (uint8_t i = 0; i < MATRIX_ROWS; ++i) {
    digitalWrite(MATRIX_ROW_PINS[i], LOW);
    pinMode(MATRIX_ROW_PINS[i], INPUT);
  }
  Serial.begin(SENSOR_SERIAL_BAUD, SERIAL_8N1);
  delay(50);

  for (uint8_t i = 0; i < 3; ++i) {
    devices[i].begin();
  }
  delay(20);

  // AVDD reference, AIN0 vs AVSS, gain 1, 330 SPS single-shot.
  static const uint8_t initial_config[4] = {0x81, 0x80, 0x80, 0x00};
  for (uint8_t i = 0; i < 3; ++i) {
    uint8_t readback[4];
    device_ok[i] = devices[i].configure(initial_config, readback);
  }
}

void loop() {
  scanFrame();
}
