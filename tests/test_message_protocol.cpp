#include "../firmware/shared/MessageProtocol.h"
#include <cassert>
#include <cstdio>
int main() {
  using namespace MessageProtocol;
  EventData e = {0x12345678, 42, 0xffffffffUL, 0, AccessGranted, 100, Fingerprint, 1, 0, 1};
  uint8_t bytes[kEventLength];
  assert(encodeEvent(e, bytes, sizeof bytes));
  assert(bytes[2] == 0x78 && bytes[3] == 0x56 && bytes[4] == 0x34 && bytes[5] == 0x12);
  EventData decoded = {};
  assert(decodeEvent(bytes, sizeof bytes, decoded));
  assert(decoded.messageId == e.messageId && decoded.boot == e.boot && decoded.uptime == e.uptime);
  assert(decoded.kind == AccessGranted && decoded.user == 100 && decoded.method == Fingerprint && decoded.epoch == 0);
  assert(!decodeEvent(bytes, sizeof bytes - 1, decoded));
  bytes[19] = 101; assert(!decodeEvent(bytes, sizeof bytes, decoded));
  e.epoch = 1; assert(!encodeEvent(e, bytes, sizeof bytes));
  e.epoch = 1700000000UL; assert(encodeEvent(e, bytes, sizeof bytes));
  puts("message protocol: encoding and validation passed");
}
