"""Exercita resets recebidos durante espera DY50 e a fila limitada real."""
from pathlib import Path
import os, subprocess, sys, tempfile, unittest
from test_mega_link import MEGA, PREFIX

PREFIX = PREFIX.replace('int availableForWrite() { return 1; }', 'int availableForWrite() { return writable; }').replace('std::vector<uint8_t> input,output; size_t pos=0;', 'std::vector<uint8_t> input,output; size_t pos=0; bool writable=true;')
PREFIX = PREFIX[:PREFIX.index('unsigned resets=0;')] + r'''
unsigned resets=0, writes=0; uint64_t applied=42; bool busy=false;
const char *resetPassword(uint16_t id,const String &pin,const char *,uint64_t token) {
 ++resets; if(id!=1) return "unknown_user"; if(token==applied) return "ok";
 if(busy) return "device_busy"; if(pin!="123456") return "invalid_pin";
 applied=token; ++writes; return "ok";
}
'''
CASES = r'''
struct Sink { std::vector<uint8_t> data; void write(uint8_t b){data.push_back(b);} };
void send(uint32_t cmd,uint64_t token) { using namespace MessageProtocol; uint8_t b[21]={kVersion,Reset}; put32(b+2,cmd); b[6]=1; memcpy(b+7,"123456",6); for(int i=0;i<8;i++) b[13+i]=token>>(8*i); Sink s; assert(SerialFrame::send(s,b,21)); Serial2.input.insert(Serial2.input.end(),s.data.begin(),s.data.end()); }
void pump(bool sensor,int times=20){for(int i=0;i<times;i++){++now;linkTick(sensor);}}
int main(){ using namespace MessageProtocol;
 // Token já aplicado deve confirmar após a espera mesmo com dispositivo ocupado.
 busy=true; send(1,42); pump(true); assert(resets==0 && replyCount==1);
 pump(false); assert(resets==1 && writes==0 && replyCount==0);
 SerialFrame::Parser p; bool ok=false; for(auto b:Serial2.output) if(p.feed(b,now) && p.data()[1]==ResetResult) ok=p.data()[6]==1; assert(ok);
 // Fila cheia: nenhuma aplicação ou resposta falsa para o comando descartado.
 Serial2.output.clear(); Serial2.writable=false; busy=false;
 for(int i=0;i<6;i++) send(10+i,50+i); pump(true,30);
 assert(replyCount==4 && droppedReplies>=2 && resets==1);
 // Mesmo sem espaço UART, uma resposta pode ocupar o quadro corrente;
 // ela conserva o resultado antes de qualquer outro comando ser executado.
 pump(false,2); assert(resets==2 && writes==1);
 Serial2.writable=true; pump(false,50); assert(resets==5 && writes==4);
 // Reenvio com token já persistido após perda de resposta/reboot lógico.
 uint64_t last=applied; send(20,last); pump(true); assert(resets==5); pump(false); assert(resets==6 && writes==4);
 // Comando descartado pode ser reenviado e aplicado.
 send(30,55); pump(false); assert(resets==7 && writes==5 && applied==55);
}
'''
class ResetAdiadoTests(unittest.TestCase):
 def test_wait_retries_and_bounded_responses(self):
  sketch=(MEGA/'MegaControlador.ino').read_text()
  body=sketch[sketch.index('MessageProtocol::EventData outbound'):sketch.index('void serialTick()')]
  with tempfile.TemporaryDirectory() as d:
   source=Path(d)/'test.cpp'; binary=Path(d)/'test'; source.write_text(PREFIX+body+CASES)
   cmd=[os.environ.get('CXX','c++'),'-std=c++11','-I',str(MEGA)]
   sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
   if sys.platform=='darwin' and sdk.exists(): cmd+=['-isysroot',str(sdk)]
   subprocess.run(cmd+[str(source),'-o',str(binary)],check=True)
   subprocess.run([str(binary)],check=True,timeout=3)
