#pragma once
#include <Arduino.h>
// Exemplo para compilação. Copie para Config.h ignorado e altere a senha.
constexpr char ADMIN_PIN[] = "0000000000";
constexpr uint8_t LOCK_MODE = 0, LOCK_PIN = 35, LOCK_ON = HIGH;
constexpr uint32_t LOCK_PULSE_MS = 200;
constexpr uint8_t BUZZER_PIN = 36, LCD_ADDRESS = 0x27;
constexpr uint8_t BUTTON_1 = 30, BUTTON_2 = 31, LED_R = 32, LED_G = 33, LED_B = 34;
constexpr bool RGB_COMMON_ANODE = false;
const byte ROW_PINS[4] = {22,23,24,25}, COL_PINS[4] = {26,27,28,29};
constexpr uint8_t MAX_USERS = 100;
constexpr uint32_t ENTRY_MS = 60000, OPEN_MS = 300000, UI_TIMEOUT_MS = 60000;
