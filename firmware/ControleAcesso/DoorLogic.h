#pragma once
#include <stdint.h>

enum class DoorState { Idle, AwaitOpen, Open, Alarm };
enum class DoorEvent { None, Opened, Closed, EntryExpired, OpenTooLong, ForcedOpen };

class DoorLogic {
 public:
  DoorState state = DoorState::Idle;
  uint16_t user = 0;
  uint32_t since = 0;
  bool closed = true;

  void begin(bool isClosed, uint32_t now) {
    closed = isClosed; user = 0; since = now;
    state = isClosed ? DoorState::Idle : DoorState::Alarm;
  }
  bool authorize(uint16_t id, uint32_t now) {
    if (!closed || state != DoorState::Idle) return false;
    user = id; since = now; state = DoorState::AwaitOpen; return true;
  }
  DoorEvent tick(bool isClosed, uint32_t now, uint32_t entryMs, uint32_t openMs) {
    closed = isClosed;
    if (state == DoorState::Idle && !closed) {
      user = 0; state = DoorState::Alarm; since = now; return DoorEvent::ForcedOpen;
    }
    if (state == DoorState::AwaitOpen) {
      if (!closed) {
        state = DoorState::Open; since = now; return DoorEvent::Opened;
      }
      if (uint32_t(now - since) >= entryMs) {
        state = DoorState::Idle; return DoorEvent::EntryExpired;
      }
    } else if (state == DoorState::Open || state == DoorState::Alarm) {
      if (closed) { state = DoorState::Idle; return DoorEvent::Closed; }
      if (state == DoorState::Open && uint32_t(now - since) >= openMs) {
        state = DoorState::Alarm; return DoorEvent::OpenTooLong;
      }
    }
    return DoorEvent::None;
  }
};
