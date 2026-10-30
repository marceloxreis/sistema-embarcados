"""Serializa com o código real da CAM e entrega os dados ao servidor HTTP local.

O transporte da CAM é dublado e o teste repassa seus bytes ao servidor real;
não emula Wi-Fi ou o driver físico da câmera.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from library_deps import require_library
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CAM = ROOT / 'firmware/Esp32CamRede'
spec = importlib.util.spec_from_file_location('integration_server', ROOT / 'servidor/server.py')
server = importlib.util.module_from_spec(spec); spec.loader.exec_module(server)
PREFIX = r'''
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <string>
#include <vector>
#include <map>
#include <cassert>
#include <ArduinoJson.h>
#include "MessageProtocol.h"
using String=std::string;
using namespace MessageProtocol;
const char DEVICE_ID[]="porta01", DEVICE_KEY[]="device-test", SERVER_URL[]="http://mock";
struct Item { EventData event; uint8_t *photo; size_t photoSize; };
const char * const eventNames[]={"", "device_boot", "storage_error", "user_snapshot", "user_enrolled", "user_disabled", "user_enabled", "password_reset", "admin_login", "access_granted", "access_denied", "door_opened", "door_closed", "entry_expired", "door_timeout", "forced_open", "enroll_failed"};
const char * const methodNames[]={"", "password", "fingerprint", "admin", "keypad", "system", "sensor", "usb", "web"};
const char * const reasonNames[]={"", "inactive_or_unknown", "invalid_pin", "unknown_finger", "sensor_error", "simulation", "actuator_enabled", "open_at_boot", "Erro de hash", "Erro ao gravar DY", "Erro na memoria", "Erro de leitura", "Digital ilegivel", "Digital ja usada", "Slot DY orfao", "Falha na pesquisa", "Digitais diferem"};
String capturedJson, photoId; std::vector<uint8_t> photoBytes; bool eventOffline=true, photoOffline=true;
int request(const char *path,const String &body,String &response) {
 assert(String(path)=="/api/device/events"); capturedJson=body;
 if (eventOffline) return -1;
 JsonDocument doc; assert(!deserializeJson(doc,body)); JsonDocument ack;
 ack["accepted"]=doc["event_id"].as<String>(); serializeJson(ack,response); return 200;
}
struct WiFiClient {};
struct HTTPClient {
 std::map<String,String> headers;
 void setConnectTimeout(int) {} void setTimeout(int) {}
 bool begin(WiFiClient &,const String &url) { assert(url=="http://mock/api/device/photo"); return true; }
 void addHeader(const char *name,const String &value) { headers[name]=value; }
 int POST(uint8_t *data,size_t n) {
  assert(headers["X-Device-Key"]==DEVICE_KEY && headers["Content-Type"]=="image/jpeg");
  photoId=headers["X-Event-Id"]; photoBytes.assign(data,data+n); return photoOffline ? -1 : 200;
 }
 String getString() { JsonDocument doc; doc["accepted"]=photoId; String s; serializeJson(doc,s); return s; }
 void end() {}
};
'''
CASES = r'''
int main() {
 uint8_t jpeg[]={JPEG_BYTES};
 Item item={}; item.event={9,3,12345,0,AccessGranted,1,Password,1,0,12350}; item.photo=jpeg; item.photoSize=sizeof jpeg;
 assert(!sendEvent(item)); eventOffline=false; assert(sendEvent(item));
 assert(!sendPhoto(item)); photoOffline=false; assert(sendPhoto(item));
 String granted=capturedJson; item.event.kind=EnrollFailed; item.event.reason=14; item.photo=nullptr;
 assert(sendEvent(item)); JsonDocument failure; assert(!deserializeJson(failure,capturedJson));
 assert(failure["reason"].as<String>()=="Slot DY orfao"); capturedJson=granted;
 printf("%s\n%s\n",capturedJson.c_str(),photoId.c_str());
 for (uint8_t b:photoBytes) printf("%02x",b); puts("");
}
'''
class CameraServerIntegrationTests(unittest.TestCase):
    def test_actual_cam_payload_reaches_real_server(self):
        json_lib = require_library(self, 'ArduinoJson', '7.4.3', ('src/ArduinoJson.h',)) / 'src'
        sketch=(CAM/'Esp32CamRede.ino').read_text()
        event_id=sketch[sketch.index('void eventId('):sketch.index('bool startCamera()')]
        sending=sketch[sketch.index('bool sendEvent('):sketch.index('void networkTask(')]
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'sim.cpp'; binary=Path(directory)/'sim'; fixture=(ROOT / 'tests/fixtures/synthetic.jpg').read_bytes()
            cases=CASES.replace('JPEG_BYTES', ','.join(str(b) for b in fixture))
            source.write_text(PREFIX+event_id+sending+cases)
            cmd=[os.environ.get('CXX','c++'),'-std=c++11','-I',str(CAM),'-I',str(json_lib)]
            sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform=='darwin' and sdk.exists(): cmd+=['-isysroot',str(sdk)]
            result=subprocess.run(cmd+[str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            event_line,photo_id,photo_hex=result.stdout.strip().splitlines()
            payload=json.loads(event_line); jpeg=bytes.fromhex(photo_hex)
            self.assertEqual(payload['event_id'],photo_id)
            self.assertEqual(jpeg,fixture)
            app=server.App(Path(directory)/'server.sqlite3','1234567890','device-test')
            httpd=server.make_server('127.0.0.1',0,app)
            thread=threading.Thread(target=httpd.serve_forever,daemon=True); thread.start()
            base=f'http://127.0.0.1:{httpd.server_port}'
            try:
                req=Request(base+'/api/device/events',event_line.encode(),{'X-Device-Key':'device-test','Content-Type':'application/json'})
                with urlopen(req,timeout=3) as response: self.assertEqual(json.load(response)['accepted'],photo_id)
                for _ in range(2):
                    req=Request(base+'/api/device/photo',jpeg,{'X-Device-Key':'device-test','X-Event-Id':photo_id,'Content-Type':'image/jpeg'})
                    with urlopen(req,timeout=3) as response: self.assertEqual(json.load(response)['accepted'],photo_id)
                req=Request(base+'/api/admin/photo?event_id='+photo_id,headers={'X-Admin-Pin':'1234567890'})
                with urlopen(req,timeout=3) as response: self.assertEqual(response.read(),jpeg)
            finally:
                httpd.shutdown(); httpd.server_close(); thread.join()
