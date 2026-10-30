#pragma once
#include <stdint.h>
#include <string.h>

// Store adapter: uint8_t read(uint16_t); void update(uint16_t, uint8_t).
// Layout is byte-defined so host and AVR use exactly the same representation.
namespace UserStore {
constexpr uint8_t kUsers = 100, kPayload = 29, kRecord = 31;
constexpr uint16_t kJournal = kUsers * kRecord, kRequired = kJournal + 34;
constexpr uint8_t kCommitted = 0xa5;
struct Record { uint8_t bytes[kPayload]; }; // state, salt[4], digest[16], last web token[8]

inline uint16_t crc(const uint8_t *data, uint8_t len, uint16_t value = 0xffff) {
  while (len--) {
    value ^= uint16_t(*data++) << 8;
    for (uint8_t bit = 0; bit < 8; ++bit)
      value = value & 0x8000 ? uint16_t((value << 1) ^ 0x1021) : uint16_t(value << 1);
  }
  return value;
}
inline uint16_t checksum(uint8_t id, const uint8_t *payload) {
  return crc(payload, kPayload, crc(&id, 1));
}
template <class E> bool valid(E &e, uint16_t addr, uint8_t id) {
  uint8_t payload[kPayload];
  for (uint8_t i = 0; i < kPayload; ++i) payload[i] = e.read(addr + i);
  if (payload[0] != 1 && payload[0] != 2) return false;
  uint16_t sum = uint16_t(e.read(addr + kPayload)) | uint16_t(e.read(addr + kPayload + 1)) << 8;
  return sum == checksum(id, payload);
}
template <class E> bool recover(E &e) {
  uint8_t marker = e.read(kJournal);
  if (marker == 0xff || marker == 0) return true;
  if (marker != kCommitted) return false;
  uint8_t id = e.read(kJournal + 1);
  if (id < 1 || id > kUsers || !valid(e, kJournal + 2, id)) return false;
  uint16_t dest = uint16_t(id - 1) * kRecord;
  for (uint8_t i = 0; i < kRecord; ++i) e.update(dest + i, e.read(kJournal + 2 + i));
  if (!valid(e, dest, id)) return false;
  e.update(kJournal, 0);
  return true;
}
// Returns 0 for empty, 1 for valid, -1 for corrupt. Do not reuse corrupt slots.
template <class E> int8_t load(E &e, uint8_t id, Record &record) {
  if (id < 1 || id > kUsers) return -1;
  uint16_t addr = uint16_t(id - 1) * kRecord;
  bool empty = true;
  for (uint8_t i = 0; i < kRecord; ++i) if (e.read(addr + i) != 0xff) empty = false;
  if (empty) return 0;
  if (!valid(e, addr, id)) return -1;
  for (uint8_t i = 0; i < kPayload; ++i) record.bytes[i] = e.read(addr + i);
  return 1;
}
template <class E> bool save(E &e, uint8_t id, const Record &record) {
  if (id < 1 || id > kUsers || (record.bytes[0] != 1 && record.bytes[0] != 2) || !recover(e)) return false;
  Record current;
  if (load(e, id, current) < 0) return false;
  // Clear first; a new journal cannot become authoritative until complete.
  e.update(kJournal, 0);
  e.update(kJournal + 1, id);
  for (uint8_t i = 0; i < kPayload; ++i) e.update(kJournal + 2 + i, record.bytes[i]);
  uint16_t sum = checksum(id, record.bytes);
  e.update(kJournal + 2 + kPayload, uint8_t(sum));
  e.update(kJournal + 3 + kPayload, uint8_t(sum >> 8));
  if (!valid(e, kJournal + 2, id)) return false;
  e.update(kJournal, kCommitted);
  return recover(e);
}
} // namespace UserStore
