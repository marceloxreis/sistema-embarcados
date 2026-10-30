#pragma once
#include <stdint.h>
#include <stddef.h>

// Wire format v1. Integers are little endian; no native structs cross the UART.
// Frame envelope and CRC are provided by SerialFrame.h.
namespace MessageProtocol {
constexpr uint8_t kVersion = 1;
enum Type : uint8_t { Event = 1, Ack = 2, Clock = 3, Reset = 4, ResetResult = 5, PhotoChallenge = 6, PhotoProof = 7 };
enum EventType : uint8_t {
  DeviceBoot = 1, StorageError, UserSnapshot, UserEnrolled, UserDisabled,
  UserEnabled, PasswordReset, AdminLogin, AccessGranted, AccessDenied,
  DoorOpened, DoorClosed, EntryExpired, DoorTimeout, ForcedOpen, EnrollFailed
};
enum Method : uint8_t { None = 0, Password, Fingerprint, Admin, Keypad, System, Sensor, Usb, Web };
constexpr size_t kEventLength = 27;
struct EventData {
  uint32_t messageId, boot, uptime, epoch;
  uint8_t kind, user, method, active, reason;
  uint32_t sentUptime;
};
inline void put32(uint8_t *p, uint32_t value) {
  for (uint8_t i = 0; i < 4; ++i) p[i] = uint8_t(value >> (8 * i));
}
inline uint32_t get32(const uint8_t *p) {
  return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
}
inline bool validEvent(const EventData &e) {
  return e.messageId && e.boot && e.kind >= DeviceBoot && e.kind <= EnrollFailed &&
    e.user <= 100 && e.method <= Web && e.active <= 1 &&
    (!e.epoch || (e.epoch >= 1700000000UL && e.epoch <= 4102444800UL));
}
inline bool encodeEvent(const EventData &e, uint8_t *out, size_t capacity) {
  if (capacity < kEventLength || !validEvent(e)) return false;
  out[0] = kVersion; out[1] = Event; put32(out + 2, e.messageId);
  put32(out + 6, e.boot); put32(out + 10, e.uptime); put32(out + 14, e.epoch);
  out[18] = e.kind; out[19] = e.user; out[20] = e.method; out[21] = e.active; out[22] = e.reason;
  put32(out + 23, e.sentUptime);
  return true;
}
inline bool decodeEvent(const uint8_t *data, size_t length, EventData &e) {
  if (length != kEventLength || data[0] != kVersion || data[1] != Event) return false;
  EventData value = {get32(data+2), get32(data+6), get32(data+10), get32(data+14),
                     data[18], data[19], data[20], data[21], data[22], get32(data+23)};
  if (!validEvent(value)) return false;
  e = value; return true;
}
}
