#include "../firmware/MegaControlador/BootCounter.h"
#include <cassert>
#include <cstring>
#include <cstdio>
#include <stdexcept>
#include <initializer_list>
struct Memory {
  uint8_t data[4096]; int budget = -1;
  Memory() { memset(data, 0xff, sizeof data); }
  uint8_t read(uint16_t a) { assert(a < sizeof data); return data[a]; }
  void update(uint16_t a, uint8_t v) {
    assert(a < sizeof data); if (data[a] == v) return;
    if (budget == 0) throw std::runtime_error("power loss");
    if (budget > 0) --budget; data[a] = v;
  }
};
int main() {
  static_assert(BootCounter::kRequired <= 4096, "EEPROM overflow");
  Memory base; uint32_t first = 0;
  assert(BootCounter::next(base, first) && first == 1);
  for (int cutoff = 0; cutoff < 12; ++cutoff) {
    Memory empty; empty.budget = cutoff; uint32_t interrupted = 0;
    try { BootCounter::next(empty, interrupted); } catch (const std::runtime_error &) {}
    empty.budget = -1; uint32_t after = 0;
    assert(BootCounter::next(empty, after));
    assert(after >= 1 && (!interrupted || after > interrupted));
  }
  for (int cutoff = 0; cutoff < 20; ++cutoff) {
    Memory mem = base; mem.budget = cutoff; uint32_t interrupted = 0;
    try { BootCounter::next(mem, interrupted); } catch (const std::runtime_error &) {}
    mem.budget = -1; uint32_t after = 0;
    assert(BootCounter::next(mem, after));
    assert(after > first && (!interrupted || after > interrupted));
  }
  Memory two = base; uint32_t second = 0;
  assert(BootCounter::next(two, second) && second == 2);
  for (uint8_t marker : {uint8_t(0), uint8_t(0xff)}) {
    Memory corrupted = two; corrupted.data[BootCounter::kBase + BootCounter::kSlotSize] = marker;
    for (int cutoff = 0; cutoff < 20; ++cutoff) {
      Memory mem = corrupted; mem.budget = cutoff; uint32_t interrupted = 0;
      try { BootCounter::next(mem, interrupted); } catch (const std::runtime_error &) {}
      mem.budget = -1; uint32_t after = 0;
      assert(BootCounter::next(mem, after));
      assert(after > second && (!interrupted || after > interrupted));
    }
  }
  // Duas perdas consecutivas não podem destruir o maior watermark, mesmo
  // quando ele estava inativo antes de qualquer tentativa.
  for (uint8_t marker : {uint8_t(0), uint8_t(0xff)}) {
    for (int firstCut = 0; firstCut < 12; ++firstCut) {
      for (int secondCut = 0; secondCut < 12; ++secondCut) {
        Memory mem = two;
        mem.data[BootCounter::kBase + BootCounter::kSlotSize] = marker;
        uint32_t latest = second;
        for (int cut : {firstCut, secondCut}) {
          mem.budget = cut; uint32_t emitted = 0;
          try {
            if (BootCounter::next(mem, emitted)) {
              assert(emitted > latest); latest = emitted;
            }
          } catch (const std::runtime_error &) {}
        }
        mem.budget = -1; uint32_t recovered = 0;
        assert(BootCounter::next(mem, recovered) && recovered > latest);
      }
    }
  }
  Memory unknown = two;
  unknown.data[BootCounter::kBase + BootCounter::kSlotSize] = 0x42;
  uint32_t ignored = 0;
  assert(!BootCounter::next(unknown, ignored));
  Memory maximum = two;
  const uint16_t slot = BootCounter::kBase + BootCounter::kSlotSize;
  for (uint8_t i = 0; i < 4; ++i) maximum.data[slot + 1 + i] = 0xff;
  uint16_t crc = UserStore::crc(maximum.data + slot + 1, 4);
  maximum.data[slot + 5] = uint8_t(crc);
  maximum.data[slot + 6] = uint8_t(crc >> 8);
  assert(!BootCounter::next(maximum, ignored));
  maximum.data[slot] = 0;
  assert(!BootCounter::next(maximum, ignored));
  base.data[BootCounter::kBase + 1] ^= 1;
  assert(!BootCounter::next(base, first));
  puts("boot counter: interruption and corruption checks passed");
}
