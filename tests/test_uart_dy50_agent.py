"""Exercita o adaptador DY50 e enlace reais durante espera com RX finito."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from test_mega_link import MEGA, PREFIX

PREFIX = PREFIX.replace('#include <vector>', '#include <vector>\n#include <deque>\n#include "Dy50ResponseFilter.h"')
PREFIX = PREFIX.replace('std::vector<uint8_t> input,output; size_t pos=0;\n int available() { return int(input.size()-pos); }', '''
 std::deque<uint8_t> input; std::vector<uint8_t> output; unsigned overflow=0;
 void receive(uint8_t b) { if (input.size()==64) ++overflow; else input.push_back(b); }
 int available() { return int(input.size()); }''').replace('uint8_t read() { return input[pos++]; }', 'uint8_t read() { auto b=input.front(); input.pop_front(); return b; }')
PREFIX += r'''
class Print { public: virtual size_t write(uint8_t)=0; };
class Stream:public Print { public: virtual int available()=0; virtual int read()=0; virtual int peek()=0; virtual void flush()=0; };
struct SensorPort { std::deque<uint8_t> input; int available(){return input.size();} int read(){auto b=input.front(); input.pop_front(); return b;} int peek(){return input.empty()?-1:input.front();} void flush(){} size_t write(uint8_t){return 1;} } Serial1;
bool doorServiceReady=true;
void linkTick(bool);
'''
CASES = r'''
struct Sink { std::vector<uint8_t> data; void write(uint8_t b) { data.push_back(b); } };
std::vector<uint8_t> framed(const uint8_t *b,size_t n) { Sink s; assert(SerialFrame::send(s,b,n)); return s.data; }
void waitWithArrival(ServicedFingerStream &sensor, const std::vector<uint8_t> &wire, unsigned ms) {
 size_t i=0; for(unsigned t=0;t<ms;++t) { ++now; for(int j=0;j<4 && i<wire.size();++j) Serial2.receive(wire[i++]); sensor.available(); }
 assert(i==wire.size() && !Serial2.overflow && Serial2.input.empty());
}
int main() {
 using namespace MessageProtocol; ServicedFingerStream sensor;
 authorizationAt=now; queueEvent("access_granted",1,"password","");
 uint8_t challenge[26]={kVersion,PhotoChallenge}; put32(challenge+2,1); put32(challenge+6,3); challenge[10]=77;
 uint8_t clock[10]={kVersion,Clock}; put32(clock+6,1700000000UL);
 uint8_t reset[21]={kVersion,Reset}; put32(reset+2,9); reset[6]=1; memcpy(reset+7,"123456",6); reset[13]=42;
 auto wire=framed(challenge,sizeof challenge); auto c=framed(clock,sizeof clock); auto r=framed(reset,sizeof reset);
 wire.insert(wire.end(),c.begin(),c.end()); wire.insert(wire.end(),r.begin(),r.end());
 waitWithArrival(sensor,wire,1000); assert(syncEpoch==1700000000UL && resets==0);
 SerialFrame::Parser parser; bool proof=false,busy=false;
 for(auto b:Serial2.output) if(parser.feed(b,now)) { if(parser.data()[1]==PhotoProof) proof=parser.data()[10]==77; if(parser.data()[1]==ResetResult) busy=parser.data()[6]==0 && parser.data()[7]==2; }
 assert(proof && !busy);
 linkTick(false); assert(resets==1);
 Serial2.output.clear(); now=authorizationAt+5001; waitWithArrival(sensor,framed(challenge,sizeof challenge),100);
 for(auto b:Serial2.output) if(parser.feed(b,now)) assert(parser.data()[1]!=PhotoProof);
 assert(!photoFresh[head]);
 // Após a espera, um reset reenviado usa o caminho normal.
 waitWithArrival(sensor,{},1); for(auto b:r) Serial2.receive(b); linkTick(false); assert(resets==2);
}
'''
class UartDy50Tests(unittest.TestCase):
 def test_finite_rx_during_sensor_wait(self):
  sketch=(MEGA/'MegaControlador.ino').read_text()
  adapter=sketch[sketch.index('class ServicedFingerStream'):sketch.index('ServicedFingerStream fingerStream;')]
  body=sketch[sketch.index('MessageProtocol::EventData outbound'):sketch.index('void serialTick()')]
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'test.cpp'; binary=Path(tmp)/'test'; source.write_text(PREFIX+adapter+body+CASES)
   cmd=[os.environ.get('CXX','c++'),'-std=c++11','-I',str(MEGA)]
   sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
   if sys.platform=='darwin' and sdk.exists(): cmd+=['-isysroot',str(sdk)]
   subprocess.run(cmd+[str(source),'-o',str(binary)],check=True)
   subprocess.run([str(binary)],check=True,timeout=3)
