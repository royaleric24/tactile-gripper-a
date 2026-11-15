#pragma once

#include <Arduino.h>

// Small fixed-buffer JSON writer used instead of heap-allocating a document on
// every sample frame.  The device streams continuously; avoiding a per-frame
// heap allocation keeps long runs predictable.
class JsonLineWriter {
 public:
  JsonLineWriter(char* buffer, size_t capacity)
      : buffer_(buffer), capacity_(capacity), length_(0), ok_(capacity > 1) {
    if (capacity_ > 0) {
      buffer_[0] = '\0';
    }
  }

  void reset() {
    length_ = 0;
    ok_ = capacity_ > 1;
    if (capacity_ > 0) {
      buffer_[0] = '\0';
    }
  }

  bool ok() const { return ok_; }
  size_t length() const { return length_; }
  const char* data() const { return buffer_; }

  void ch(char value) {
    if (!ok_) {
      return;
    }
    if (length_ + 1 >= capacity_) {
      ok_ = false;
      return;
    }
    buffer_[length_++] = value;
    buffer_[length_] = '\0';
  }

  void lit(const char* value) {
    while (value != nullptr && *value != '\0') {
      ch(*value++);
    }
  }

  void str(const char* value) {
    ch('"');
    if (value != nullptr) {
      for (const char* p = value; *p != '\0'; ++p) {
        const unsigned char c = static_cast<unsigned char>(*p);
        switch (c) {
          case '"': lit("\\\""); break;
          case '\\': lit("\\\\"); break;
          case '\n': lit("\\n"); break;
          case '\r': lit("\\r"); break;
          case '\t': lit("\\t"); break;
          default:
            if (c < 0x20) {
              char tmp[7];
              snprintf(tmp, sizeof(tmp), "\\u%04x", c);
              lit(tmp);
            } else {
              ch(static_cast<char>(c));
            }
        }
      }
    }
    ch('"');
  }

  void i32(int32_t value) {
    char tmp[16];
    snprintf(tmp, sizeof(tmp), "%ld", static_cast<long>(value));
    lit(tmp);
  }

  void u32(uint32_t value) {
    char tmp[16];
    snprintf(tmp, sizeof(tmp), "%lu", static_cast<unsigned long>(value));
    lit(tmp);
  }

  void u64(uint64_t value) {
    char tmp[24];
    snprintf(tmp, sizeof(tmp), "%llu", static_cast<unsigned long long>(value));
    lit(tmp);
  }

  // Fixed two-decimal representation of a value in hundredths (for example
  // 4823 -> 48.23).  Avoids relying on floating-point printf support.
  void centi(uint32_t value) {
    u32(value / 100);
    ch('.');
    const uint32_t fraction = value % 100;
    if (fraction < 10) {
      ch('0');
    }
    u32(fraction);
  }

  void boolean(bool value) { lit(value ? "true" : "false"); }
  void nul() { lit("null"); }

  // Appends a newline, but keeps the NUL terminator.
  void newline() { ch('\n'); }

 private:
  char* buffer_;
  size_t capacity_;
  size_t length_;
  bool ok_;
};
