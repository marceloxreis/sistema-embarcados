"""Exercita funções reais da CAM (rede, fila, descarte e heartbeat) com dublês."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from library_deps import require_library

ROOT = Path(__file__).resolve().parents[1]
CAM = ROOT / 'firmware/Esp32CamRede'
PREFIX = r'''
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <cstdarg>
#include <cstring>
#include <string>
#include <vector>
#include <map>
#include <functional>
#include <ctime>
#include <cassert>
#include <ArduinoJson.h>
#include "MessageProtocol.h"
using String=std::string; using namespace MessageProtocol;
const char DEVICE_ID[]="porta01", DEVICE_KEY[]="test-key", SERVER_URL[]="http://mock", WIFI_SSID[]="test", WIFI_PASSWORD[]="test";
struct Item { EventData event; uint8_t *photo; size_t photoSize; };
struct Command { uint32_t id; uint8_t user; char pin[7]; uint64_t token; };
struct Result { uint32_t id; bool ok; uint8_t reason; };
template <class T> struct Queue { std::vector<T> entries; size_t capacity; explicit Queue(size_t c=8):capacity(c) {} };
Queue<Item> eventQueue; Queue<Command> commandQueue(1); Queue<Result> resultQueue(1);
auto *events=&eventQueue; auto *commands=&commandQueue; auto *results=&resultQueue;
constexpr int pdTRUE=1;
int forcedSendFailures=0;
template<class T> int xQueuePeek(Queue<T> *q,T *out,int) { if(q->entries.empty()) return 0; *out=q->entries.front(); return 1; }
template<class T> int xQueueReceive(Queue<T> *q,T *out,int) { if(!xQueuePeek(q,out,0)) return 0; q->entries.erase(q->entries.begin()); return 1; }
template<class T> int xQueueSend(Queue<T> *q,T *item,int) {
 if(forcedSendFailures>0) { --forcedSendFailures; return 0; }
 if(q->entries.size()>=q->capacity) return 0;
 q->entries.push_back(*item); return 1;
}
template<class T> unsigned uxQueueMessagesWaiting(Queue<T> *q) { return q->entries.size(); }
template<class T> unsigned uxQueueSpacesAvailable(Queue<T> *q) { return q->capacity-q->entries.size(); }
uint32_t ticks=0, lastBoot=1, lastEvent=0; unsigned cycles=0, eventCalls=0, photoCalls=0, resultCalls=0, stopAt=12;
bool commandMode=false, commandDelivered=false, megaApplied=false;
bool cameraReady=false, networkReady=false;
int freeCalls=0;
std::vector<std::vector<uint8_t>> sentFrames;
std::vector<String> heartbeats;
std::function<int(const char*,const String&,String&)> requestOverride;
std::function<int(size_t)> postOverride;
int eventCode=200; bool wrongAck=false; String failingId;
uint32_t millis() { return ticks; }
#define pdMS_TO_TICKS(x) (x)
void vTaskDelay(unsigned n) {
 ticks+=n; ++cycles;
 if(commandMode && cycles==35 && !commandQueue.entries.empty()) {
  Command c=commandQueue.entries.front(); commandQueue.entries.erase(commandQueue.entries.begin());
  assert(c.id==7 && c.user==1 && String(c.pin)=="123456" && c.token==42);
  resultQueue.entries.push_back({c.id,true,0}); megaApplied=true;
 }
 if(cycles==stopAt) throw 1;
}
constexpr int WIFI_STA=1, WL_CONNECTED=3;
uint32_t wifiDownFrom=0, wifiDownUntil=0; // intervalo de millis() sem Wi-Fi (0/0 = sempre conectado após o início)
struct WiFiMock { void mode(int) {} void setAutoReconnect(bool) {} void begin(const char*,const char*) {} int status() { return (cycles<2 || (ticks>=wifiDownFrom && ticks<wifiDownUntil)) ? 0 : WL_CONNECTED; } void reconnect() {} } WiFi;
void configTime(int,int,const char*,const char*) {}
const char * const eventNames[]={"", "device_boot", "storage_error", "user_snapshot", "user_enrolled", "user_disabled", "user_enabled", "password_reset", "admin_login", "access_granted", "access_denied", "door_opened", "door_closed", "entry_expired", "door_timeout", "forced_open", "enroll_failed"};
const char * const methodNames[]={"", "password", "fingerprint", "admin", "keypad", "system", "sensor", "usb", "web"};
const char * const reasonNames[]={"", "inactive_or_unknown", "invalid_pin", "unknown_finger", "sensor_error", "simulation", "actuator_enabled", "open_at_boot", "Erro de hash", "Erro ao gravar DY", "Erro na memoria", "Erro de leitura", "Digital ilegivel", "Digital ja usada", "Slot DY orfao", "Falha na pesquisa", "Digitais diferem"};
const char * const resetReasons[]={"ok", "unknown_user", "device_busy", "invalid_pin", "pin_in_use", "storage_error"};
namespace SerialFrame { template<class S> bool send(S&,const uint8_t *p,uint16_t n) { sentFrames.emplace_back(p,p+n); return true; } }
struct camera_fb_t { uint8_t *buf; size_t len; int format; };
constexpr int PIXFORMAT_JPEG=4;
bool cameraHasFrame=false; uint8_t cameraBytes[8]={1,2,3,4,5,6,7,8}; camera_fb_t cameraFrame={};
camera_fb_t *esp_camera_fb_get() { if(!cameraHasFrame) return nullptr; cameraFrame=camera_fb_t{cameraBytes,sizeof cameraBytes,PIXFORMAT_JPEG}; return &cameraFrame; }
void esp_camera_fb_return(camera_fb_t *) {}
bool psramFound() { return false; }
void *ps_malloc(size_t n) { return malloc(n); }
uint32_t esp_random() { return 0x11223344; }
int request(const char *path,const String &body,String &response) {
 if (requestOverride) { int code=requestOverride(path,body,response); if (code!=-2) return code; }
 if (String(path)=="/api/device/events") {
  ++eventCalls; if(eventCalls<3) return -1;
  JsonDocument doc; assert(!deserializeJson(doc,body)); JsonDocument ack;
  ack["accepted"]=eventCalls==3 ? String("outro-evento") : doc["event_id"].as<String>(); serializeJson(ack,response); return 200;
 }
 if (commandMode && String(path)=="/api/device/command?device=porta01" && !commandDelivered) {
  commandDelivered=true; response="{\"command\":{\"id\":7,\"user_id\":1,\"pin\":\"123456\",\"token\":\"000000000000002a\"}}"; return 200;
 }
 if (commandMode && String(path)=="/api/device/command-result") {
  assert(megaApplied); ++resultCalls; JsonDocument doc; assert(!deserializeJson(doc,body));
  assert(doc["command_id"].as<unsigned>()==7 && doc["ok"].as<bool>());
  response=resultCalls==1 ? "{\"accepted\":8}" : "{\"accepted\":7}"; return 200;
 }
 return -1;
}
struct WiFiClient {};
struct HTTPClient {
 std::map<String,String> headers;
 void setConnectTimeout(int) {} void setTimeout(int) {}
 bool begin(WiFiClient &,const String &) { return true; }
 void addHeader(const char *n,const String &v) { headers[n]=v; }
 int POST(uint8_t *,size_t n) {
  ++photoCalls;
  if (postOverride) { int code=postOverride(n); if (code!=-2) return code; }
  return photoCalls<3 ? -1 : 200;
 }
 String getString() { JsonDocument d; d["accepted"]=photoCalls==3 ? String("outro-evento") : headers["X-Event-Id"]; String s; serializeJson(d,s); return s; }
 void end() {}
};
void releasePhoto(void *p) { if (p) ++freeCalls; ::free(p); }
#define free(p) releasePhoto(p)
'''
# Serial e ARDUINO ficam fora do PREFIX compartilhado (test_erro_fila_agent reutiliza PREFIX com seu próprio Serial).
SERIAL_MOCK = r'''
#define ARDUINO 1
struct SerialMock {
 std::string log;
 void println(const char *s) { log+=s; log+='\n'; }
 void print(const char *s) { log+=s; }
 void printf(const char *f,...) { char b[512]; va_list a; va_start(a,f); vsnprintf(b,sizeof b,f,a); va_end(a); log+=b; }
} Serial, Serial2;
'''
SKETCH_SLICES = [
    ('constexpr uint8_t kPermanentRejectLimit', 'bool startCamera()'),
    ('struct PendingPhoto', 'int request('),
    ('bool sendEvent(', 'void setup()'),
]
CASES = r'''
int main() {
 Item item={}; item.event={9,3,12345,0,AccessGranted,1,Password,1,0,12350};
 item.photo=static_cast<uint8_t *>(malloc(4)); assert(item.photo); item.photoSize=4;
 eventQueue.entries.push_back(item);
 try { networkTask(nullptr); } catch(int) {}
 assert(cycles==12 && eventQueue.entries.empty());
 assert(eventCalls==4 && photoCalls==4);
 ticks=0; cycles=0; commandMode=true; stopAt=45;
 try { networkTask(nullptr); } catch(int) {}
 assert(commandDelivered && megaApplied && resultCalls==2 && resultQueue.entries.empty());
}
'''
CASES_HELPERS = r'''
// Roteiro por tentativa de evento: (código HTTP, avanço de millis() antes da resposta). Vazio = eventResponder.
std::vector<std::pair<int,uint32_t>> script;
Item makeItem(uint32_t id, bool photo) {
 Item item={}; item.event=EventData{id,3,12345,0,AccessGranted,1,Password,1,0,12350};
 if(photo) { item.photo=static_cast<uint8_t *>(malloc(4)); item.photoSize=4; }
 return item;
}
void resetAll() {
 eventQueue.entries.clear(); commandQueue.entries.clear(); resultQueue.entries.clear();
 ticks=0; cycles=0; eventCalls=0; photoCalls=0; resultCalls=0; stopAt=12;
 commandMode=false; commandDelivered=false; megaApplied=false;
 requestOverride=nullptr; postOverride=nullptr; eventCode=200; wrongAck=false; failingId.clear();
 forcedSendFailures=0; freeCalls=0; sentFrames.clear(); heartbeats.clear(); Serial.log.clear(); Serial2.log.clear();
 pendingPhoto.active=false; droppedEvents=0; rejectedItems=0; photoRejected=0; lastBoot=1; lastEvent=0;
 cameraReady=false; cameraHasFrame=false; networkReady=true;
 wifiDownFrom=0; wifiDownUntil=0; script.clear();
}
// Respostas do servidor: só o item em failingId (ou todos, se vazio) recebe eventCode; wrongAck simula ACK divergente.
int eventResponder(const char *path,const String &body,String &response) {
 if (String(path)=="/api/device/heartbeat") { heartbeats.push_back(body); return 200; }
 if (String(path)!="/api/device/events") return -1;
 ++eventCalls;
 JsonDocument doc; assert(!deserializeJson(doc,body)); String id=doc["event_id"].as<String>();
 bool failing=failingId.empty() || id==failingId;
 if (failing && eventCode!=200) return eventCode;
 JsonDocument ack; ack["accepted"]=(failing && wrongAck) ? String("outro-evento") : id;
 serializeJson(ack,response); return 200;
}
int scriptedResponder(const char *path,const String &body,String &response) {
 if (String(path)!="/api/device/events" || script.empty()) return eventResponder(path,body,response);
 auto step=script.front(); script.erase(script.begin());
 ticks+=step.second; ++eventCalls;
 if (step.first!=200) return step.first;
 JsonDocument doc; assert(!deserializeJson(doc,body)); JsonDocument ack; ack["accepted"]=doc["event_id"].as<String>();
 serializeJson(ack,response); return 200;
}
'''
CASES_DROP = CASES_HELPERS + r'''
int main() {
 // Contadores saturam em UINT32_MAX.
 uint32_t saturated=UINT32_MAX-1; bump(saturated); assert(saturated==UINT32_MAX); bump(saturated); assert(saturated==UINT32_MAX);

 // Fila cheia no caminho da foto (xQueueSend em finishPendingPhoto): libera foto, sem ACK e sem contar perda.
 // Não é perda: o Mega retransmite o evento sem ACK, então dropped não sobe (antes contava 1).
 resetAll();
 for(uint32_t i=0;i<8;++i) eventQueue.entries.push_back(makeItem(100+i,false));
 pendingPhoto.active=true; pendingPhoto.item=makeItem(9,true); pendingPhoto.started=0;
 finishPendingPhoto(true);
 assert(droppedEvents==0 && !pendingPhoto.active && sentFrames.empty() && freeCalls==1 && eventQueue.entries.size()==8 && lastEvent==0);

 // Fila cheia na recepção: evento recusado antes de criar item; não é perda contada e não recebe ACK (Mega reenvia).
 resetAll();
 for(uint32_t i=0;i<8;++i) eventQueue.entries.push_back(makeItem(100+i,false));
 uint8_t wire[kEventLength]; assert(encodeEvent(EventData{50,3,1000,0,AccessGranted,1,Password,1,0,1100},wire,sizeof wire));
 receiveEvent(wire,sizeof wire,0);
 assert(droppedEvents==0 && sentFrames.empty() && eventQueue.entries.size()==8 && !pendingPhoto.active);

 // Falha de xQueueSend após aceitar o evento (caminho sem foto): sem ACK e sem item; não é perda (Mega reenvia), dropped segue 0.
 resetAll(); forcedSendFailures=1;
 receiveEvent(wire,sizeof wire,0);
 assert(droppedEvents==0 && sentFrames.empty() && eventQueue.entries.empty() && lastEvent==0);

 // Descarte exige 5 rejeições permanentes (400/409/413/422) E 30 s da primeira à última. Após cada rejeição
 // permanente há espera de 2 s (kPermanentRetryDelayMs): a primeira é em 200 ms e a 16ª tentativa, em 30 200 ms,
 // é a primeira com 30 000 ms. Item seguinte é entregue na tentativa 17; foto liberada uma vez.
 for (int code : {400, 409, 413, 422}) {
  resetAll(); requestOverride=eventResponder; failingId="porta01-00000003-1"; eventCode=code;
  eventQueue.entries.push_back(makeItem(1,true)); eventQueue.entries.push_back(makeItem(2,false));
  stopAt=320;
  try { networkTask(nullptr); } catch(int) {}
  assert(eventQueue.entries.empty() && rejectedItems==1 && photoRejected==0 && droppedEvents==0);
  assert(eventCalls==17 && freeCalls==1);
  assert(Serial.log.find("DESCARTADO apos 5 rejeicoes")!=std::string::npos);
 }

 // Rajada de 5 rejeições (tentativas em 200, 2200, 4200, 6200 e 8200 ms: menos de 30 s) não descarta: o item segue até o servidor aceitar.
 resetAll(); eventQueue.entries.push_back(makeItem(1,false)); stopAt=120;
 int burst=5;
 requestOverride=[&](const char *path,const String &body,String &response)->int {
  if (String(path)=="/api/device/events" && burst>0) { --burst; ++eventCalls; return 400; }
  return eventResponder(path,body,response);
 };
 try { networkTask(nullptr); } catch(int) {}
 assert(eventQueue.entries.empty() && rejectedItems==0 && eventCalls==6 && burst==0);
 assert(Serial.log.find("DESCARTADO")==std::string::npos);

 // Rejeições espaçadas de 10 s (cada resposta avança o relógio em 10 s; a espera de 2 s passa): a janela de 30 s
 // já passa na 4ª, mas o descarte só ocorre na 5ª.
 resetAll(); eventQueue.entries.push_back(makeItem(1,false)); stopAt=600;
 requestOverride=[&](const char *path,const String &body,String &response)->int {
  if (String(path)=="/api/device/events" && eventCalls<5) { ticks+=10000; ++eventCalls; return 400; }
  return eventResponder(path,body,response);
 };
 try { networkTask(nullptr); } catch(int) {}
 assert(eventQueue.entries.empty() && rejectedItems==1 && eventCalls==5);

 // Rejeição permanente da foto (evento já aceito): conta em photo_rejected, não em rejected; evento enviado uma vez.
 // A foto é tentada a cada 2 s: 16 tentativas até o descarte em 30 200 ms.
 resetAll(); requestOverride=eventResponder; postOverride=[](size_t){ return 400; };
 eventQueue.entries.push_back(makeItem(1,true)); stopAt=320;
 try { networkTask(nullptr); } catch(int) {}
 assert(eventQueue.entries.empty() && photoRejected==1 && rejectedItems==0 && eventCalls==1 && photoCalls==16 && freeCalls==1);

 // 401, 403, 404, 408, 429, 5xx, rede e ACK inválido (-10000) nunca descartam, mesmo após muitas tentativas.
 // stopAt=320 cobre a janela de 30 s (a 301ª tentativa, a cada 100 ticks, já passa de 30 s); com 60 um descarte indevido não apareceria.
 for (int code : {401, 403, 404, 408, 429, 500, 503, -1, -10000}) {
  resetAll(); requestOverride=eventResponder; eventCode=code==-10000 ? 200 : code; wrongAck=code==-10000;
  eventQueue.entries.push_back(makeItem(1,false)); stopAt=320;
  try { networkTask(nullptr); } catch(int) {}
  assert(eventQueue.entries.size()==1 && rejectedItems==0 && photoRejected==0 && eventCalls>=301);
  assert(Serial.log.find("DESCARTADO")==std::string::npos);
 }
 // 401 (chave errada ou proxy) recebe diagnóstico de possível erro de configuração. O diagnóstico é limitado a
 // 1 a cada 10 s e a falta de rede inicial já o ocupa; por isso a execução passa de 10 000 ticks.
 resetAll(); requestOverride=eventResponder; eventCode=401; eventQueue.entries.push_back(makeItem(1,false)); stopAt=120;
 try { networkTask(nullptr); } catch(int) {}
 assert(Serial.log.find("possivel erro de configuracao")!=std::string::npos);

 // Contadores aparecem no corpo do heartbeat (queued continua presente).
 resetAll(); requestOverride=eventResponder; eventCode=401; failingId="porta01-00000003-1";
 droppedEvents=3; rejectedItems=1; photoRejected=2; eventQueue.entries.push_back(makeItem(1,false)); stopAt=110;
 try { networkTask(nullptr); } catch(int) {}
 assert(heartbeats.size()==1);
 JsonDocument hb; assert(!deserializeJson(hb,heartbeats.back()));
 assert(hb["dropped"].as<uint32_t>()==3 && hb["rejected"].as<uint32_t>()==1 && hb["photo_rejected"].as<uint32_t>()==2 && hb["queued"].as<uint32_t>()==1);
}
'''


# Cenários adicionais (cada um compila com os auxiliares de CASES_HELPERS).
CASES_WIFI = CASES_HELPERS + r'''
int main() {
 // Queda de Wi-Fi de 40 s zera a série: 1x400, queda, depois 4x400 (espaçadas de 2 s) não descartam
 // (sem o reset, a 5ª rejeição contaria desde o 1º 400, em 48 300 ms, com mais de 30 s: descartaria).
 resetAll(); requestOverride=eventResponder; eventCode=400;
 eventQueue.entries.push_back(makeItem(1,false)); wifiDownFrom=300; wifiDownUntil=40300; stopAt=500;
 try { networkTask(nullptr); } catch(int) {}
 assert(eventQueue.entries.size()==1 && rejectedItems==0 && droppedEvents==0 && eventCalls>=5);
 assert(Serial.log.find("DESCARTADO")==std::string::npos);
}
'''
CASES_SERIE = CASES_HELPERS + r'''
int main() {
 // 400,400,500,400...: o 500 (não permanente) zera a série. Ele avança 30 s para que só a série, e não a janela, decida.
 resetAll(); requestOverride=scriptedResponder;
 script={{400,0},{400,0},{500,30000},{400,0},{400,0},{400,0},{400,0}};
 eventQueue.entries.push_back(makeItem(1,false)); stopAt=440;
 try { networkTask(nullptr); } catch(int) {}
 assert(eventQueue.entries.empty() && rejectedItems==0 && script.empty() && eventCalls==8);
 assert(Serial.log.find("DESCARTADO")==std::string::npos);

 // Item A com 4x400 e aceito depois de 30 s; item B com 1x400 logo em seguida não herda a série de A.
 resetAll(); requestOverride=scriptedResponder;
 script={{400,0},{400,0},{400,0},{400,0},{200,30000},{400,0}};
 eventQueue.entries.push_back(makeItem(1,false)); eventQueue.entries.push_back(makeItem(2,false)); stopAt=420;
 try { networkTask(nullptr); } catch(int) {}
 assert(eventQueue.entries.empty() && rejectedItems==0 && script.empty() && eventCalls==7);
 assert(Serial.log.find("DESCARTADO")==std::string::npos);
}
'''
CASES_FOTO_SEGUNDO_ITEM = CASES_HELPERS + r'''
int main() {
 // Descarte no estágio foto (evento A já aceito): B precisa enviar o próprio evento, não herdar o estado de A.
 resetAll(); requestOverride=eventResponder; postOverride=[](size_t){ return 400; };
 eventQueue.entries.push_back(makeItem(1,true)); eventQueue.entries.push_back(makeItem(2,false)); stopAt=320;
 try { networkTask(nullptr); } catch(int) {}
 assert(eventQueue.entries.empty() && photoRejected==1 && rejectedItems==0 && photoCalls==16 && freeCalls==1);
 assert(eventCalls==2);
}
'''
CASES_ROLLOVER = CASES_HELPERS + r'''
int main() {
 // millis() perto de 2^32: a janela de 30 s atravessa o rollover e o descarte ocorre na mesma tentativa (16ª, a cada 2 s).
 resetAll(); requestOverride=eventResponder; eventCode=400; ticks=UINT32_MAX-15000;
 eventQueue.entries.push_back(makeItem(1,false)); stopAt=320;
 try { networkTask(nullptr); } catch(int) {}
 assert(eventQueue.entries.empty() && rejectedItems==1 && droppedEvents==0 && eventCalls==16);
 assert(Serial.log.find("DESCARTADO apos 5 rejeicoes")!=std::string::npos);
}
'''
CASES_CAM_BOOT_ID = CASES_HELPERS + r'''
int main() {
 // Formatação: 8 hex minúsculos com zeros à esquerda.
 char out[9]; formatCamBootId(0xABC, out, sizeof out); assert(String(out)=="00000abc");
 formatCamBootId(0xFFFFFFFF, out, sizeof out); assert(String(out)=="ffffffff");

 // Heartbeats: cam_boot_id é estável; boot_id (lastBoot do Mega) muda no 2º heartbeat e cam_boot_id não.
 resetAll(); initCamBootId(); // mesmo caminho do setup(): esp_random() mockado = 0x11223344
 requestOverride=[&](const char *path,const String &body,String &response)->int {
  int code=eventResponder(path,body,response);
  if (String(path)=="/api/device/heartbeat" && heartbeats.size()==1) lastBoot=0x2222;
  return code;
 };
 stopAt=350;
 try { networkTask(nullptr); } catch(int) {}
 assert(heartbeats.size()==3);
 assert(String(camBootId)=="11223344");
 for (size_t i=0;i<heartbeats.size();++i) {
  JsonDocument hb; assert(!deserializeJson(hb,heartbeats[i]));
  String cam=hb["cam_boot_id"].as<String>(), boot=hb["boot_id"].as<String>();
  assert(cam=="11223344" && cam.size()==8);
  for (char ch : cam) assert((ch>='0' && ch<='9') || (ch>='a' && ch<='f'));
  assert(boot==(i==0 ? String("00000001") : String("00002222")) && boot!=cam);
  assert(hb["dropped"].as<uint32_t>()==0);
 }
}
'''
CASES_BACKOFF = CASES_HELPERS + r'''
int main() {
 // Rejeição permanente sem descarte: o MESMO item é reenviado a cada 2 s (não a cada 100 ms); heartbeat e poll seguem na espera.
 resetAll(); eventCode=400; failingId="porta01-00000003-1"; std::vector<uint32_t> at; int polls=0;
 auto spy=[&](const char *path,const String &body,String &response)->int {
  if (String(path)=="/api/device/events") at.push_back(ticks);
  if (String(path)=="/api/device/command?device=porta01") ++polls;
  return eventResponder(path,body,response);
 };
 requestOverride=spy;
 eventQueue.entries.push_back(makeItem(1,false)); stopAt=105; // 10 500 ms
 try { networkTask(nullptr); } catch(int) {}
 assert(at.size()==6 && at.front()==200 && at.back()==10200);
 for (size_t i=1;i<at.size();++i) assert(at[i]-at[i-1]==2000);
 assert(eventQueue.entries.size()==1 && rejectedItems==0 && droppedEvents==0);
 assert(heartbeats.size()==1 && polls>=2); // heartbeat em 10 000 ms cai dentro da espera (8 200 a 10 200)

 // Descarte continua valendo: 16 tentativas (200 a 30 200 ms) e só então o descarte; o item seguinte é aceito em 30 300 ms.
 resetAll(); eventCode=400; failingId="porta01-00000003-1"; at.clear();
 requestOverride=spy;
 eventQueue.entries.push_back(makeItem(1,false)); eventQueue.entries.push_back(makeItem(2,false)); stopAt=320;
 try { networkTask(nullptr); } catch(int) {}
 assert(at.size()==17 && at[15]==30200 && at[15]-at[0]==30000 && at[16]==30300);
 assert(eventQueue.entries.empty() && rejectedItems==1 && droppedEvents==0);
 assert(Serial.log.find("DESCARTADO apos 5 rejeicoes")!=std::string::npos);
}
'''
CASES_RESULTADO_RESET = CASES_HELPERS + r'''
int main() {
 // CAM-01: resultado de reset com HTTP 400/404 é descartado (senão bloqueia a fila de comandos); 500 e rede mantêm o resultado.
 for (int code : {400, 404, 500, -1}) {
  resetAll(); commandMode=true; int polls=0; int posts=0;
  requestOverride=[&](const char *path,const String &body,String &response)->int {
   if (String(path)=="/api/device/command-result") { ++posts; return code; }
   if (String(path)=="/api/device/command?device=porta01") ++polls;
   return -2; // poll e demais caminhos seguem no dublê padrão (entrega do comando id 7 e Mega aplica em 3 500 ms)
  };
  stopAt=80;
  try { networkTask(nullptr); } catch(int) {}
  assert(megaApplied && posts>=1);
  if (code==400 || code==404) {
   assert(resultQueue.entries.empty() && posts==1 && polls>=2);
   assert(Serial.log.find(String("CAM: resultado de reset 7 descartado (HTTP ")+std::to_string(code)+")")!=std::string::npos);
  } else {
   assert(resultQueue.entries.size()==1 && posts>=2 && polls==1);
   assert(Serial.log.find("resultado de reset")==std::string::npos);
  }
 }
}
'''


def build_source(cases, sketch):
    parts = [sketch[sketch.index(start):sketch.index(end)] for start, end in SKETCH_SLICES]
    return PREFIX + SERIAL_MOCK + ''.join(parts) + cases


class CameraNetworkTests(unittest.TestCase):
    def _compile_and_run(self, cases):
        json_lib = require_library(self, 'ArduinoJson', '7.4.3', ('src/ArduinoJson.h',)) / 'src'
        sketch = (CAM / 'Esp32CamRede.ino').read_text()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'sim.cpp'
            binary = Path(directory) / 'sim'
            source.write_text(build_source(cases, sketch))
            cmd = [os.environ.get('CXX', 'c++'), '-std=c++11', '-I', str(CAM), '-I', str(json_lib)]
            sdk = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform == 'darwin' and sdk.exists():
                cmd += ['-isysroot', str(sdk)]
            result = subprocess.run(cmd + [str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_reconnect_and_retry_event_and_photo(self):
        self._compile_and_run(CASES)

    def test_queue_drop_and_permanent_rejection_counters(self):
        self._compile_and_run(CASES_DROP)

    def test_queda_de_wifi_zera_serie_de_rejeicoes(self):
        self._compile_and_run(CASES_WIFI)

    def test_serie_reinicia_em_erro_nao_permanente_e_nao_passa_ao_item_seguinte(self):
        self._compile_and_run(CASES_SERIE)

    def test_descarte_no_estagio_foto_libera_proximo_item(self):
        self._compile_and_run(CASES_FOTO_SEGUNDO_ITEM)

    def test_janela_de_descarte_atravessa_rollover_de_millis(self):
        self._compile_and_run(CASES_ROLLOVER)

    def test_cam_boot_id_no_heartbeat_estavel_e_distinto_de_boot_id(self):
        self._compile_and_run(CASES_CAM_BOOT_ID)

    def test_rejeicao_permanente_reenvia_a_cada_2_s_e_descarta_apos_30_s(self):
        self._compile_and_run(CASES_BACKOFF)

    def test_resultado_de_reset_400_404_descartado_500_e_rede_mantido(self):
        self._compile_and_run(CASES_RESULTADO_RESET)

    def test_setup_gera_cam_boot_id_uma_vez(self):
        sketch = (CAM / 'Esp32CamRede.ino').read_text()
        setup = sketch[sketch.index('void setup() {'):sketch.index('void loop() {')]
        self.assertEqual(setup.count('initCamBootId();'), 1)
