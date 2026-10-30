/* PROTÓTIPO EM DESENVOLVIMENTO: não gravar para operar fechadura. */
#include <Arduino.h>
#include <Wire.h>
#include <EEPROM.h>
#include <SHA256.h>
#include <Adafruit_Fingerprint.h>
#include <Keypad.h>
#include <LiquidCrystal_I2C.h>
#include "Config.h"
#include "UserStore.h"
#include "BootCounter.h"
#include "Dy50ResponseFilter.h"
#include "SerialFrame.h"
#include "MessageProtocol.h"
#include "DoorLogic.h"
#include "BuzzerLogic.h"
struct UserRecord { uint8_t active, salt[4], hash[16]; uint64_t lastWebToken; };
bool storageReady = false, fingerprintReady = false;
bool lcdReady = true;
uint16_t lastId = 0;
uint32_t bootNumber = 0, eventSequence = 0, droppedEvents = 0;
void doorTick();
void outputsTick();
void linkTick(bool sensorWait);
bool doorServiceReady = false;
// A biblioteca do DY50 pode aguardar UART por até um segundo; continuar
// atendendo a porta durante a espera em vez de bloquear seus temporizadores.
class ServicedFingerStream : public Stream {
 public:
  int available() override {
    if (doorServiceReady) { doorTick(); outputsTick(); linkTick(true); }
    // A biblioteca não confere checksum nem tamanho da resposta. Só liberar
    // ao parser dela um pacote ACK completo e verificado.
    for (uint8_t i = 0; i < 64 && Serial1.available() && !filter.available(); ++i)
      filter.feed(uint8_t(Serial1.read()));
    return filter.available();
  }
  int read() override { return filter.read(); }
  int peek() override { return filter.peek(); }
  void flush() override { Serial1.flush(); }
  size_t write(uint8_t value) override {
    // Cada chamada de biblioteca envia um quadro; descartar bytes antigos antes
    // do próximo comando e registrar seu código para validar o tamanho do ACK.
    if (!txCount) {
      while (Serial1.available()) Serial1.read();
      filter.begin(0); txLength = txTotal = 0;
    }
    if (txCount == 7) txLength = uint16_t(value) << 8;
    if (txCount == 8) { txLength |= value; txTotal = 9 + txLength; }
    if (txCount == 9) filter.begin(value);
    size_t written = Serial1.write(value);
    ++txCount;
    if (txTotal && txCount >= txTotal) txCount = 0;
    return written;
  }
  using Print::write;
 private:
  Dy50ResponseFilter filter;
  uint8_t txCount = 0;
  uint16_t txLength = 0, txTotal = 0;
};
ServicedFingerStream fingerStream;
Adafruit_Fingerprint finger(static_cast<Stream *>(&fingerStream));
LiquidCrystal_I2C lcd(LCD_ADDRESS, 16, 2);
char keys[4][4] = {{'1','2','3','A'}, {'4','5','6','B'}, {'7','8','9','C'}, {'*','0','#','D'}};
byte rows[4], cols[4];
Keypad keypad(makeKeymap(keys), rows, cols, 4, 4);
DoorLogic door; BuzzerLogic buzzer;
void queueEvent(const char *, uint16_t, const char *, const char *);
enum class Ui { Access, Menu, FirstFinger, RemoveFinger, SecondFinger,
                FirstPin, ConfirmPin, DisableId, EnableId, ConfirmStatus };
Ui ui = Ui::Access;
String entry, firstPin;
uint32_t entryTouched = 0;
uint16_t pendingId = 0;
bool enableRequested = false, waitFingerRemoval = false, noticeError = false;
String noticeLine1, noticeLine2, accessMethod;
uint32_t noticeSince = 0, noticeDuration = 0, uiTouched = 0;
uint32_t lastFingerPoll = 0, lastLcd = 0, authorizationAt = 0;
uint32_t doorGeneration = 0;
bool rawClosed = false, stableClosed = false;
uint32_t rawSince = 0;
bool serialAuthed = false, serialOverflow = false;
uint32_t serialTouched = 0;
String serialLine;
String lcdPrevA, lcdPrevB;
uint32_t lastFingerRecovery = 0, lastLcdRecovery = 0;

bool validPin(const String &pin, size_t length) {
  if (pin.length() != length) return false;
  for (size_t i = 0; i < length; ++i) if (pin[i] < '0' || pin[i] > '9') return false;
  return true;
}
// Arquivos são lidos sob demanda para caber na SRAM do Mega.
bool readRecord(uint16_t id, UserRecord &record) {
  if (id < 1 || id > MAX_USERS) return false;
  UserStore::Record raw;
  int8_t status = UserStore::load(EEPROM, id, raw);
  if (status < 0) storageReady = false;
  if (status != 1) return false;
  record.active = raw.bytes[0] == 1;
  memcpy(record.salt, raw.bytes + 1, 4); memcpy(record.hash, raw.bytes + 5, 16);
  memcpy(&record.lastWebToken, raw.bytes + 21, 8);
  return true;
}
bool exists(uint16_t id) { UserRecord record; return readRecord(id, record); }
bool activeUser(uint16_t id) { UserRecord record; return readRecord(id, record) && record.active; }
bool digest(const String &pin, const uint8_t *salt, uint8_t *out) {
  SHA256 sha; sha.reset(); sha.update(salt, 4); sha.update(pin.c_str(), 6);
  sha.finalize(out, 16); return true;
}
bool matches(uint16_t id, const String &pin) {
  UserRecord record; uint8_t hash[16];
  return validPin(pin, 6) && readRecord(id, record) && digest(pin, record.salt, hash)
      && memcmp(hash, record.hash, sizeof(hash)) == 0;
}
void linkTick(bool sensorWait);
uint16_t ownerOfPin(const String &pin) {
  for (uint16_t id = 1; id <= MAX_USERS; ++id) {
    // A busca de 100 hashes leva tempo no AVR. Continuar a atender a porta
    // entre registros; se ela abrir, abortar a operação em andamento.
    doorTick(); outputsTick(); linkTick(true);
    if (!storageReady) return MAX_USERS + 2;
    if (door.state != DoorState::Idle || !door.closed) return MAX_USERS + 1;
    bool match = matches(id, pin);
    doorTick(); outputsTick(); linkTick(true);
    if (!storageReady) return MAX_USERS + 2;
    if (door.state != DoorState::Idle || !door.closed) return MAX_USERS + 1;
    if (match) return id;
  }
  return 0;
}
// Cada escrita EEPROM pode levar milissegundos na placa real. Atender a porta
// entre bytes sem interromper o journal, inclusive se a porta for aberta.
struct ServicedEeprom {
  uint8_t read(uint16_t address) { return EEPROM.read(address); }
  void update(uint16_t address, uint8_t value) {
    EEPROM.update(address, value); doorTick(); outputsTick(); linkTick(true);
  }
};
bool saveRecord(uint16_t id, const UserRecord &record) {
  if (!storageReady || id < 1 || id > MAX_USERS) return false;
  UserStore::Record raw = {}; raw.bytes[0] = record.active ? 1 : 2;
  memcpy(raw.bytes + 1, record.salt, 4); memcpy(raw.bytes + 5, record.hash, 16);
  memcpy(raw.bytes + 21, &record.lastWebToken, 8);
  ServicedEeprom storage;
  if (!UserStore::save(storage, id, raw)) { storageReady = false; return false; }
  if (id > lastId) lastId = id; return true;
}
// Salt de separação, não é fonte de entropia criptográfica: PINs de 6 dígitos
// continuam vulneráveis a ataque offline com acesso à EEPROM.
void fillSalt(uint8_t *salt, uint16_t id) {
  uint32_t n = bootNumber ^ (uint32_t(id) << 24) ^ millis();
  for (uint8_t i = 0; i < 4; ++i) salt[i] = uint8_t(n >> (8 * i));
}
void audit(const char *type, uint16_t id = 0, const char *method = "", const char *reason = "") {
  queueEvent(type, id, method, reason);
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
  UserRecord updated; if (!readRecord(id, updated)) return false; updated.active = enabled;
  if (!saveRecord(id, updated)) return false;
  audit(enabled ? "user_enabled" : "user_disabled", id, "admin"); return true;
}
const char *resetPassword(uint16_t id, const String &pin, const char *source, uint64_t token) {
  if (!exists(id)) return "unknown_user";
  // Salvo no MESMO registro que o hash: reenvio após reboot só confirma a aplicação.
  // Reset USB copia/preserva esse token, impedindo reaplicar comando web antigo.
  UserRecord current; if (!readRecord(id, current)) return "storage_error";
  if (token && current.lastWebToken == token) return "ok";
  if (ui != Ui::Access || door.state != DoorState::Idle || !door.closed) return "device_busy";
  if (!validPin(pin, 6)) return "invalid_pin";
  uint16_t owner = ownerOfPin(pin);
  if (owner == MAX_USERS + 2) return "storage_error";
  if (owner > MAX_USERS) return "device_busy";
  if (owner && owner != id) return "pin_in_use";
  UserRecord updated = current;
  if (token) updated.lastWebToken = token;
  fillSalt(updated.salt, id);
  if (!digest(pin, updated.salt, updated.hash) || !saveRecord(id, updated)) return "storage_error";
  audit("password_reset", id, source);
  return "ok";
}
void authorize(uint16_t id, const char *method) {
  if (!storageReady || !exists(id) || !activeUser(id)) {
    notice("Acesso negado", "Cadastro inativo", true);
    audit("access_denied", id, method, "inactive_or_unknown"); return;
  }
  const uint32_t authorizedAt = millis();
  if (!door.authorize(id, authorizedAt)) {
    notice("Aguarde", "Ciclo em andamento"); return;
  }
  authorizationAt = authorizedAt; accessMethod = method;
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
  uint16_t owner = ownerOfPin(entry);
  if (owner > MAX_USERS) return;
  if (owner) {
    firstPin = ""; entry = ""; ui = Ui::FirstPin;
    notice("Senha ja usada", "Escolha outra", true); return;
  }
  UserRecord record = {}; record.active = 1;
  const uint16_t enrollmentId = pendingId;
  const uint32_t generation = doorGeneration;
  const Ui enrollmentUi = ui;
  fillSalt(record.salt, enrollmentId);
  if (!digest(entry, record.salt, record.hash)) { failEnrollment("Erro de hash"); return; }
  // O DY50 recebe o modelo antes de publicar o cadastro. Modelo órfão não autoriza.
  // Próximo cadastro pode sobrescrever este slot se o NVS não foi confirmado.
  uint8_t stored = finger.storeModel(enrollmentId);
  if (stored == FINGERPRINT_PACKETRECIEVEERR) fingerprintReady = false;
  if (doorGeneration != generation || ui != enrollmentUi || door.state != DoorState::Idle || !door.closed) {
    if (stored == FINGERPRINT_OK && finger.deleteModel(enrollmentId) == FINGERPRINT_PACKETRECIEVEERR) fingerprintReady = false;
    waitFingerRemoval = true;
    return;
  }
  if (stored != FINGERPRINT_OK) {
    failEnrollment("Erro ao gravar DY"); return;
  }
  if (!saveRecord(enrollmentId, record)) {
    if (finger.deleteModel(enrollmentId) == FINGERPRINT_PACKETRECIEVEERR) fingerprintReady = false;
    failEnrollment("Erro na memoria"); return;
  }
  const uint16_t id = enrollmentId;
  audit("user_enrolled", id, "admin"); resetUi();
  waitFingerRemoval = true;
  if (doorGeneration == generation && door.state == DoorState::Idle) notice("Pessoa cadastrada", idText(id));
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
      const uint16_t id = pendingId; const bool enabling = enableRequested;
      const uint32_t generation = doorGeneration;
      bool ok = changeStatus(id, enabling);
      resetUi();
      if (generation == doorGeneration && door.state == DoorState::Idle)
        notice(ok ? (enabling ? "Reativado" : "Desativado") : "Erro na alteracao", idText(id), !ok);
    }
    return;
  }
  if (ui == Ui::FirstFinger || ui == Ui::RemoveFinger || ui == Ui::SecondFinger) return;
  if (key >= '0' && key <= '9') {
    const size_t limit = ui == Ui::Access ? 10 : ((ui == Ui::DisableId || ui == Ui::EnableId) ? 3 : 6);
    if (entry.length() < limit) { entry += key; if (ui == Ui::Access) entryTouched = millis(); }
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
      if (id > MAX_USERS) { entry = ""; return; }
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
// Senha parcial no teclado expira após 30 s sem tecla; sem aviso nem evento.
void expireEntry() {
  if (ui == Ui::Access && entry.length() && uint32_t(millis() - entryTouched) >= 30000) entry = "";
}
void fingerprintTick() {
  if (!fingerprintReady || uint32_t(millis() - lastFingerPoll) < 150 || noticeActive()) return;
  lastFingerPoll = millis();
  if (ui == Ui::Menu || ui == Ui::FirstPin || ui == Ui::ConfirmPin ||
      ui == Ui::DisableId || ui == Ui::EnableId || ui == Ui::ConfirmStatus) return;
  if (door.state != DoorState::Idle || !door.closed) return;
  const Ui startedUi = ui;
  const uint32_t generation = doorGeneration;
  uint8_t p = finger.getImage();
  if (p == FINGERPRINT_PACKETRECIEVEERR) fingerprintReady = false;
  if (ui != startedUi || doorGeneration != generation || door.state != DoorState::Idle || !door.closed) { waitFingerRemoval = true; return; }
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
  p = finger.image2Tz(ui == Ui::SecondFinger ? 2 : 1);
  if (p == FINGERPRINT_PACKETRECIEVEERR) fingerprintReady = false;
  if (ui != startedUi || doorGeneration != generation || door.state != DoorState::Idle || !door.closed) { waitFingerRemoval = true; return; }
  if (p != FINGERPRINT_OK) {
    if (ui != Ui::Access) failEnrollment("Digital ilegivel");
    else { waitFingerRemoval = true; notice("Digital ilegivel", "Retire o dedo", true); }
    return;
  }
  if (ui == Ui::FirstFinger) {
    p = finger.fingerFastSearch();
    if (p == FINGERPRINT_PACKETRECIEVEERR) fingerprintReady = false;
    if (ui != startedUi || doorGeneration != generation || door.state != DoorState::Idle || !door.closed) { waitFingerRemoval = true; return; }
    if (p == FINGERPRINT_OK) {
      // Uma correspondência órfã pode ocultar outra digital existente; não
      // presumir que a credencial seja única nem apagar modelos existentes.
      if (exists(finger.fingerID)) failEnrollment("Digital ja usada");
      else failEnrollment("Slot DY orfao");
      return;
    } else if (p != FINGERPRINT_NOTFOUND) { failEnrollment("Falha na pesquisa"); return; }
    enableRequested = true; ui = Ui::RemoveFinger; uiTouched = millis();
  } else if (ui == Ui::SecondFinger) {
    p = finger.createModel();
    if (p == FINGERPRINT_PACKETRECIEVEERR) fingerprintReady = false;
    if (ui != startedUi || doorGeneration != generation || door.state != DoorState::Idle || !door.closed) { waitFingerRemoval = true; return; }
    if (p != FINGERPRINT_OK) { failEnrollment("Digitais diferem"); return; }
    ui = Ui::FirstPin; entry = ""; uiTouched = millis();
  } else {
    waitFingerRemoval = true;
    p = finger.fingerFastSearch();
    if (p == FINGERPRINT_PACKETRECIEVEERR) fingerprintReady = false;
    if (ui != startedUi || doorGeneration != generation || door.state != DoorState::Idle || !door.closed) return;
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
  if (e == DoorEvent::ForcedOpen) { ++doorGeneration; resetUi(); accessMethod = ""; audit("forced_open", 0, "sensor"); }
}
// Religa o DY50 a cada 10 s, só com a tela de acesso livre, porta fechada e teclado vazio.
// verifyPassword bloqueia ~1 s sem varrer o teclado.
void fingerprintRecoveryTick() {
  if (fingerprintReady || uint32_t(millis() - lastFingerRecovery) < 10000) return;
  if (ui != Ui::Access || door.state != DoorState::Idle || !door.closed || noticeActive() || entry.length()) return;
  lastFingerRecovery = millis();
  fingerprintReady = finger.verifyPassword() && finger.getParameters() == FINGERPRINT_OK && finger.capacity > MAX_USERS;
}
// Após timeout I2C, tenta religar o LCD a cada 30 s e força o redesenho completo.
// lcd.init() bloqueia ~1 s: só tentar com a mesma segurança do DY50 e sem buzzer ativo.
void lcdRecoveryTick() {
  if (lcdReady || uint32_t(millis() - lastLcdRecovery) < 30000) return;
  if (ui != Ui::Access || door.state != DoorState::Idle || !door.closed || buzzer.isOn(millis()) || noticeActive() || entry.length()) return;
  lastLcdRecovery = millis();
  // Sonda antes do init: LCD ausente (NACK) ou barramento com timeout não conta como religado.
  Wire.clearWireTimeoutFlag(); Wire.beginTransmission(LCD_ADDRESS);
  const bool present = Wire.endTransmission() == 0 && !Wire.getWireTimeoutFlag();
  if (!present) return;
  doorTick(); outputsTick();
  lcd.init();
  doorTick(); outputsTick();
  if (!Wire.getWireTimeoutFlag()) { lcd.backlight(); lcdReady = !Wire.getWireTimeoutFlag(); }
  if (lcdReady) { lcdPrevA = ""; lcdPrevB = ""; }
}
void displayTick() {
  if (!lcdReady) return;
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
  if (a != lcdPrevA || b != lcdPrevB) {
    String paddedA = a.substring(0, 16), paddedB = b.substring(0, 16);
    while (paddedA.length() < 16) paddedA += ' ';
    while (paddedB.length() < 16) paddedB += ' ';
    Wire.clearWireTimeoutFlag();
    lcd.setCursor(0, 0);
    if (Wire.getWireTimeoutFlag()) { lcdReady = false; return; }
    for (size_t i = 0; i < paddedA.length(); ++i) {
      doorTick(); outputsTick(); linkTick(true);
      lcd.write(uint8_t(paddedA[i]));
      if (Wire.getWireTimeoutFlag()) { lcdReady = false; return; }
    }
    lcd.setCursor(0, 1);
    if (Wire.getWireTimeoutFlag()) { lcdReady = false; return; }
    for (size_t i = 0; i < paddedB.length(); ++i) {
      doorTick(); outputsTick(); linkTick(true);
      lcd.write(uint8_t(paddedB[i]));
      if (Wire.getWireTimeoutFlag()) { lcdReady = false; return; }
    }
    lcdPrevA = a; lcdPrevB = b;
  }
}


// Lista circular pequena em RAM; confirmação UART significa somente que a CAM aceitou o evento.
MessageProtocol::EventData outbound[16];
bool photoFresh[16] = {};
uint8_t head = 0, count = 0; uint32_t transmitAt = 0, syncEpoch = 0, syncAt = 0;
SerialFrame::Parser receiver;
const char * const eventNames[] = {"", "device_boot", "storage_error", "user_snapshot", "user_enrolled", "user_disabled", "user_enabled", "password_reset", "admin_login", "access_granted", "access_denied", "door_opened", "door_closed", "entry_expired", "door_timeout", "forced_open", "enroll_failed"};
const char * const methodNames[] = {"", "password", "fingerprint", "admin", "keypad", "system", "sensor", "usb", "web"};
const char * const reasonNames[] = {"", "inactive_or_unknown", "invalid_pin", "unknown_finger", "sensor_error", "simulation", "actuator_enabled", "open_at_boot", "Erro de hash", "Erro ao gravar DY", "Erro na memoria", "Erro de leitura", "Digital ilegivel", "Digital ja usada", "Slot DY orfao", "Falha na pesquisa", "Digitais diferem"};
uint8_t nameIndex(const char *name, const char * const *names, uint8_t length) {
  for (uint8_t i = 0; i < length; ++i) if (!strcmp(name, names[i])) return i;
  return 0;
}
void queueEvent(const char *type, uint16_t id, const char *method, const char *reason) {
  uint8_t kind = nameIndex(type, eventNames, 17);
  if (!kind || !bootNumber || eventSequence == 0xffffffffUL || count == 16) { ++droppedEvents; return; }
  MessageProtocol::EventData e = {};
  e.messageId = ++eventSequence; e.boot = bootNumber;
  e.uptime = kind == MessageProtocol::AccessGranted ? authorizationAt : millis();
  e.epoch = syncEpoch ? syncEpoch + uint32_t(e.uptime - syncAt) / 1000 : 0;
  e.kind = kind; e.user = id <= 100 ? uint8_t(id) : 0; e.method = nameIndex(method, methodNames, 9);
  e.active = activeUser(id); e.reason = nameIndex(reason, reasonNames, 17);
  uint8_t slot = (head + count) % 16;
  outbound[slot] = e; photoFresh[slot] = kind == MessageProtocol::AccessGranted; ++count;
}
// Um quadro pendente preserva sua ordem sem aguardar espaço na UART.
constexpr uint16_t LINK_TX_MAX = 2 * (SerialFrame::kMaxBody + 2) + 2;
struct LinkTx {
  uint8_t bytes[LINK_TX_MAX]; uint16_t length = 0, position = 0;
  void write(uint8_t value) { bytes[length++] = value; }
  bool pending() const { return position < length; }
  bool begin(const uint8_t *body, uint16_t size) {
    if (pending()) return false;
    length = position = 0;
    return SerialFrame::send(*this, body, size);
  }
  void tick() {
    for (uint8_t sent = 0; sent < 64 && pending() && Serial2.availableForWrite(); ++sent) {
      doorTick(); outputsTick(); Serial2.write(bytes[position++]);
    }
    if (!pending()) length = position = 0;
  }
} linkTx;
// Respostas aguardam o quadro corrente; comandos sem espaço não são aplicados.
struct LinkReply { uint8_t body[26], size; uint32_t photoAt; bool deferredReset; };
LinkReply linkReplies[4];
uint8_t replyHead = 0, replyCount = 0;
uint32_t droppedReplies = 0;
void queueLinkReply(const uint8_t *body, uint8_t size, uint32_t photoAt = 0, bool deferredReset = false) {
  LinkReply &reply = linkReplies[(replyHead + replyCount) % 4];
  memcpy(reply.body, body, size); reply.size = size; reply.photoAt = photoAt; reply.deferredReset = deferredReset; ++replyCount;
}
bool linkBusy = false;
// Bytes lidos da UART durante reset/busca (linkBusy): guardados sem parsear e processados antes dos novos.
uint8_t linkStash[128]; uint8_t linkStashLen = 0;
void linkTickBody(bool sensorWait) {
  using namespace MessageProtocol;
  for (uint8_t i = 0; i < count; ++i) {
    uint8_t slot = (head + i) % 16;
    if (photoFresh[slot] && uint32_t(millis() - outbound[slot].uptime) > 5000) photoFresh[slot] = false;
  }
  linkTx.tick();
  // Primeiro os bytes guardados durante um reset, depois a UART; o limite de 64 vale para os dois.
  uint8_t stashRead = 0;
  for (uint8_t received = 0; received < 64 && (stashRead < linkStashLen || Serial2.available()); ++received) {
    doorTick(); outputsTick();
    uint8_t in;
    if (stashRead < linkStashLen) in = linkStash[stashRead++];
    else if (Serial2.available()) in = uint8_t(Serial2.read());
    else break;
    if (!receiver.feed(in, millis())) continue;
    const uint8_t *p = receiver.data(); uint16_t n = receiver.size();
    if (n == 26 && p[1] == PhotoChallenge && count &&
        get32(p+2) == outbound[head].messageId && get32(p+6) == bootNumber &&
        outbound[head].kind == AccessGranted && photoFresh[head]) {
      const uint32_t age = uint32_t(millis() - outbound[head].uptime);
      if (age <= 5000) {
        uint8_t proof[26]; memcpy(proof, p, sizeof proof); proof[1] = PhotoProof;
        if (replyCount < 4) queueLinkReply(proof, sizeof proof, outbound[head].uptime);
        else ++droppedReplies;
      } else photoFresh[head] = false;
    } else if (n == 10 && p[1] == Ack && count && get32(p+2) == outbound[head].messageId && get32(p+6) == bootNumber) {
      head = (head + 1) % 16; --count; transmitAt = 0;
    } else if (n == 10 && p[1] == Clock) {
      uint32_t epoch = get32(p+6);
      if (epoch >= 1700000000UL && epoch <= 4102444800UL) { syncEpoch = epoch; syncAt = millis(); }
    } else if (n == 21 && p[1] == Reset) {
      // Reenvios idênticos enquanto o comando aguarda ocupam apenas uma vaga.
      bool duplicate = false;
      for (uint8_t i = 0; i < replyCount; ++i) {
        LinkReply &queued = linkReplies[(replyHead + i) % 4];
        if (queued.deferredReset && !memcmp(queued.body, p, n)) { duplicate = true; break; }
      }
      if (duplicate) continue;
      if (replyCount == 4) { ++droppedReplies; continue; }
      // Reservar a resposta antes de aplicar; durante DY50 não reentrar no
      // armazenamento nem produzir uma rejeição terminal por espera transitória.
      queueLinkReply(p, n, 0, true);
    }
  }
  if (stashRead) {
    linkStashLen -= stashRead;
    memmove(linkStash, linkStash + stashRead, linkStashLen);
  }
  // Uma prova expirada nunca inicia transmissão; o envio já iniciado permanece íntegro.
  while (!linkTx.pending() && replyCount) {
    // Durante a espera, uma prova pode ultrapassar resets ainda não executados.
    // A ordem dos demais itens permanece inalterada e um quadro iniciado é atômico.
    uint8_t offset = 0;
    if (sensorWait) {
      while (offset < replyCount && linkReplies[(replyHead + offset) % 4].deferredReset) ++offset;
      if (offset == replyCount) break;
    }
    uint8_t slot = (replyHead + offset) % 4;
    LinkReply &reply = linkReplies[slot];
    if (reply.deferredReset) {
      uint32_t cmd = get32(reply.body+2); uint8_t id = reply.body[6];
      char pin[7]; memcpy(pin, reply.body+7, 6); pin[6] = 0;
      uint64_t token = 0; for (uint8_t i=0; i<8; ++i) token |= uint64_t(reply.body[13+i]) << (8*i);
      const char *result = !cmd || !token ? "invalid_pin" : resetPassword(id, String(pin), "web", token);
      uint8_t response[8] = {kVersion, ResetResult, 0,0,0,0, 0,0}; put32(response+2, cmd);
      response[6] = !strcmp(result, "ok");
      const char * const reasons[] = {"ok", "unknown_user", "device_busy", "invalid_pin", "pin_in_use", "storage_error"};
      response[7] = nameIndex(result, reasons, 6);
      memcpy(reply.body, response, sizeof response); reply.size = sizeof response; reply.deferredReset = false;
    }
    bool fresh = reply.body[1] != PhotoProof || uint32_t(millis() - reply.photoAt) <= 5000;
    if (fresh) linkTx.begin(reply.body, reply.size);
    else ++droppedReplies;
    for (uint8_t i = offset; i + 1 < replyCount; ++i)
      linkReplies[(replyHead + i) % 4] = linkReplies[(replyHead + i + 1) % 4];
    --replyCount;
  }
  if (!linkTx.pending() && count && (!transmitAt || uint32_t(millis() - transmitAt) >= 1000)) {
    uint8_t bytes[kEventLength];
    outbound[head].sentUptime = millis();
    if (encodeEvent(outbound[head], bytes, sizeof bytes)) { linkTx.begin(bytes, sizeof bytes); transmitAt = millis() ? millis() : 1; }
    else { head = (head + 1) % 16; --count; ++droppedEvents; transmitAt = 0; }
  }
  linkTx.tick();
}
// Reset/busca chamados de dentro do enlace (resetPassword -> ownerOfPin) não reentram:
// só copiam a UART para linkStash, sem parsear; o processamento fica para a chamada seguinte.
void linkTick(bool sensorWait = false) {
  if (linkBusy) {
    while (linkStashLen < sizeof linkStash && Serial2.available()) linkStash[linkStashLen++] = uint8_t(Serial2.read());
    return;
  }
  linkBusy = true; linkTickBody(sensorWait); linkBusy = false;
}

void serialTick() {
  if (serialAuthed && uint32_t(millis() - serialTouched) > 300000) serialAuthed = false;
  while (Serial.available()) {
    doorTick(); outputsTick();
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
      Serial.print("last_id="); Serial.print(lastId); Serial.print(" queued="); Serial.print(count);
      Serial.print(" dropped="); Serial.print(droppedEvents); Serial.print(" replies_dropped="); Serial.print(droppedReplies); Serial.print(" lcd="); Serial.print(lcdReady ? "ok" : "timeout");
      Serial.print(F(" dy50=")); Serial.print(fingerprintReady ? F("ok") : F("indisponivel"));
      Serial.print(" lock_mode="); Serial.println(LOCK_MODE);
    } else if (line == "LIST") {
      for (uint16_t id = 1; id <= lastId; ++id) {
        doorTick(); outputsTick();
        if (exists(id)) { Serial.print("ID "); Serial.print(id); Serial.println(activeUser(id) ? " ativo" : " inativo"); }
      }
    } else if (line.startsWith("RESET ")) {
      unsigned id = 0; char pin[8] = {}, confirmation[8] = {}, extra[2] = {};
      int n = sscanf(line.c_str(), "RESET %u %7s %7s %1s", &id, pin, confirmation, extra);
      if (n != 3 || id > MAX_USERS || strcmp(pin, confirmation)) Serial.println("ERR invalid_or_mismatched");
      else { const char *result = resetPassword(id, String(pin), "usb", 0); Serial.print(strcmp(result, "ok") ? "ERR " : "OK "); Serial.println(result); }
    } else Serial.println("ERR commands: STATUS | LIST | RESET <id> <6digits> <repeat> | LOGOUT");
  }
}


void setup() {
  digitalWrite(LOCK_PIN, !LOCK_ON); pinMode(LOCK_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW); pinMode(BUZZER_PIN, OUTPUT);
  Serial.begin(115200); Serial1.begin(57600); Serial2.begin(38400);
  for (byte i = 0; i < 4; ++i) { rows[i] = ROW_PINS[i]; cols[i] = COL_PINS[i]; }
  pinMode(BUTTON_1, INPUT_PULLUP); pinMode(BUTTON_2, INPUT_PULLUP);
  pinMode(LED_R, OUTPUT); pinMode(LED_G, OUTPUT); pinMode(LED_B, OUTPUT); rgb(false, false, false);
  Wire.begin(); Wire.setWireTimeout(10000, true); Wire.clearWireTimeoutFlag();
  lcd.init();
  if (!Wire.getWireTimeoutFlag()) lcd.backlight();
  lcdReady = !Wire.getWireTimeoutFlag();
  if (lcdReady) {
    lcd.print("Iniciando...");
    lcdReady = !Wire.getWireTimeoutFlag();
  }
  // BootCounter usa região própria da EEPROM (após o journal) e não depende de recover.
  const bool usersRecovered = UserStore::recover(EEPROM);
  const bool bootCounted = BootCounter::next(EEPROM, bootNumber);
  storageReady = usersRecovered && bootCounted;
  for (uint16_t id = 1; storageReady && id <= MAX_USERS; ++id) {
    UserStore::Record record; int8_t state = UserStore::load(EEPROM, id, record);
    if (state < 0) storageReady = false; else if (state == 1) lastId = id;
  }
  finger.begin(57600);
  fingerprintReady = finger.verifyPassword() && finger.getParameters() == FINGERPRINT_OK && finger.capacity > MAX_USERS;
  rawClosed = stableClosed = digitalRead(BUTTON_1) == LOW && digitalRead(BUTTON_2) == LOW;
  rawSince = millis(); door.begin(stableClosed, millis()); resetUi(); doorServiceReady = true;
  audit("device_boot", 0, "system", LOCK_MODE ? "actuator_enabled" : "simulation");
  if (!stableClosed) audit("forced_open", 0, "sensor", "open_at_boot");
  if (!storageReady) audit("storage_error", 0, "system");
  // Diagnóstico de bancada, sem segredos: uma linha por boot.
  Serial.print(F("BOOT boot=")); Serial.print(bootNumber);
  Serial.print(F(" storage=")); Serial.print(storageReady ? F("ok") : F("falha"));
  Serial.print(F(" lcd=")); Serial.print(lcdReady ? F("ok") : F("timeout"));
  Serial.print(F(" dy50=")); Serial.print(fingerprintReady ? F("ok") : F("indisponivel"));
  Serial.print(F(" lock_mode=")); Serial.println(LOCK_MODE);
}
void loop() {
  doorTick(); outputsTick();
  if (ui != Ui::Access && uint32_t(millis() - uiTouched) >= UI_TIMEOUT_MS) {
    resetUi(); notice("Tempo esgotado", "Cadastro cancelado");
  }
  expireEntry();
  handleKey(keypad.getKey()); fingerprintTick(); fingerprintRecoveryTick(); linkTick(); serialTick();
  static uint16_t snapshot = 1;
  if (snapshot <= lastId && count == 0) {
    if (exists(snapshot)) audit("user_snapshot", snapshot, "system");
    ++snapshot;
  }
  doorTick(); outputsTick(); lcdRecoveryTick(); displayTick(); delay(5);
}
