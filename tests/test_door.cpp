#include <cassert>
#include <iostream>
#include "../firmware/MegaControlador/DoorLogic.h"

int main() {
  const uint32_t minute = 60000, fiveMinutes = 300000;
  DoorLogic d;
  d.begin(true, 0);
  assert(d.state == DoorState::Idle);
  assert(d.authorize(1, 100));
  assert(!d.authorize(2, 200)); // não substituir a pessoa do ciclo em andamento
  assert(d.tick(true, 60099, minute, fiveMinutes) == DoorEvent::None);
  assert(d.tick(true, 60100, minute, fiveMinutes) == DoorEvent::EntryExpired);
  assert(d.state == DoorState::Idle);
  assert(d.authorize(2, 70000));
  assert(d.tick(false, 71000, minute, fiveMinutes) == DoorEvent::Opened);
  assert(d.user == 2);
  assert(d.tick(false, 370999, minute, fiveMinutes) == DoorEvent::None);
  assert(d.tick(false, 371000, minute, fiveMinutes) == DoorEvent::OpenTooLong);
  assert(d.state == DoorState::Alarm);
  assert(!d.authorize(3, 372000));
  assert(d.tick(true, 373000, minute, fiveMinutes) == DoorEvent::Closed);
  assert(d.user == 2);
  assert(d.tick(false, 374000, minute, fiveMinutes) == DoorEvent::ForcedOpen);
  assert(d.user == 0);
  assert(d.tick(true, 375000, minute, fiveMinutes) == DoorEvent::Closed);
  d.begin(false, 0);
  assert(d.state == DoorState::Alarm && !d.authorize(1, 0));
  assert(d.tick(true, 1, minute, fiveMinutes) == DoorEvent::Closed);
  assert(d.authorize(100, 2));
  assert(d.tick(false, 3, minute, fiveMinutes) == DoorEvent::Opened);
  assert(d.tick(true, 4, minute, fiveMinutes) == DoorEvent::Closed);
  // millis() de 32 bits volta a zero em aproximadamente 49 dias.
  d.begin(true, UINT32_MAX - 100);
  assert(d.authorize(9, UINT32_MAX - 100));
  assert(d.tick(true, 59898, minute, fiveMinutes) == DoorEvent::None);
  assert(d.tick(true, 59899, minute, fiveMinutes) == DoorEvent::EntryExpired);
  std::cout << "26 verificacoes da porta passaram (tempos, ID, fechamento, alarme e rollover).\n";
}
