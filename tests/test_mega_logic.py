"""Testa as funções reais de credenciais do sketch Mega com dublês locais."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MEGA = ROOT / 'firmware/MegaControlador'
PREFIX = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <string>
#include "UserStore.h"
#include "DoorLogic.h"
#include "BuzzerLogic.h"
class String : public std::string {
 public: using std::string::string; using std::string::operator=;
 String(const std::string &s):std::string(s) {}
 long toInt() const { try { return std::stol(*this); } catch (...) { return 0; } }
};
static uint32_t now = 1234;
uint32_t millis() { return now; }
struct Memory {
 uint8_t data[4096]; Memory() { memset(data,255,sizeof data); }
 uint8_t read(uint16_t i) { return data[i]; }
 void update(uint16_t i, uint8_t b) { data[i]=b; }
} EEPROM;
// Hash de teste, usado somente para verificar fluxo; não verifica SHA-256 real.
struct SHA256 {
 uint32_t v=2166136261u;
 void reset() { v=2166136261u; }
 void update(const void *p, size_t n) { auto b=static_cast<const uint8_t *>(p); while(n--) v=(v^*b++)*16777619u; }
 void finalize(void *p, size_t n) { auto b=static_cast<uint8_t *>(p); while(n--) { v=v*1664525u+1013904223u; *b++=v>>24; } }
};
struct UserRecord { uint8_t active, salt[4], hash[16]; uint64_t lastWebToken; };
constexpr uint8_t MAX_USERS=100;
const char ADMIN_PIN[]="0000000000";
bool storageReady=true, fingerprintReady=true;
uint16_t lastId=0; uint32_t bootNumber=1;
DoorLogic door; BuzzerLogic buzzer;
extern uint32_t doorGeneration;
void resetUi();
int ticksUntilOpen=0;
void doorTick() { if(ticksUntilOpen && --ticksUntilOpen==0) { door.closed=false; door.state=DoorState::Alarm; ++doorGeneration; resetUi(); } }
void outputsTick() {}
constexpr int FINGERPRINT_OK=0, FINGERPRINT_PACKETRECIEVEERR=1, FINGERPRINT_NOFINGER=2, FINGERPRINT_NOTFOUND=9;
struct Finger {
 bool openOnStore=false, openInSave=false; uint16_t deleted=0, fingerID=1; int openDuring=0, scans=0; uint8_t imageStatus=0;
 void maybeOpen(int step) { if(openDuring==step) { ticksUntilOpen=1; doorTick(); } }
 uint8_t getImage() { ++scans; maybeOpen(1); return imageStatus; }
 uint8_t image2Tz(uint8_t) { maybeOpen(2); return FINGERPRINT_OK; }
 uint8_t fingerFastSearch() { maybeOpen(3); return FINGERPRINT_OK; }
 uint8_t createModel() { maybeOpen(4); return FINGERPRINT_OK; }
 uint8_t storeModel(uint16_t) { if(openOnStore) { ticksUntilOpen=1; doorTick(); } if(openInSave) ticksUntilOpen=2; return 0; }
 uint8_t deleteModel(uint16_t id) { deleted=id; return 0; }
} finger;
void queueEvent(const char *,uint16_t,const char *,const char *) {}
void linkTick(bool) {}
'''
CASES = r'''
int main() {
 door.begin(true, now); resetUi();
 pendingId=1; firstPin="123456"; entry="123456"; confirmEnrollment();
 assert(exists(1) && matches(1,"123456") && lastId==1);
 assert(!strcmp(resetPassword(1,"111111","web",0x1234),"ok"));
 assert(!strcmp(resetPassword(1,"222222","usb",0),"ok"));
 assert(!strcmp(resetPassword(1,"111111","web",0x1234),"ok"));
 assert(matches(1,"222222") && !matches(1,"111111"));
 assert(changeStatus(1,false)); assert(!activeUser(1)); assert(ownerOfPin("222222")==1);
 assert(changeStatus(1,true)); assert(activeUser(1));
 ui=Ui::ConfirmPin; pendingId=2; firstPin="444444"; entry="444444"; finger.openOnStore=true;
 confirmEnrollment(); assert(!exists(2) && finger.deleted==2 && ui==Ui::Access);
 finger.openOnStore=false; finger.deleted=0; door.begin(true,now);
 ui=Ui::ConfirmPin; pendingId=2; firstPin="444444"; entry="444444"; finger.openInSave=true;
 confirmEnrollment(); assert(exists(2) && lastId==2 && finger.deleted==0 && door.state==DoorState::Alarm);
 finger.openInSave=false; door.begin(true,now);
 resetUi(); noticeDuration=0; waitFingerRemoval=false; ui=Ui::FirstFinger;
 finger.fingerID=3; now+=200; fingerprintTick();
 assert(ui==Ui::Access && !exists(3) && noticeLine2=="Slot DY orfao");
 finger.fingerID=1;
 // Cada espera do sensor pode detectar uma abertura forçada no meio da leitura.
 for (int step=1;step<=4;++step) {
  door.begin(true,now); resetUi(); noticeDuration=0; waitFingerRemoval=false;
  ui=step==4 ? Ui::SecondFinger : Ui::Access; now+=200; finger.openDuring=step;
  fingerprintTick();
  assert(door.state==DoorState::Alarm && ui==Ui::Access && waitFingerRemoval);
 }
 finger.openDuring=0; door.begin(true,now); resetUi();
 noticeDuration=0; waitFingerRemoval=false; finger.imageStatus=FINGERPRINT_PACKETRECIEVEERR;
 finger.openDuring=1; now+=200; fingerprintTick(); assert(!fingerprintReady);
 int previousScans=finger.scans; door.begin(true,now); resetUi(); now+=200;
 fingerprintTick(); assert(finger.scans==previousScans);
 fingerprintReady=true; finger.imageStatus=0; finger.openDuring=0;
 ui=Ui::ConfirmStatus; pendingId=1; enableRequested=false; noticeDuration=0; ticksUntilOpen=2;
 handleKey('#'); assert(!activeUser(1) && door.state==DoorState::Alarm && noticeDuration==0);
 door.begin(true,now); assert(changeStatus(1,true));
 ticksUntilOpen=2; // abre enquanto o primeiro hash está sendo calculado
 assert(!strcmp(resetPassword(1,"333333","usb",0),"device_busy"));
 door.begin(true,now); assert(matches(1,"222222"));
 UserRecord existing; assert(readRecord(1,existing)); ticksUntilOpen=2;
 assert(saveRecord(1,existing)); assert(door.state==DoorState::Alarm && matches(1,"222222"));
 door.begin(true,now);
 door.authorize(1,now); assert(!strcmp(resetPassword(1,"333333","usb",0),"device_busy"));
 assert(matches(1,"222222"));
 EEPROM.data[4]^=1; assert(!matches(1,"222222") && !storageReady);
}
'''

class MegaLogicTests(unittest.TestCase):
    def test_credentials_and_replay(self):
        sketch = (MEGA / 'MegaControlador.ino').read_text()
        body = sketch[sketch.index('enum class Ui'):sketch.index('void handleKey(')]
        handle_key = sketch[sketch.index('void handleKey('):sketch.index('void fingerprintTick()')]
        finger_tick = sketch[sketch.index('void fingerprintTick()'):sketch.index('void rgb(')]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'test.cpp'
            binary = Path(directory) / 'test'
            source.write_text(PREFIX + body + handle_key + finger_tick + CASES)
            cmd = [os.environ.get('CXX', 'c++'), '-std=c++11', '-I', str(MEGA)]
            sdk = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform == 'darwin' and sdk.exists(): cmd += ['-isysroot', str(sdk)]
            result = subprocess.run(cmd + [str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
