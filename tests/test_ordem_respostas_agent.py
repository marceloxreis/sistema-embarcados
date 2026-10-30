"""Prova fresca deve passar por resets adiados sem reentrar no DY50."""
import os, subprocess, sys, tempfile, unittest
from pathlib import Path
from test_mega_link import MEGA, PREFIX

CASES = r'''
struct Sink { std::vector<uint8_t> data; void write(uint8_t b){data.push_back(b);} };
void inject(const uint8_t *b,size_t n) { Sink s; assert(SerialFrame::send(s,b,n)); Serial2.input.insert(Serial2.input.end(),s.data.begin(),s.data.end()); }
int main(){ using namespace MessageProtocol;
 queueEvent("access_granted",1,"password",""); linkTick(); Serial2.output.clear();
 uint8_t reset[21]={kVersion,Reset}; put32(reset+2,5); reset[6]=1; memcpy(reset+7,"123456",6); reset[13]=42;
 for(int i=0;i<6;i++) inject(reset,21);
 uint8_t challenge[26]={kVersion,PhotoChallenge}; put32(challenge+2,1); put32(challenge+6,3); challenge[10]=0x7e; inject(challenge,26);
 for(int i=0;i<20;i++) linkTick(true);
 assert(resets==0 && replyCount==1);
 SerialFrame::Parser p; int proofs=0; for(auto b:Serial2.output) if(p.feed(b,now)) { assert(p.data()[1]==PhotoProof); assert(p.data()[10]==0x7e); ++proofs; }
 assert(proofs==1);
 for(int i=0;i<20;i++) linkTick(false);
 assert(resets==1 && replyCount==0);
}
'''
class OrdemTests(unittest.TestCase):
 def test_photo_bypasses_duplicate_deferred_resets(self):
  sketch=(MEGA/'MegaControlador.ino').read_text(); body=sketch[sketch.index('MessageProtocol::EventData outbound'):sketch.index('void serialTick()')]
  with tempfile.TemporaryDirectory() as d:
   source=Path(d)/'test.cpp'; binary=Path(d)/'test'; source.write_text(PREFIX+body+CASES)
   cmd=[os.environ.get('CXX','c++'),'-std=c++11','-I',str(MEGA)]
   sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
   if sys.platform=='darwin' and sdk.exists(): cmd+=['-isysroot',str(sdk)]
   subprocess.run(cmd+[str(source),'-o',str(binary)],check=True)
   subprocess.run([str(binary)],check=True,timeout=3)
