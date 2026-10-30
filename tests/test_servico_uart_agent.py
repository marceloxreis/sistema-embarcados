"""Exercita o enlace Mega com recepção contínua e TX temporariamente cheio."""
from pathlib import Path
import os
import sys
import subprocess
import tempfile
import unittest
from test_mega_link import MEGA, PREFIX

PREFIX = PREFIX.replace('void doorTick() {} void outputsTick() {}\nunsigned resets=0;', '''
unsigned services=0, outputs=0;
void doorTick() { ++services; ++now; }
void outputsTick() { ++outputs; }
unsigned resets=0;''').replace('int available() { return int(input.size()-pos); }', '''
 bool continuous=false; int blocked=0;
 int available() { return pos<input.size() ? int(input.size()-pos) : (continuous ? 1 : 0); }
 int availableForWrite() { return blocked>0 ? (--blocked, 0) : 1; }''').replace(' int availableForWrite() { return 1; }','').replace('uint8_t read() { return input[pos++]; }', 'uint8_t read() { return pos<input.size() ? input[pos++] : 0; }')
CASES = r'''
struct Sink { std::vector<uint8_t> data; void write(uint8_t b) { data.push_back(b); } };
void inject(const uint8_t *b, size_t n) { Sink s; assert(SerialFrame::send(s,b,n)); Serial2.input.insert(Serial2.input.end(),s.data.begin(),s.data.end()); }
int main() {
 using namespace MessageProtocol;
 queueEvent("access_granted",1,"password","");
 Serial2.continuous=true; Serial2.blocked=10000;
 for(int i=0;i<10;++i) { doorTick(); outputsTick(); linkTick(); }
 assert(services>=10 && outputs==services && Serial2.output.empty() && linkTx.pending());
 Serial2.blocked=0; linkTick();
 assert(!Serial2.output.empty());
 Serial2.continuous=false;
 SerialFrame::Parser p; bool got=false; for(auto b:Serial2.output) got |= p.feed(b,now);
 EventData e={}; assert(got && decodeEvent(p.data(),p.size(),e) && e.messageId==1);
 Serial2.output.clear();
 uint8_t challenge[26]={kVersion,PhotoChallenge}; put32(challenge+2,1); put32(challenge+6,3); challenge[10]=0x7e;
 inject(challenge,sizeof challenge);
 for(int i=0;i<4 && Serial2.pos<Serial2.input.size();++i) linkTick();
 got=false; for(auto b:Serial2.output) got |= p.feed(b,now);
 assert(got && p.size()==26 && p.data()[1]==PhotoProof && p.data()[10]==0x7e);
 uint8_t ack[10]={kVersion,Ack}; put32(ack+2,1); put32(ack+6,3); inject(ack,sizeof ack);
 for(int i=0;i<4 && Serial2.pos<Serial2.input.size();++i) linkTick();
 assert(count==0 && Serial2.pos==Serial2.input.size());
}
'''
class UartServiceTests(unittest.TestCase):
 def test_continuous_rx_blocked_tx_and_handshake(self):
  sketch=(MEGA/'MegaControlador.ino').read_text()
  body=sketch[sketch.index('MessageProtocol::EventData outbound'):sketch.index('void serialTick()')]
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'test.cpp'; binary=Path(tmp)/'test'; source.write_text(PREFIX+body+CASES)
   cmd=[os.environ.get('CXX','c++'),'-std=c++11','-I',str(MEGA)]
   sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
   if sys.platform=='darwin' and sdk.exists(): cmd+=['-isysroot',str(sdk)]
   subprocess.run(cmd+[str(source),'-o',str(binary)],check=True)
   subprocess.run([str(binary)],check=True,timeout=3)
