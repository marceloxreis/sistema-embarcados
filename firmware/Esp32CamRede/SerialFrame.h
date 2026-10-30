#pragma once
#include <stdint.h>

// HDLC-style framing, CRC-16/CCITT-FALSE. Body begins with version, type and
// a 32-bit little-endian message ID. ACKs identify that ID, not server storage.
namespace SerialFrame {
constexpr uint8_t kFlag = 0x7e, kEscape = 0x7d, kVersion = 1;
constexpr uint16_t kMaxBody = 192, kTimeoutMs = 1000;
inline uint16_t crc(const uint8_t *data, uint16_t size) {
  uint16_t value = 0xffff;
  while (size--) {
    value ^= uint16_t(*data++) << 8;
    for (uint8_t bit = 0; bit < 8; ++bit)
      value = value & 0x8000 ? uint16_t((value << 1) ^ 0x1021) : uint16_t(value << 1);
  }
  return value;
}
template <typename Sink> void escaped(Sink &out, uint8_t b) {
  if (b == kFlag || b == kEscape) { out.write(kEscape); out.write(b ^ 0x20); }
  else out.write(b);
}
template <typename Sink> bool send(Sink &out, const uint8_t *body, uint16_t size) {
  if (size < 6 || size > kMaxBody || body[0] != kVersion) return false;
  out.write(kFlag);
  for (uint16_t i = 0; i < size; ++i) escaped(out, body[i]);
  uint16_t sum = crc(body, size);
  escaped(out, uint8_t(sum)); escaped(out, uint8_t(sum >> 8)); out.write(kFlag);
  return true;
}
class Parser {
 public:
  Parser() : size_(0), active_(false), escape_(false), last_(0), started_(0) {}
  // On true, data() and size() remain valid until the next received byte.
  bool feed(uint8_t b, uint32_t now) {
    if (active_ && uint32_t(now - last_) > kTimeoutMs) reset();
    last_ = now;
    if (b == kFlag) {
      bool complete = active_ && !escape_ && size_ >= 8 && buffer_[0] == kVersion &&
        crc(buffer_, size_ - 2) == (uint16_t(buffer_[size_-2]) | uint16_t(buffer_[size_-1]) << 8);
      if (complete) { size_ -= 2; active_ = false; return true; }
      size_ = 0; active_ = true; escape_ = false; started_ = now; return false;
    }
    if (!active_) return false;
    if (escape_) { b ^= 0x20; escape_ = false; }
    else if (b == kEscape) { escape_ = true; return false; }
    if (size_ >= sizeof buffer_) { reset(); return false; }
    buffer_[size_++] = b;
    return false;
  }
  const uint8_t *data() const { return buffer_; }
  uint16_t size() const { return size_; }
  uint32_t startedAt() const { return started_; }
 private:
  void reset() { size_ = 0; active_ = false; escape_ = false; }
  uint8_t buffer_[kMaxBody + 2]; uint16_t size_; bool active_, escape_; uint32_t last_, started_;
};
}
