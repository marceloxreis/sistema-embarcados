/* PROTÓTIPO EM DESENVOLVIMENTO: não gravar para operar fechadura. */
#include <Arduino.h>
#include <EEPROM.h>
#include <SHA256.h>
#include <Adafruit_Fingerprint.h>
#include <Keypad.h>
#include <SPI.h>
#include <MFRC522.h>
#include "Config.h"
#include <LiquidCrystal.h>
#ifndef LCD_PIN_RS
#define LCD_PIN_RS 37
#endif
#ifndef LCD_PIN_E
#define LCD_PIN_E 38
#endif
#ifndef LCD_PIN_D4
#define LCD_PIN_D4 39
#endif
#ifndef LCD_PIN_D5
#define LCD_PIN_D5 40
#endif
#ifndef LCD_PIN_D6
#define LCD_PIN_D6 41
#endif
#ifndef LCD_PIN_D7
#define LCD_PIN_D7 42
#endif
// RC522 (SPI): no Mega, SS=D53 e RST=D49 (SPI em D50-D52). Config.h pode trocar com #define.
#ifndef RFID_SS_PIN
#define RFID_SS_PIN 53
#endif
#ifndef RFID_RST_PIN
#define RFID_RST_PIN 49
#endif
// Espelho do LCD na serial USB (linhas "LCD| ..."); desligue com LCD_SERIAL_MIRROR 0 em Config.h.
#ifndef LCD_SERIAL_MIRROR
#define LCD_SERIAL_MIRROR 1
#endif
#ifndef SHOW_TYPED_DIGITS
#define SHOW_TYPED_DIGITS 0  // 1 = espelho da serial mostra os dígitos digitados (o LCD continua com *); só para bancada
#endif
#include "UserStore.h"
#include "BootCounter.h"
#include "CardStore.h"
#include "Dy50ResponseFilter.h"
#include "SerialFrame.h"
#include "MessageProtocol.h"
#include "DoorLogic.h"
#include "BuzzerLogic.h"
struct UserRecord { uint8_t active, salt[4], hash[16]; uint64_t lastWebToken; };
bool storageReady = false, fingerprintReady = false;
uint16_t lastId = 0;
uint32_t bootNumber = 0, eventSequence = 0, droppedEvents = 0;
void doorTick();
void outputsTick();
void linkTick(bool sensorWait);
void readerResetTick();
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
LiquidCrystal lcd(LCD_PIN_RS, LCD_PIN_E, LCD_PIN_D4, LCD_PIN_D5, LCD_PIN_D6, LCD_PIN_D7);
MFRC522 rfid(RFID_SS_PIN, RFID_RST_PIN);
char keys[4][4] = {{'1','2','3','A'}, {'4','5','6','B'}, {'7','8','9','C'}, {'*','0','#','D'}};
byte rows[4], cols[4];
Keypad keypad(makeKeymap(keys), rows, cols, 4, 4);
DoorLogic door; BuzzerLogic buzzer;
void queueEvent(const char *, uint16_t, const char *, const char *);
enum class Ui { Access, Menu, FirstFinger, RemoveFinger, SecondFinger,
                FirstPin, ConfirmPin, DisableId, EnableId, ConfirmStatus,
                CardEnroll, LinkId, CardLink, AccessPin, UnlinkId, ConfirmUnlink };
Ui ui = Ui::Access;
// B4: falhas seguidas de getImage durante o cadastro; só a 4a aborta (PACKETRECIEVEERR aborta já).
uint8_t enrollReadFails = 0;
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
// Filtro dos sensores D30/D31: a leitura bruta só vira estado se ficar igual por este tempo
// (cada borda reinicia a janela). Era 50 ms; 200 ms ignora o ruído do pulso da fechadura.
constexpr uint32_t kDoorDebounceMs = 200;
// Reinício dos leitores após a fechadura: lockReleasedAt marca quando a saída voltou a LOW;
// readerResetStage 1 = falta o reinício de 1 s, 2 = falta o de 1 s + 3 s, 0 = nada agendado.
constexpr uint32_t kReaderResetFirstMs = 1000, kReaderResetSecondMs = 3000;
bool lockEnergized = false;
uint8_t readerResetStage = 0;
uint32_t lockReleasedAt = 0;
bool serialAuthed = false, serialOverflow = false;
uint32_t serialTouched = 0;
String serialLine;
String lcdPrevA, lcdPrevB;
String mirrorPrevA, mirrorPrevB;  // último par espelhado na serial (independe do LCD)
uint32_t lastFingerRecovery = 0;
// RC522: leitura a cada 100 ms com a porta em repouso; o mesmo UID é ignorado por 2 s.
bool rfidReady = false;
uint32_t lastRfidPoll = 0, lastRfidRecovery = 0, lastCardAt = 0;
CardStore::Tag lastCard = {}, pendingCard = {};
bool cardPending = false;
// B4: 5 senhas erradas seguidas (ID ou admin com 10 digitos) travam o teclado por 60 s.
// Senha certa não zera o contador; ele volta a zero após 10 min sem nenhuma falha. Só em RAM:
// um reinício zera o contador e libera o teclado (aceito; não grava na EEPROM).
constexpr uint8_t kPinFailLimit = 5;
constexpr uint32_t kKeypadLockMs = 60000, kPinFailDecayMs = 600000;
uint8_t pinFailures = 0;
uint32_t lastPinFailureAt = 0;
bool keypadLockActive = false;
uint32_t keypadLockedAt = 0;
// Tempo restante do bloqueio em ms (0 = livre). Uma única leitura de millis() por chamada,
// para que a decisão e o número exibido no LCD usem o mesmo instante.
uint32_t keypadLockRemainingMs() {
  if (!keypadLockActive) return 0;
  const uint32_t elapsed = uint32_t(millis() - keypadLockedAt);
  if (elapsed < kKeypadLockMs) return kKeypadLockMs - elapsed;
  keypadLockActive = false; pinFailures = 0; return 0;
}
bool keypadLocked() { return keypadLockRemainingMs() != 0; }
// LED: flash ciano de 150 ms quando um cartão é lido ou uma digital é capturada (antes do resultado).
constexpr uint32_t kReadFlashMs = 150;
bool readFlashOn = false;
uint32_t readFlashAt = 0;
void startReadFlash() { readFlashOn = true; readFlashAt = millis(); }
bool readFlashActive() {
  if (readFlashOn && uint32_t(millis() - readFlashAt) >= kReadFlashMs) readFlashOn = false;
  return readFlashOn;
}

bool validPin(const String &pin, size_t length) {
  if (pin.length() != length) return false;
  for (size_t i = 0; i < length; ++i) if (pin[i] < '0' || pin[i] > '9') return false;
  return true;
}
// Entrada de 1 a 3 digitos que é começo do ADMIN_PIN: não pode aparecer na tela de ID.
bool adminPrefix(const String &typed) {
  return typed.length() >= 1 && typed.length() <= 3 && !strncmp(typed.c_str(), ADMIN_PIN, typed.length());
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
// Conta uma senha errada (ID ou admin) no mesmo contador. Após 10 min sem falha, recomeça em 1.
// Retorna true quando a falha atinge o limite e o teclado é travado (com a auditoria keypad_locked).
bool registerPinFailure() {
  const uint32_t at = millis();
  if (uint32_t(at - lastPinFailureAt) >= kPinFailDecayMs) pinFailures = 0;
  lastPinFailureAt = at;
  if (++pinFailures < kPinFailLimit) return false;
  pinFailures = 0; keypadLockActive = true; keypadLockedAt = at;
  audit("keypad_locked", 0, "keypad", "invalid_pin");
  return true;
}
void notice(const String &a, const String &b, bool error = false, uint32_t duration = 2000) {
  noticeLine1 = a; noticeLine2 = b; noticeError = error;
  noticeSince = millis(); noticeDuration = duration;
}
bool noticeActive() { return uint32_t(millis() - noticeSince) < noticeDuration; }
String idText(uint16_t id) { char b[12]; snprintf(b, sizeof(b), "ID %03u", id); return String(b); }
void resetUi() {
  ui = Ui::Access; entry = ""; firstPin = ""; pendingId = 0; enrollReadFails = 0;
  cardPending = false; uiTouched = millis();
}
// message é o código de auditoria (reasonNames, usado pela CAM e pelo servidor); lcdLine é só o texto do LCD, até 16 colunas.
void failEnrollment(const char *message, const char *lcdLine) {
  audit("enroll_failed", 0, "admin", message);
  resetUi(); notice("Cadastro falhou", lcdLine, true);
}
bool changeStatus(uint16_t id, bool enabled) {
  if (!exists(id)) return false;
  UserRecord updated; if (!readRecord(id, updated)) return false; updated.active = enabled;
  if (!saveRecord(id, updated)) return false;
  audit(enabled ? "user_enabled" : "user_disabled", id, "admin"); return true;
}
const char *resetPassword(uint16_t id, const String &pin, const char *source, uint64_t token) {
  // Registro corrompido também dá false, mas readRecord já marcou storageReady=false: é erro de armazenamento.
  // Salvo no MESMO registro que o hash: reenvio após reboot só confirma a aplicação.
  // Reset USB copia/preserva esse token, impedindo reaplicar comando web antigo.
  const bool storageOk = storageReady;
  UserRecord current; if (!readRecord(id, current)) return (storageOk && !storageReady) ? "storage_error" : "unknown_user";
  if (token && current.lastWebToken == token) return "ok";
  if (ui != Ui::Access || door.state != DoorState::Idle || !door.closed) return "device_busy";
  if (!validPin(pin, 6)) return "invalid_pin";
  // B5: senhas podem repetir entre IDs; a nova senha não é comparada com as dos outros.
  UserRecord updated = current;
  if (token) updated.lastWebToken = token;
  fillSalt(updated.salt, id);
  if (!digest(pin, updated.salt, updated.hash) || !saveRecord(id, updated)) return "storage_error";
  audit("password_reset", id, source);
  return "ok";
}
void authorize(uint16_t id, const char *method) {
  // Uma única leitura: registro corrompido derruba storageReady e vira falha de memória, não "inativo".
  UserRecord record;
  const bool found = storageReady && readRecord(id, record);
  if (!storageReady) {
    notice("Falha memoria", "Acesso negado", true);
    audit("access_denied", id, method, "Erro na memoria"); return;
  }
  if (!found || !record.active) {
    notice("Acesso negado", "Cadastro inativo", true);
    audit("access_denied", id, method, "inactive_or_unknown"); return;
  }
  const uint32_t authorizedAt = millis();
  if (!door.authorize(id, authorizedAt)) {
    notice("Aguarde", "Ciclo em curso"); return;
  }
  authorizationAt = authorizedAt; accessMethod = method;
  buzzer.reset();
  entry = ""; // uma digital válida também pode substituir uma senha ainda incompleta
  audit("access_granted", id, method);
  // Remover qualquer erro anterior para a indicação verde prevalecer.
  noticeDuration = 0;
}

// B2: a senha só é comparada com o registro do próprio ID. ID inexistente, fora de 1..100,
// inativo com senha errada ou senha errada recebem a mesma resposta (não revela o cadastro).
void checkPassword(uint16_t id, const String &pin) {
  const bool known = id >= 1 && id <= MAX_USERS;
  const bool ok = known && matches(id, pin);
  if (!storageReady) {
    notice("Falha memoria", "Acesso negado", true);
    audit("access_denied", 0, "password", "Erro na memoria"); return;
  }
  if (ok) { authorize(id, "password"); return; }
  audit("access_denied", known ? id : 0, "password", "invalid_pin");
  if (!registerPinFailure()) { notice("Acesso negado", "Senha incorreta", true); return; }
  // B4: 5a senha errada seguida: teclado travado por 60 s, sem aviso de senha errada.
}

void beginEnrollment() {
  if (!storageReady || !fingerprintReady) { notice("Indisponivel", "Veja digital/mem", true); return; }
  if (lastId >= MAX_USERS) { notice("Limite atingido", "100 IDs em uso", true); return; }
  pendingId = lastId + 1;
  firstPin = ""; entry = ""; enrollReadFails = 0; cardPending = false;
  // Exigir área livre antes da primeira captura, inclusive se o dedo ficou no leitor.
  ui = Ui::RemoveFinger; enableRequested = false;
}
void confirmEnrollment() {
  if (entry != firstPin) {
    firstPin = ""; entry = ""; ui = Ui::FirstPin;
    notice("Senhas nao batem", "Digite novamente", true); return;
  }
  // B5: senha repetida é aceita. Erro de armazenamento encerra o cadastro com aviso;
  // porta aberta durante o cadastro aborta em silêncio (o ciclo da porta já mostra).
  if (!storageReady) { failEnrollment("Erro na memoria", "Erro na memoria"); return; }
  if (door.state != DoorState::Idle || !door.closed) return;
  UserRecord record = {}; record.active = 1;
  const uint16_t enrollmentId = pendingId;
  const uint32_t generation = doorGeneration;
  const Ui enrollmentUi = ui;
  fillSalt(record.salt, enrollmentId);
  if (!digest(entry, record.salt, record.hash)) { failEnrollment("Erro de hash", "Erro de hash"); return; }
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
    failEnrollment("Erro ao gravar DY", "Erro gravar DY"); return;
  }
  // Cartão antes do registro: se gravar o cartão falhar, nenhum usuário fica pela metade.
  ServicedEeprom storage;
  if (cardPending) {
    if (!CardStore::write(storage, enrollmentId, pendingCard)) {
      if (finger.deleteModel(enrollmentId) == FINGERPRINT_PACKETRECIEVEERR) fingerprintReady = false;
      failEnrollment("Erro na memoria", "Erro na memoria"); return;
    }
  } else {
    // A1: cadastro sem cartão apaga o slot deixado por cadastro anterior interrompido (órfão).
    CardStore::clear(storage, enrollmentId);
  }
  if (!saveRecord(enrollmentId, record)) {
    if (cardPending) CardStore::clear(storage, enrollmentId);
    if (finger.deleteModel(enrollmentId) == FINGERPRINT_PACKETRECIEVEERR) fingerprintReady = false;
    failEnrollment("Erro na memoria", "Erro na memoria"); return;
  }
  const uint16_t id = enrollmentId;
  audit("user_enrolled", id, "admin"); resetUi();
  waitFingerRemoval = true;
  if (doorGeneration == generation && door.state == DoorState::Idle) notice("Cadastrado", idText(id));
}
void handleKey(char key) {
  // B4: enquanto o teclado está travado, todas as teclas são ignoradas (cartão e digital seguem).
  if (!key || noticeActive() || keypadLocked()) return;
  uiTouched = millis(); entryTouched = millis();
  if (key == 'D') {
    if (ui != Ui::Access) { resetUi(); notice("Cancelado", ""); }
    else if (door.state == DoorState::Idle) entry = "";
    // D cancela administração/cadastro. Não anuncia cancelamento de um acesso liberado.
    return;
  }
  if (key == '*' && (ui == Ui::CardLink || ui == Ui::ConfirmUnlink)) { resetUi(); notice("Cancelado", ""); return; }
  if (key == '*') {
    // B3: na senha, '*' com entrada vazia volta à tela de ID; com dígitos, só limpa.
    if (ui == Ui::AccessPin && entry.length() == 0) { ui = Ui::Access; pendingId = 0; }
    entry = ""; return;
  }
  if (ui == Ui::Menu) {
    if (key == '1') beginEnrollment();
    if (key == '2' || key == '3') {
      enableRequested = key == '3'; ui = enableRequested ? Ui::EnableId : Ui::DisableId;
      entry = "";
    }
    if (key == '4') { ui = Ui::LinkId; entry = ""; }
    if (key == '5') { ui = Ui::UnlinkId; entry = ""; }
    return;
  }
  if (ui == Ui::ConfirmUnlink) {
    // Menu 5: '#' apaga o cartão do ID; '*' e 'D' cancelam (acima); dígitos são ignorados.
    if (key == '#') {
      const uint16_t id = pendingId;
      const uint32_t generation = doorGeneration;
      ServicedEeprom storage; CardStore::Tag tag;
      const bool ok = CardStore::clear(storage, uint8_t(id)) && !CardStore::read(EEPROM, uint8_t(id), tag);
      if (ok) audit("card_unlinked", id, "admin");
      resetUi();
      if (generation == doorGeneration && door.state == DoorState::Idle)
        notice(ok ? "Cartao removido" : "Erro na memoria", ok ? idText(id) : String("Cartao mantido"), !ok);
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
        notice(ok ? (enabling ? "Reativado" : "Desativado") : "Falha ao alterar", idText(id), !ok);
    }
    return;
  }
  if (ui == Ui::FirstFinger || ui == Ui::RemoveFinger || ui == Ui::SecondFinger) return;
  if (ui == Ui::CardEnroll || ui == Ui::CardLink) {
    // Cadastro: # pula o cartão e segue para a senha. Vincular: só D e * agem (acima).
    if (key == '#' && ui == Ui::CardEnroll) { ui = Ui::FirstPin; entry = ""; uiTouched = millis(); }
    return;
  }
  if (key >= '0' && key <= '9') {
    const size_t limit = ui == Ui::Access ? 10 : ((ui == Ui::DisableId || ui == Ui::EnableId || ui == Ui::LinkId || ui == Ui::UnlinkId) ? 3 : 6);
    if (entry.length() < limit) entry += key;
    return;
  }
  if (key != '#') return;
  if (ui == Ui::Access) {
    if (entry == ADMIN_PIN) {
      if (door.state == DoorState::Idle && door.closed) {
        ui = Ui::Menu; audit("admin_login", 0, "keypad");
      } else notice("Feche a porta", "Aguarde o ciclo", true);
    } else if (entry.length() == 10) {
      // 10 digitos que não são o admin: falha de senha (mesmo contador), aviso de entrada inválida.
      audit("access_denied", 0, "keypad", "invalid_pin");
      if (!registerPinFailure()) notice("Entrada invalida", "ID e # ou admin", true);
    } else if (entry.length() >= 1 && entry.length() <= 3) {
      // B1: ID de 1 a 3 dígitos pede a senha (sempre, mesmo se o ID não existir).
      pendingId = uint16_t(entry.toInt()); ui = Ui::AccessPin;
    } else { notice("Entrada invalida", "ID e # ou admin", true); }
    entry = "";
  } else if (ui == Ui::AccessPin) {
    if (!validPin(entry, 6)) { entry = ""; notice("Entrada invalida", "Use 6 digitos", true); return; }
    const uint16_t id = pendingId; const String pin = entry;
    entry = ""; ui = Ui::Access; pendingId = 0;
    checkPassword(id, pin);
  } else if (ui == Ui::FirstPin || ui == Ui::ConfirmPin) {
    if (!validPin(entry, 6)) { entry = ""; notice("Senha invalida", "Use 6 digitos", true); return; }
    if (ui == Ui::FirstPin) { firstPin = entry; entry = ""; ui = Ui::ConfirmPin; }
    else confirmEnrollment();
  } else if (ui == Ui::DisableId || ui == Ui::EnableId) {
    pendingId = entry.toInt(); entry = "";
    if (!exists(pendingId)) { notice("ID inexistente", "Digite novamente", true); return; }
    ui = Ui::ConfirmStatus;
  } else if (ui == Ui::LinkId) {
    // Vincular cartão: o ID pode estar ativo ou inativo.
    pendingId = entry.toInt(); entry = "";
    if (!exists(pendingId)) { notice("ID inexistente", "Digite novamente", true); return; }
    ui = Ui::CardLink; uiTouched = millis();
  } else if (ui == Ui::UnlinkId) {
    // Remover cartão (menu 5): ID inexistente ou sem cartão avisa e pede o ID de novo.
    pendingId = entry.toInt(); entry = "";
    CardStore::Tag tag;
    if (!exists(pendingId)) { notice("ID inexistente", "Digite novamente", true); return; }
    if (!CardStore::read(EEPROM, uint8_t(pendingId), tag)) { notice("Sem cartao", idText(pendingId), true); return; }
    ui = Ui::ConfirmUnlink; uiTouched = millis();
  }
}
// Senha parcial no teclado expira após 30 s sem tecla; sem aviso nem evento.
// Vale para a tela de ID e a de senha: sem tecla por 30 s volta ao repouso e limpa tudo.
void expireEntry() {
  if (ui != Ui::Access && ui != Ui::AccessPin) return;
  if (uint32_t(millis() - entryTouched) < 30000) return;
  if (ui == Ui::AccessPin) resetUi();
  else if (entry.length()) entry = "";
}
void fingerprintTick() {
  if (!fingerprintReady || uint32_t(millis() - lastFingerPoll) < 150 || noticeActive()) return;
  lastFingerPoll = millis();
  if (ui == Ui::Menu || ui == Ui::FirstPin || ui == Ui::ConfirmPin ||
      ui == Ui::DisableId || ui == Ui::EnableId || ui == Ui::ConfirmStatus ||
      ui == Ui::LinkId || ui == Ui::CardEnroll || ui == Ui::CardLink || ui == Ui::AccessPin ||
      ui == Ui::UnlinkId || ui == Ui::ConfirmUnlink) return;
  if (door.state != DoorState::Idle || !door.closed) return;
  const Ui startedUi = ui;
  const uint32_t generation = doorGeneration;
  uint8_t p = finger.getImage();
  if (p == FINGERPRINT_PACKETRECIEVEERR) fingerprintReady = false;
  if (ui != startedUi || doorGeneration != generation || door.state != DoorState::Idle || !door.closed) { waitFingerRemoval = true; return; }
  // B4: no cadastro, falha passageira de leitura (ex.: IMAGEFAIL) tenta de novo no próximo tick.
  // Só a 4a seguida aborta; erro de comunicação (PACKETRECIEVEERR) aborta já. OK/NOFINGER zeram.
  const bool enrolling = ui == Ui::RemoveFinger || ui == Ui::FirstFinger || ui == Ui::SecondFinger;
  if (p == FINGERPRINT_OK || p == FINGERPRINT_NOFINGER) enrollReadFails = 0;
  else if (enrolling && p != FINGERPRINT_PACKETRECIEVEERR && ++enrollReadFails <= 3) return;
  if (ui == Ui::RemoveFinger) {
    if (p == FINGERPRINT_NOFINGER) ui = enableRequested ? Ui::SecondFinger : Ui::FirstFinger;
    else if (p != FINGERPRINT_OK) failEnrollment("Erro de leitura", "Erro de leitura");
    return;
  }
  if (p == FINGERPRINT_NOFINGER) { waitFingerRemoval = false; return; }
  if (p != FINGERPRINT_OK) {
    // Diagnóstico de bancada: código cru do getImage (0x01 pacote, 0x03 imagem, 0xFE timeout).
    // Fora da placa (simulação dos testes no host) não há Serial.
#ifdef ARDUINO
    Serial.print(F("DY50 err=0x")); Serial.println(p, HEX);
#endif
    if (ui != Ui::Access) failEnrollment("Erro de leitura", "Erro de leitura");
    else notice("Falha no leitor", "Tente novamente", true);
    return;
  }
  if (ui == Ui::Access && waitFingerRemoval) return;
  startReadFlash();  // digital capturada: ciano enquanto converte e pesquisa
  p = finger.image2Tz(ui == Ui::SecondFinger ? 2 : 1);
  if (p == FINGERPRINT_PACKETRECIEVEERR) fingerprintReady = false;
  if (ui != startedUi || doorGeneration != generation || door.state != DoorState::Idle || !door.closed) { waitFingerRemoval = true; return; }
  if (p != FINGERPRINT_OK) {
    if (ui != Ui::Access) failEnrollment("Digital ilegivel", "Digital ilegivel");
    else { waitFingerRemoval = true; notice("Digital ilegivel", "Retire o dedo", true); }
    return;
  }
  if (ui == Ui::FirstFinger) {
    p = finger.fingerFastSearch();
    if (p == FINGERPRINT_PACKETRECIEVEERR) fingerprintReady = false;
    if (ui != startedUi || doorGeneration != generation || door.state != DoorState::Idle || !door.closed) { waitFingerRemoval = true; return; }
    if (p == FINGERPRINT_OK) {
      // A EEPROM é a fonte da verdade. Modelo sem registro é lixo de um cadastro
      // interrompido (falta de energia entre storeModel e saveRecord): apaga o
      // slot e volta a pedir para retirar o dedo. A nova busca acha qualquer
      // digital cadastrada que a órfã escondia ("Digital ja usada"). Cada
      // limpeza remove um slot, então não há laço sem retirada do dedo.
      if (exists(finger.fingerID)) { failEnrollment("Digital ja usada", "Digital ja usada"); return; }
      if (!storageReady || finger.fingerID < 1 || finger.fingerID > MAX_USERS) {
        failEnrollment("Slot DY orfao", "Slot DY orfao"); return;
      }
      p = finger.deleteModel(finger.fingerID);
      if (p == FINGERPRINT_PACKETRECIEVEERR) fingerprintReady = false;
      if (ui != startedUi || doorGeneration != generation || door.state != DoorState::Idle || !door.closed) { waitFingerRemoval = true; return; }
      if (p != FINGERPRINT_OK) { failEnrollment("Slot DY orfao", "Slot DY orfao"); return; }
      enableRequested = false; ui = Ui::RemoveFinger; uiTouched = millis();
      notice("Slot orfao limpo", "Recoloque o dedo");
      return;
    } else if (p != FINGERPRINT_NOTFOUND) { failEnrollment("Falha na pesquisa", "Falha na busca"); return; }
    enableRequested = true; ui = Ui::RemoveFinger; uiTouched = millis();
  } else if (ui == Ui::SecondFinger) {
    p = finger.createModel();
    if (p == FINGERPRINT_PACKETRECIEVEERR) fingerprintReady = false;
    if (ui != startedUi || doorGeneration != generation || door.state != DoorState::Idle || !door.closed) { waitFingerRemoval = true; return; }
    if (p != FINGERPRINT_OK) { failEnrollment("Digitais diferem", "Digitais diferem"); return; }
    ui = Ui::CardEnroll; entry = ""; cardPending = false; uiTouched = millis();
  } else {
    waitFingerRemoval = true;
    p = finger.fingerFastSearch();
    if (p == FINGERPRINT_PACKETRECIEVEERR) fingerprintReady = false;
    if (ui != startedUi || doorGeneration != generation || door.state != DoorState::Idle || !door.closed) return;
    if (p == FINGERPRINT_OK) authorize(finger.fingerID, "fingerprint");
    else {
      notice("Acesso negado", p == FINGERPRINT_NOTFOUND ? "Dig. desconhec." : "Erro de leitura", true);
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
  // Fim do pulso (modo 1) ou desenergização (modo 2): agenda o reinício dos leitores.
  if (lockEnergized && !energized) { lockReleasedAt = now; readerResetStage = 1; }
  lockEnergized = energized;
  // Porta aberta sem autorização (ForcedOpen ou boot com porta aberta): bipe rápido até fechar.
  const bool forcedAlarm = door.state == DoorState::Alarm && door.user == 0;
  const bool buzz = forcedAlarm ? uint32_t(now - door.since) % 500 < 250 : buzzer.isOn(now);
  digitalWrite(BUZZER_PIN, buzz ? HIGH : LOW);
  // Prioridade: alarme > teclado travado > erro > flash de leitura > admin/cadastro (branco)
  // > senha (magenta) > ID (ciano) > porta aberta > acesso liberado > repouso.
  if (door.state == DoorState::Alarm) rgb((now / 350) % 2, false, false);
  else if (keypadLocked()) rgb(uint32_t(now - keypadLockedAt) % 2000 < 1000, false, false);  // 1 s aceso / 1 s apagado
  else if (noticeActive() && noticeError) rgb(true, false, false);
  else if (readFlashActive()) rgb(false, true, true);
  else if (ui == Ui::AccessPin) rgb(true, false, true);
  else if (ui != Ui::Access) rgb(true, true, true);
  else if (entry.length()) rgb(false, true, true);
  else if (door.state == DoorState::Open) { bool on = (now / 600) % 2; rgb(on, on, false); }
  else if (door.state == DoorState::AwaitOpen) rgb(false, true, false);
  else rgb(false, false, now % 10000 < 200);  // repouso: piscada azul de 200 ms a cada 10 s
}
void doorTick() {
  const uint32_t now = millis();
  const bool current = digitalRead(BUTTON_1) == LOW && digitalRead(BUTTON_2) == LOW;
  if (current != rawClosed) { rawClosed = current; rawSince = now; }
  if (uint32_t(now - rawSince) >= kDoorDebounceMs) stableClosed = rawClosed;
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
// Handshake do DY50 (o mesmo do setup): senha, parâmetros e capacidade suficiente.
bool fingerprintHandshake() {
  return finger.verifyPassword() && finger.getParameters() == FINGERPRINT_OK && finger.capacity > MAX_USERS;
}
void fingerprintRecoveryTick() {
  if (fingerprintReady || uint32_t(millis() - lastFingerRecovery) < 10000) return;
  if (ui != Ui::Access || door.state != DoorState::Idle || !door.closed || noticeActive() || entry.length()) return;
  lastFingerRecovery = millis();
  fingerprintReady = fingerprintHandshake();
}
// LCD 1602 em modo 4 bits (LiquidCrystal): não há detecção de módulo ausente.
void lcdBoot() { lcd.begin(16, 2); lcd.print("Iniciando..."); }
void displayTick() {
  if (uint32_t(millis() - lastLcd) < 150) return;
  lastLcd = millis();
  String a, b;
  bool masked = false;
  uint32_t lockLeft = 0;
  bool homeAnimated = false;
  String mirrorA, mirrorB;  // texto do espelho quando a home animada está numa cena com ícones
  if (door.state == DoorState::Alarm) { a = "Feche a porta"; b = door.user ? idText(door.user) : "Sem autorizacao"; }
  else if (noticeActive()) { a = noticeLine1; b = noticeLine2; }
  else if ((lockLeft = keypadLockRemainingMs()) != 0) {
    // B4: 17 colunas não cabem; "Teclado travado" usa 15 e mostra a contagem (arredondada para cima, no máximo 60).
    char restText[16];
    snprintf(restText, sizeof restText, "Aguarde %lu s", (unsigned long)((lockLeft + 999) / 1000));
    a = "Teclado travado"; b = restText;
  }
  else if (ui != Ui::Access) {
    switch (ui) {
      case Ui::Menu:
        // Duas telas alternadas a cada 2,5 s: 1-3 e D na primeira; cartão (4 e 5) na segunda.
        if ((millis() / 2500) % 2) { a = "4 Vincula cartao"; b = "5 Remove cartao"; }
        else { a = "1 Novo 2 Inativ."; b = "3 Reativ. D Sair"; }
        break;
      case Ui::RemoveFinger: a = "Cadastrando"; b = "Retire o dedo"; break;
      case Ui::FirstFinger: a = "Cadastrando"; b = "Coloque o dedo"; break;
      case Ui::SecondFinger: a = "Confirme digital"; b = "Mesmo dedo"; break;
      case Ui::FirstPin: a = "Crie senha (6)"; break;
      case Ui::ConfirmPin: a = "Repita senha (6)"; break;
      case Ui::DisableId: a = "Desativar ID:"; b = entry; break;
      case Ui::EnableId: a = "Reativar ID:"; b = entry; break;
      case Ui::LinkId: a = "Vincular ID:"; b = entry; break;
      case Ui::UnlinkId: a = "Desvincular ID:"; b = entry; break;
      case Ui::ConfirmUnlink: a = "Remover cartao?"; b = "#Sim *Nao"; break;
      case Ui::CardEnroll: a = "Aproxime cartao"; b = "# pula"; break;
      case Ui::CardLink: a = "Aproxime cartao"; b = idText(pendingId) + " * cancela"; break;
      case Ui::AccessPin: a = "#Confirma *Limpa"; b = idText(pendingId) + ": "; break;
      case Ui::ConfirmStatus: a = idText(pendingId) + (enableRequested ? " Reativar?" : " Inativar?"); b = "# Sim D Cancelar"; break;
      default: break;
    }
    if (ui == Ui::FirstPin || ui == Ui::ConfirmPin || ui == Ui::AccessPin) { for (size_t i = 0; i < entry.length(); ++i) b += '*'; if (entry.length()) masked = true; }
  } else if (door.state == DoorState::AwaitOpen) { a = "Acesso liberado"; b = idText(door.user); }
  else if (door.state == DoorState::Open) { a = "Porta aberta"; b = idText(door.user); }
  else {
    // B6: ID de até 3 dígitos aparece (não é segredo); entrada maior pode ser o admin, então mascara.
    // Prefixo de 1 a 3 dígitos do ADMIN_PIN também vira '*' (LCD e espelho; masked fica falso para o
    // espelho de bancada com SHOW_TYPED_DIGITS não mostrar esse prefixo).
    // Repouso: "Controle acesso" / "ID cartao dedo"; ao digitar, a linha 1 vira a ajuda das teclas
    // e a linha 2 mostra "ID: " e a entrada (até 10 dígitos mascarados = 14 colunas).
    if (entry.length()) { a = "#Confirma *Limpa"; b = "ID: "; }
    else a = !storageReady ? "Falha memoria" : "Controle acesso";
    if (entry.length() > 3 || adminPrefix(entry)) {
      for (size_t i = 0; i < entry.length(); ++i) b += '*';
      masked = entry.length() > 3;
    }
    else if (entry.length()) b += entry;
    else b = fingerprintReady ? "ID cartao dedo" : "ID ou cartao";
    // Home animada: 4 cenas de 3 s ("Controle acesso", cartão, ID + senha, digital), quadros de 300 ms.
    // Sem digital pronta, a cena da digital vira a de texto. O espelho da serial fica no texto.
    if (!entry.length() && storageReady) {
      auto sp = [](uint8_t n) { String s; while (n--) s += ' '; return s; };
      const uint32_t t = millis();
      uint8_t scene = (t / 3000) % 4;
      if (scene == 3 && !fingerprintReady) scene = 0;
      const uint8_t f = (t % 3000) / 300;  // quadro 0 a 9
      // O espelho da serial guarda o texto completo; no LCD, a cena de texto mostra só "Controle acesso".
      homeAnimated = true; mirrorA = a; mirrorB = b;
      if (scene == 0) b = "";
      else if (scene == 1) {
        // Cartão desliza até o leitor; no fim, o visto.
        const uint8_t pos = 2 + f;  // coluna 2 a 11
        a = "Aproxime cartao"; b = sp(pos); b += char(1); b += sp(12 - pos); b += char(2);
        if (f >= 8) b += char(7);
      } else if (scene == 2) {
        // Digitação de exemplo: ID 007 e #, depois a senha em asteriscos.
        a = "Digite ID+senha"; b = ""; b += char(3); b += ' ';
        if (f < 3) { b += "ID: "; for (uint8_t i = 0; i <= f; ++i) b += (i < 2 ? '0' : '7'); }
        else if (f == 3) b += "ID: 007 #";
        else { b += "Senha: "; for (uint8_t i = 0; i < (f == 9 ? 6 : f - 3); ++i) b += '*'; if (f == 9) b += '#'; }
      } else if (scene == 3) {
        // Digital pulsando: o ícone alterna e os anéis abrem e fecham.
        const uint8_t r = f % 3;
        a = "Encoste o dedo"; b = sp(7 - r);
        for (uint8_t i = 0; i < r; ++i) b += '(';
        b += char(f % 2 ? 5 : 4);
        for (uint8_t i = 0; i < r; ++i) b += ')';
      }
    }
  }
#if LCD_SERIAL_MIRROR
  // Espelho na serial USB: o mesmo texto do LCD, inclusive quando o LCD está ausente.
#if SHOW_TYPED_DIGITS
  // Troca só os '*' finais pelos dígitos (mantém o prefixo "ID: " ou "ID 00X: ").
  const String mb = homeAnimated ? mirrorB : masked ? b.substring(0, b.length() - entry.length()) + entry : b;
#else
  const String mb = homeAnimated ? mirrorB : b; (void)masked;
#endif
  const String ma = homeAnimated ? mirrorA : a;
  if (ma != mirrorPrevA || mb != mirrorPrevB) {
    mirrorPrevA = ma; mirrorPrevB = mb;
    Serial.print(F("LCD| ")); Serial.print(ma.substring(0, 16));
    Serial.print(F(" | ")); Serial.println(mb.substring(0, 16));
  }
#endif
  if (a != lcdPrevA || b != lcdPrevB) {
    String paddedA = a.substring(0, 16), paddedB = b.substring(0, 16);
    while (paddedA.length() < 16) paddedA += ' ';
    while (paddedB.length() < 16) paddedB += ' ';
    lcd.setCursor(0, 0);
    for (size_t i = 0; i < paddedA.length(); ++i) {
      doorTick(); outputsTick(); linkTick(true);
      lcd.write(uint8_t(paddedA[i]));
    }
    lcd.setCursor(0, 1);
    for (size_t i = 0; i < paddedB.length(); ++i) {
      doorTick(); outputsTick(); linkTick(true);
      lcd.write(uint8_t(paddedB[i]));
    }
    lcdPrevA = a; lcdPrevB = b;
  }
}


// Lista circular pequena em RAM; confirmação UART significa somente que a CAM aceitou o evento.
MessageProtocol::EventData outbound[16];
bool photoFresh[16] = {};
uint8_t head = 0, count = 0; uint32_t transmitAt = 0, syncEpoch = 0, syncAt = 0;
SerialFrame::Parser receiver;
const char * const eventNames[] = {"", "device_boot", "storage_error", "user_snapshot", "user_enrolled", "user_disabled", "user_enabled", "password_reset", "admin_login", "access_granted", "access_denied", "door_opened", "door_closed", "entry_expired", "door_timeout", "forced_open", "enroll_failed", "card_linked", "keypad_locked", "card_unlinked"};
const char * const methodNames[] = {"", "password", "fingerprint", "admin", "keypad", "system", "sensor", "usb", "web", "card"};
const char * const reasonNames[] = {"", "inactive_or_unknown", "invalid_pin", "unknown_finger", "sensor_error", "simulation", "actuator_enabled", "open_at_boot", "Erro de hash", "Erro ao gravar DY", "Erro na memoria", "Erro de leitura", "Digital ilegivel", "Digital ja usada", "Slot DY orfao", "Falha na pesquisa", "Digitais diferem", "unknown_card"};
uint8_t nameIndex(const char *name, const char * const *names, uint8_t length) {
  for (uint8_t i = 0; i < length; ++i) if (!strcmp(name, names[i])) return i;
  return 0;
}
void queueEvent(const char *type, uint16_t id, const char *method, const char *reason) {
  uint8_t kind = nameIndex(type, eventNames, 20);
  if (!kind || !bootNumber || eventSequence == 0xffffffffUL || count == 16) { ++droppedEvents; return; }
  MessageProtocol::EventData e = {};
  e.messageId = ++eventSequence; e.boot = bootNumber;
  e.uptime = kind == MessageProtocol::AccessGranted ? authorizationAt : millis();
  e.epoch = syncEpoch ? syncEpoch + uint32_t(e.uptime - syncAt) / 1000 : 0;
  e.kind = kind; e.user = id <= 100 ? uint8_t(id) : 0; e.method = nameIndex(method, methodNames, 10);
  e.active = activeUser(id); e.reason = nameIndex(reason, reasonNames, 18);
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
// Reset/gravação chamados de dentro do enlace (resetPassword -> saveRecord -> ServicedEeprom::update)
// não reentram: só copiam a UART para linkStash, sem parsear; o processamento fica para a chamada seguinte.
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
      Serial.print(" dropped="); Serial.print(droppedEvents); Serial.print(" replies_dropped="); Serial.print(droppedReplies);
      Serial.print(F(" dy50=")); Serial.print(fingerprintReady ? F("ok") : F("indisponivel"));
      Serial.print(" lock_mode="); Serial.println(LOCK_MODE);
    } else if (line == "LIST") {
      for (uint16_t id = 1; id <= lastId; ++id) {
        doorTick(); outputsTick();
        if (exists(id)) {
          CardStore::Tag tag;
          Serial.print("ID "); Serial.print(id); Serial.print(activeUser(id) ? " ativo" : " inativo");
          Serial.println(CardStore::read(EEPROM, id, tag) ? " cartao=sim" : " cartao=nao");
        }
      }
    } else if (line.startsWith("RESET ")) {
      unsigned id = 0; char pin[8] = {}, confirmation[8] = {}, extra[2] = {};
      int n = sscanf(line.c_str(), "RESET %u %7s %7s %1s", &id, pin, confirmation, extra);
      if (n != 3 || id > MAX_USERS || strcmp(pin, confirmation)) Serial.println("ERR invalid_or_mismatched");
      else { const char *result = resetPassword(id, String(pin), "usb", 0); Serial.print(strcmp(result, "ok") ? "ERR " : "OK "); Serial.println(result); }
    } else Serial.println("ERR commands: STATUS | LIST | RESET <id> <6digits> <repeat> | LOGOUT");
  }
}


// Cartão RFID (RC522). Access lê para autorizar; CardEnroll (cadastro) e CardLink (menu 4) gravam.
// Só a leitura do cartão fica aqui; a gravação usa ServicedEeprom, que atende a porta entre bytes.
bool rfidVersionOk() {
  const uint8_t version = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  return version != 0x00 && version != 0xff;
}
// PCD_Init refaz o reset do RC522, os registradores e liga a antena (PCD_AntennaOn).
// Bloqueia ~50-150 ms (espera do reset na biblioteca).
void rfidReinit() { rfid.PCD_Init(); rfidReady = rfidVersionOk(); }
// Religa o RC522 a cada 15 s enquanto estiver indisponível (como o DY50).
void rfidRecoveryTick() {
  if (uint32_t(millis() - lastRfidRecovery) < 15000) return;
  lastRfidRecovery = millis();
  // A3: o RC522 que estava pronto também é conferido; se falhar, a próxima volta o religa.
  if (rfidReady) { if (!rfidVersionOk()) rfidReady = false; return; }
  rfidReinit();
}
bool sameRecentCard(const CardStore::Tag &tag) {
  return tag.size && uint32_t(millis() - lastCardAt) < 2000 && tag.size == lastCard.size &&
         !memcmp(tag.uid, lastCard.uid, tag.size);
}
// Dono do UID entre IDs com registro de usuário. Slot de cartão sem registro (órfão) não conta.
uint8_t cardOwner(const uint8_t *uid, uint8_t size) {
  if (!CardStore::validSize(size)) return 0;
  for (uint8_t id = 1; id <= MAX_USERS; ++id) {
    CardStore::Tag tag;
    if (CardStore::read(EEPROM, id, tag) && tag.size == size && !memcmp(tag.uid, uid, size) && exists(id)) return id;
  }
  return 0;
}
void cardAccess(const CardStore::Tag &tag) {
  if (!storageReady) {
    notice("Falha memoria", "Acesso negado", true);
    audit("access_denied", 0, "card", "Erro na memoria"); return;
  }
  const uint8_t id = cardOwner(tag.uid, tag.size);
  if (!id) {
    notice("Acesso negado", "Cartao desconh.", true);
    audit("access_denied", 0, "card", "unknown_card"); return;
  }
  authorize(id, "card");
}
void cardTick() {
  if (!rfidReady || uint32_t(millis() - lastRfidPoll) < 200) return;
  lastRfidPoll = millis();
  if (door.state != DoorState::Idle || !door.closed) return;
  const bool access = ui == Ui::Access;
  if (!access && ui != Ui::CardEnroll && ui != Ui::CardLink) return;
  if (access && noticeActive()) return;
  // A2: a leitura do RC522 bloqueia ~25-36 ms na SPI; atende a UART da CAM antes dela.
  linkTick(true);
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;
  CardStore::Tag tag = {};
  const uint8_t size = rfid.uid.size;
  if (CardStore::validSize(size)) { tag.size = size; memcpy(tag.uid, rfid.uid.uidByte, size); }
  rfid.PICC_HaltA(); rfid.PCD_StopCrypto1();
  if (sameRecentCard(tag)) return;
  if (tag.size) { lastCard = tag; lastCardAt = millis(); }
  startReadFlash();  // cartão lido: ciano antes do resultado
  if (access) { cardAccess(tag); return; }
  if (!tag.size) { notice("Cartao invalido", "Use outro", true); return; }
  if (ui == Ui::CardEnroll) {
    if (cardOwner(tag.uid, tag.size)) { notice("Cartao em uso", "Use outro", true); return; }
    pendingCard = tag; cardPending = true;
    ui = Ui::FirstPin; entry = ""; uiTouched = millis();
    notice("Cartao lido", "Crie senha (6)", false, 1000);
    return;
  }
  // CardLink (menu 4): o cartão de outro usuário é recusado; o de quem já é o dono é regravado igual.
  const uint8_t owner = cardOwner(tag.uid, tag.size);
  if (owner && owner != pendingId) { notice("Cartao em uso", "Use outro", true); return; }
  const uint16_t id = pendingId;
  const uint32_t generation = doorGeneration;
  ServicedEeprom storage;
  if (!CardStore::write(storage, id, tag)) { resetUi(); notice("Erro na memoria", "Cartao nao salvo", true); return; }
  audit("card_linked", id, "admin");
  resetUi();
  if (doorGeneration == generation) notice("Cartao vinculado", idText(id));
}
void setup() {
  digitalWrite(LOCK_PIN, !LOCK_ON); pinMode(LOCK_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW); pinMode(BUZZER_PIN, OUTPUT);
  Serial.begin(115200); Serial1.begin(57600); Serial2.begin(38400);
  for (byte i = 0; i < 4; ++i) { rows[i] = ROW_PINS[i]; cols[i] = COL_PINS[i]; }
  pinMode(BUTTON_1, INPUT_PULLUP); pinMode(BUTTON_2, INPUT_PULLUP);
  pinMode(LED_R, OUTPUT); pinMode(LED_G, OUTPUT); pinMode(LED_B, OUTPUT); rgb(false, false, false);
  lcdBoot();
  {
    // Ícones da home animada nos slots 1 a 7 da CGRAM (o slot 0 vira '\0' e cortaria a String).
    static const uint8_t icons[7][8] = {
      {0x00, 0x1F, 0x1F, 0x11, 0x17, 0x11, 0x1F, 0x00},  // 1 cartão
      {0x08, 0x04, 0x12, 0x0A, 0x12, 0x04, 0x08, 0x00},  // 2 ondas do leitor
      {0x00, 0x15, 0x00, 0x15, 0x00, 0x15, 0x00, 0x00},  // 3 teclado
      {0x0E, 0x11, 0x04, 0x0A, 0x15, 0x15, 0x11, 0x0A},  // 4 digital, quadro A
      {0x0E, 0x11, 0x0E, 0x11, 0x0A, 0x15, 0x15, 0x0A},  // 5 digital, quadro B
      {0x0E, 0x11, 0x11, 0x1F, 0x1B, 0x1B, 0x1F, 0x00},  // 6 cadeado
      {0x00, 0x01, 0x03, 0x16, 0x1C, 0x08, 0x00, 0x00},  // 7 visto
    };
    for (uint8_t i = 0; i < 7; ++i) lcd.createChar(i + 1, (uint8_t *)icons[i]);
  }
  // BootCounter usa região própria da EEPROM (após o journal) e não depende de recover.
  const bool usersRecovered = UserStore::recover(EEPROM);
  const bool bootCounted = BootCounter::next(EEPROM, bootNumber);
  storageReady = usersRecovered && bootCounted;
  for (uint16_t id = 1; storageReady && id <= MAX_USERS; ++id) {
    UserStore::Record record; int8_t state = UserStore::load(EEPROM, id, record);
    if (state < 0) storageReady = false; else if (state == 1) lastId = id;
  }
  // A1: cartão de ID sem registro (órfão de cadastro interrompido) é apagado antes do uso.
  if (storageReady) for (uint16_t id = lastId + 1; id <= MAX_USERS; ++id) CardStore::clear(EEPROM, uint8_t(id));
  finger.begin(57600);
  fingerprintReady = fingerprintHandshake();
  SPI.begin(); rfidReinit(); lastRfidRecovery = millis();
  rawClosed = stableClosed = digitalRead(BUTTON_1) == LOW && digitalRead(BUTTON_2) == LOW;
  rawSince = millis(); door.begin(stableClosed, millis()); resetUi(); doorServiceReady = true;
  audit("device_boot", 0, "system", LOCK_MODE ? "actuator_enabled" : "simulation");
  if (!stableClosed) audit("forced_open", 0, "sensor", "open_at_boot");
  if (!storageReady) audit("storage_error", 0, "system");
  // Diagnóstico de bancada, sem segredos: uma linha por boot.
  Serial.print(F("BOOT boot=")); Serial.print(bootNumber);
  Serial.print(F(" storage=")); Serial.print(storageReady ? F("ok") : F("falha"));
  Serial.print(F(" dy50=")); Serial.print(fingerprintReady ? F("ok") : F("indisponivel"));
  Serial.print(F(" rfid=")); Serial.print(rfidReady ? F("ok") : F("indisponivel"));
  Serial.print(F(" lock_mode=")); Serial.println(LOCK_MODE);
}
// Telas de administração (menu, cadastro, menus 2 a 5) voltam ao repouso após UI_TIMEOUT_MS sem tecla.
void uiTimeoutTick() {
  if (ui != Ui::Access && ui != Ui::AccessPin && uint32_t(millis() - uiTouched) >= UI_TIMEOUT_MS) {
    resetUi(); notice("Tempo esgotado", "Cadastro expirou");
  }
}
void loop() {
  doorTick(); outputsTick();
  uiTimeoutTick();
  expireEntry();
  handleKey(keypad.getKey()); fingerprintTick(); fingerprintRecoveryTick(); cardTick(); rfidRecoveryTick(); readerResetTick(); linkTick(); serialTick();
  static uint16_t snapshot = 1;
  if (snapshot <= lastId && count == 0) {
    if (exists(snapshot)) audit("user_snapshot", snapshot, "system");
    ++snapshot;
  }
  doorTick(); outputsTick(); displayTick(); delay(5);
}
// Reinício dos leitores após a fechadura (bancada 06/11/2026): o pulso de 2 A da fechadura
// deixava RC522 e DY50 mudos até reiniciar o Mega. 1 s depois que a saída volta a LOW,
// e de novo 3 s após isso, refaz a inicialização dos dois. Só roda no loop (nunca dentro
// do atendimento da porta) e espera a fechadura desenergizada. Bloqueios: PCD_Init ~50-150 ms;
// handshake do DY50 até ~1 s se não responder, com a porta e a CAM atendidas no stream do
// DY50 (só o teclado espera). finger.begin não é usado porque tem delay(1000) sem atendimento.
void readerResetTick() {
  if (!readerResetStage || lockEnergized) return;
  const uint32_t due = readerResetStage == 1 ? kReaderResetFirstMs : kReaderResetFirstMs + kReaderResetSecondMs;
  if (uint32_t(millis() - lockReleasedAt) < due) return;
  readerResetStage = readerResetStage == 1 ? 2 : 0;
  linkTick(true);  // como no cardTick: atende a UART da CAM antes do bloqueio na SPI
  rfidReinit(); lastRfidRecovery = millis();
  Serial.print(F("RFID reiniciado ")); Serial.println(rfidReady ? F("ok") : F("sem resposta"));
  linkTick(true);
  Serial1.begin(57600);  // reabre a UART do DY50 (descarta erro de quadro) antes do handshake
  fingerprintReady = fingerprintHandshake(); lastFingerRecovery = millis();
  Serial.print(F("DY50 reiniciado ")); Serial.println(fingerprintReady ? F("ok") : F("sem resposta"));
}
