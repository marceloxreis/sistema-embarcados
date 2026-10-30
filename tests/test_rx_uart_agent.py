"""Regressão: RX continua mesmo com TX sem espaço."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_mega_link import MEGA, PREFIX

PREFIX = PREFIX.replace('int availableForWrite() { return 1; }', 'bool blocked=false; int availableForWrite() { return blocked ? 0 : 1; }')
CASES = r'''
struct Sink { std::vector<uint8_t> data; void write(uint8_t b) { data.push_back(b); } };
void inject(const uint8_t *b,size_t n) { Sink s; assert(SerialFrame::send(s,b,n)); Serial2.input.insert(Serial2.input.end(),s.data.begin(),s.data.end()); }
int main() {
 using namespace MessageProtocol;
 queueEvent("access_granted",1,"password",""); Serial2.blocked=true; linkTick(); assert(linkTx.pending());
 uint8_t challenge[26]={kVersion,PhotoChallenge}; put32(challenge+2,1); put32(challenge+6,3); challenge[10]=0x7e; inject(challenge,26);
 uint8_t reset[21]={kVersion,Reset}; put32(reset+2,5); reset[6]=1; memcpy(reset+7,"123456",6); reset[13]=42;
 for(int i=0;i<4;i++) { put32(reset+2,5+i); inject(reset,21); }
 uint8_t clock[10]={kVersion,Clock}; put32(clock+6,1700000000UL); inject(clock,10);
 uint8_t ack[10]={kVersion,Ack}; put32(ack+2,1); put32(ack+6,3); inject(ack,10);
 for(int i=0;i<10;i++) linkTick();
 assert(syncEpoch==1700000000UL && count==0 && Serial2.pos==Serial2.input.size());
 assert(resets==0 && replyCount==4 && droppedReplies==1);
 Serial2.blocked=false; for(int i=0;i<15;i++) linkTick();
 SerialFrame::Parser parser; std::vector<uint8_t> types;
 for(auto b:Serial2.output) if(parser.feed(b,now)) types.push_back(parser.data()[1]);
 assert(types.size()==5 && types[0]==Event && types[1]==PhotoProof);
 for(unsigned i=2;i<types.size();i++) assert(types[i]==ResetResult);
 assert(!linkTx.pending() && replyCount==0 && resets==3);
 // Uma prova na fila expira enquanto o TX anterior permanece bloqueado.
 Serial2.output.clear(); Serial2.blocked=true; queueEvent("access_granted",1,"password",""); linkTick();
 put32(challenge+2,2); inject(challenge,26); linkTick(); assert(replyCount==1);
 now+=5001; Serial2.blocked=false; for(int i=0;i<10;i++) linkTick();
 types.clear(); for(auto b:Serial2.output) if(parser.feed(b,now)) types.push_back(parser.data()[1]);
 for(auto type:types) assert(type!=PhotoProof);
 assert(droppedReplies==2 && replyCount==0);
}

'''
class RxTests(unittest.TestCase):
 def test_blocked_tx(self):
  sketch=(MEGA/'MegaControlador.ino').read_text(); body=sketch[sketch.index('MessageProtocol::EventData outbound'):sketch.index('void serialTick()')]
  with tempfile.TemporaryDirectory() as d:
   source=Path(d)/'test.cpp'; binary=Path(d)/'test'; source.write_text(PREFIX+body+CASES)
   cmd=[os.environ.get('CXX','c++'),'-std=c++11','-I',str(MEGA)]
   sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
   if sys.platform=='darwin' and sdk.exists(): cmd+=['-isysroot',str(sdk)]
   subprocess.run(cmd+[str(source),'-o',str(binary)],check=True)
   subprocess.run([str(binary)],check=True,timeout=3)
