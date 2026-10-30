"""Conecta funções reais dos sketches por UART simulada (sem hardware)."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MEGA = ROOT / 'firmware/MegaControlador'
CAM = ROOT / 'firmware/Esp32CamRede'

PREFIX = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <string>
#include <vector>
#include "UserStore.h"
#include "BootCounter.h"
#include "DoorLogic.h"
#include "BuzzerLogic.h"
#include "SerialFrame.h"
#include "MessageProtocol.h"
struct Port {
 std::vector<uint8_t> input,output; size_t pos=0;
 int available() { return int(input.size()-pos); }
 int availableForWrite() { return 1; }
 uint8_t read() { return input[pos++]; }
 void write(uint8_t b) { output.push_back(b); }
};
namespace Mega {
class String : public std::string {
 public: using std::string::string; using std::string::operator=;
 String(const std::string &s):std::string(s) {}
};
uint32_t now=1000; uint32_t millis() { return now; }
struct Memory { uint8_t data[4096]; Memory() { memset(data,255,sizeof data); }
 uint8_t read(uint16_t i) { return data[i]; } void update(uint16_t i,uint8_t b) { data[i]=b; }
} EEPROM;
struct SHA256 { uint32_t v=2166136261u; void reset() { v=2166136261u; }
 void update(const void *p,size_t n) { auto b=static_cast<const uint8_t *>(p); while(n--) v=(v^*b++)*16777619u; }
 void finalize(void *p,size_t n) { auto b=static_cast<uint8_t *>(p); while(n--) { v=v*1664525u+1013904223u; *b++=v>>24; } }
};
struct UserRecord { uint8_t active,salt[4],hash[16]; uint64_t lastWebToken; };
constexpr uint8_t MAX_USERS=100; bool storageReady=true,fingerprintReady=true;
uint16_t lastId=0; uint32_t bootNumber=1,eventSequence=0,droppedEvents=0;
DoorLogic door; BuzzerLogic buzzer; Port Serial2;
void doorTick() {} void outputsTick() {}
constexpr int FINGERPRINT_OK=0, FINGERPRINT_PACKETRECIEVEERR=1;
struct Finger { uint8_t storeModel(uint16_t) { return 0; } uint8_t deleteModel(uint16_t) { return 0; } } finger;
void queueEvent(const char *,uint16_t,const char *,const char *);
'''
CAM_PREFIX = r'''
} // Mega
namespace Cam {
using namespace MessageProtocol;
struct Item { EventData event; uint8_t *photo; size_t photoSize; };
struct Command { uint32_t id; uint8_t user; char pin[7]; uint64_t token; };
struct Result { uint32_t id; bool ok; uint8_t reason; };
template <class T> struct Queue { std::vector<T> items; size_t capacity=8; };
Queue<Item> queue; Queue<Command> commandQueue; Queue<Result> resultQueue;
Queue<Item> *events=&queue; Queue<Command> *commands=&commandQueue; Queue<Result> *results=&resultQueue;
template <class T> int uxQueueSpacesAvailable(Queue<T> *q) { return int(q->capacity-q->items.size()); }
constexpr int pdTRUE=1;
template <class T> int xQueueSend(Queue<T> *q,T *item,int) { if(!uxQueueSpacesAvailable(q)) return 0; q->items.push_back(*item); return 1; }
template <class T> int xQueuePeek(Queue<T> *q,T *item,int) { if(q->items.empty()) return 0; *item=q->items.front(); return 1; }
template <class T> int xQueueReceive(Queue<T> *q,T *item,int) { if(!xQueuePeek(q,item,0)) return 0; q->items.erase(q->items.begin()); return 1; }
Port Serial2; bool cameraReady=true, networkReady=true; uint32_t lastBoot=0,lastEvent=0;
uint32_t droppedEvents=0, rejectedItems=0; void bump(uint32_t &v) { if (v != UINT32_MAX) ++v; }
SerialFrame::Parser parser;
uint32_t millis() { return Mega::now; } void delay(unsigned) {}
uint32_t randomState=1; uint32_t esp_random() { return randomState++; }
constexpr int PIXFORMAT_JPEG=1;
struct camera_fb_t { int format; size_t len; uint8_t *buf; };
uint8_t jpeg[]={0xff,0xd8,0xff,0xd9}; int captures=0;
camera_fb_t fb={PIXFORMAT_JPEG,sizeof jpeg,jpeg};
camera_fb_t *esp_camera_fb_get() { ++captures; return &fb; }
void esp_camera_fb_return(camera_fb_t *) {}
bool psramFound() { return false; }
void *ps_malloc(size_t n) { return malloc(n); }
'''
CASES = r'''
} // Cam
SerialFrame::Parser cameraParser;
void megaToCamera(uint32_t byteDelay=0) {
 for (uint8_t b:Mega::Serial2.output) {
  if (cameraParser.feed(b,Mega::now)) {
    if (cameraParser.data()[1]==MessageProtocol::Event) Cam::receiveEvent(cameraParser.data(),cameraParser.size(),cameraParser.startedAt());
    else if (cameraParser.data()[1]==MessageProtocol::PhotoProof) Cam::receivePhotoProof(cameraParser.data(),cameraParser.size());
  }
  Mega::now+=byteDelay;
 }
 Mega::Serial2.output.clear();
}
void cameraToMega() {
 Mega::Serial2.input.insert(Mega::Serial2.input.end(),Cam::Serial2.output.begin(),Cam::Serial2.output.end());
 Cam::Serial2.output.clear(); Mega::linkTick();
}
struct Sink { std::vector<uint8_t> bytes; void write(uint8_t b) { bytes.push_back(b); } };
int main() {
 assert(BootCounter::next(Mega::EEPROM,Mega::bootNumber) && Mega::bootNumber==1);
 Mega::door.begin(true,Mega::now); Mega::resetUi();
 Mega::pendingId=1; Mega::firstPin="123456"; Mega::entry="123456"; Mega::confirmEnrollment();
 assert(Mega::exists(1) && Mega::count==1);
 Mega::linkTick(); megaToCamera(); cameraToMega(); assert(Mega::count==0 && Cam::queue.items.size()==1);
 Mega::authorize(1,"password"); assert(Mega::door.state==DoorState::AwaitOpen && Mega::count==1);
 Mega::linkTick(); megaToCamera(); assert(Cam::pendingPhoto.active && Cam::captures==2);
 cameraToMega(); megaToCamera(); assert(Cam::queue.items.size()==2);
 // ACK perdido: Mega reenvia, CAM não duplica foto e volta a confirmar.
 Cam::Serial2.output.clear(); Mega::now+=1001; Mega::linkTick(); megaToCamera();
 assert(Cam::queue.items.size()==2 && Cam::captures==2); cameraToMega(); assert(Mega::count==0);
 auto access=Cam::queue.items[1]; assert(access.event.kind==MessageProtocol::AccessGranted && access.event.user==1 && access.photoSize==4);
 // O tempo entre bytes conta para o prazo da foto, como no loop real da CAM.
 Mega::authorizationAt=Mega::now; Mega::queueEvent("access_granted",1,"password",""); Mega::linkTick();
 uint32_t started=Mega::now; megaToCamera(500); cameraToMega();
 assert(Mega::now-started>5000 && Cam::pendingPhoto.active);
 Mega::now+=5000; Cam::photoTick(); cameraToMega();
 assert(Mega::count==0 && Cam::queue.items.size()==3);
 assert(Cam::queue.items[2].photo==nullptr);
 // O loop real da CAM encaminha o comando e recebe o resultado real do Mega.
 Mega::door.begin(true,Mega::now);
 Cam::Command command={7,1,"111111",42}; assert(Cam::xQueueSend(Cam::commands,&command,0));
 Cam::loop(); assert(!Cam::Serial2.output.empty());
 Mega::Serial2.input.insert(Mega::Serial2.input.end(),Cam::Serial2.output.begin(),Cam::Serial2.output.end());
 Cam::Serial2.output.clear(); Mega::linkTick();
 assert(Mega::matches(1,"111111"));
 Cam::Serial2.input.insert(Cam::Serial2.input.end(),Mega::Serial2.output.begin(),Mega::Serial2.output.end());
 Mega::Serial2.output.clear(); Cam::loop();
 assert(Cam::commandQueue.items.empty() && Cam::resultQueue.items.size()==1);
 assert(Cam::resultQueue.items[0].id==7 && Cam::resultQueue.items[0].ok);
 assert(!strcmp(Mega::resetPassword(1,"222222","usb",0),"ok"));
 // Reinício preserva credenciais e o token já aplicado.
 assert(BootCounter::next(Mega::EEPROM,Mega::bootNumber) && Mega::bootNumber==2);
 Mega::eventSequence=0; Mega::head=0; Mega::count=0;
 Cam::resultQueue.items.clear(); assert(Cam::xQueueSend(Cam::commands,&command,0));
 Mega::now+=1001; Cam::Serial2.output.clear(); Cam::loop();
 Mega::Serial2.input.insert(Mega::Serial2.input.end(),Cam::Serial2.output.begin(),Cam::Serial2.output.end()); Mega::linkTick();
 assert(Mega::matches(1,"222222") && !Mega::matches(1,"111111"));
 Mega::queueEvent("access_granted",1,"password","");
 assert(Mega::outbound[Mega::head].boot==2 && Mega::outbound[Mega::head].messageId==1);
 for (auto &item:Cam::queue.items) free(item.photo);
 puts("integrated UART/camera simulation passed");
}
'''

class IntegratedSimulationTests(unittest.TestCase):
    def test_actual_sketch_functions_together(self):
        mega=(MEGA/'MegaControlador.ino').read_text(); cam=(CAM/'Esp32CamRede.ino').read_text()
        logic=mega[mega.index('enum class Ui'):mega.index('void handleKey(')]
        link=mega[mega.index('MessageProtocol::EventData outbound'):mega.index('void serialTick()')]
        capture=cam[cam.index('struct PendingPhoto'):cam.index('int request(')]
        camera_loop=cam[cam.index('void loop()'):]
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'sim.cpp'; binary=Path(directory)/'sim'
            source.write_text(PREFIX+logic+link+CAM_PREFIX+capture+camera_loop+CASES)
            cmd=[os.environ.get('CXX','c++'),'-std=c++11','-I',str(MEGA)]
            sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform=='darwin' and sdk.exists(): cmd+=['-isysroot',str(sdk)]
            result=subprocess.run(cmd+[str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
