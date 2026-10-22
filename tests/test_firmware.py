"""Executa funções reais do sketch com dublês de hardware, NVS e hash.

O trecho é extraído do .ino em cada execução, sem reimplementar a lógica de
credenciais. Não valida eletrônica, protocolo físico DY50 nem criptografia.
Requer compilador C++11. Nenhuma dependência Python externa.
"""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = ROOT / "firmware/ControleAcesso"

PREFIX = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <cstdarg>
#include <string>
#include <vector>
#include <map>
#include "DoorLogic.h"
#include "BuzzerLogic.h"
class String : public std::string {
 public:
  using std::string::string;
  using std::string::operator=;
  String(const std::string &s) : std::string(s) {}
  long toInt() const { try { return std::stol(*this); } catch (...) { return 0; } }
  bool startsWith(const char *prefix) const { return find(prefix)==0; }
  String substring(size_t from) const { return String(substr(from)); }
  void trim() {
    auto first=find_first_not_of(" \t\r\n"),last=find_last_not_of(" \t\r\n");
    *this=first==npos?"":substr(first,last-first+1);
  }
};
static uint32_t fakeMillis = 1000;
uint32_t millis() { return fakeMillis; }
void esp_fill_random(void *buffer, size_t length) {
  static uint8_t seed=1; auto p=static_cast<uint8_t *>(buffer);
  for(size_t i=0;i<length;++i) p[i]=seed++;
}
// Hash determinístico de teste: exercita salt/comparação, NÃO substitui SHA-256 na placa.
constexpr int MBEDTLS_MD_SHA256=1;
const void *mbedtls_md_info_from_type(int) { return reinterpret_cast<void *>(1); }
int mbedtls_md(const void *, const uint8_t *input, size_t size, uint8_t *out) {
  uint32_t h=2166136261u;
  for(size_t i=0;i<size;++i) h=(h^input[i])*16777619u;
  for(int i=0;i<32;++i) { h=h*1664525u+1013904223u; out[i]=h>>24; }
  return 0;
}
struct FakePrefs {
  std::map<std::string,std::vector<uint8_t>> disk; bool fail=false;
  size_t putBytes(const char *key, const void *data, size_t size) {
    if(fail) return 0;
    auto bytes=static_cast<const uint8_t *>(data); disk[key]={bytes,bytes+size}; return size;
  }
} prefs;
constexpr uint8_t FINGERPRINT_OK=0, FINGERPRINT_NOFINGER=2, FINGERPRINT_NOTFOUND=9;
struct FakeFinger {
  uint16_t fingerID=0, stored=0;
  uint8_t image=FINGERPRINT_NOFINGER, search=FINGERPRINT_NOTFOUND;
  uint8_t conversion=FINGERPRINT_OK, model=FINGERPRINT_OK, store=FINGERPRINT_OK;
  unsigned scans=0, writes=0, deletes=0;
  uint8_t getImage() { ++scans; return image; }
  uint8_t image2Tz(uint8_t) { return conversion; }
  uint8_t fingerFastSearch() { return search; }
  uint8_t createModel() { return model; }
  uint8_t storeModel(uint16_t id) { ++writes; stored=id; return store; }
  uint8_t deleteModel(uint16_t) { ++deletes; return FINGERPRINT_OK; }
} finger;
struct FakeSerial {
  std::string input, output; size_t pos=0;
  int available() { return pos<input.size(); }
  char read() { return input[pos++]; }
  void println(const char *s) { output+=s;output+='\n'; }
  void printf(const char *format, ...) {
    char result[512];va_list args;va_start(args,format);vsnprintf(result,sizeof(result),format,args);va_end(args);output+=result;
  }
} Serial;
constexpr int WL_CONNECTED=3;
struct FakeWiFi { int status() { return WL_CONNECTED; } } WiFi;
int eventsQueue=0;uint32_t droppedEvents=0;
unsigned uxQueueMessagesWaiting(int) { return 0; }
std::vector<std::string> auditTypes;
void audit(const char *type, uint16_t = 0, const char * = "", const char * = "") { auditTypes.push_back(type); }
'''

CASES = r'''
void fresh() {
  fakeMillis=1000; memset(users,0,sizeof(users)); lastId=0; prefs=FakePrefs(); finger=FakeFinger();
  auditTypes.clear(); storageReady=true; fingerprintReady=true; resetUi();
  door.begin(true,fakeMillis); buzzer.reset(); noticeDuration=0; waitFingerRemoval=false; lastFingerPoll=0;
  Serial=FakeSerial();serialAuthed=false;serialOverflow=false;serialLine="";serialTouched=0;
}
void addUser(uint16_t id, const char *pin, bool active=true) {
  UserRecord r={}; r.magic=0xACCE0001; r.active=active;
  esp_fill_random(r.salt,sizeof(r.salt)); assert(digest(String(pin),r.salt,r.hash));
  assert(saveRecord(id,r));
}
void rebootFromNvs() {
  memset(users,0,sizeof(users)); lastId=0;
  for(uint16_t i=1;i<=MAX_USERS;++i) { char key[12];recordKey(i,key);
    auto item=prefs.disk.find(key); if(item==prefs.disk.end())continue;
    memcpy(&users[i],item->second.data(),sizeof(UserRecord));lastId=i;
  }
  resetUi(); door.begin(true,fakeMillis); noticeDuration=0;
}
void test_partial_entry_fingerprint() {
  fresh(); addUser(1,"123456"); entry="1";
  finger.image=FINGERPRINT_OK; finger.search=FINGERPRINT_OK;finger.fingerID=1;
  fingerprintTick(); assert(finger.scans==1); assert(door.state==DoorState::AwaitOpen);
  assert(door.user==1);assert(entry.empty());
}
void test_d_during_authorization() {
  fresh();addUser(1,"123456");authorize(1,"password");handleKey('D');
  assert(door.state==DoorState::AwaitOpen);
  assert(!noticeActive() || noticeLine1!="Operacao cancelada");
}
void test_pin_policy() {
  fresh();assert(validPin("012345",6));assert(!validPin("12345",6));assert(!validPin("12a456",6));
  addUser(1,"012345");addUser(2,"987654",false);
  assert(ownerOfPin("012345")==1);assert(ownerOfPin("987654")==2);assert(ownerOfPin("555555")==0);
  assert(strcmp(resetPassword(1,"987654","usb",0),"pin_in_use")==0);
  assert(strcmp(resetPassword(1,"12a456","usb",0),"invalid_pin")==0);
  assert(strcmp(resetPassword(100,"111111","usb",0),"unknown_user")==0);
}
void test_softdelete_reactivate() {
  fresh();addUser(1,"123456");UserRecord before=users[1];
  assert(changeStatus(1,false));authorize(1,"password");assert(door.state==DoorState::Idle);
  assert(ownerOfPin("123456")==1);assert(changeStatus(1,true));
  assert(memcmp(before.hash,users[1].hash,32)==0);assert(finger.deletes==0);
  authorize(1,"fingerprint");assert(door.user==1 && door.state==DoorState::AwaitOpen);
  rebootFromNvs();assert(users[1].active && matches(1,"123456"));
}
void test_replay_after_usb_and_reboot() {
  fresh();addUser(1,"123456");
  assert(strcmp(resetPassword(1,"111111","web",0x123456u),"ok")==0);
  rebootFromNvs();assert(strcmp(resetPassword(1,"222222","usb",0),"ok")==0);
  rebootFromNvs();assert(strcmp(resetPassword(1,"111111","web",0x123456u),"ok")==0);
  assert(matches(1,"222222"));assert(!matches(1,"111111"));
}
void test_full_lifetime_and_last_id() {
  fresh();for(uint16_t i=1;i<=100;++i) {char pin[7];snprintf(pin,sizeof(pin),"%06u",unsigned(i));addUser(i,pin);}
  assert(lastId==100);assert(changeStatus(100,false));rebootFromNvs();assert(lastId==100);
  ui=Ui::Menu;beginEnrollment();assert(ui==Ui::Menu && noticeLine1=="Limite atingido");
}
void test_enrollment_two_pins_and_cancel() {
  fresh();ui=Ui::Menu;beginEnrollment();assert(pendingId==1 && ui==Ui::RemoveFinger);
  fingerprintTick();assert(ui==Ui::FirstFinger);
  fakeMillis+=151;finger.image=FINGERPRINT_OK;fingerprintTick();assert(ui==Ui::RemoveFinger);
  fakeMillis+=151;finger.image=FINGERPRINT_NOFINGER;fingerprintTick();assert(ui==Ui::SecondFinger);
  fakeMillis+=151;finger.image=FINGERPRINT_OK;fingerprintTick();assert(ui==Ui::FirstPin);
  entry="123456";handleKey('#');assert(ui==Ui::ConfirmPin && firstPin=="123456");
  entry="999999";handleKey('#');assert(lastId==0 && finger.writes==0 && ui==Ui::FirstPin);
  fakeMillis+=2001;entry="123456";handleKey('#');entry="123456";handleKey('#');
  assert(lastId==1 && users[1].active && matches(1,"123456") && finger.writes==1);
  fakeMillis+=2001;ui=Ui::Menu;beginEnrollment();handleKey('D');assert(ui==Ui::Access && lastId==1);
}
void test_duplicate_finger_inactive_and_mismatch() {
  fresh();addUser(1,"123456",false);ui=Ui::FirstFinger;pendingId=2;
  finger.image=FINGERPRINT_OK;finger.search=FINGERPRINT_OK;finger.fingerID=1;
  fingerprintTick();assert(ui==Ui::Access && lastId==1 && finger.writes==0);
  fakeMillis+=2001;noticeDuration=0;ui=Ui::SecondFinger;pendingId=2;finger.model=1;
  fingerprintTick();assert(ui==Ui::Access && lastId==1 && finger.writes==0);
}
void test_duplicate_pin_and_storage_failure() {
  fresh();addUser(1,"123456",false);pendingId=2;ui=Ui::ConfirmPin;entry=firstPin="123456";
  confirmEnrollment();assert(lastId==1 && finger.writes==0 && ui==Ui::FirstPin);
  noticeDuration=0;pendingId=2;ui=Ui::ConfirmPin;entry=firstPin="654321";prefs.fail=true;
  confirmEnrollment();assert(lastId==1 && !exists(2));assert(finger.deletes==1);
  assert(matches(1,"123456"));
}
void test_admin_menu_and_credential_rejection() {
  fresh();entry=ADMIN_PIN;handleKey('#');assert(ui==Ui::Menu);
  handleKey('D');assert(ui==Ui::Access);fakeMillis+=2001;
  entry="000000";handleKey('#');assert(door.state==DoorState::Idle);
  fresh();addUser(1,"123456");finger.image=FINGERPRINT_OK;finger.search=FINGERPRINT_NOTFOUND;
  fingerprintTick();assert(door.state==DoorState::Idle);
}
void test_usb_auth_and_parser() {
  fresh();addUser(1,"123456");
  Serial.input="RESET 1 654321 654321\n";serialTick();assert(matches(1,"123456"));
  assert(Serial.output.find("auth_required")!=std::string::npos);
  Serial.input+=std::string("AUTH ")+ADMIN_PIN+"\nRESET 1 654321 654321\nSTATUS\nLIST\n";
  serialTick();assert(matches(1,"654321"));assert(!matches(1,"123456"));
  assert(Serial.output.find(ADMIN_PIN)==std::string::npos);
  assert(Serial.output.find("654321")==std::string::npos);
  Serial.input+="RESET 1 111111 222222\n";serialTick();assert(matches(1,"654321"));
  fakeMillis+=300001;Serial.input+="RESET 1 111111 111111\n";serialTick();assert(matches(1,"654321"));
}
int main(int argc, char **argv) {
  assert(argc==2);std::string name=argv[1];
  if(name=="partial")test_partial_entry_fingerprint();
  else if(name=="cancel")test_d_during_authorization();
  else if(name=="pin")test_pin_policy();
  else if(name=="softdelete")test_softdelete_reactivate();
  else if(name=="replay")test_replay_after_usb_and_reboot();
  else if(name=="capacity")test_full_lifetime_and_last_id();
  else if(name=="enrollment")test_enrollment_two_pins_and_cancel();
  else if(name=="duplicate_finger")test_duplicate_finger_inactive_and_mismatch();
  else if(name=="storage")test_duplicate_pin_and_storage_failure();
  else if(name=="admin")test_admin_menu_and_credential_rejection();
  else if(name=="usb")test_usb_auth_and_parser();
  else return 2;
}
'''


class FirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        temporary = Path(cls.temp.name)
        source = (FIRMWARE / "ControleAcesso.ino").read_text()
        # Testes reproduzíveis sem depender das credenciais locais do proprietário.
        config = (FIRMWARE / "Config.example.h").read_text()
        record = source[source.index("struct UserRecord {"):source.index("struct AuditEvent {")]
        globals_ui = source[source.index("enum class Ui {"):source.index("bool validPin(")]
        functions = source[source.index("bool validPin("):source.index("void rgb(")]
        # Auditoria de transporte é testada no servidor; aqui capturamos os tipos emitidos.
        functions = functions[:functions.index("void audit(")] + functions[functions.index("void notice("):]
        constants = '\n'.join(re.findall(r'^constexpr .*\b(?:MAX_USERS|ADMIN_PIN|LOCK_MODE)\b.*;', config, re.M))
        functions += source[source.index("void serialTick("):source.index("int httpCall(")]
        globals_records = "UserRecord users[MAX_USERS+1]={}; bool storageReady=true,fingerprintReady=true; uint16_t lastId=0; DoorLogic door; BuzzerLogic buzzer;\n"
        cpp = temporary / "firmware.cpp"
        cpp.write_text(PREFIX + constants + record + globals_records + globals_ui + functions + CASES)
        cls.binary = temporary / "firmware-test"
        command = [os.environ.get("CXX", "c++"), "-std=c++11", "-I", str(FIRMWARE)]
        # O SDK27 deste Mac não é compatível com seu linker; usar SDK26 se existir.
        sdk = Path("/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk")
        if sys.platform == "darwin" and sdk.exists():
            command += ["-isysroot", str(sdk)]
        command += [str(cpp), "-o", str(cls.binary)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)

    def run_case(self, name):
        result = subprocess.run([str(self.binary), name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_fingerprint_after_partial_pin(self): self.run_case("partial")
    def test_d_does_not_falsely_cancel_authorization(self): self.run_case("cancel")
    def test_pin_uniqueness_and_format(self): self.run_case("pin")
    def test_softdelete_reactivate_and_persistence(self): self.run_case("softdelete")
    def test_web_replay_does_not_overwrite_later_usb_reset(self): self.run_case("replay")
    def test_lifetime_limit_survives_inactivation_and_reboot(self): self.run_case("capacity")
    def test_full_enrollment_confirmation_and_cancel(self): self.run_case("enrollment")
    def test_duplicate_inactive_finger_and_mismatched_captures(self): self.run_case("duplicate_finger")
    def test_duplicate_pin_and_failed_nvs_write(self): self.run_case("storage")
    def test_admin_and_unknown_credentials(self): self.run_case("admin")
    def test_usb_authentication_confirmation_and_timeout(self): self.run_case("usb")
