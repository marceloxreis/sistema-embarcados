#include "../firmware/MegaControlador/UserStore.h"
#include <cassert>
#include <cstring>
#include <cstdio>
#include <stdexcept>
struct Memory {
  uint8_t data[4096]; int budget = -1;
  Memory() { memset(data, 0xff, sizeof data); }
  uint8_t read(uint16_t a) { assert(a < sizeof data); return data[a]; }
  void update(uint16_t a, uint8_t v) {
    assert(a < sizeof data);
    if (data[a] == v) return;
    if (budget == 0) throw std::runtime_error("power loss");
    if (budget > 0) --budget;
    data[a] = v;
  }
};
int main() {
  static_assert(UserStore::kRequired <= 4096, "EEPROM overflow");
  UserStore::Record old = {}, next = {}, got = {};
  old.bytes[0] = 1; next.bytes[0] = 2;
  for (int i = 1; i < UserStore::kPayload; ++i) { old.bytes[i] = i; next.bytes[i] = i + 50; }
  Memory base;
  assert(UserStore::recover(base));
  assert(UserStore::save(base, 100, old));
  assert(UserStore::load(base, 100, got) == 1 && !memcmp(got.bytes, old.bytes, sizeof got.bytes));
  for (int cutoff = 0; cutoff < 100; ++cutoff) {
    Memory mem = base; mem.budget = cutoff;
    try { UserStore::save(mem, 100, next); } catch (const std::runtime_error &) {}
    mem.budget = -1;
    assert(UserStore::recover(mem));
    assert(UserStore::load(mem, 100, got) == 1);
    assert(!memcmp(got.bytes, old.bytes, sizeof got.bytes) || !memcmp(got.bytes, next.bytes, sizeof got.bytes));
  }
  base.data[(100 - 1) * UserStore::kRecord + 4] ^= 1;
  assert(UserStore::load(base, 100, got) == -1);
  assert(!UserStore::save(base, 100, next));
  base.data[UserStore::kJournal] = 0x17;
  assert(!UserStore::recover(base));
  puts("user store: power-cut recovery and corruption checks passed");
}
