/* PROTÓTIPO EM DESENVOLVIMENTO. Não usar para controlar fechadura. */
#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <esp_camera.h>
#include <esp_system.h>
#include <time.h>
#include "Config.h"
#include "SerialFrame.h"
#include "MessageProtocol.h"
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
const char * const eventNames[] = {"", "device_boot", "storage_error", "user_snapshot", "user_enrolled", "user_disabled", "user_enabled", "password_reset", "admin_login", "access_granted", "access_denied", "door_opened", "door_closed", "entry_expired", "door_timeout", "forced_open", "enroll_failed"};
const char * const methodNames[] = {"", "password", "fingerprint", "admin", "keypad", "system", "sensor", "usb", "web"};
const char * const reasonNames[] = {"", "inactive_or_unknown", "invalid_pin", "unknown_finger", "sensor_error", "simulation", "actuator_enabled", "open_at_boot", "Erro de hash", "Erro ao gravar DY", "Erro na memoria", "Erro de leitura", "Digital ilegivel", "Digital ja usada", "Slot DY orfao", "Falha na pesquisa", "Digitais diferem"};
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
int request(const char *path, const String &body, String &response) {
  WiFiClient client; HTTPClient http; http.setConnectTimeout(600); http.setTimeout(900);
  if (!http.begin(client,String(SERVER_URL)+path)) return -1;
  http.addHeader("X-Device-Key",DEVICE_KEY);
  int code;
  if (body.length()) { http.addHeader("Content-Type","application/json"); code=http.POST(body); }
  else code=http.GET();
  if (code > 0) response=http.getString(); http.end(); return code;
}
bool sendEvent(const Item &item, int *status = nullptr) {
  char id[73], boot[16]; eventId(item.event,id,sizeof id);
  snprintf(boot,sizeof boot,"%08lx",(unsigned long)item.event.boot);
  JsonDocument doc; doc["event_id"]=id; doc["device"]=DEVICE_ID; doc["boot_id"]=boot;
  doc["type"]=eventNames[item.event.kind]; doc["method"]=methodNames[item.event.method];
  doc["user_id"]=item.event.user; doc["active"]=bool(item.event.active);
  doc["reason"] = item.event.kind == AccessGranted && !item.photo ? "photo_unavailable" :
    (item.event.reason < 17 ? reasonNames[item.event.reason] : "");
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
  WiFiClient client; HTTPClient http; http.setConnectTimeout(600); http.setTimeout(1500);
  if (!http.begin(client,String(SERVER_URL)+"/api/device/photo")) { if (status) *status=-1; return false; }
  http.addHeader("X-Device-Key",DEVICE_KEY); http.addHeader("X-Event-Id",id); http.addHeader("Content-Type","image/jpeg");
  int code=http.POST(item.photo,item.photoSize); String body=code>0 ? http.getString() : ""; http.end();
  JsonDocument ack; bool accepted=code==200 && !deserializeJson(ack,body) && ack["accepted"].as<String>()==id;
  if (status) *status=accepted ? 0 : (code==200 ? -10000 : code);
  return accepted;
}
// Só erros por item são permanentes. 401/403/404 e demais 4xx costumam ser chave, rota ou proxy errados: o item fica na fila.
constexpr uint32_t kPermanentRejectWindowMs = 30000;
constexpr uint32_t kPermanentRetryDelayMs = 2000; // espera antes de reenviar o mesmo item rejeitado (sem descarte)
bool isPermanentStatus(int status) { return status == 400 || status == 409 || status == 413 || status == 422; }
void networkTask(void *) {
  WiFi.mode(WIFI_STA); WiFi.setAutoReconnect(true); WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
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
      String body,response; serializeJson(doc,body); request("/api/device/heartbeat",body,response);
    }
    vTaskDelay(pdMS_TO_TICKS(100));
  }
}
void setup() {
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
