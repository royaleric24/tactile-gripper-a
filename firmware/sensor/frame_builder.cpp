#include "frame_builder.h"

#include "json_writer.h"

bool buildSampleFrame(char* buffer, size_t capacity, const FrameSample& sample) {
  JsonLineWriter writer(buffer, capacity);
  writer.lit("{\"protocol_version\":1,\"type\":\"SAMPLE\",\"device_id\":");
  writer.str(sample.device_id);
  writer.lit(",\"boot_id\":");
  writer.str(sample.boot_id);
  writer.lit(",\"firmware_version\":");
  writer.str(sample.firmware_version);
  writer.lit(",\"frame_seq\":");
  writer.u32(sample.frame_seq);
  writer.lit(",\"timestamp_us\":");
  writer.u32(sample.timestamp_us);
  writer.lit(",\"mcu_time_us\":");
  writer.u32(sample.timestamp_us);
  writer.lit(",\"frame_period_us\":");
  if (sample.has_previous) {
    writer.u32(sample.timestamp_us - sample.previous_frame_us);
  } else {
    writer.nul();
  }

  writer.lit(",\"channel_ids\":[");
  for (uint8_t i = 0; i < 12; ++i) {
    if (i > 0) writer.ch(',');
    writer.u32(i);
  }
  writer.lit("],\"channel_count\":12");

  writer.lit(",\"raw_adc\":[");
  for (uint8_t i = 0; i < 12; ++i) {
    if (i > 0) writer.ch(',');
    if (sample.valid[i]) {
      writer.i32(sample.raw_adc[i]);
    } else {
      writer.nul();
    }
  }
  writer.lit("],\"channels\":[");
  for (uint8_t i = 0; i < 12; ++i) {
    if (i > 0) writer.ch(',');
    if (sample.valid[i]) {
      writer.i32(sample.raw_adc[i]);
    } else {
      writer.nul();
    }
  }
  writer.lit("],\"valid\":[");
  for (uint8_t i = 0; i < 12; ++i) {
    if (i > 0) writer.ch(',');
    writer.boolean(sample.valid[i]);
  }
  writer.lit("],\"valid_mask\":[");
  for (uint8_t i = 0; i < 12; ++i) {
    if (i > 0) writer.ch(',');
    writer.boolean(sample.valid[i]);
  }
  writer.lit("],\"sample_timestamp_us\":[");
  for (uint8_t i = 0; i < 12; ++i) {
    if (i > 0) writer.ch(',');
    if (sample.valid[i]) {
      writer.u32(sample.sample_timestamp_us[i]);
    } else {
      writer.nul();
    }
  }
  writer.lit("],\"channel_flags\":[");
  for (uint8_t i = 0; i < 12; ++i) {
    if (i > 0) writer.ch(',');
    writer.u32(sample.channel_flags[i]);
  }
  writer.lit("],\"reference_mode\":");
  writer.str(sample.reference_mode);
  writer.lit(",\"effective_frame_rate_hz\":");
  writer.centi(sample.effective_frame_rate_centi_hz);
  writer.lit(",\"adc_status\":[");
  for (uint8_t i = 0; i < 3; ++i) {
    if (i > 0) writer.ch(',');
    const FrameAdcStatus& status = sample.adc_status[i];
    writer.lit("{\"id\":");
    writer.u32(i + 1);
    writer.lit(",\"state\":");
    writer.str(status.state);
    writer.lit(",\"code\":");
    writer.u32(status.code);
    writer.lit(",\"consecutive_errors\":");
    writer.u32(status.consecutive_errors);
    writer.lit(",\"total_errors\":");
    writer.u32(status.total_errors);
    writer.lit(",\"recovered\":");
    writer.u32(status.recovered);
    writer.lit(",\"last_error\":");
    if (status.last_error == nullptr) {
      writer.nul();
    } else {
      writer.str(status.last_error);
    }
    writer.ch('}');
  }
  writer.lit("]}");
  writer.newline();
  return writer.ok();
}
