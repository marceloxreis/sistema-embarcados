#include "../firmware/shared/SerialFrame.h"
#include <vector>
#include <cassert>
#include <cstring>
#include <cstdio>
struct Sink { std::vector<uint8_t> bytes; void write(uint8_t b) { bytes.push_back(b); } };
int main() {
  uint8_t data[] = {1, 2, 1, 0, 0, 0, 0x7e, 0x7d, 0xff};
  Sink out; assert(SerialFrame::send(out, data, sizeof data));
  SerialFrame::Parser p; bool received = false;
  for (uint8_t b : out.bytes) received |= p.feed(b, 1);
  assert(received && p.size() == sizeof data && !memcmp(p.data(), data, sizeof data));
  out.bytes[2] ^= 1; received = false;
  for (uint8_t b : out.bytes) received |= p.feed(b, 2);
  assert(!received);
  p.feed(0x7e, 4); p.feed(1, 5); assert(!p.feed(0x7e, 2000));
  puts("serial frame: roundtrip, escaping, CRC and timeout checks passed");
}
