// Small fixed-buffer JSON line writer.
//
// Same role as firmware/sensor/json_writer.h, kept as its own copy so the V2
// sketch never depends on the frozen 12-channel firmware.  A write that would
// overflow the buffer sets ok() to false; the caller must check it before
// sending the line and report an ERROR frame instead of a truncated line.
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

class JsonLineWriter {
 public:
  JsonLineWriter(char* buffer, size_t capacity)
      : buffer_(buffer), capacity_(capacity), length_(0), ok_(true) {
    if (buffer_ == nullptr || capacity_ == 0) {
      ok_ = false;
      return;
    }
    buffer_[0] = '\0';
  }

  void reset() {
    length_ = 0;
    ok_ = buffer_ != nullptr && capacity_ > 0;
    if (ok_) buffer_[0] = '\0';
  }

  bool ok() const { return ok_; }
  size_t length() const { return length_; }
  const char* data() const { return buffer_; }

  void ch(char value) { append(&value, 1); }

  // Writes "name": and inserts the separating comma unless this is the first
  // member of the current object.  Frame builders therefore never have to
  // track object state themselves.
  void key(const char* name) {
    if (length_ > 0 && buffer_[length_ - 1] != '{') ch(',');
    str(name);
    ch(':');
  }

  void lit(const char* text) {
    if (text == nullptr) return;
    append(text, strlen(text));
  }

  void str(const char* text) {
    ch('"');
    if (text != nullptr) {
      for (const char* cursor = text; *cursor != '\0'; ++cursor) {
        const unsigned char value = static_cast<unsigned char>(*cursor);
        switch (value) {
          case '"': lit("\\\""); break;
          case '\\': lit("\\\\"); break;
          case '\n': lit("\\n"); break;
          case '\r': lit("\\r"); break;
          case '\t': lit("\\t"); break;
          default:
            if (value < 0x20) {
              char escape[7];
              snprintf(escape, sizeof(escape), "\\u%04x", value);
              lit(escape);
            } else {
              ch(static_cast<char>(value));
            }
            break;
        }
      }
    }
    ch('"');
  }

  void i32(int32_t value) {
    char text[12];
    snprintf(text, sizeof(text), "%ld", static_cast<long>(value));
    lit(text);
  }

  void u32(uint32_t value) {
    char text[12];
    snprintf(text, sizeof(text), "%lu", static_cast<unsigned long>(value));
    lit(text);
  }

  void u64(uint64_t value) {
    char text[24];
    snprintf(text, sizeof(text), "%llu", static_cast<unsigned long long>(value));
    lit(text);
  }

  // Fixed-point value with two decimals, used for Hz fields.
  void centi(uint32_t hundredths) {
    char text[24];
    snprintf(text, sizeof(text), "%lu.%02lu", static_cast<unsigned long>(hundredths / 100),
             static_cast<unsigned long>(hundredths % 100));
    lit(text);
  }

  void boolean(bool value) { lit(value ? "true" : "false"); }

  void nul() { lit("null"); }

  void newline() { ch('\n'); }

 private:
  void append(const char* data, size_t count) {
    if (!ok_ || count == 0) return;
    if (length_ + count + 1 > capacity_) {
      ok_ = false;
      return;
    }
    memcpy(buffer_ + length_, data, count);
    length_ += count;
    buffer_[length_] = '\0';
  }

  char* buffer_;
  size_t capacity_;
  size_t length_;
  bool ok_;
};
