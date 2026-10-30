"""Fila e inicializacao do Mega: id invalido no evento e falha de recover nao travam a fila."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

MEGA = Path(__file__).resolve().parents[1] / 'firmware/MegaControlador'
PREFIX = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#include "MessageProtocol.h"
#include "SerialFrame.h"
#include "UserStore.h"
#include "BootCounter.h"
using String = std::string;
uint32_t authorizationAt=0; uint32_t now=100,bootNumber=3,eventSequence=0,droppedEvents=0;
bool storageReady=false;
uint32_t millis() { return now; }
bool activeUser(uint16_t id) { return id==1; }
struct SerialPort {
 std::vector<uint8_t> input,output; size_t pos=0;
 int available() { return int(input.size()-pos); }
 int availableForWrite() { return 1; }
 uint8_t read() { return input[pos++]; }
 void write(uint8_t b) { output.push_back(b); }
} Serial2;
struct EepromStub {
 std::vector<uint8_t> mem;
 EepromStub() : mem(4096, 0xff) {}
 uint8_t read(uint16_t a) { return mem[a]; }
 void update(uint16_t a, uint8_t v) { mem[a] = v; }
} EEPROM;
void doorTick() {} void outputsTick() {}
void audit(const char *type, uint16_t id = 0, const char *method = "", const char *reason = "");
unsigned resets=0;
const char *resetPassword(uint16_t id,const String &pin,const char *,uint64_t token) {
 ++resets; return id==1 && pin=="123456" && token==42 ? "ok" : "invalid_pin";
}
'''
CASES = r'''
struct Sink { std::vector<uint8_t> data; void write(uint8_t b) { data.push_back(b); } };
void sendToMega(const uint8_t *body,size_t len) { Sink s; assert(SerialFrame::send(s,body,len)); Serial2.input.insert(Serial2.input.end(),s.data.begin(),s.data.end()); }
void ack(uint32_t id) { uint8_t a[10]={MessageProtocol::kVersion,MessageProtocol::Ack}; MessageProtocol::put32(a+2,id); MessageProtocol::put32(a+6,3); sendToMega(a,sizeof a); }
std::vector<std::vector<uint8_t>> frames() {
 std::vector<std::vector<uint8_t>> out; SerialFrame::Parser p;
 for (auto b : Serial2.output) if (p.feed(b, now)) out.emplace_back(p.data(), p.data() + p.size());
 Serial2.output.clear(); return out;
}
void audit(const char *type, uint16_t id, const char *method, const char *reason) { queueEvent(type, id, method, reason); }
int main() {
 using namespace MessageProtocol;
 MODE_PLACEHOLDER
 return 0;
}
'''
# Cenario 1: id 120 no evento e evento bloqueado na cabeca da fila.
MAIN_QUEUE = r'''
 // Id acima de MAX_USERS vira user 0 e o evento segue normalmente.
 queueEvent("access_denied",120,"fingerprint","unknown_finger");
 queueEvent("access_granted",1,"password","");
 assert(count==2 && droppedEvents==0);
 linkTick();
 auto out=frames(); assert(out.size()==1);
 EventData e={}; assert(decodeEvent(out[0].data(),out[0].size(),e));
 assert(e.messageId==1 && e.user==0 && e.kind==AccessDenied);
 ack(1); linkTick();
 out=frames(); assert(out.size()==1);
 assert(decodeEvent(out[0].data(),out[0].size(),e) && e.messageId==2 && e.user==1 && e.kind==AccessGranted);
 ack(2); linkTick();
 assert(count==0 && droppedEvents==0);
 // Evento que a codificacao rejeita (user > 100, simulando dado corrompido) e descartado.
 EventData bad={}; bad.messageId=3; bad.boot=3; bad.kind=AccessDenied; bad.user=200; bad.method=Password; bad.reason=1;
 outbound[head]=bad; count=1; eventSequence=3;
 queueEvent("access_granted",1,"password","");
 assert(count==2);
 linkTick();
 assert(droppedEvents==1 && count==1 && frames().empty());
 linkTick();
 out=frames(); assert(out.size()==1);
 assert(decodeEvent(out[0].data(),out[0].size(),e) && e.messageId==4);
 ack(4); linkTick();
 assert(count==0 && droppedEvents==1);
'''
# Cenario 2: recover falha (journal corrompido) e BootCounter ainda gera bootNumber.
MAIN_BOOT = r'''
 EEPROM.mem[UserStore::kJournal]=UserStore::kCommitted; EEPROM.mem[UserStore::kJournal+1]=0;
 bootNumber=0;
@SETUP@
 if (!storageReady) audit("storage_error", 0, "system");
 assert(!storageReady && bootNumber==1);
 linkTick();
 auto out=frames(); assert(out.size()==1);
 EventData e={}; assert(decodeEvent(out[0].data(),out[0].size(),e));
 assert(e.kind==StorageError && e.boot==1 && e.messageId==1);
'''


class FilaRobustaTests(unittest.TestCase):
    def _compile_and_run(self, main_body):
        sketch = (MEGA / 'MegaControlador.ino').read_text()
        body = sketch[sketch.index('MessageProtocol::EventData outbound'):sketch.index('void serialTick()')]
        cases = CASES.replace('MODE_PLACEHOLDER', main_body)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'test.cpp'
            binary = Path(directory) / 'test'
            source.write_text(PREFIX + body + cases)
            cmd = [os.environ.get('CXX', 'c++'), '-std=c++11', '-I', str(MEGA)]
            sdk = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform == 'darwin' and sdk.exists():
                cmd += ['-isysroot', str(sdk)]
            result = subprocess.run(cmd + [str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_id_fora_do_limite_nao_trava_fila(self):
        self._compile_and_run(MAIN_QUEUE)

    def test_recover_falho_mantem_boot_e_registra_storage_error(self):
        sketch = (MEGA / 'MegaControlador.ino').read_text()
        start = sketch.index('  const bool usersRecovered')
        end_marker = 'storageReady = usersRecovered && bootCounted;'
        setup = sketch[start:sketch.index(end_marker) + len(end_marker)]
        self._compile_and_run(MAIN_BOOT.replace('@SETUP@', setup))


if __name__ == '__main__':
    unittest.main()
