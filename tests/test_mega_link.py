"""Exercita fila e enlace reais do sketch Mega com UART simulada."""
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
using String = std::string;
uint32_t authorizationAt=0; uint32_t now=100,bootNumber=3,eventSequence=0,droppedEvents=0;
uint32_t millis() { return now; }
bool activeUser(uint16_t id) { return id==1; }
struct SerialPort {
 std::vector<uint8_t> input,output; size_t pos=0;
 int available() { return int(input.size()-pos); }
 int availableForWrite() { return 1; }
 uint8_t read() { return input[pos++]; }
 void write(uint8_t b) { output.push_back(b); }
} Serial2;
void doorTick() {} void outputsTick() {}
unsigned resets=0;
const char *resetPassword(uint16_t id,const String &pin,const char *,uint64_t token) {
 ++resets; return id==1 && pin=="123456" && token==42 ? "ok" : "invalid_pin";
}
'''
CASES = r'''
struct Sink { std::vector<uint8_t> data; void write(uint8_t b) { data.push_back(b); } };
void sendToMega(const uint8_t *body,size_t len) { Sink s; assert(SerialFrame::send(s,body,len)); Serial2.input.insert(Serial2.input.end(),s.data.begin(),s.data.end()); }
int main() {
 using namespace MessageProtocol;
 queueEvent("access_granted",1,"password",""); assert(count==1);
 linkTick(); assert(!Serial2.output.empty());
 SerialFrame::Parser p; bool got=false;
 for(auto b:Serial2.output) got |= p.feed(b,now);
 EventData e={}; assert(got && decodeEvent(p.data(),p.size(),e));
 assert(e.kind==AccessGranted && e.user==1 && e.boot==3 && e.messageId==1);
 uint8_t ack[10]={kVersion,Ack}; put32(ack+2,1); put32(ack+6,4); sendToMega(ack,sizeof ack);
 linkTick(); assert(count==1); put32(ack+6,3); sendToMega(ack,sizeof ack); linkTick(); assert(count==0);
 uint8_t clock[10]={kVersion,Clock}; put32(clock+2,1); put32(clock+6,1700000000UL);
 sendToMega(clock,sizeof clock); linkTick(); assert(syncEpoch==1700000000UL);
 uint8_t reset[21]={kVersion,Reset}; put32(reset+2,5); reset[6]=1; memcpy(reset+7,"123456",6); reset[13]=42;
 sendToMega(reset,sizeof reset); linkTick(); assert(resets==1);
 // A fila tem limite e não confirma como entregue o evento descartado.
 for (int i=0;i<16;++i) queueEvent("access_granted",1,"password","");
 assert(count==16 && droppedEvents==0);
 queueEvent("access_granted",1,"password","");
 assert(count==16 && droppedEvents==1);
}
'''
class MegaLinkTests(unittest.TestCase):
    def test_real_queue_ack_clock_and_reset(self):
        sketch=(MEGA/'MegaControlador.ino').read_text()
        body=sketch[sketch.index('MessageProtocol::EventData outbound'):sketch.index('void serialTick()')]
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'test.cpp'; binary=Path(directory)/'test'; source.write_text(PREFIX+body+CASES)
            cmd=[os.environ.get('CXX','c++'),'-std=c++11','-I',str(MEGA)]
            sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform=='darwin' and sdk.exists(): cmd+=['-isysroot',str(sdk)]
            result=subprocess.run(cmd+[str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
