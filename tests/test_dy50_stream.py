"""Testa o adaptador real da UART biométrica com pacotes e porta simulados."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

MEGA=Path(__file__).resolve().parents[1]/'firmware/MegaControlador'
PREFIX=r'''
#include <cstdint>
#include <cstdio>
#include <cassert>
#include <vector>
#include "Dy50ResponseFilter.h"
class Print { public: virtual size_t write(uint8_t)=0; };
class Stream:public Print { public: virtual int available()=0; virtual int read()=0; virtual int peek()=0; virtual void flush()=0; };
struct SerialMock {
 std::vector<uint8_t> input,output; size_t pos=0;
 int available() { return int(input.size()-pos); }
 int read() { return input[pos++]; }
 int peek() { return available() ? input[pos] : -1; }
 void flush() {}
 size_t write(uint8_t b) { output.push_back(b); return 1; }
} Serial1;
bool doorServiceReady=true; int doorChecks=0,outputChecks=0;
void doorTick() { ++doorChecks; } void outputsTick() { ++outputChecks; }
void linkTick(bool) {}
'''
CASES=r'''
std::vector<uint8_t> response(std::vector<uint8_t> data) {
 uint16_t len=data.size()+2, sum=7+(len>>8)+(len&255);
 std::vector<uint8_t> p={0xef,1,255,255,255,255,7,uint8_t(len>>8),uint8_t(len)};
 for(auto b:data) { p.push_back(b); sum+=b; } p.push_back(sum>>8); p.push_back(sum); return p;
}
void command(ServicedFingerStream &s,uint8_t cmd) {
 uint8_t frame[]={0xef,1,255,255,255,255,1,0,3,cmd,0,uint8_t(4+cmd)};
 for(auto b:frame) assert(s.write(b)==1);
}
int main() {
 ServicedFingerStream stream; command(stream,0x1b);
 auto good=response({0,0,1,0,80}); auto bad=good; bad[10]^=1;
 Serial1.input.insert(Serial1.input.end(),bad.begin(),bad.end());
 assert(stream.available()==0 && doorChecks && outputChecks);
 Serial1.input.insert(Serial1.input.end(),good.begin(),good.end());
 assert(stream.available()==int(good.size())); for(auto b:good) assert(stream.read()==b);
 // Um ACK tardio de busca não é aceito como ACK simples de outra operação.
 command(stream,1); Serial1.input.insert(Serial1.input.end(),good.begin(),good.end());
 assert(stream.available()==0);
 auto simple=response({0}); Serial1.input.insert(Serial1.input.end(),simple.begin(),simple.end());
 assert(stream.available()==int(simple.size()));
}
'''
class Dy50StreamTests(unittest.TestCase):
    def test_uart_filter_and_door_service(self):
        sketch=(MEGA/'MegaControlador.ino').read_text()
        adapter=sketch[sketch.index('class ServicedFingerStream'):sketch.index('ServicedFingerStream fingerStream;')]
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'test.cpp'; binary=Path(directory)/'test'; source.write_text(PREFIX+adapter+CASES)
            cmd=[os.environ.get('CXX','c++'),'-std=c++11','-I',str(MEGA)]
            sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform=='darwin' and sdk.exists(): cmd+=['-isysroot',str(sdk)]
            result=subprocess.run(cmd+[str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
