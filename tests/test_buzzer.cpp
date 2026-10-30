#include <cassert>
#include <iostream>
#include "../firmware/MegaControlador/BuzzerLogic.h"

int main() {
  DoorLogic door;
  BuzzerLogic buzzer;
  door.begin(true, 0);
  assert(!buzzer.isOn(0));
  assert(door.authorize(1, 0));
  buzzer.onEvent(door.tick(true, 59999, 60000, 300000), 59999);
  assert(!buzzer.isOn(59999));
  buzzer.onEvent(door.tick(true, 60000, 60000, 300000), 60000);
  assert(buzzer.isOn(60000));
  assert(buzzer.isOn(60199));
  assert(!buzzer.isOn(60200));
  assert(buzzer.isOn(60400));
  assert(!buzzer.isOn(60600));
  assert(buzzer.isOn(60800));
  assert(!buzzer.isOn(61000));
  assert(!buzzer.isOn(61200));
  assert(!buzzer.isOn(100000));
  assert(door.authorize(2, 100000)); buzzer.reset();
  buzzer.onEvent(door.tick(false, 100001, 60000, 300000), 100001);
  assert(!buzzer.isOn(100001));
  buzzer.onEvent(door.tick(false, 400000, 60000, 300000), 400000);
  assert(!buzzer.isOn(400000));
  buzzer.onEvent(door.tick(false, 400001, 60000, 300000), 400001);
  assert(buzzer.isOn(400001));
  assert(!buzzer.isOn(400251));
  assert(buzzer.isOn(402001));
  buzzer.onEvent(door.tick(true, 402050, 60000, 300000), 402050);
  assert(!buzzer.isOn(402050));
  buzzer.onEvent(DoorEvent::OpenTooLong, 500000);
  buzzer.reset(); assert(!buzzer.isOn(500000));
  buzzer.onEvent(DoorEvent::EntryExpired, UINT32_MAX - 99);
  assert(buzzer.isOn(0));
  assert(!buzzer.isOn(100));
  assert(buzzer.isOn(300));
  buzzer.onEvent(DoorEvent::ForcedOpen, 301);
  assert(!buzzer.isOn(301));
  std::cout << "Buzzer: janela de acesso, 3 bipes, alerta de 5 min, fechamento e rollover OK.\n";
}
