"""Executa a biblioteca Adafruit real com o filtro do sketch e UART simulada."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from library_deps import require_library

ROOT=Path(__file__).resolve().parents[1]
MEGA=ROOT/'firmware/MegaControlador'
ARDUINO=r'''
#pragma once
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <vector>
using boolean=bool;
class Print { public: virtual size_t write(uint8_t)=0; };
class Stream:public Print { public: virtual int available()=0; virtual int read()=0; virtual int peek()=0; virtual void flush()=0; };
class HardwareSerial:public Stream {
 public:
 std::vector<uint8_t> input,output,next; size_t pos=0, count=0, total=0; uint16_t length=0;
 void begin(uint32_t) {}
 int available() override { return int(input.size()-pos); }
 int read() override { return available() ? input[pos++] : -1; }
 int peek() override { return available() ? input[pos] : -1; }
 void flush() override {}
 size_t write(uint8_t b) override {
  output.push_back(b);
  if(count==7) length=uint16_t(b)<<8;
  if(count==8) { length|=b; total=9+length; }
  ++count;
  if(total && count==total) { input.insert(input.end(),next.begin(),next.end()); next.clear(); count=0; total=0; }
  return 1;
 }
};
extern HardwareSerial Serial1;
void delay(unsigned long);
'''
PREFIX=r'''
#include <cassert>
#include <cstdio>
#include <vector>
#include "Arduino.h"
#include "Adafruit_Fingerprint.h"
#include "Dy50ResponseFilter.h"
HardwareSerial Serial1;
void delay(unsigned long) {}
bool doorServiceReady=true; int doorChecks=0;
void doorTick() { ++doorChecks; } void outputsTick() {}
void linkTick(bool) {}
'''
CASES=r'''
std::vector<uint8_t> ack(std::vector<uint8_t> data) {
 uint16_t n=data.size()+2, sum=7+(n>>8)+(n&255);
 std::vector<uint8_t> p={0xef,1,255,255,255,255,7,uint8_t(n>>8),uint8_t(n)};
 for(auto b:data) { p.push_back(b); sum+=b; } p.push_back(sum>>8); p.push_back(sum); return p;
}
int main() {
 ServicedFingerStream stream; Adafruit_Fingerprint sensor(static_cast<Stream *>(&stream));
 Serial1.next=ack({0}); assert(sensor.getImage()==FINGERPRINT_OK);
 Serial1.next=ack({2}); assert(sensor.getImage()==FINGERPRINT_NOFINGER);
 Serial1.next=ack({0,0,1,0,80}); assert(sensor.fingerFastSearch()==FINGERPRINT_OK);
 assert(sensor.fingerID==1 && sensor.confidence==80);
 Serial1.next=ack({0,0,1,0,80}); Serial1.next[10]^=1;
 int before=doorChecks; assert(sensor.fingerFastSearch()==FINGERPRINT_PACKETRECIEVEERR);
 assert(doorChecks-before>=1000);
 Serial1.next=ack({0}); assert(sensor.fingerFastSearch()==FINGERPRINT_PACKETRECIEVEERR);
 std::vector<uint8_t> parameters(17,0); parameters[5]=1; parameters[6]=0;
 Serial1.next=ack(parameters); assert(sensor.getParameters()==FINGERPRINT_OK && sensor.capacity==256);
 puts("Adafruit library and DY50 filter integration passed");
}
'''
class Dy50LibraryIntegrationTests(unittest.TestCase):
    def test_real_library_with_verified_stream(self):
        lib = require_library(self, 'Adafruit_Fingerprint_Sensor_Library', '2.1.4', ('Adafruit_Fingerprint.cpp', 'Adafruit_Fingerprint.h'))
        sketch=(MEGA/'MegaControlador.ino').read_text()
        adapter=sketch[sketch.index('class ServicedFingerStream'):sketch.index('ServicedFingerStream fingerStream;')]
        with tempfile.TemporaryDirectory() as directory:
            temp=Path(directory); (temp/'Arduino.h').write_text(ARDUINO)
            source=temp/'test.cpp'; binary=temp/'test'; source.write_text(PREFIX+adapter+CASES)
            cmd=[os.environ.get('CXX','c++'),'-std=c++11','-I',str(temp),'-I',str(MEGA),'-I',str(lib)]
            sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform=='darwin' and sdk.exists(): cmd+=['-isysroot',str(sdk)]
            result=subprocess.run(cmd+[str(source),str(lib/'Adafruit_Fingerprint.cpp'),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
