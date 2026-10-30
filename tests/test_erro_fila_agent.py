"""Testa diagnósticos dos envios reais da CAM com transporte simulado."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from library_deps import require_library
from test_camera_server_integration import CAM, PREFIX
import test_camera_network as network_fixture


class QueueFailureTests(unittest.TestCase):
    def test_http_network_ack_and_retry(self):
        lib = require_library(self, 'ArduinoJson', '7.4.3', ('src/ArduinoJson.h',)) / 'src'
        sketch = (CAM / 'Esp32CamRede.ino').read_text()
        event_id = sketch[sketch.index('void eventId('):sketch.index('bool startCamera()')]
        sending = sketch[sketch.index('bool sendEvent('):sketch.index('void networkTask(')]
        prefix = PREFIX.replace('bool eventOffline=true, photoOffline=true;',
                                'bool eventOffline=true, photoOffline=true; int eventCode=-1, photoCode=-1;')
        prefix = prefix.replace('if (eventOffline) return -1;', 'if (eventCode != 200) return eventCode;')
        prefix = prefix.replace('return photoOffline ? -1 : 200;', 'return photoCode;')
        cases = r'''
int main() {
 uint8_t jpeg[]={1,2,3}; Item item={};
 item.event={9,3,12345,0,AccessGranted,1,Password,1,0,12350}; item.photo=jpeg; item.photoSize=3;
 int status=42;
 eventCode=400; assert(!sendEvent(item,&status) && status==400);
 eventCode=409; assert(!sendEvent(item,&status) && status==409);
 eventCode=-2; assert(!sendEvent(item,&status) && status==-2);
 eventCode=200; assert(sendEvent(item,&status) && status==0);
 String id=photoId; photoCode=409; assert(!sendPhoto(item,&status) && status==409);
 id=photoId; photoCode=200; assert(sendPhoto(item,&status) && status==0 && photoId==id);
 item.photo=nullptr; assert(sendPhoto(item,&status) && status==0);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'test.cpp'
            binary = Path(directory) / 'test'
            source.write_text(prefix + event_id + sending + cases)
            command = [os.environ.get('CXX', 'c++'), '-std=c++11', '-I', str(CAM), '-I', str(lib)]
            sdk = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform == 'darwin' and sdk.exists():
                command += ['-isysroot', str(sdk)]
            result = subprocess.run(command + [str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_queue_serial_reports_and_recovers(self):
        lib = require_library(self, 'ArduinoJson', '7.4.3', ('src/ArduinoJson.h',)) / 'src'
        sketch = (CAM / 'Esp32CamRede.ino').read_text()
        event_id = sketch[sketch.index('void eventId('):sketch.index('bool startCamera()')]
        network = sketch[sketch.index('bool sendEvent('):sketch.index('void setup()')]
        prefix = network_fixture.PREFIX.replace('ticks+=n; ++cycles;', 'ticks+=10000; ++cycles;')
        prefix = prefix.replace('return cycles<2 ? 0 : WL_CONNECTED;', 'return WL_CONNECTED;')
        prefix = prefix.replace('++eventCalls; if(eventCalls<3) return -1;',
                                '++eventCalls; if(eventCalls==1) return 400; if(eventCalls==2) return 409;')
        prefix = prefix.replace('eventCalls==3 ? String("outro-evento") : doc["event_id"].as<String>()',
                                'doc["event_id"].as<String>()')
        serial = r'''
#include <cstdarg>
#define ARDUINO 10800
std::string logs;
struct SerialMock {
 void println(const char *s) { logs+=s; logs+="\n"; }
 void printf(const char *fmt, ...) { char buf[512]; va_list args; va_start(args,fmt); vsnprintf(buf,sizeof buf,fmt,args); va_end(args); logs+=buf; }
} Serial;
constexpr uint8_t kPermanentRejectLimit = 5;
uint32_t droppedEvents = 0, rejectedItems = 0, photoRejected = 0;
void bump(uint32_t &v) { if (v != UINT32_MAX) ++v; }
char camBootId[9] = "";
'''
        cases = r'''
int main() {
 Item item={}; item.event={9,3,12345,0,AccessGranted,1,Password,1,0,12350};
 eventQueue.entries.push_back(item);
 try { networkTask(nullptr); } catch(int) {}
 assert(eventQueue.entries.empty() && eventCalls==3);
 assert(logs.find("HTTP rejeitado (possivelmente permanente) (400)")!=String::npos);
 assert(logs.find("HTTP rejeitado (possivelmente permanente) (409)")!=String::npos);
 assert(logs.find("sem foto disponivel")!=String::npos);
 assert(logs.find("entregue apos falha")!=String::npos);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'test.cpp'; binary = Path(directory) / 'test'
            source.write_text(prefix + serial + event_id + network + cases)
            command = [os.environ.get('CXX', 'c++'), '-std=c++11', '-I', str(CAM), '-I', str(lib)]
            sdk = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform == 'darwin' and sdk.exists():
                command += ['-isysroot', str(sdk)]
            result = subprocess.run(command + [str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
