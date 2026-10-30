"""Mega e CAM: fila cheia e acesso atrasado, com hardware dublado."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import test_integrated_simulation as base

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
int main() {
 assert(BootCounter::next(Mega::EEPROM,Mega::bootNumber));
 Mega::door.begin(true,Mega::now);
 Cam::queue.capacity=1;
 Mega::queueEvent("device_boot",0,"system","");
 Mega::linkTick(); megaToCamera(); cameraToMega();
 assert(Mega::count==0 && Cam::queue.items.size()==1);
 Mega::authorizationAt=Mega::now; Mega::queueEvent("access_granted",1,"password","");
 Mega::now+=1001; Mega::linkTick(); megaToCamera(); cameraToMega();
 assert(Mega::count==1 && Cam::queue.items.size()==1 && Cam::captures==0);
 // Após liberação da fila, o mesmo evento é reenviado com atraso maior que 5 s.
 Cam::queue.items.clear(); Mega::now+=5001;
 Mega::linkTick(); megaToCamera(); cameraToMega();
 if (Cam::pendingPhoto.active) { Mega::now+=5000; Cam::photoTick(); cameraToMega(); }
 assert(Mega::count==0 && Cam::queue.items.size()==1);
 auto item=Cam::queue.items[0];
 assert(item.event.kind==MessageProtocol::AccessGranted && item.event.user==1);
 assert(item.photo==nullptr && Cam::captures==0);
 // Sem rede inicializada, nenhum ACK é emitido, mesmo com espaço livre.
 Cam::queue.items.clear(); Cam::networkReady=false;
 Mega::queueEvent("access_denied",1,"password","invalid_pin");
 Mega::now+=1001; Mega::linkTick(); megaToCamera(); cameraToMega();
 assert(Mega::count==1 && Cam::queue.items.empty());
 Cam::networkReady=true; Mega::now+=1001; Mega::linkTick(); megaToCamera(); cameraToMega();
 assert(Mega::count==0 && Cam::queue.items.size()==1);
 assert(Cam::queue.items[0].event.kind==MessageProtocol::AccessDenied);
 // A transmissão dura mais de 5 s, mas cada intervalo é menor que o timeout.
 Cam::queue.items.clear(); Mega::authorizationAt=Mega::now; Mega::queueEvent("access_granted",1,"password","");
 Mega::linkTick(); uint32_t started=Mega::now; megaToCamera(500); cameraToMega();
 assert(Mega::now-started>5000 && Cam::pendingPhoto.active);
 Mega::now+=5000; Cam::photoTick(); cameraToMega();
 assert(Mega::count==0 && Cam::queue.items.size()==1);
 assert(Cam::queue.items[0].photo==nullptr);
}
'''

class IntegracaoAgentTests(unittest.TestCase):
    def test_fila_cheia_atraso_e_rede_indisponivel(self):
        mega=(base.MEGA/'MegaControlador.ino').read_text()
        cam=(base.CAM/'Esp32CamRede.ino').read_text()
        logic=mega[mega.index('enum class Ui'):mega.index('void handleKey(')]
        link=mega[mega.index('MessageProtocol::EventData outbound'):mega.index('void serialTick()')]
        capture=cam[cam.index('struct PendingPhoto'):cam.index('int request(')]
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'sim.cpp'; binary=Path(directory)/'sim'
            source.write_text(base.PREFIX+logic+link+base.CAM_PREFIX+capture+CASES)
            cmd=[os.environ.get('CXX','c++'),'-std=c++11','-I',str(base.MEGA)]
            sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform=='darwin' and sdk.exists(): cmd+=['-isysroot',str(sdk)]
            result=subprocess.run(cmd+[str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
