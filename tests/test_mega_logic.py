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
constexpr int FINGERPRINT_OK=0, FINGERPRINT_PACKETRECIEVEERR=1, FINGERPRINT_NOFINGER=2, FINGERPRINT_IMAGEFAIL=3, FINGERPRINT_NOTFOUND=9;
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
 // Órfã em 1..MAX_USERS é apagada e o cadastro pede para retirar o dedo (antes: "Slot DY orfao").
 assert(ui==Ui::RemoveFinger && finger.deleted==3 && noticeLine2=="Recoloque o dedo");
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

    def test_falha_passageira_de_leitura_no_cadastro(self):
        sketch = (MEGA / 'MegaControlador.ino').read_text()
        body = sketch[sketch.index('enum class Ui'):sketch.index('void handleKey(')]
        handle_key = sketch[sketch.index('void handleKey('):sketch.index('void fingerprintTick()')]
        finger_tick = sketch[sketch.index('void fingerprintTick()'):sketch.index('void rgb(')]
        registro = PREFIX.replace(
            'uint8_t fingerFastSearch() { maybeOpen(3); return FINGERPRINT_OK; }',
            'uint8_t searchResult=FINGERPRINT_OK; uint8_t fingerFastSearch() { maybeOpen(3); return searchResult; }'
        ).replace(
            'void queueEvent(const char *,uint16_t,const char *,const char *) {}',
            '#include <vector>\nstd::vector<std::string> audits;\n'
            'void queueEvent(const char *t,uint16_t id,const char *m,const char *r) {'
            ' audits.push_back(std::string(t)+"|"+std::to_string(id)+"|"+m+"|"+r); }')
        cases = r'''
int main() {
 // Uma leitura do DY50 com o resultado dado; avança o relógio além do intervalo de 150 ms.
 auto ler = [](uint8_t r) { finger.imageStatus = r; now += 200; fingerprintTick(); };
 auto comecar = [](Ui etapa) {
  door.begin(true, now); resetUi(); noticeDuration=0; waitFingerRemoval=false; audits.clear();
  fingerprintReady=true; storageReady=true; finger.searchResult=FINGERPRINT_OK; ui=etapa;
 };
 // (a) 3 IMAGEFAIL seguidos em FirstFinger não abortam; a leitura OK seguinte segue o fluxo.
 comecar(Ui::FirstFinger);
 for (int i=0;i<3;++i) ler(FINGERPRINT_IMAGEFAIL);
 assert(ui==Ui::FirstFinger && enrollReadFails==3 && noticeDuration==0 && audits.empty());
 finger.searchResult=FINGERPRINT_NOTFOUND; ler(FINGERPRINT_OK);
 assert(ui==Ui::RemoveFinger && enableRequested && enrollReadFails==0 && audits.empty());
 // (b) 4 IMAGEFAIL seguidos abortam com o mesmo aviso e auditoria de antes, em cada etapa.
 Ui etapas[] = {Ui::RemoveFinger, Ui::FirstFinger, Ui::SecondFinger};
 for (Ui etapa : etapas) {
  comecar(etapa);
  for (int i=0;i<3;++i) ler(FINGERPRINT_IMAGEFAIL);
  assert(ui==etapa && audits.empty());
  ler(FINGERPRINT_IMAGEFAIL);
  assert(ui==Ui::Access && noticeLine1=="Cadastro falhou" && noticeLine2=="Erro de leitura" && noticeError);
  assert(audits.size()==1 && audits[0]=="enroll_failed|0|admin|Erro de leitura" && enrollReadFails==0);
 }
 // (c) IMAGEFAIL, IMAGEFAIL, NOFINGER, IMAGEFAIL x3: NOFINGER zera; não aborta.
 comecar(Ui::FirstFinger);
 ler(FINGERPRINT_IMAGEFAIL); ler(FINGERPRINT_IMAGEFAIL); ler(FINGERPRINT_NOFINGER);
 assert(ui==Ui::FirstFinger && enrollReadFails==0);
 for (int i=0;i<3;++i) ler(FINGERPRINT_IMAGEFAIL);
 assert(ui==Ui::FirstFinger && enrollReadFails==3 && audits.empty());
 // (d) PACKETRECIEVEERR aborta já na 1a, em cada etapa, e marca o DY50 como indisponível.
 for (Ui etapa : etapas) {
  comecar(etapa);
  ler(FINGERPRINT_PACKETRECIEVEERR);
  assert(ui==Ui::Access && noticeLine2=="Erro de leitura" && !fingerprintReady && enrollReadFails==0);
  assert(audits.size()==1 && audits[0]=="enroll_failed|0|admin|Erro de leitura");
 }
 // (e) contador zera entre etapas (3 falhas, OK, NOFINGER, 3 falhas) e ao cancelar ou iniciar outro cadastro.
 comecar(Ui::FirstFinger); finger.searchResult=FINGERPRINT_NOTFOUND;
 for (int i=0;i<3;++i) ler(FINGERPRINT_IMAGEFAIL);
 ler(FINGERPRINT_OK); assert(ui==Ui::RemoveFinger && enrollReadFails==0);
 ler(FINGERPRINT_NOFINGER); assert(ui==Ui::SecondFinger && enrollReadFails==0);
 for (int i=0;i<3;++i) ler(FINGERPRINT_IMAGEFAIL);
 assert(ui==Ui::SecondFinger && enrollReadFails==3 && audits.empty());
 comecar(Ui::FirstFinger);
 for (int i=0;i<3;++i) ler(FINGERPRINT_IMAGEFAIL);
 resetUi(); assert(enrollReadFails==0);
 ui=Ui::FirstFinger;
 for (int i=0;i<3;++i) ler(FINGERPRINT_IMAGEFAIL);
 assert(ui==Ui::FirstFinger && audits.empty());
 comecar(Ui::FirstFinger);
 for (int i=0;i<3;++i) ler(FINGERPRINT_IMAGEFAIL);
 assert(enrollReadFails==3);
 beginEnrollment();
 assert(ui==Ui::RemoveFinger && enrollReadFails==0);
 for (int i=0;i<3;++i) ler(FINGERPRINT_IMAGEFAIL);
 assert(ui==Ui::RemoveFinger && audits.empty());
 // (f) fora do cadastro (Ui::Access), IMAGEFAIL só mostra o aviso e não usa o contador.
 comecar(Ui::Access);
 for (int i=0;i<5;++i) { noticeDuration=0; ler(FINGERPRINT_IMAGEFAIL); }
 assert(ui==Ui::Access && noticeLine1=="Falha no leitor" && noticeLine2=="Tente novamente");
 assert(audits.empty() && enrollReadFails==0);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'test.cpp'
            binary = Path(directory) / 'test'
            source.write_text(registro + body + handle_key + finger_tick + cases)
            cmd = [os.environ.get('CXX', 'c++'), '-std=c++11', '-I', str(MEGA)]
            sdk = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform == 'darwin' and sdk.exists(): cmd += ['-isysroot', str(sdk)]
            result = subprocess.run(cmd + [str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_erro_de_armazenamento_mostra_aviso_e_audita(self):
        sketch = (MEGA / 'MegaControlador.ino').read_text()
        globais = sketch[sketch.index('enum class Ui'):sketch.index('bool validPin(')]
        fluxo = sketch[sketch.index('bool validPin('):sketch.index('void handleKey(')]
        teclado = sketch[sketch.index('void handleKey('):sketch.index('void expireEntry()')]
        registro = PREFIX.replace(
            'void queueEvent(const char *,uint16_t,const char *,const char *) {}',
            '#include <vector>\nstd::vector<std::string> audits;\n'
            'void queueEvent(const char *t,uint16_t id,const char *m,const char *r) {'
            ' audits.push_back(std::string(t)+"|"+std::to_string(id)+"|"+m+"|"+r); }')
        cases = r'''
int main() {
 door.begin(true, now); resetUi();
 // Id desconhecido com armazenamento ok: mantém o motivo antigo.
 storageReady=true; audits.clear(); noticeDuration=0;
 authorize(5,"fingerprint");
 assert(noticeLine1=="Acesso negado" && noticeLine2=="Cadastro inativo" && noticeError);
 assert(audits.size()==1 && audits[0]=="access_denied|5|fingerprint|inactive_or_unknown");
 // Armazenamento com falha: aviso explícito, sem liberar a porta, auditoria com motivo de memória.
 storageReady=false; audits.clear(); noticeDuration=0;
 authorize(1,"fingerprint");
 assert(noticeLine1=="Falha memoria" && noticeLine2=="Acesso negado" && noticeError);
 assert(door.state==DoorState::Idle && audits.size()==1);
 assert(audits[0]=="access_denied|1|fingerprint|Erro na memoria");
 // Cadastro com falha de armazenamento: encerra com aviso e audita enroll_failed, sem gravar.
 door.begin(true, now); resetUi(); noticeDuration=0; audits.clear();
 ui=Ui::ConfirmPin; pendingId=2; firstPin="123456"; entry="123456";
 confirmEnrollment();
 assert(noticeLine1=="Cadastro falhou" && noticeLine2=="Erro na memoria" && noticeError);
 assert(ui==Ui::Access && entry=="" && finger.deleted==0);
 assert(audits.size()==1 && audits[0]=="enroll_failed|0|admin|Erro na memoria");
 // Teclado com falha de armazenamento: aviso explícito e senha limpa.
 ui=Ui::Access; entry="123456"; noticeDuration=0; audits.clear();
 handleKey('#');
 assert(noticeLine1=="Falha memoria" && noticeLine2=="Acesso negado" && entry=="");
 assert(audits.size()==1 && audits[0]=="access_denied|0|password|Erro na memoria");
 // Teclado com armazenamento ok e senha errada: continua como senha incorreta.
 storageReady=true; ui=Ui::Access; entry="999999"; noticeDuration=0; audits.clear();
 handleKey('#');
 assert(noticeLine2=="Senha incorreta" && audits.size()==1 && audits[0]=="access_denied|0|password|invalid_pin");
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'test.cpp'
            binary = Path(directory) / 'test'
            source.write_text(registro + globais + fluxo + teclado + cases)
            cmd = [os.environ.get('CXX', 'c++'), '-std=c++11', '-I', str(MEGA)]
            sdk = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform == 'darwin' and sdk.exists(): cmd += ['-isysroot', str(sdk)]
            result = subprocess.run(cmd + [str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_orfa_no_dy50_e_apagada_antes_de_nova_busca(self):
        sketch = (MEGA / 'MegaControlador.ino').read_text()
        body = sketch[sketch.index('enum class Ui'):sketch.index('void handleKey(')]
        handle_key = sketch[sketch.index('void handleKey('):sketch.index('void fingerprintTick()')]
        finger_tick = sketch[sketch.index('void fingerprintTick()'):sketch.index('void rgb(')]
        registro = PREFIX.replace(
            'uint8_t fingerFastSearch() { maybeOpen(3); return FINGERPRINT_OK; }',
            'uint8_t searchResult=FINGERPRINT_OK; uint8_t fingerFastSearch() { maybeOpen(3); return searchResult; }'
        ).replace(
            'uint8_t deleteModel(uint16_t id) { deleted=id; return 0; }',
            'int deleteCalls=0; uint8_t deleteResult=0; bool openOnDelete=false;\n'
            ' uint8_t deleteModel(uint16_t id) { deleted=id; ++deleteCalls; if(openOnDelete) { ticksUntilOpen=1; doorTick(); } return deleteResult; }'
        ).replace(
            'void queueEvent(const char *,uint16_t,const char *,const char *) {}',
            '#include <vector>\nstd::vector<std::string> audits;\n'
            'void queueEvent(const char *t,uint16_t id,const char *m,const char *r) {'
            ' audits.push_back(std::string(t)+"|"+std::to_string(id)+"|"+m+"|"+r); }')
        cases = r'''
int main() {
 // Digital 1 cadastrada na EEPROM; a órfã usada nos casos é o slot 3.
 UserRecord cadastrado = {}; cadastrado.active = 1; assert(saveRecord(1, cadastrado) && exists(1));
 // (a) órfã em 1..MAX_USERS: apaga, volta a retirar o dedo, sem falha e sem auditoria nova.
 door.begin(true,now); resetUi(); noticeDuration=0; waitFingerRemoval=false; audits.clear();
 ui=Ui::FirstFinger; finger.fingerID=3; finger.deleteCalls=0; finger.deleteResult=0; finger.deleted=0;
 now+=200; fingerprintTick();
 assert(finger.deleteCalls==1 && finger.deleted==3);
 assert(ui==Ui::RemoveFinger && !enableRequested && uiTouched==now);
 assert(noticeLine1=="Slot orfao limpo" && noticeLine2=="Recoloque o dedo" && !noticeError);
 assert(audits.empty() && door.state==DoorState::Idle);
 // Aviso ativo bloqueia leitura; expirado, retirar o dedo leva de volta à primeira captura.
 now+=100; finger.imageStatus=0; fingerprintTick(); assert(finger.deleteCalls==1 && ui==Ui::RemoveFinger);
 now+=2100; finger.imageStatus=FINGERPRINT_NOFINGER; fingerprintTick(); assert(ui==Ui::FirstFinger);
 // Nova busca NOTFOUND segue o fluxo normal: retirar o dedo e depois o segundo toque.
 now+=200; finger.imageStatus=0; finger.searchResult=FINGERPRINT_NOTFOUND; fingerprintTick();
 assert(ui==Ui::RemoveFinger && enableRequested && finger.deleteCalls==1 && noticeLine2=="Recoloque o dedo");
 now+=2100; finger.imageStatus=FINGERPRINT_NOFINGER; fingerprintTick(); assert(ui==Ui::SecondFinger);
 // (a2) se a órfã escondia uma digital cadastrada, a nova busca a encontra e rejeita o cadastro.
 door.begin(true,now); resetUi(); noticeDuration=0; waitFingerRemoval=false; audits.clear();
 ui=Ui::FirstFinger; finger.fingerID=3; finger.deleteCalls=0; finger.searchResult=FINGERPRINT_OK; finger.imageStatus=0;
 now+=200; fingerprintTick(); assert(finger.deleteCalls==1 && ui==Ui::RemoveFinger);
 now+=2100; finger.imageStatus=FINGERPRINT_NOFINGER; fingerprintTick(); assert(ui==Ui::FirstFinger);
 now+=200; finger.imageStatus=0; finger.fingerID=1; fingerprintTick();
 assert(noticeLine2=="Digital ja usada" && noticeError && ui==Ui::Access && finger.deleteCalls==1);
 assert(audits.size()==1 && audits[0]=="enroll_failed|0|admin|Digital ja usada");
 // (b) apagamento falha (erro de pacote ou falha do DY50): encerra como antes, com "Slot DY orfao".
 uint8_t falhas[] = {FINGERPRINT_PACKETRECIEVEERR, 0x10};
 for (uint8_t falha : falhas) {
  door.begin(true,now); resetUi(); noticeDuration=0; waitFingerRemoval=false; audits.clear();
  fingerprintReady=true; ui=Ui::FirstFinger; finger.fingerID=3; finger.deleteResult=falha;
  int antes=finger.deleteCalls; now+=200; fingerprintTick();
  assert(finger.deleteCalls==antes+1 && finger.deleted==3);
  assert(ui==Ui::Access && noticeLine2=="Slot DY orfao" && noticeError);
  assert(audits.size()==1 && audits[0]=="enroll_failed|0|admin|Slot DY orfao");
  assert(fingerprintReady==(falha!=FINGERPRINT_PACKETRECIEVEERR));
  fingerprintReady=true; finger.deleteResult=0;
 }
 // (c) ID fora de 1..MAX_USERS: nunca apaga; encerra como antes.
 uint16_t fora[] = {0, 101};
 for (uint16_t id : fora) {
  door.begin(true,now); resetUi(); noticeDuration=0; waitFingerRemoval=false; audits.clear();
  ui=Ui::FirstFinger; finger.fingerID=id; int antes=finger.deleteCalls; now+=200; fingerprintTick();
  assert(finger.deleteCalls==antes && ui==Ui::Access && noticeLine2=="Slot DY orfao");
  assert(audits.size()==1 && audits[0]=="enroll_failed|0|admin|Slot DY orfao");
 }
 // (d) digital já cadastrada: rejeita sem apagar nada.
 door.begin(true,now); resetUi(); noticeDuration=0; waitFingerRemoval=false; audits.clear();
 ui=Ui::FirstFinger; finger.fingerID=1; finger.deleteCalls=0; now+=200; fingerprintTick();
 assert(noticeLine2=="Digital ja usada" && ui==Ui::Access && finger.deleteCalls==0);
 // (e) porta abre durante o apagamento: não segue para o aviso de limpeza.
 door.begin(true,now); resetUi(); noticeDuration=0; waitFingerRemoval=false; audits.clear();
 ui=Ui::FirstFinger; finger.fingerID=3; finger.deleteCalls=0; finger.deleteResult=0; finger.openOnDelete=true;
 now+=200; fingerprintTick();
 assert(finger.deleteCalls==1 && door.state==DoorState::Alarm && ui==Ui::Access && waitFingerRemoval);
 assert(noticeLine1!="Slot orfao limpo" && audits.empty());
 finger.openOnDelete=false;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'test.cpp'
            binary = Path(directory) / 'test'
            source.write_text(registro + body + handle_key + finger_tick + cases)
            cmd = [os.environ.get('CXX', 'c++'), '-std=c++11', '-I', str(MEGA)]
            sdk = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform == 'darwin' and sdk.exists(): cmd += ['-isysroot', str(sdk)]
            result = subprocess.run(cmd + [str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
