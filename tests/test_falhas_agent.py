"""Limites em host: funções reais, sem hardware/RTOS e sem persistência de fila."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_camera_logic import CAM, PREFIX

ROOT = Path(__file__).resolve().parents[1]


def run_cpp(test, source, includes):
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / 'probe.cpp'
        exe = Path(d) / 'probe'
        src.write_text(source)
        cmd = [os.environ.get('CXX', 'c++'), '-std=c++11']
        for path in includes:
            cmd += ['-I', str(path)]
        sdk = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
        if sys.platform == 'darwin' and sdk.exists():
            cmd += ['-isysroot', str(sdk)]
        result = subprocess.run(cmd + [str(src), '-o', str(exe)], capture_output=True, text=True)
        test.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(exe)], capture_output=True, text=True)
        test.assertEqual(result.returncode, 0, result.stderr)


class FalhasAgent(unittest.TestCase):
    def test_camera_saturation_and_restart_during_capture(self):
        sketch = (CAM / 'Esp32CamRede.ino').read_text()
        body = sketch[sketch.index('struct PendingPhoto'):sketch.index('int request(')]
        prefix = PREFIX.replace(
            'camera_fb_t *esp_camera_fb_get() { ++captures; ticks += captureDelay; return &fb; }',
            'bool powerCut=false; camera_fb_t *esp_camera_fb_get() { ++captures; if(powerCut) throw 1; return &fb; }')
        cases = r'''
int main() {
 EventData e={1,1,100,0,AccessGranted,1,Password,1,0,100}; uint8_t b[kEventLength];
 // Oito aceitos, o nono não tem ACK. Libera espaço e reenvia o nono.
 for(unsigned i=1;i<=8;i++){e.messageId=i; assert(encodeEvent(e,b,sizeof b)); receiveEvent(b,sizeof b,ticks); uint8_t proof[26]; memcpy(proof,pendingPhoto.challenge,26); proof[1]=PhotoProof; receivePhotoProof(proof,26);}
 assert(queue.items.size()==8 && captures==16);
 size_t ack=Serial2.bytes.size(); e.messageId=9; assert(encodeEvent(e,b,sizeof b)); receiveEvent(b,sizeof b,ticks);
 assert(queue.items.size()==8 && Serial2.bytes.size()==ack && captures==16);
 free(queue.items.front().photo); queue.items.erase(queue.items.begin()); receiveEvent(b,sizeof b,ticks); uint8_t proof[26]; memcpy(proof,pendingPhoto.challenge,26); proof[1]=PhotoProof; receivePhotoProof(proof,26);
 assert(queue.items.size()==8 && captures==18 && Serial2.bytes.size()>ack);
 // Reboot da CAM: descarte da RAM e reinicialização das variáveis globais.
 for(auto &item:queue.items) free(item.photo); queue.items.clear(); lastBoot=lastEvent=0; Serial2.bytes.clear();
 e.messageId=10; assert(encodeEvent(e,b,sizeof b)); powerCut=true;
 try { receiveEvent(b,sizeof b,ticks); assert(false); } catch(int) {}
 assert(queue.items.empty() && Serial2.bytes.empty());
 powerCut=false; lastBoot=lastEvent=0; receiveEvent(b,sizeof b,ticks); memcpy(proof,pendingPhoto.challenge,26); proof[1]=PhotoProof; receivePhotoProof(proof,26);
 assert(queue.items.size()==1 && queue.items[0].event.messageId==10 && !Serial2.bytes.empty());
 free(queue.items[0].photo); queue.items.clear();
 // Cem autorizações com drenagem simulada: verifica capacidade de continuar processando.
 int before=captures;
 for(unsigned i=11;i<111;i++) {
  e.messageId=i; assert(encodeEvent(e,b,sizeof b)); receiveEvent(b,sizeof b,ticks); memcpy(proof,pendingPhoto.challenge,26); proof[1]=PhotoProof; receivePhotoProof(proof,26);
  assert(queue.items.size()==1 && queue.items[0].event.messageId==i);
  free(queue.items[0].photo); queue.items.clear();
 }
 assert(captures==before+200);
}
'''
        run_cpp(self, prefix + body + cases, [CAM])

    def test_full_store_and_repeated_interrupted_recovery(self):
        cases = r'''
#include "UserStore.h"
#include <cassert>
#include <cstring>
#include <stdexcept>
struct Memory {
 unsigned char data[4096]; int budget=-1;
 Memory(){memset(data,255,sizeof data);}
 uint8_t read(uint16_t a){assert(a<sizeof data);return data[a];}
 void update(uint16_t a,uint8_t b){assert(a<sizeof data);if(data[a]==b)return; if(budget==0)throw 1; if(budget>0)--budget;data[a]=b;}
};
int main(){
 Memory base; UserStore::Record r={}, got={};
 for(int id=1;id<=100;id++){r.bytes[0]=1; r.bytes[1]=id; assert(UserStore::save(base,id,r));}
 assert(!UserStore::save(base,101,r));
 for(int id=1;id<=100;id++){assert(UserStore::load(base,id,got)==1); assert(got.bytes[1]==id);}
 // Corte em cada escrita de atualização; em seguida um segundo corte durante recovery.
 for(int first=0;first<70;first++) for(int second=0;second<35;second++){
  Memory m=base; r.bytes[0]=2;r.bytes[1]=200; m.budget=first;
  try{UserStore::save(m,50,r);}catch(int){}
  m.budget=second; try{UserStore::recover(m);}catch(int){}
  m.budget=-1; assert(UserStore::recover(m));
  for(int id=1;id<=100;id++){assert(UserStore::load(m,id,got)==1);
   assert(got.bytes[1]==id || (id==50 && got.bytes[1]==200));}
 }
}
'''
        run_cpp(self, cases, [ROOT / 'firmware/MegaControlador'])
