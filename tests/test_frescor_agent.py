"""Frescor: trechos reais dos dois sketches e UART simulada; não é ensaio físico."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import test_integrated_simulation as base

CASES = r'''
} // Cam
SerialFrame::Parser parser;
void deliverMega() {
 for(auto b:Mega::Serial2.output) if(parser.feed(b,Cam::clock)) {
  if(parser.data()[1]==MessageProtocol::Event) Cam::receiveEvent(parser.data(),parser.size(),parser.startedAt());
  else if(parser.data()[1]==MessageProtocol::PhotoProof) Cam::receivePhotoProof(parser.data(),parser.size());
 }
 Mega::Serial2.output.clear();
}
void deliverCam() {
 Mega::Serial2.input.insert(Mega::Serial2.input.end(),Cam::Serial2.output.begin(),Cam::Serial2.output.end());
 Cam::Serial2.output.clear(); Mega::linkTick();
}
void startAccess() { Mega::authorizationAt=Mega::now; Mega::queueEvent("access_granted",1,"password",""); Mega::linkTick(); }
void timeout() { Cam::clock+=5000; Cam::photoTick(); deliverCam(); }
int main() {
 // Evento fresco e prova correta; ACK e repetição não duplicam imagem.
 startAccess(); deliverMega(); assert(Cam::pendingPhoto.active && Cam::queue.items.empty());
 uint8_t old[26]; memcpy(old,Cam::pendingPhoto.challenge,26); old[1]=MessageProtocol::PhotoProof;
 deliverCam(); deliverMega(); assert(Cam::queue.items.size()==1 && Cam::queue.items[0].photo);
 deliverCam(); assert(Mega::count==0);
 // Seis segundos na UART antes da CAM ler: captura candidata nunca é associada.
 Mega::now+=1001; Cam::clock+=1001; startAccess(); Mega::now+=6000; Cam::clock+=6000;
 deliverMega(); assert(Cam::pendingPhoto.active); deliverCam(); deliverMega();
 assert(Cam::queue.items.size()==1); timeout(); assert(Cam::queue.items.size()==2 && !Cam::queue.items[1].photo);
 // Resposta antiga não valida nonce de um evento novo; perda leva a timeout.
 Mega::now+=1001; Cam::clock+=1001; startAccess(); deliverMega(); assert(Cam::pendingPhoto.active);
 Cam::receivePhotoProof(old,sizeof old); assert(Cam::pendingPhoto.active);
 uint8_t wrong[26]; memcpy(wrong,Cam::pendingPhoto.challenge,26); wrong[1]=MessageProtocol::PhotoProof; wrong[6]^=1;
 Cam::receivePhotoProof(wrong,sizeof wrong); assert(Cam::pendingPhoto.active); timeout();
 assert(!Cam::queue.items.back().photo);
 // A câmera gastou mais de cinco segundos; o Mega não valida a foto.
 Mega::now+=1001; Cam::clock+=1001; Cam::captureDelay=3000; startAccess(); deliverMega();
 Cam::captureDelay=0; assert(Cam::pendingPhoto.active); deliverCam(); deliverMega();
 assert(Cam::pendingPhoto.active); timeout(); assert(!Cam::queue.items.back().photo);
 // Reinício do Mega invalida identidade; resposta antiga não é aceita.
 Mega::now+=1001; Cam::clock+=1001; startAccess(); deliverMega();
 Mega::bootNumber++; Mega::count=0; Mega::head=0; Mega::eventSequence=0;
 deliverCam(); deliverMega(); assert(Cam::pendingPhoto.active); timeout(); assert(!Cam::queue.items.back().photo);
 // Prova íntegra atrasada após timeout é ignorada, inclusive se duplicada.
 Mega::now+=1001; Cam::clock+=1001; startAccess(); deliverMega(); deliverCam();
 Cam::clock+=5000; Cam::photoTick(); assert(!Cam::queue.items.back().photo);
 deliverMega(); deliverCam(); assert(!Cam::queue.items.back().photo);
 // Rollover dos dois relógios, com evento realmente recente.
 Mega::now=0xfffffff0u; Cam::clock=0xfffffff0u; startAccess(); Mega::now+=32; Cam::clock+=32;
 deliverMega(); deliverCam(); deliverMega(); assert(Cam::queue.items.back().photo); deliverCam();
 for(auto &item:Cam::queue.items) free(item.photo);
}
'''
class FrescorUartTests(unittest.TestCase):
    def test_vinculo_e_atrasos_reais_dos_sketches(self):
        mega=(base.MEGA/'MegaControlador.ino').read_text(); cam=(base.CAM/'Esp32CamRede.ino').read_text()
        logic=mega[mega.index('enum class Ui'):mega.index('void handleKey(')]
        link=mega[mega.index('MessageProtocol::EventData outbound'):mega.index('void serialTick()')]
        capture=cam[cam.index('struct PendingPhoto'):cam.index('int request(')]
        prefix=base.CAM_PREFIX.replace('uint32_t millis() { return Mega::now; }', 'uint32_t clock=1000; uint32_t millis() { return clock; }')
        prefix=prefix.replace('camera_fb_t *esp_camera_fb_get() { ++captures; return &fb; }', 'uint32_t captureDelay=0; camera_fb_t *esp_camera_fb_get() { ++captures; clock+=captureDelay; Mega::now+=captureDelay; return &fb; }')
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'sim.cpp'; binary=Path(directory)/'sim'
            source.write_text(base.PREFIX+logic+link+prefix+capture+CASES)
            cmd=[os.environ.get('CXX','c++'),'-std=c++11','-I',str(base.MEGA)]
            sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform=='darwin' and sdk.exists(): cmd+=['-isysroot',str(sdk)]
            result=subprocess.run(cmd+[str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
