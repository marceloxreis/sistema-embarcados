#pragma once
#include <stdint.h>

// Verifica quadros ACK antes de entregá-los à biblioteca do sensor.
// Não autentica o leitor nem fornece identificação de transação UART.
class Dy50ResponseFilter {
 public:
  void begin(uint8_t command) { command_ = command; size_ = pos_ = total_ = 0; ready_ = false; }
  void feed(uint8_t byte) {
    if (ready_) return;
    if (size_ == 0 && byte != 0xef) return;
    if (size_ == 1 && byte != 0x01) { size_ = byte == 0xef ? 1 : 0; return; }
    if (size_ >= sizeof(buffer_)) { reset(); return; }
    buffer_[size_++] = byte;
    if (size_ == 9) {
      uint16_t length = uint16_t(buffer_[7]) << 8 | buffer_[8];
      if (length < 3 || length > sizeof(buffer_) - 9) { reset(); return; }
      total_ = 9 + length;
    }
    if (!total_ || size_ != total_) return;
    bool address = buffer_[2] == 0xff && buffer_[3] == 0xff && buffer_[4] == 0xff && buffer_[5] == 0xff;
    uint16_t sum = buffer_[6] + buffer_[7] + buffer_[8];
    for (uint8_t i = 9; i < total_ - 2; ++i) sum += buffer_[i];
    uint16_t received = uint16_t(buffer_[total_-2]) << 8 | buffer_[total_-1];
    uint16_t length = total_ - 9;
    uint16_t successLength = command_ == 0x0f ? 19 : command_ == 0x1b ? 7 : 3;
    if (!address || buffer_[6] != 0x07 || sum != received || (buffer_[9] == 0 && length != successLength)) { reset(); return; }
    ready_ = true; pos_ = 0;
  }
  int available() const { return ready_ ? size_ - pos_ : 0; }
  int peek() const { return ready_ ? buffer_[pos_] : -1; }
  int read() {
    if (!ready_) return -1;
    uint8_t value = buffer_[pos_++];
    if (pos_ == size_) reset();
    return value;
  }
 private:
  void reset() { size_ = pos_ = total_ = 0; ready_ = false; }
  uint8_t buffer_[64] = {}; uint8_t size_ = 0, pos_ = 0, total_ = 0, command_ = 0;
  bool ready_ = false;
};
