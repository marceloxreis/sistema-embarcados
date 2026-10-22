/* Protótipo acadêmico. Consulte README.md e docs/MONTAGEM.md antes de ligar cargas. */
#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <Adafruit_Fingerprint.h>
#include <Keypad.h>
#include <LiquidCrystal_I2C.h>
#include <ArduinoJson.h>
#include <mbedtls/md.h>
#include <esp_system.h>
#include <time.h>
#include "Config.h"
#include "DoorLogic.h"
#include "BuzzerLogic.h"

struct UserRecord {
  uint32_t magic;
  uint8_t active;
  uint8_t salt[16];
  uint8_t hash[32];
  uint64_t lastWebToken;
};
struct AuditEvent {
  char key[72], type[28], method[16], reason[40];
  uint16_t user;
  uint8_t active;
  int64_t epoch;
  uint32_t uptime;
};
struct ResetCommand { int32_t id; uint16_t user; char pin[7]; uint64_t token; };
struct ResetResult { int32_t id; bool ok; char reason[40]; };

Preferences prefs;
UserRecord users[MAX_USERS + 1] = {};
bool storageReady = false, fingerprintReady = false;
uint16_t lastId = 0;
uint32_t eventSequence = 0, droppedEvents = 0;
char bootId[20];
QueueHandle_t eventsQueue, commandsQueue, resultsQueue;
HardwareSerial sensorSerial(2);
// Cast para Stream preserva o RX/TX configurado em sensorSerial.begin().
Adafruit_Fingerprint finger(static_cast<Stream *>(&sensorSerial));
LiquidCrystal_I2C lcd(LCD_ADDRESS, 16, 2);
char keys[4][4] = {{'1','2','3','A'}, {'4','5','6','B'},
                   {'7','8','9','C'}, {'*','0','#','D'}};
byte rows[4], cols[4];
class EspKeypad : public Keypad {
 public:
  EspKeypad(char *map, byte *r, byte *c) : Keypad(map, r, c, 4, 4) {}
  void pin_mode(byte pin, byte mode) override {
    // GPIO34-39 não possuem pull-up interno no ESP32 clássico.
    pinMode(pin, pin >= 34 && mode == INPUT_PULLUP ? INPUT : mode);
  }
};
EspKeypad keypad(makeKeymap(keys), rows, cols);
DoorLogic door;
BuzzerLogic buzzer;

enum class Ui { Access, Menu, FirstFinger, RemoveFinger, SecondFinger,
                FirstPin, ConfirmPin, DisableId, EnableId, ConfirmStatus };
Ui ui = Ui::Access;
String entry, firstPin;
uint16_t pendingId = 0;
bool enableRequested = false, waitFingerRemoval = false, noticeError = false;
String noticeLine1, noticeLine2, accessMethod;
uint32_t noticeSince = 0, noticeDuration = 0, uiTouched = 0;
uint32_t lastFingerPoll = 0, lastLcd = 0, authorizationAt = 0;
bool rawClosed = false, stableClosed = false;
uint32_t rawSince = 0;
bool serialAuthed = false, serialOverflow = false;
uint32_t serialTouched = 0;
String serialLine;

bool validPin(const String &pin, size_t length) {
  if (pin.length() != length) return false;
  for (size_t i = 0; i < length; ++i) if (pin[i] < '0' || pin[i] > '9') return false;
  return true;
}
bool exists(uint16_t id) { return id >= 1 && id <= MAX_USERS && users[id].magic == 0xACCE0001; }
bool digest(const String &pin, const uint8_t *salt, uint8_t *out) {
  uint8_t input[22];
  memcpy(input, salt, 16); memcpy(input + 16, pin.c_str(), 6);
  return mbedtls_md(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), input, sizeof(input), out) == 0;
}
bool matches(uint16_t id, const String &pin) {
  uint8_t hash[32];
  return exists(id) && validPin(pin, 6) && digest(pin, users[id].salt, hash)
      && memcmp(hash, users[id].hash, sizeof(hash)) == 0;
}
uint16_t ownerOfPin(const String &pin) {
  for (uint16_t id = 1; id <= MAX_USERS; ++id) if (matches(id, pin)) return id;
  return 0;
}
void recordKey(uint16_t id, char *key) { snprintf(key, 12, "u%03u", id); }
bool saveRecord(uint16_t id, const UserRecord &record) {
  if (!storageReady || id < 1 || id > MAX_USERS) return false;
  char key[12]; recordKey(id, key);
  if (prefs.putBytes(key, &record, sizeof(record)) != sizeof(record)) return false;
  users[id] = record;
  if (id > lastId) lastId = id;
  return true;
}
void audit(const char *type, uint16_t id = 0, const char *method = "", const char *reason = "") {
  AuditEvent e = {};
  snprintf(e.key, sizeof(e.key), "%s-%s-%lu", DEVICE_ID, bootId, (unsigned long)++eventSequence);
  strlcpy(e.type, type, sizeof(e.type)); strlcpy(e.method, method, sizeof(e.method));
  strlcpy(e.reason, reason, sizeof(e.reason));
  e.user = id; e.active = exists(id) && users[id].active;
  time_t now = time(nullptr); e.epoch = now >= 1700000000 ? int64_t(now) : 0;
  e.uptime = millis();
  if (xQueueSend(eventsQueue, &e, 0) != pdTRUE) ++droppedEvents;
}
void notice(const String &a, const String &b, bool error = false, uint32_t duration = 2000) {
  noticeLine1 = a; noticeLine2 = b; noticeError = error;
  noticeSince = millis(); noticeDuration = duration;
}
bool noticeActive() { return uint32_t(millis() - noticeSince) < noticeDuration; }
String idText(uint16_t id) { char b[12]; snprintf(b, sizeof(b), "ID %03u", id); return String(b); }
void resetUi() {
  ui = Ui::Access; entry = ""; firstPin = ""; pendingId = 0;
  uiTouched = millis();
}
void failEnrollment(const char *message) {
  audit("enroll_failed", 0, "admin", message);
  resetUi(); notice("Cadastro falhou", message, true);
}
bool changeStatus(uint16_t id, bool enabled) {
  if (!exists(id)) return false;
  UserRecord updated = users[id]; updated.active = enabled;
  if (!saveRecord(id, updated)) return false;
  audit(enabled ? "user_enabled" : "user_disabled", id, "admin"); return true;
}
const char *resetPassword(uint16_t id, const String &pin, const char *source, uint64_t token) {
  if (!exists(id)) return "unknown_user";
  // Salvo no MESMO registro que o hash: reenvio após reboot só confirma a aplicação.
  // Reset USB copia/preserva esse token, impedindo reaplicar comando web antigo.
  if (token && users[id].lastWebToken == token) return "ok";
  if (ui != Ui::Access) return "device_busy";
  if (!validPin(pin, 6)) return "invalid_pin";
  uint16_t owner = ownerOfPin(pin);
  if (owner && owner != id) return "pin_in_use";
  UserRecord updated = users[id];
  if (token) updated.lastWebToken = token;
  esp_fill_random(updated.salt, sizeof(updated.salt));
  if (!digest(pin, updated.salt, updated.hash) || !saveRecord(id, updated)) return "storage_error";
  audit("password_reset", id, source);
  return "ok";
}
void authorize(uint16_t id, const char *method) {
  if (!storageReady || !exists(id) || !users[id].active) {
    notice("Acesso negado", "Cadastro inativo", true);
    audit("access_denied", id, method, "inactive_or_unknown"); return;
  }
  if (!door.authorize(id, millis())) {
    notice("Aguarde", "Ciclo em andamento"); return;
  }
  authorizationAt = millis(); accessMethod = method;
  buzzer.reset();
  entry = ""; // uma digital válida também pode substituir uma senha ainda incompleta
  audit("access_granted", id, method);
  // Remover qualquer erro anterior para a indicação verde prevalecer.
  noticeDuration = 0;
}

void beginEnrollment() {
  if (!storageReady || !fingerprintReady) { notice("Indisponivel", "Verifique DY50/NVS", true); return; }
  if (lastId >= MAX_USERS) { notice("Limite atingido", "100 IDs utilizados", true); return; }
  pendingId = lastId + 1;
  firstPin = ""; entry = "";
  // Exigir área livre antes da primeira captura, inclusive se o dedo ficou no leitor.
  ui = Ui::RemoveFinger; enableRequested = false;
}
void confirmEnrollment() {
  if (entry != firstPin) {
    firstPin = ""; entry = ""; ui = Ui::FirstPin;
    notice("Senhas diferentes", "Digite novamente", true); return;
  }
  if (ownerOfPin(entry)) {
    firstPin = ""; entry = ""; ui = Ui::FirstPin;
    notice("Senha ja usada", "Escolha outra", true); return;
  }
  UserRecord record = {}; record.magic = 0xACCE0001; record.active = 1;
  esp_fill_random(record.salt, sizeof(record.salt));
  if (!digest(entry, record.salt, record.hash)) { failEnrollment("Erro de hash"); return; }
  // O DY50 recebe o modelo antes de publicar o cadastro. Modelo órfão não autoriza.
  // Próximo cadastro pode sobrescrever este slot se o NVS não foi confirmado.
  if (finger.storeModel(pendingId) != FINGERPRINT_OK) { failEnrollment("Erro ao gravar DY"); return; }
  if (!saveRecord(pendingId, record)) {
    finger.deleteModel(pendingId); failEnrollment("Erro na memoria"); return;
  }
  const uint16_t id = pendingId;
  audit("user_enrolled", id, "admin"); resetUi();
  waitFingerRemoval = true;
  notice("Pessoa cadastrada", idText(id));
}
void handleKey(char key) {
  if (!key || noticeActive()) return;
  uiTouched = millis();
  if (key == 'D') {
    if (ui != Ui::Access) { resetUi(); notice("Operacao cancelada", ""); }
    else if (door.state == DoorState::Idle) entry = "";
    // D cancela administração/cadastro. Não anuncia cancelamento de um acesso liberado.
    return;
  }
  if (key == '*') { entry = ""; return; }
  if (ui == Ui::Menu) {
    if (key == '1') beginEnrollment();
    if (key == '2' || key == '3') {
      enableRequested = key == '3'; ui = enableRequested ? Ui::EnableId : Ui::DisableId;
      entry = "";
    }
    return;
  }
  if (ui == Ui::ConfirmStatus) {
    if (key == '#') {
      bool ok = changeStatus(pendingId, enableRequested);
      const uint16_t id = pendingId; resetUi();
      notice(ok ? (enableRequested ? "Reativado" : "Desativado") : "Erro na alteracao", idText(id), !ok);
    }
    return;
  }
  if (ui == Ui::FirstFinger || ui == Ui::RemoveFinger || ui == Ui::SecondFinger) return;
  if (key >= '0' && key <= '9') {
    const size_t limit = ui == Ui::Access ? 10 : ((ui == Ui::DisableId || ui == Ui::EnableId) ? 3 : 6);
    if (entry.length() < limit) entry += key;
    return;
  }
  if (key != '#') return;
  if (ui == Ui::Access) {
    if (entry == ADMIN_PIN) {
      if (door.state == DoorState::Idle && door.closed) {
        ui = Ui::Menu; audit("admin_login", 0, "keypad");
      } else notice("Feche a porta", "Aguarde o ciclo", true);
    } else if (validPin(entry, 6)) {
      uint16_t id = ownerOfPin(entry);
      if (id) authorize(id, "password");
      else { notice("Acesso negado", "Senha incorreta", true); audit("access_denied", 0, "password", "invalid_pin"); }
    } else { notice("Entrada invalida", "6 ou 10 digitos", true); }
    entry = "";
  } else if (ui == Ui::FirstPin || ui == Ui::ConfirmPin) {
    if (!validPin(entry, 6)) { entry = ""; notice("Senha invalida", "Use 6 digitos", true); return; }
    if (ui == Ui::FirstPin) { firstPin = entry; entry = ""; ui = Ui::ConfirmPin; }
    else confirmEnrollment();
  } else if (ui == Ui::DisableId || ui == Ui::EnableId) {
    pendingId = entry.toInt(); entry = "";
    if (!exists(pendingId)) { notice("ID inexistente", "Digite novamente", true); return; }
    ui = Ui::ConfirmStatus;
  }
}
void fingerprintTick() {
  if (!fingerprintReady || uint32_t(millis() - lastFingerPoll) < 150 || noticeActive()) return;
  lastFingerPoll = millis();
  if (ui == Ui::Menu || ui == Ui::FirstPin || ui == Ui::ConfirmPin ||
      ui == Ui::DisableId || ui == Ui::EnableId || ui == Ui::ConfirmStatus) return;
  if (ui == Ui::Access && door.state != DoorState::Idle) return;
  uint8_t p = finger.getImage();
  if (ui == Ui::RemoveFinger) {
    if (p == FINGERPRINT_NOFINGER) ui = enableRequested ? Ui::SecondFinger : Ui::FirstFinger;
    else if (p != FINGERPRINT_OK) failEnrollment("Erro de leitura");
    return;
  }
  if (p == FINGERPRINT_NOFINGER) { waitFingerRemoval = false; return; }
  if (p != FINGERPRINT_OK) {
    if (ui != Ui::Access) failEnrollment("Erro de leitura");
    else notice("Falha no leitor", "Tente novamente", true);
    return;
  }
  if (ui == Ui::Access && waitFingerRemoval) return;
  if (finger.image2Tz(ui == Ui::SecondFinger ? 2 : 1) != FINGERPRINT_OK) {
    if (ui != Ui::Access) failEnrollment("Digital ilegivel");
    else { waitFingerRemoval = true; notice("Digital ilegivel", "Retire o dedo", true); }
    return;
  }
  if (ui == Ui::FirstFinger) {
    p = finger.fingerFastSearch();
    if (p == FINGERPRINT_OK) {
      // Somente cadastros publicados bloqueiam duplicidade: slot órfão pode ser refeito.
      if (exists(finger.fingerID)) { failEnrollment("Digital ja usada"); return; }
    } else if (p != FINGERPRINT_NOTFOUND) { failEnrollment("Falha na pesquisa"); return; }
    enableRequested = true; ui = Ui::RemoveFinger; uiTouched = millis();
  } else if (ui == Ui::SecondFinger) {
    if (finger.createModel() != FINGERPRINT_OK) { failEnrollment("Digitais diferem"); return; }
    ui = Ui::FirstPin; entry = ""; uiTouched = millis();
  } else {
    waitFingerRemoval = true;
    p = finger.fingerFastSearch();
    if (p == FINGERPRINT_OK) authorize(finger.fingerID, "fingerprint");
    else {
      notice("Acesso negado", p == FINGERPRINT_NOTFOUND ? "Digital desconhec." : "Erro de leitura", true);
      audit("access_denied", 0, "fingerprint", p == FINGERPRINT_NOTFOUND ? "unknown_finger" : "sensor_error");
    }
  }
}

void rgb(bool r, bool g, bool b) {
  digitalWrite(LED_R, r ^ RGB_COMMON_ANODE);
  digitalWrite(LED_G, g ^ RGB_COMMON_ANODE);
  digitalWrite(LED_B, b ^ RGB_COMMON_ANODE);
}
void outputsTick() {
  uint32_t now = millis();
  bool energized = false;
  if (door.state == DoorState::AwaitOpen) {
    if (LOCK_MODE == 1) energized = uint32_t(now - authorizationAt) < LOCK_PULSE_MS;
    if (LOCK_MODE == 2) energized = true;
  }
  digitalWrite(LOCK_PIN, energized ? LOCK_ON : !LOCK_ON);
  digitalWrite(BUZZER_PIN, buzzer.isOn(now) ? HIGH : LOW);
  if (door.state == DoorState::Alarm) rgb((now / 350) % 2, false, false);
  else if (noticeActive() && noticeError) rgb(true, false, false);
  else if (ui != Ui::Access) rgb(true, false, true);
  else if (door.state == DoorState::Open) { bool on = (now / 600) % 2; rgb(on, on, false); }
  else if (door.state == DoorState::AwaitOpen) rgb(false, true, false);
  else rgb(false, false, now % 60000 < 200);
}
void doorTick() {
  const uint32_t now = millis();
  const bool current = digitalRead(BUTTON_1) == LOW && digitalRead(BUTTON_2) == LOW;
  if (current != rawClosed) { rawClosed = current; rawSince = now; }
  if (uint32_t(now - rawSince) >= 50) stableClosed = rawClosed;
  DoorEvent e = door.tick(stableClosed, now, ENTRY_MS, OPEN_MS);
  buzzer.onEvent(e, now);
  if (e == DoorEvent::None) return;
  if (e == DoorEvent::Opened) audit("door_opened", door.user, accessMethod.c_str());
  if (e == DoorEvent::Closed) {
    audit("door_closed", door.user, accessMethod.c_str());
    notice("Porta fechada", idText(door.user)); entry = "";
  }
  if (e == DoorEvent::EntryExpired) { audit("entry_expired", door.user, accessMethod.c_str()); notice("Tempo esgotado", "Acesso encerrado"); }
  if (e == DoorEvent::OpenTooLong) audit("door_timeout", door.user, accessMethod.c_str());
  if (e == DoorEvent::ForcedOpen) { resetUi(); accessMethod = ""; audit("forced_open", 0, "sensor"); }
}
void displayTick() {
  if (uint32_t(millis() - lastLcd) < 150) return;
  lastLcd = millis();
  String a, b;
  if (door.state == DoorState::Alarm) { a = "Feche a porta"; b = door.user ? idText(door.user) : "Sem autorizacao"; }
  else if (noticeActive()) { a = noticeLine1; b = noticeLine2; }
  else if (ui != Ui::Access) {
    switch (ui) {
      case Ui::Menu: a = "1 Novo 2 Inativar"; b = "3 Reativar D Sair"; break;
      case Ui::RemoveFinger: a = "Cadastrando"; b = "Retire o dedo"; break;
      case Ui::FirstFinger: a = "Cadastrando"; b = "Coloque o dedo"; break;
      case Ui::SecondFinger: a = "Confirme digital"; b = "Mesmo dedo"; break;
      case Ui::FirstPin: a = "Crie senha (6)"; break;
      case Ui::ConfirmPin: a = "Repita senha (6)"; break;
      case Ui::DisableId: a = "Desativar ID:"; b = entry; break;
      case Ui::EnableId: a = "Reativar ID:"; b = entry; break;
      case Ui::ConfirmStatus: a = idText(pendingId) + (enableRequested ? " Reativar?" : " Inativar?"); b = "# Sim  D Cancelar"; break;
      default: break;
    }
    if (ui == Ui::FirstPin || ui == Ui::ConfirmPin) for (size_t i = 0; i < entry.length(); ++i) b += '*';
  } else if (door.state == DoorState::AwaitOpen) { a = "Acesso liberado"; b = idText(door.user); }
  else if (door.state == DoorState::Open) { a = "Porta aberta"; b = idText(door.user); }
  else {
    a = !storageReady ? "Falha memoria" : "Senha ou digital";
    if (entry.length()) for (size_t i = 0; i < entry.length(); ++i) b += '*';
    else b = fingerprintReady ? "# OK * Limpar" : "DY50 indisponivel";
  }
  static String prevA, prevB;
  if (a != prevA || b != prevB) {
    String paddedA = a.substring(0, 16), paddedB = b.substring(0, 16);
    while (paddedA.length() < 16) paddedA += ' ';
    while (paddedB.length() < 16) paddedB += ' ';
    lcd.setCursor(0, 0); lcd.print(paddedA); lcd.setCursor(0, 1); lcd.print(paddedB);
    prevA = a; prevB = b;
  }
}

void serialTick() {
  if (serialAuthed && uint32_t(millis() - serialTouched) > 300000) serialAuthed = false;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c != '\n') {
      if (serialLine.length() < 96 && !serialOverflow) serialLine += c;
      else serialOverflow = true;
      continue;
    }
    String line = serialLine; serialLine = "";
    if (serialOverflow) { serialOverflow = false; Serial.println("ERR line_too_long"); continue; }
    line.trim();
    if (line.startsWith("AUTH ")) {
      serialAuthed = line.substring(5) == ADMIN_PIN;
      serialTouched = millis(); Serial.println(serialAuthed ? "OK authenticated" : "ERR auth");
      continue;
    }
    if (line == "LOGOUT") { serialAuthed = false; Serial.println("OK logout"); continue; }
    if (!serialAuthed) { Serial.println("ERR auth_required"); continue; }
    serialTouched = millis();
    if (line == "STATUS") {
      Serial.printf("last_id=%u wifi=%d queued=%u dropped=%lu lock_mode=%u\n", lastId,
                    WiFi.status() == WL_CONNECTED, (unsigned)uxQueueMessagesWaiting(eventsQueue),
                    (unsigned long)droppedEvents, LOCK_MODE);
    } else if (line == "LIST") {
      for (uint16_t id = 1; id <= lastId; ++id) if (exists(id)) Serial.printf("ID %03u %s\n", id, users[id].active ? "ativo" : "inativo");
    } else if (line.startsWith("RESET ")) {
      unsigned id = 0; char pin[8] = {}, confirmation[8] = {}, extra[2] = {};
      int n = sscanf(line.c_str(), "RESET %u %7s %7s %1s", &id, pin, confirmation, extra);
      if (n != 3 || id > MAX_USERS || strcmp(pin, confirmation)) Serial.println("ERR invalid_or_mismatched");
      else { const char *result = resetPassword(id, String(pin), "usb", 0); Serial.printf("%s %s\n", strcmp(result, "ok") ? "ERR" : "OK", result); }
    } else Serial.println("ERR commands: STATUS | LIST | RESET <id> <6digits> <repeat> | LOGOUT");
  }
}

int httpCall(const char *method, const String &path, const String &body, String &response) {
  WiFiClient client;
  HTTPClient http;
  http.setConnectTimeout(600); http.setTimeout(900);
  if (!http.begin(client, String(SERVER_URL) + path)) return -1;
  http.addHeader("X-Device-Key", DEVICE_KEY);
  http.addHeader("Content-Type", "application/json");
  int code = strcmp(method, "GET") == 0 ? http.GET() : http.POST(body);
  if (code > 0) response = http.getString();
  http.end(); return code;
}
void networkTask(void *) {
  WiFi.mode(WIFI_STA); WiFi.setAutoReconnect(true); WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  uint32_t reconnectAt = millis(), eventAt = 0, commandAt = 0, heartbeatAt = 0;
  bool waitingResult = false, pendingAck = false;
  ResetResult result = {};
  for (;;) {
    uint32_t now = millis();
    if (WiFi.status() != WL_CONNECTED) {
      if (uint32_t(now - reconnectAt) > 15000) { WiFi.reconnect(); reconnectAt = now; }
      vTaskDelay(pdMS_TO_TICKS(100)); continue;
    }
    if (uint32_t(now - eventAt) >= 500) {
      eventAt = now;
      AuditEvent e;
      if (xQueuePeek(eventsQueue, &e, 0) == pdTRUE) {
        JsonDocument doc;
        doc["event_id"] = e.key; doc["device"] = DEVICE_ID; doc["boot_id"] = bootId;
        doc["type"] = e.type; doc["user_id"] = e.user; doc["method"] = e.method;
        doc["reason"] = e.reason; doc["active"] = bool(e.active); doc["uptime_ms"] = e.uptime;
        if (e.epoch) doc["epoch"] = e.epoch; else doc["epoch"] = nullptr;
        String body, response; serializeJson(doc, body);
        int code = httpCall("POST", "/api/device/events", body, response);
        JsonDocument ack;
        if (code == 200 && !deserializeJson(ack, response) && ack["accepted"].as<String>() == e.key) {
          xQueueReceive(eventsQueue, &e, 0);
        } else { vTaskDelay(pdMS_TO_TICKS(2000)); }
      }
    }
    if (waitingResult && xQueueReceive(resultsQueue, &result, 0) == pdTRUE) { pendingAck = true; waitingResult = false; }
    if (uint32_t(now - commandAt) >= 3000) {
      commandAt = now;
      String response;
      if (pendingAck) {
        JsonDocument d; d["device"] = DEVICE_ID; d["command_id"] = result.id;
        d["ok"] = result.ok; d["reason"] = result.reason;
        String body; serializeJson(d, body);
        JsonDocument ack;
        if (httpCall("POST", "/api/device/command-result", body, response) == 200 &&
            !deserializeJson(ack, response) && ack["accepted"].as<int>() == result.id) pendingAck = false;
      } else if (!waitingResult) {
        int code = httpCall("GET", String("/api/device/command?device=") + DEVICE_ID, "", response);
        JsonDocument doc;
        if (code == 200 && !deserializeJson(doc, response) && !doc["command"].isNull()) {
          ResetCommand command = {};
          command.id = doc["command"]["id"].as<int32_t>();
          command.user = doc["command"]["user_id"].as<uint16_t>();
          String pin = doc["command"]["pin"].as<String>();
          String tokenText = doc["command"]["token"].as<String>();
          char *end = nullptr;
          command.token = strtoull(tokenText.c_str(), &end, 16);
          if (command.id > 0 && command.user >= 1 && command.user <= MAX_USERS && validPin(pin, 6) &&
              tokenText.length() == 16 && command.token && end && *end == '\0') {
            strlcpy(command.pin, pin.c_str(), sizeof(command.pin));
            if (xQueueSend(commandsQueue, &command, 0) == pdTRUE) waitingResult = true;
          }
        }
      }
    }
    if (uint32_t(now - heartbeatAt) >= 10000) {
      heartbeatAt = now;
      JsonDocument d; d["device"] = DEVICE_ID; d["boot_id"] = bootId;
      d["clock_synced"] = time(nullptr) >= 1700000000;
      d["queued"] = uxQueueMessagesWaiting(eventsQueue);
      String body, response; serializeJson(d, body);
      httpCall("POST", "/api/device/heartbeat", body, response);
    }
    vTaskDelay(pdMS_TO_TICKS(50));
  }
}

void setup() {
  // Definir latch desligado ANTES de colocar o pino em modo de saída.
  digitalWrite(LOCK_PIN, !LOCK_ON); pinMode(LOCK_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW); pinMode(BUZZER_PIN, OUTPUT);
  Serial.begin(115200); serialLine.reserve(96);
  for (byte i = 0; i < 4; ++i) { rows[i] = ROW_PINS[i]; cols[i] = COL_PINS[i]; }
  pinMode(BUTTON_1, INPUT); pinMode(BUTTON_2, INPUT);
  pinMode(LED_R, OUTPUT); pinMode(LED_G, OUTPUT); pinMode(LED_B, OUTPUT); rgb(false, false, false);
  Wire.begin(I2C_SDA, I2C_SCL); lcd.init(); lcd.backlight();
  lcd.print("Iniciando...");
  snprintf(bootId, sizeof(bootId), "%08lx%08lx", (unsigned long)esp_random(), (unsigned long)esp_random());
  eventsQueue = xQueueCreate(EVENT_QUEUE_SIZE, sizeof(AuditEvent));
  commandsQueue = xQueueCreate(1, sizeof(ResetCommand)); resultsQueue = xQueueCreate(1, sizeof(ResetResult));
  if (!eventsQueue || !commandsQueue || !resultsQueue) {
    lcd.clear(); lcd.print("Erro memoria RAM"); while (true) delay(1000);
  }
  storageReady = prefs.begin("acesso-v1", false);
  if (storageReady) {
    for (uint16_t id = 1; id <= MAX_USERS; ++id) {
      char key[12]; recordKey(id, key);
      if (!prefs.isKey(key)) continue;
      if (prefs.getBytesLength(key) != sizeof(UserRecord) ||
          prefs.getBytes(key, &users[id], sizeof(UserRecord)) != sizeof(UserRecord) ||
          users[id].magic != 0xACCE0001 || users[id].active > 1) {
        storageReady = false; break;
      }
      lastId = id;
    }
  }
  sensorSerial.begin(57600, SERIAL_8N1, FINGER_RX, FINGER_TX);
  finger.begin(57600); // com Stream, aguarda o boot sem reconfigurar RX/TX
  fingerprintReady = finger.verifyPassword() && finger.getParameters() == FINGERPRINT_OK && finger.capacity > MAX_USERS;
  rawClosed = stableClosed = digitalRead(BUTTON_1) == LOW && digitalRead(BUTTON_2) == LOW;
  rawSince = millis(); door.begin(stableClosed, millis()); resetUi();
  audit("device_boot", 0, "system", LOCK_MODE ? "actuator_enabled" : "simulation");
  if (!stableClosed) audit("forced_open", 0, "sensor", "open_at_boot");
  if (!storageReady) audit("storage_error", 0, "system");
  for (uint16_t id = 1; id <= lastId; ++id) if (exists(id)) audit("user_snapshot", id, "system");
  if (xTaskCreate(networkTask, "rede", 10000, nullptr, 1, nullptr) != pdPASS) {
    notice("Rede indisponivel", "Erro tarefa", true, 5000);
  }
  Serial.println("Controle de acesso pronto. AUTH <senha-admin>; monitor 115200, nova linha.");
}
void loop() {
  doorTick(); outputsTick();
  if (ui != Ui::Access && uint32_t(millis() - uiTouched) >= UI_TIMEOUT_MS) {
    resetUi(); notice("Tempo esgotado", "Cadastro cancelado");
  }
  // Não iniciar mutações remotamente no meio de um cadastro biométrico.
  ResetCommand command;
  if (xQueueReceive(commandsQueue, &command, 0) == pdTRUE) {
    const char *reason = resetPassword(command.user, String(command.pin), "web", command.token);
    ResetResult result = {}; result.id = command.id; result.ok = strcmp(reason, "ok") == 0;
    strlcpy(result.reason, reason, sizeof(result.reason)); xQueueSend(resultsQueue, &result, 0);
  }
  handleKey(keypad.getKey()); fingerprintTick(); serialTick();
  doorTick(); outputsTick(); displayTick(); delay(5);
}
