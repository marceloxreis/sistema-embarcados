#pragma once
#include <stdint.h>
#include "DoorLogic.h"

// Buzzer ativo: a frequência sonora é gerada pelo próprio componente.
// Esta classe produz somente os intervalos ligado/desligado, sem delay().
class BuzzerLogic {
 public:
  void reset() { burst = false; overdue = false; }
  void onEvent(DoorEvent event, uint32_t now) {
    if (event == DoorEvent::EntryExpired) { burst = true; since = now; }
    else if (event == DoorEvent::OpenTooLong) { overdue = true; since = now; }
    else if (event == DoorEvent::Opened || event == DoorEvent::Closed ||
             event == DoorEvent::ForcedOpen) reset();
  }
  bool isOn(uint32_t now) {
    const uint32_t elapsed = uint32_t(now - since);
    if (overdue) return elapsed % 2000 < 250; // repete até fechar
    if (burst && elapsed >= 1200) burst = false;
    return burst && elapsed % 400 < 200; // três bipes
  }
 private:
  bool burst = false, overdue = false;
  uint32_t since = 0;
};
