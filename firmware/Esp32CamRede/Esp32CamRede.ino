/* PROTÓTIPO EM DESENVOLVIMENTO. Não usar para controlar fechadura. */
#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <esp_camera.h>
#include <esp_system.h>
#include <time.h>
#include <sys/time.h>
#include "Config.h"
#include "SerialFrame.h"
#include "MessageProtocol.h"
#if defined(ARDUINO) && defined(ESP_ARDUINO_VERSION_MAJOR)
#include <WiFiClientSecure.h>
#include "ServerCA.h"
#endif
#if defined(ARDUINO) && defined(ESP_ARDUINO_VERSION_MAJOR) && defined(OTA_PASSWORD)
#include <ArduinoOTA.h>
#include <WebServer.h>
#include <mbedtls/sha256.h>
#include <mbedtls/md.h>
#include "MegaProgrammer.h"
static_assert(sizeof(OTA_PASSWORD) > 8, "OTA_PASSWORD deve ter pelo menos 8 caracteres");
// A gravação do Mega usa a API do mbedtls 3 (mbedtls_sha256 devolve int), que vem com o core 3.x.
static_assert(ESP_ARDUINO_VERSION_MAJOR >= 3, "a gravacao do Mega exige o core esp32 3.x (mbedtls 3)");
#endif
// Pinos da gravação do Mega (fora dos pinos da câmera AI-Thinker e do link Serial2 em IO13/IO14).
// IO12: base do BC337 (HIGH = Mega em reset); é pino de strapping e tem 10k ao GND externo.
constexpr uint8_t kMegaResetPin = 12, kMegaTxPin = 2, kMegaRxPin = 15;
static_assert(sizeof(DEVICE_ID) <= 33, "DEVICE_ID deve ter no máximo 32 caracteres");
using namespace MessageProtocol;
struct Item { EventData event; uint8_t *photo; size_t photoSize; };
struct Command { uint32_t id; uint8_t user; char pin[7]; uint64_t token; };
struct Result { uint32_t id; bool ok; uint8_t reason; };
QueueHandle_t events, commands, results;
SerialFrame::Parser parser;
bool cameraReady = false;
bool networkReady = false;
uint32_t lastBoot = 0, lastEvent = 0;
const char * const eventNames[] = {"", "device_boot", "storage_error", "user_snapshot", "user_enrolled", "user_disabled", "user_enabled", "password_reset", "admin_login", "access_granted", "access_denied", "door_opened", "door_closed", "entry_expired", "door_timeout", "forced_open", "enroll_failed", "card_linked", "keypad_locked", "card_unlinked"};
const char * const methodNames[] = {"", "password", "fingerprint", "admin", "keypad", "system", "sensor", "usb", "web", "card"};
const char * const reasonNames[] = {"", "inactive_or_unknown", "invalid_pin", "unknown_finger", "sensor_error", "simulation", "actuator_enabled", "open_at_boot", "Erro de hash", "Erro ao gravar DY", "Erro na memoria", "Erro de leitura", "Digital ilegivel", "Digital ja usada", "Slot DY orfao", "Falha na pesquisa", "Digitais diferem", "unknown_card"};
const char * const resetReasons[] = {"ok", "unknown_user", "device_busy", "invalid_pin", "pin_in_use", "storage_error"};
// Contadores enviados no heartbeat; saturam em UINT32_MAX e são zerados só no reboot.
// rejected: descartes no estágio evento; photo_rejected: descartes no estágio foto (evento já aceito).
// dropped: reservado; nenhum caminho incrementa hoje (fila cheia não confirma ao Mega, que retransmite).
constexpr uint8_t kPermanentRejectLimit = 5;
uint32_t droppedEvents = 0, rejectedItems = 0, photoRejected = 0;
void bump(uint32_t &v) { if (v != UINT32_MAX) ++v; }
// cam_boot_id: 8 hex minúsculos gerados uma vez no setup() (initCamBootId); distinto de boot_id, que é o boot do Mega.
char camBootId[9] = "";
void formatCamBootId(uint32_t random, char *out, size_t size) { snprintf(out, size, "%08lx", (unsigned long)random); }
void initCamBootId() { formatCamBootId(esp_random(), camBootId, sizeof camBootId); }
void eventId(const EventData &e, char *out, size_t size) {
  snprintf(out, size, "%s-%08lx-%lu", DEVICE_ID, (unsigned long)e.boot, (unsigned long)e.messageId);
}
bool startCamera() {
  camera_config_t c = {};
  c.pin_pwdn=32; c.pin_reset=-1; c.pin_xclk=0; c.pin_sccb_sda=26; c.pin_sccb_scl=27;
  c.pin_d7=35; c.pin_d6=34; c.pin_d5=39; c.pin_d4=36; c.pin_d3=21; c.pin_d2=19; c.pin_d1=18; c.pin_d0=5;
  c.pin_vsync=25; c.pin_href=23; c.pin_pclk=22; c.xclk_freq_hz=20000000;
  c.ledc_timer=LEDC_TIMER_0; c.ledc_channel=LEDC_CHANNEL_0; c.pixel_format=PIXFORMAT_JPEG;
  c.frame_size=FRAMESIZE_QVGA; c.jpeg_quality=15; c.fb_count=1;
  c.fb_location=psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  c.grab_mode=CAMERA_GRAB_WHEN_EMPTY;
  esp_err_t err = esp_camera_init(&c);
  if (err == ESP_OK) return true;
#ifdef ARDUINO
  Serial.printf("CAM: camera falhou (%s)\n", esp_err_to_name(err));
#endif
  return false;
}
#if defined(ARDUINO) && defined(ESP_ARDUINO_VERSION_MAJOR) && defined(OTA_PASSWORD)
// Gravação do Mega pela rede: POST http://controle-cam.local:8081/mega (Digest, usuário "admin",
// senha OTA_PASSWORD), corpo binário da flash e headers X-Image-SHA256 e X-Image-MAC. Porta 8081: o
// servidor Python usa 8080 no Mac e a ArduinoOTA usa 3232 na CAM.
// X-Image-MAC = HMAC-SHA256(chave OTA_PASSWORD, sha256 do corpo em hex minúsculo), em hex. O Digest
// do WebServer não renova o nonce após um acesso aceito nem confere nc, então um pedido capturado
// poderia ser reenviado com outro corpo; o MAC amarra o pedido ao conteúdo. Sem MAC ou MAC errado:
// 403 sem gravar. Falha de autenticação (Digest com Authorization presente, ou MAC) espera 1 s.
// Respostas reconhecíveis (JSON com ok, tentativas, bytes, ms, etapa, motivo):
//   401 desafio Digest (senha errada ou sem Authorization);
//   400 etapa "sonda": POST autenticado com corpo vazio; confirma a senha sem gravar nada;
//   409 OTA da própria CAM em andamento; 403 MAC ausente ou errado; 413 tamanho; 200/502 gravação.
// Falha final (502): o Mega recebe um pulso de reset e fica com a flash parcial (páginas gravadas
// até a falha) rodando; recupere regravando, pela CAM ou pela USB.
// Modelo de tarefas: o WebServer roda numa tarefa própria ("mega-prog", núcleo 1, prioridade 1).
// A gravação é síncrona dentro dela (~1 min por tentativa, até ~4 min com 3), então networkTask (eventos, heartbeat, OTA),
// loop() (link Serial2 com o Mega) e o Wi-Fi (núcleo 0) seguem rodando. O watchdog de tarefas
// vigia a ociosidade do núcleo 0; a tarefa cede CPU a cada espera de byte e a cada página.
constexpr uint16_t kMegaProgPort = 8081;
WebServer megaServer(kMegaProgPort);
volatile bool megaBusy = false;  // gravação em curso; networkTask pausa a ArduinoOTA da CAM enquanto isso
volatile bool camOtaActive = false;  // OTA da CAM em curso (onStart até onEnd/onError); /mega responde 409
struct MegaUpload { bool started, authorized; int refuse; const char *why; uint8_t *image; size_t expected, received; char sha[65], mac[65]; } megaUpload = {};
struct CamMegaPort : MegaProgrammer::Port {
  void write(const uint8_t *data, size_t size) override { Serial1.write(data, size); }
  int read(uint32_t timeoutMs) override {
    uint32_t t = millis();
    for (;;) {
      int c = Serial1.read();
      if (c >= 0) return c;
      if (uint32_t(millis() - t) >= timeoutMs) return -1;
      vTaskDelay(1);
    }
  }
  void flushInput() override { while (Serial1.read() >= 0) {} }
  uint32_t millis() override { return ::millis(); }
  void delayMs(uint32_t ms) override { vTaskDelay(pdMS_TO_TICKS(ms ? ms : 1)); }
  void setReset(bool active) override { digitalWrite(kMegaResetPin, active ? HIGH : LOW); }
  void attemptFailed(uint8_t attempt, MegaProgrammer::Stage stage, const char *reason, uint32_t address) override {
    Serial.printf("MEGA prog: tentativa %u falhou em %s (%s) endereco 0x%05lx\n", (unsigned)attempt,
                  MegaProgrammer::stageName(stage), reason, (unsigned long)address);
  }
  void pageDone(uint32_t done) override { if ((done & 0x3FFF) == 0) Serial.printf("MEGA prog: %lu bytes\n", (unsigned long)done); vTaskDelay(1); }
};
void megaReleaseUpload() {
  free(megaUpload.image);
  megaUpload = {};
  megaBusy = false;
}
// Só Digest: o authenticate(usuário, senha) do WebServer aceitaria também Basic (senha em claro).
bool megaAuthorized() {
  return megaServer.authenticate([](HTTPAuthMethod mode, String user, String *) -> String * {
    return mode == DIGEST_AUTH && user.equalsConstantTime("admin") ? new String(OTA_PASSWORD) : nullptr;
  });
}
bool megaHex64(const String &s) {
  if (s.length() != 64) return false;
  for (char c : s) if (!isxdigit((unsigned char)c)) return false;
  return true;
}
// HMAC-SHA256(OTA_PASSWORD, shaHex) em hex minúsculo; false se o mbedtls falhar.
bool megaExpectedMac(const char *shaHex, char out[65]) {
  const mbedtls_md_info_t *md = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  uint8_t mac[32];
  if (!md || mbedtls_md_hmac(md, reinterpret_cast<const uint8_t *>(OTA_PASSWORD), sizeof(OTA_PASSWORD) - 1,
                             reinterpret_cast<const uint8_t *>(shaHex), 64, mac) != 0) return false;
  for (uint8_t i = 0; i < 32; ++i) snprintf(out + 2 * i, 3, "%02x", mac[i]);
  return true;
}
// Recebe o corpo em blocos (antes do handler); confere senha, tamanho e header logo no início.
void megaRaw() {
  String type = megaServer.header("Content-Type");
  if (type.startsWith("multipart/")) return;  // upload de formulário não passa por aqui
  HTTPRaw &raw = megaServer.raw();
  if (raw.status == RAW_START) {
    // O WebServer atende um cliente por vez nesta tarefa: um segundo POST espera na fila TCP e
    // só começa depois da resposta do primeiro, então nunca há duas gravações ao mesmo tempo.
    // Sobra de um pedido anterior que não chegou ao handler é liberada aqui.
    if (megaUpload.image) megaReleaseUpload();
    megaUpload = {}; megaUpload.started = true;
    megaUpload.authorized = megaAuthorized();
    if (!megaUpload.authorized) return;
    int length = megaServer.clientContentLength();
    String sha = megaServer.header("X-Image-SHA256"), mac = megaServer.header("X-Image-MAC");
    if (camOtaActive) { megaUpload.refuse = 409; megaUpload.why = "OTA da CAM em andamento"; return; }
    // Sonda do script: senha conferida, corpo vazio; nada é alocado nem gravado.
    if (length == 0) { megaUpload.refuse = 400; megaUpload.why = "senha ok; corpo vazio"; return; }
    if (length < 0 || uint32_t(length) > MegaProgrammer::kMaxImage) { megaUpload.refuse = 413; megaUpload.why = "tamanho invalido"; return; }
    if (!megaHex64(sha)) { megaUpload.refuse = 400; megaUpload.why = "X-Image-SHA256 ausente ou invalido"; return; }
    if (!megaHex64(mac)) { megaUpload.refuse = 403; megaUpload.why = "X-Image-MAC ausente ou invalido"; return; }
    if (!psramFound()) { megaUpload.refuse = 503; megaUpload.why = "sem PSRAM"; return; }
    megaUpload.image = static_cast<uint8_t *>(ps_malloc(length));
    if (!megaUpload.image) { megaUpload.refuse = 503; megaUpload.why = "sem memoria"; return; }
    megaUpload.expected = length;
    sha.toLowerCase(); memcpy(megaUpload.sha, sha.c_str(), 65);
    mac.toLowerCase(); memcpy(megaUpload.mac, mac.c_str(), 65);
    Serial.printf("MEGA prog: recebendo %d bytes\n", length);
  } else if (raw.status == RAW_WRITE) {
    if (megaUpload.image && megaUpload.received + raw.currentSize <= megaUpload.expected) {
      memcpy(megaUpload.image + megaUpload.received, raw.buf, raw.currentSize);
      megaUpload.received += raw.currentSize;
    }
  } else if (raw.status == RAW_ABORTED) {
    Serial.println("MEGA prog: envio interrompido");
    if (megaUpload.image) megaReleaseUpload(); else megaUpload = {};
  }
}
void megaReply(int code, bool ok, uint8_t attempts, uint32_t bytes, uint32_t ms, const char *stage, const char *reason) {
  JsonDocument doc; doc["ok"]=ok; doc["tentativas"]=attempts; doc["bytes"]=bytes; doc["ms"]=ms; doc["etapa"]=stage; doc["motivo"]=reason;
  String body; serializeJson(doc, body);
  megaServer.send(code, "application/json", body);
  Serial.printf("MEGA prog: HTTP %d %s\n", code, body.c_str());
}
void megaHandle() {
  if (!megaUpload.started) { megaReply(400, false, 0, 0, 0, "recebimento", "corpo binario esperado"); return; }
  if (!megaUpload.authorized) {
    megaUpload = {};
    // Sem Authorization é só o pedido do desafio; com ele, é senha errada: atrasa tentativas em série.
    if (megaServer.hasHeader("Authorization")) vTaskDelay(pdMS_TO_TICKS(1000));
    megaServer.requestAuthentication(DIGEST_AUTH, "controle-cam");
    return;
  }
  if (megaUpload.refuse) {
    int code = megaUpload.refuse; const char *why = megaUpload.why; megaReleaseUpload();
    if (code == 403) vTaskDelay(pdMS_TO_TICKS(1000));
    megaReply(code, false, 0, 0, 0, code == 400 && megaServer.clientContentLength() == 0 ? "sonda" : "recebimento", why);
    return;
  }
  uint32_t size = megaUpload.expected;
  if (megaUpload.received != size) { megaReleaseUpload(); megaReply(400, false, 0, size, 0, "recebimento", "corpo incompleto"); return; }
  uint8_t digest[32]; char hex[65];
  if (mbedtls_sha256(megaUpload.image, size, digest, 0) != 0) { megaReleaseUpload(); megaReply(500, false, 0, size, 0, "recebimento", "falha no sha256"); return; }
  for (uint8_t i = 0; i < 32; ++i) snprintf(hex + 2 * i, 3, "%02x", digest[i]);
  if (memcmp(hex, megaUpload.sha, 64) != 0) { megaReleaseUpload(); megaReply(400, false, 0, size, 0, "recebimento", "sha256 diferente"); return; }
  // MAC sobre o sha calculado aqui (igual ao do header após a conferência acima), em tempo constante.
  char expectedMac[65];
  if (!megaExpectedMac(hex, expectedMac)) { megaReleaseUpload(); megaReply(500, false, 0, size, 0, "recebimento", "falha no hmac"); return; }
  if (!MegaProgrammer::constantTimeEqual(expectedMac, megaUpload.mac, 64)) {
    megaReleaseUpload(); vTaskDelay(pdMS_TO_TICKS(1000));
    megaReply(403, false, 0, size, 0, "recebimento", "X-Image-MAC errado"); return;
  }
  // megaBusy antes de olhar a OTA: a networkTask para de chamar ArduinoOTA.handle() a partir daqui.
  megaBusy = true;
  if (camOtaActive) { megaReleaseUpload(); megaReply(409, false, 0, size, 0, "recebimento", "OTA da CAM em andamento"); return; }
  Serial.printf("MEGA prog: imagem %lu bytes, sha256 e mac ok; gravando\n", (unsigned long)size);
  // UART1 só durante a gravação: fora dela IO2 fica em entrada para não disputar com a USB do Mega.
  Serial1.setRxBufferSize(1024);
  Serial1.begin(115200, SERIAL_8N1, kMegaRxPin, kMegaTxPin);
  uint32_t started = millis();
  static CamMegaPort port;
  static MegaProgrammer::Programmer programmer(port);
  MegaProgrammer::Result r = programmer.program(megaUpload.image, size);
  uint32_t elapsed = millis() - started;
  Serial1.end();
  pinMode(kMegaTxPin, INPUT); pinMode(kMegaRxPin, INPUT);
  digitalWrite(kMegaResetPin, LOW);
  megaReleaseUpload();
  // 502: o Mega já levou o pulso de reset e roda a flash parcial; só regravar recupera.
  megaReply(r.ok ? 200 : 502, r.ok, r.attempts, r.bytes, elapsed, MegaProgrammer::stageName(r.stage), r.reason);
  static bool stackLogged = false;
  if (!stackLogged) {
    stackLogged = true;
    Serial.printf("MEGA prog: pilha livre minima %u bytes\n", (unsigned)uxTaskGetStackHighWaterMark(nullptr));
  }
}
void megaServerTask(void *) {
  // Espera o Wi-Fi da networkTask antes de abrir a porta.
  while (WiFi.status() != WL_CONNECTED) vTaskDelay(pdMS_TO_TICKS(500));
  const char *headers[] = {"X-Image-SHA256", "X-Image-MAC", "Content-Type"};
  megaServer.collectHeaders(headers, 3);
  megaServer.on("/mega", HTTP_POST, megaHandle, megaRaw);
  megaServer.begin();
  Serial.printf("CAM gravacao do Mega pronta na porta %u\n", (unsigned)kMegaProgPort);
  for (;;) { megaServer.handleClient(); vTaskDelay(pdMS_TO_TICKS(2)); }
}
#endif
// Uma foto permanece privada e sem associação até prova do Mega. Apenas um
// evento fica em trânsito, pois o Mega mantém a cabeça da fila até o ACK.
struct PendingPhoto { bool active; Item item; uint8_t challenge[26]; uint32_t started; } pendingPhoto = {};
void finishPendingPhoto(bool proven) {
  if (!pendingPhoto.active) return;
  Item item = pendingPhoto.item;
  if (!proven) { free(item.photo); item.photo = nullptr; item.photoSize = 0; }
  // Sem ACK na falha de fila: o Mega reenvia o evento, então não é perda.
  if (xQueueSend(events, &item, 0) != pdTRUE) { free(item.photo); pendingPhoto.active = false; return; }
  lastBoot = item.event.boot; lastEvent = item.event.messageId;
  uint8_t ack[10] = {kVersion,Ack}; put32(ack+2,lastEvent); put32(ack+6,lastBoot);
  SerialFrame::send(Serial2,ack,sizeof ack);
  pendingPhoto.active = false;
}
void photoTick() {
  if (pendingPhoto.active && uint32_t(millis() - pendingPhoto.started) >= 5000)
    finishPendingPhoto(false);
}
void receivePhotoProof(const uint8_t *data, uint16_t size) {
  if (!pendingPhoto.active || size != sizeof pendingPhoto.challenge || data[1] != PhotoProof) return;
  if (uint32_t(millis() - pendingPhoto.started) >= 5000) { finishPendingPhoto(false); return; }
  // A comparação inclui identidade do evento, boot e 128 bits aleatórios.
  if (memcmp(data+2, pendingPhoto.challenge+2, sizeof pendingPhoto.challenge-2) == 0)
    finishPendingPhoto(true);
}
void receiveEvent(const uint8_t *data, uint16_t size, uint32_t receivedAt) {
  (void)receivedAt;
  if (!networkReady) return;
  EventData e;
  if (!decodeEvent(data, size, e)) return;
  if (e.boot == lastBoot && e.messageId == lastEvent) {
    uint8_t ack[10]={kVersion,Ack}; put32(ack+2,e.messageId); put32(ack+6,e.boot);
    SerialFrame::send(Serial2,ack,sizeof ack); return;
  }
  if (pendingPhoto.active || uxQueueSpacesAvailable(events) == 0) return;
  Item item = {}; item.event = e;
  if (e.kind == AccessGranted && cameraReady && uint32_t(e.sentUptime - e.uptime) <= 5000) {
    camera_fb_t *stale = esp_camera_fb_get();
    if (stale) esp_camera_fb_return(stale);
    camera_fb_t *frame = stale ? esp_camera_fb_get() : nullptr;
    if (frame) {
      if (frame->format == PIXFORMAT_JPEG && frame->len <= 256 * 1024) {
        item.photo = static_cast<uint8_t *>(psramFound() ? ps_malloc(frame->len) : malloc(frame->len));
        if (item.photo) { item.photoSize = frame->len; memcpy(item.photo,frame->buf,frame->len); }
      }
      esp_camera_fb_return(frame);
    }
    if (item.photo) {
      pendingPhoto.active = true; pendingPhoto.item = item;
      uint8_t *challenge = pendingPhoto.challenge;
      challenge[0] = kVersion; challenge[1] = PhotoChallenge;
      put32(challenge+2,e.messageId); put32(challenge+6,e.boot);
      for (uint8_t i=10; i<26; i+=4) put32(challenge+i,esp_random());
      pendingPhoto.started = millis();
      SerialFrame::send(Serial2,challenge,sizeof pendingPhoto.challenge);
      return;
    }
  }
  // Sem ACK na falha de fila: o Mega reenvia o evento, então não é perda.
  if (xQueueSend(events,&item,0) != pdTRUE) { free(item.photo); return; }
  lastBoot=e.boot; lastEvent=e.messageId;
  uint8_t ack[10]={kVersion,Ack}; put32(ack+2,e.messageId); put32(ack+6,e.boot);
  SerialFrame::send(Serial2,ack,sizeof ack);
}
// SERVER_URL em https:// (servidor na nuvem atrás do Caddy): TLS com as raízes de ServerCA.h.
// Um único cliente TLS, reaproveitado entre pedidos (keep-alive do Caddy), para não refazer o
// handshake (1 a 2 s e uns 40 KB de heap) a cada poll de 3 s. Só a networkTask usa.
// O HTTPClient do caminho TLS também é estático: ~HTTPClient() chama stop() no cliente e
// fecharia a conexão a cada pedido. end() limpa os cabeçalhos, então não acumulam.
// Em http:// (LAN) nada muda: cliente novo e prazos curtos por pedido.
#if defined(ARDUINO) && defined(ESP_ARDUINO_VERSION_MAJOR)
WiFiClientSecure &secureClient() {
  static WiFiClientSecure tls; static bool configured=false;
  if (!configured) { tls.setCACert(SERVER_CA_PEM); tls.setHandshakeTimeout(8); configured=true; }
  return tls;
}
// Falha de transporte em TLS: erro do mbedtls e heap livre na serial, no máximo a cada 10 s.
void reportTlsFailure(int code) {
  static uint32_t last=0; static bool any=false;
  if (code>=0 || (any && uint32_t(millis()-last)<10000)) return;
  any=true; last=millis(); char text[96]={0};
  int err=secureClient().lastError(text,sizeof text);
  Serial.printf("CAM tls: falha %d, mbedtls %d (%s), heap %u, maior bloco %u\n",code,err,text,
    (unsigned)ESP.getFreeHeap(),(unsigned)ESP.getMaxAllocHeap());
}
#endif
int request(const char *path, const String &body, String &response) {
  const bool tls=strncmp(SERVER_URL,"https://",8)==0;
  WiFiClient client; HTTPClient local;
#if defined(ARDUINO) && defined(ESP_ARDUINO_VERSION_MAJOR)
  static HTTPClient shared; HTTPClient &http=tls ? shared : local;
  WiFiClient &link=tls ? (WiFiClient &)secureClient() : client;
#else
  HTTPClient &http=local; WiFiClient &link=client;
#endif
  http.setConnectTimeout(tls ? 5000 : 600); http.setTimeout(tls ? 5000 : 900);
  if (!http.begin(link,String(SERVER_URL)+path)) return -1;
  http.addHeader("X-Device-Key",DEVICE_KEY);
  int code;
  if (body.length()) { http.addHeader("Content-Type","application/json"); code=http.POST(body); }
  else code=http.GET();
  if (code > 0) response=http.getString(); http.end();
#if defined(ARDUINO) && defined(ESP_ARDUINO_VERSION_MAJOR)
  if (tls) reportTlsFailure(code);
#endif
  return code;
}
bool sendEvent(const Item &item, int *status = nullptr) {
  char id[73], boot[16]; eventId(item.event,id,sizeof id);
  snprintf(boot,sizeof boot,"%08lx",(unsigned long)item.event.boot);
  JsonDocument doc; doc["event_id"]=id; doc["device"]=DEVICE_ID; doc["boot_id"]=boot;
  doc["type"]=eventNames[item.event.kind]; doc["method"]=methodNames[item.event.method];
  doc["user_id"]=item.event.user; doc["active"]=bool(item.event.active);
  doc["reason"] = item.event.kind == AccessGranted && !item.photo ? "photo_unavailable" :
    (item.event.reason < 18 ? reasonNames[item.event.reason] : "");
  doc["uptime_ms"]=item.event.uptime;
  if (item.event.epoch) doc["epoch"]=item.event.epoch; else doc["epoch"]=nullptr;
  String body,response; serializeJson(doc,body); JsonDocument ack;
  int code=request("/api/device/events",body,response);
  bool accepted=code==200 && !deserializeJson(ack,response) && ack["accepted"].as<String>()==id;
  if (status) *status=accepted ? 0 : (code==200 ? -10000 : code);
  return accepted;
}
bool sendPhoto(const Item &item, int *status = nullptr) {
  if (status) *status=0;
  if (!item.photo) return true;
  char id[73]; eventId(item.event,id,sizeof id);
  const bool tls=strncmp(SERVER_URL,"https://",8)==0;
  WiFiClient client; HTTPClient local;
#if defined(ARDUINO) && defined(ESP_ARDUINO_VERSION_MAJOR)
  static HTTPClient shared; HTTPClient &http=tls ? shared : local;
  WiFiClient &link=tls ? (WiFiClient &)secureClient() : client;
#else
  HTTPClient &http=local; WiFiClient &link=client;
#endif
  http.setConnectTimeout(tls ? 5000 : 600); http.setTimeout(tls ? 8000 : 1500);
  if (!http.begin(link,String(SERVER_URL)+"/api/device/photo")) { if (status) *status=-1; return false; }
  http.addHeader("X-Device-Key",DEVICE_KEY); http.addHeader("X-Event-Id",id); http.addHeader("Content-Type","image/jpeg");
  int code=http.POST(item.photo,item.photoSize); String body=code>0 ? http.getString() : ""; http.end();
#if defined(ARDUINO) && defined(ESP_ARDUINO_VERSION_MAJOR)
  if (tls) reportTlsFailure(code);
#endif
  JsonDocument ack; bool accepted=code==200 && !deserializeJson(ack,body) && ack["accepted"].as<String>()==id;
  if (status) *status=accepted ? 0 : (code==200 ? -10000 : code);
  return accepted;
}
// Só erros por item são permanentes. 401/403/404 e demais 4xx costumam ser chave, rota ou proxy errados: o item fica na fila.
constexpr uint32_t kPermanentRejectWindowMs = 30000;
constexpr uint32_t kPermanentRetryDelayMs = 2000; // espera antes de reenviar o mesmo item rejeitado (sem descarte)
bool isPermanentStatus(int status) { return status == 400 || status == 409 || status == 413 || status == 422; }
// NTP falha sem internet IPv4; usa a hora do servidor. Não mexe no relógio já sincronizado.
bool applyServerTime(const String &response) {
  if (time(nullptr)>=1700000000) return false;
  JsonDocument doc; if (deserializeJson(doc,response)) return false;
  JsonVariant v=doc["server_time"];
  if (!v.is<uint32_t>() || v.as<uint32_t>()<1700000000) return false;
  struct timeval tv={(time_t)v.as<uint32_t>(),0}; settimeofday(&tv,nullptr);
  return true;
}
void networkTask(void *) {
  // Sem economia de energia do Wi-Fi: com o Compartilhamento de Internet do Mac a CAM deixava de receber pacotes.
  WiFi.mode(WIFI_STA); WiFi.setSleep(false); WiFi.setAutoReconnect(true); WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
  configTime(0,0,"pool.ntp.org","time.google.com");
  uint32_t lastPoll=0,lastHeartbeat=0,lastRetry=0,lastDiagnostic=0; bool sentEvent=false, reportedFailure=false;
  uint32_t rejectStreak=0, rejectSince=0, streakBoot=0, streakId=0;
  bool holdRetry=false; uint32_t retryHoldFrom=0; // retryHoldFrom: millis() da última rejeição permanente
  for (;;) {
    static bool wifiWasUp=false;
    bool wifiUp=WiFi.status()==WL_CONNECTED;
#if defined(ARDUINO) && defined(ESP_ARDUINO_VERSION_MAJOR)
    if (wifiUp!=wifiWasUp) {
      wifiWasUp=wifiUp;
      if (wifiUp) Serial.printf("CAM wifi conectado %s\n", WiFi.localIP().toString().c_str());
      else Serial.println("CAM wifi desconectado");
    }
#endif
#if defined(ARDUINO) && defined(ESP_ARDUINO_VERSION_MAJOR) && defined(OTA_PASSWORD)
    static bool otaStarted=false;
    if (wifiUp && !otaStarted) {
      otaStarted=true;
      ArduinoOTA.setHostname("controle-cam"); ArduinoOTA.setPassword(OTA_PASSWORD);
      ArduinoOTA.onStart([]() { camOtaActive = true; Serial.println("CAM ota inicio"); });
      ArduinoOTA.onEnd([]() { camOtaActive = false; Serial.println("CAM ota fim"); });
      ArduinoOTA.onError([](ota_error_t e) { camOtaActive = false; Serial.printf("CAM ota erro %u\n", (unsigned)e); });
      ArduinoOTA.begin(); Serial.println("CAM ota pronta controle-cam");
    }
    if (otaStarted && wifiUp && !megaBusy) ArduinoOTA.handle(); // sem OTA da CAM no meio da gravação do Mega
#endif
    if (!wifiUp) {
      if (uxQueueMessagesWaiting(events) && (!reportedFailure || uint32_t(millis()-lastDiagnostic)>=10000)) {
#ifdef ARDUINO
        Serial.println("Fila CAM: rede indisponivel; item mantido para reenvio");
#endif
        reportedFailure=true; lastDiagnostic=millis();
      }
      rejectStreak=0; rejectSince=0; // série de rejeições só vale com conectividade contínua
      if (uint32_t(millis()-lastRetry)>15000) { WiFi.reconnect(); lastRetry=millis(); } vTaskDelay(pdMS_TO_TICKS(100)); continue;
    }
    Item item;
    bool holding=holdRetry && uint32_t(millis()-retryHoldFrom)<kPermanentRetryDelayMs;
    if (!holding && xQueuePeek(events,&item,0)==pdTRUE) {
      if (item.event.boot!=streakBoot || item.event.messageId!=streakId) { streakBoot=item.event.boot; streakId=item.event.messageId; rejectStreak=0; }
      int status=0; const char *stage="evento";
      if (!sentEvent) sentEvent=sendEvent(item,&status);
      bool sentPhoto=false;
      if (sentEvent) { stage="foto"; sentPhoto=sendPhoto(item,&status); }
      bool permanent=!(sentEvent && sentPhoto) && isPermanentStatus(status);
      if (!permanent) rejectStreak=0;
      else { if (!rejectStreak) rejectSince=millis(); bump(rejectStreak); }
      holdRetry=permanent; if (permanent) retryHoldFrom=millis();
      if (sentEvent && sentPhoto) {
        char id[73]; eventId(item.event,id,sizeof id);
#ifdef ARDUINO
        if (item.event.kind==AccessGranted && !item.photo) Serial.printf("Fila CAM: %s sem foto disponivel\n",id);
        if (reportedFailure) Serial.printf("Fila CAM: %s entregue apos falha\n",id);
#endif
        xQueueReceive(events,&item,0); free(item.photo); sentEvent=false; reportedFailure=false;
      } else if (permanent && rejectStreak>=kPermanentRejectLimit && uint32_t(millis()-rejectSince)>=kPermanentRejectWindowMs) {
        char id[73]; eventId(item.event,id,sizeof id);
        xQueueReceive(events,&item,0); free(item.photo);
        if (sentEvent) bump(photoRejected); else bump(rejectedItems);
        const unsigned long seconds=(millis()-rejectSince)/1000;
        sentEvent=false; reportedFailure=false; rejectStreak=0; holdRetry=false;
#ifdef ARDUINO
        Serial.printf("Fila CAM: %s DESCARTADO apos %d rejeicoes HTTP permanentes em %s (%d) em %lu s; item liberado, proximo da fila segue\n",id,kPermanentRejectLimit,stage,status,seconds);
#endif
      } else if (!reportedFailure || uint32_t(millis()-lastDiagnostic)>=10000) {
        char id[73]; eventId(item.event,id,sizeof id);
        const char *kind = status == -10000 ? "confirmacao invalida" : status <= 0 ? "rede/transporte" :
          isPermanentStatus(status) ? "HTTP rejeitado (possivelmente permanente)" :
          (status == 401 || status == 403 || status == 404) ? "HTTP rejeitado (possivel erro de configuracao: chave, rota ou proxy)" :
          (status >= 400 && status < 500 && status != 408 && status != 429) ? "HTTP rejeitado (4xx transitorio)" : "HTTP temporario ou inesperado";
#ifdef ARDUINO
        Serial.printf("Fila CAM: %s %s: %s (%d); item mantido para reenvio\n",id,stage,kind,status);
#endif
        reportedFailure=true; lastDiagnostic=millis();
      }
    }
    // Reset commands are polled below; application is confirmed only by Mega's result.
    Result result;
    if (xQueuePeek(results,&result,0)==pdTRUE) {
      JsonDocument doc; doc["device"]=DEVICE_ID; doc["command_id"]=result.id; doc["ok"]=result.ok;
      doc["reason"]=result.reason < 6 ? resetReasons[result.reason] : "storage_error";
      String body,response; serializeJson(doc,body); JsonDocument ack;
      int code=request("/api/device/command-result",body,response);
      if (code==200 && !deserializeJson(ack,response) && ack["accepted"].as<uint32_t>()==result.id) xQueueReceive(results,&result,0);
      else if (code==400 || code==404) {
        // Rejeição definitiva do servidor: sem descarte, este resultado bloquearia novos comandos.
        xQueueReceive(results,&result,0);
#ifdef ARDUINO
        Serial.printf("CAM: resultado de reset %lu descartado (HTTP %d)\n",(unsigned long)result.id,code);
#endif
      }
    } else if (uint32_t(millis()-lastPoll)>=3000 && uxQueueMessagesWaiting(commands)==0) {
      lastPoll=millis(); String response;
      if (request((String("/api/device/command?device=")+DEVICE_ID).c_str(),"",response)==200) {
        JsonDocument doc;
        if (!deserializeJson(doc,response) && !doc["command"].isNull()) {
          Command c={}; c.id=doc["command"]["id"].as<uint32_t>(); c.user=doc["command"]["user_id"].as<uint8_t>();
          String pin=doc["command"]["pin"].as<String>(), token=doc["command"]["token"].as<String>();
          char *end=nullptr; c.token=strtoull(token.c_str(),&end,16);
          if (c.id && c.user>=1 && c.user<=100 && pin.length()==6 && token.length()==16 && c.token && end && *end=='\0') {
            memcpy(c.pin,pin.c_str(),6); xQueueSend(commands,&c,0);
          }
        }
      }
    }
    if (uint32_t(millis()-lastHeartbeat)>=10000) {
      lastHeartbeat=millis(); JsonDocument doc; doc["device"]=DEVICE_ID;
      char boot[16]; snprintf(boot,sizeof boot,"%08lx",(unsigned long)lastBoot); doc["boot_id"]=boot;
      doc["cam_boot_id"]=camBootId;
      doc["clock_synced"]=time(nullptr)>=1700000000; doc["queued"]=uxQueueMessagesWaiting(events);
      doc["dropped"]=droppedEvents; doc["rejected"]=rejectedItems; doc["photo_rejected"]=photoRejected;
      String body,response; serializeJson(doc,body);
      if (request("/api/device/heartbeat",body,response)==200) applyServerTime(response);
    }
    vTaskDelay(pdMS_TO_TICKS(100));
  }
}
void setup() {
  // IO12 é strapping e segura o Mega em reset se ficar HIGH: força LOW antes de tudo.
  pinMode(kMegaResetPin, OUTPUT); digitalWrite(kMegaResetPin, LOW);
  pinMode(kMegaTxPin, INPUT); pinMode(kMegaRxPin, INPUT);  // UART1 só durante a gravação
  Serial.begin(115200); Serial2.setRxBufferSize(1024); Serial2.begin(38400,SERIAL_8N1,13,14);
  initCamBootId();
  events=xQueueCreate(8,sizeof(Item)); commands=xQueueCreate(1,sizeof(Command)); results=xQueueCreate(1,sizeof(Result));
  if (!events || !commands || !results) { Serial.println("Falha memoria"); return; }
  cameraReady=startCamera();
#ifdef ARDUINO
  Serial.printf("CAM boot %s camera=%s\n", camBootId, cameraReady ? "ok" : "falha");
#endif
  networkReady = xTaskCreate(networkTask,"rede",10000,nullptr,1,nullptr) == pdPASS;
  if (!networkReady) Serial.println("Falha tarefa de rede");
#if defined(ARDUINO) && defined(ESP_ARDUINO_VERSION_MAJOR) && defined(OTA_PASSWORD)
  if (xTaskCreatePinnedToCore(megaServerTask,"mega-prog",10240,nullptr,1,nullptr,1) != pdPASS) Serial.println("Falha tarefa de gravacao do Mega");
#endif
}
void loop() {
  if (!events || !commands || !results) { delay(100); return; }
  photoTick();
  while (Serial2.available()) if (parser.feed(Serial2.read(),millis())) {
    const uint8_t *p=parser.data(); uint16_t n=parser.size();
    if (n && p[1]==Event) receiveEvent(p,n,parser.startedAt());
    else if (n && p[1]==PhotoProof) receivePhotoProof(p,n);
    else if (n==8 && p[1]==ResetResult) {
      Command c; if (xQueuePeek(commands,&c,0)==pdTRUE && c.id==get32(p+2) && uxQueueSpacesAvailable(results)) {
        Result r={c.id,bool(p[6]),p[7]}; xQueueSend(results,&r,0); xQueueReceive(commands,&c,0);
      }
    }
  }
  static uint32_t commandAt=0, clockAt=0;
  Command c;
  if (xQueuePeek(commands,&c,0)==pdTRUE && uint32_t(millis()-commandAt)>=1000) {
    commandAt=millis(); uint8_t bytes[21]={kVersion,Reset}; put32(bytes+2,c.id); bytes[6]=c.user; memcpy(bytes+7,c.pin,6);
    for (uint8_t i=0;i<8;++i) bytes[13+i]=uint8_t(c.token>>(8*i)); SerialFrame::send(Serial2,bytes,sizeof bytes);
  }
  if (uint32_t(millis()-clockAt)>=10000) {
    clockAt=millis(); time_t now=time(nullptr);
    if (now>=1700000000) { uint8_t bytes[10]={kVersion,Clock}; put32(bytes+2,1); put32(bytes+6,uint32_t(now)); SerialFrame::send(Serial2,bytes,sizeof bytes); }
  }
  delay(5);
}
