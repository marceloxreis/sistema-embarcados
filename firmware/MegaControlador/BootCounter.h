#pragma once
#include "UserStore.h"

// Two alternating records. A boot number is used only after its slot is committed.
namespace BootCounter {
constexpr uint16_t kBase = UserStore::kRequired, kSlotSize = 7;
constexpr uint16_t kRequired = kBase + 2 * kSlotSize;
constexpr uint8_t kCommitted = 0xa5;
inline uint32_t decode(const uint8_t *p) {
  return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
}
template <class E> int8_t readSlot(E &e, uint8_t slot, uint32_t &value) {
  const uint16_t base = kBase + uint16_t(slot) * kSlotSize;
  uint8_t marker = e.read(base);
  if (marker != kCommitted && marker != 0 && marker != 0xff) return -1;
  uint8_t bytes[4]; for (uint8_t i = 0; i < 4; ++i) bytes[i] = e.read(base + 1 + i);
  uint16_t expected = uint16_t(e.read(base + 5)) | uint16_t(e.read(base + 6)) << 8;
  value = decode(bytes);
  if (!value || UserStore::crc(bytes, 4) != expected) {
    value = 0;
    return marker == kCommitted ? -1 : 0;
  }
  // Um slot inativo, porém íntegro, pode ter sido publicado antes de seu
  // marcador corromper. Preservar esse número como limite inferior também após
  // uma interrupção durante a próxima gravação; números não usados podem ser pulados.
  return marker == kCommitted ? 1 : 2;
}
template <class E> bool next(E &e, uint32_t &boot) {
  uint32_t a = 0, b = 0;
  int8_t va = readSlot(e, 0, a), vb = readSlot(e, 1, b);
  if (va < 0 || vb < 0) return false;
  uint32_t previous = a > b ? a : b;
  if (previous == 0xffffffffUL) return false;
  uint8_t target = va == 0 ? 0 : (vb == 0 ? 1 : (a <= b ? 0 : 1));
  const uint16_t base = kBase + uint16_t(target) * kSlotSize;
  uint32_t nextValue = previous + 1;
  uint8_t bytes[4];
  for (uint8_t i = 0; i < 4; ++i) bytes[i] = uint8_t(nextValue >> (8 * i));
  uint16_t sum = UserStore::crc(bytes, 4);
  e.update(base, 0);
  for (uint8_t i = 0; i < 4; ++i) e.update(base + 1 + i, bytes[i]);
  e.update(base + 5, uint8_t(sum)); e.update(base + 6, uint8_t(sum >> 8));
  e.update(base, kCommitted);
  uint32_t verified = 0;
  if (readSlot(e, target, verified) != 1 || verified != nextValue) return false;
  boot = nextValue;
  return true;
}
}
