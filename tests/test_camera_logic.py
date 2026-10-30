"""Exercita a recepção real do sketch CAM com câmera e fila simuladas."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CAM = Path(__file__).resolve().parents[1] / 'firmware/Esp32CamRede'
PREFIX = r'''
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <vector>
#include "SerialFrame.h"
#include "MessageProtocol.h"
using namespace MessageProtocol;
struct Item { EventData event; uint8_t *photo; size_t photoSize; };
struct Queue { std::vector<Item> items; size_t capacity=8; } queue;
Queue *events=&queue;
int uxQueueSpacesAvailable(Queue *q) { return int(q->capacity-q->items.size()); }
constexpr int pdTRUE=1;
int xQueueSend(Queue *q, Item *item, int) { if(!uxQueueSpacesAvailable(q))return 0; q->items.push_back(*item); return 1; }
struct SerialSink { std::vector<uint8_t> bytes; void write(uint8_t b) { bytes.push_back(b); } } Serial2;
bool cameraReady=true, networkReady=true; uint32_t lastBoot=0,lastEvent=0;
uint32_t droppedEvents=0, rejectedItems=0; void bump(uint32_t &v) { if (v != UINT32_MAX) ++v; }
constexpr int PIXFORMAT_JPEG=1;
struct camera_fb_t { int format; size_t len; uint8_t *buf; };
uint32_t randomState=1; uint32_t esp_random() { return randomState++; }
uint32_t ticks=0; uint32_t millis() { return ticks; }
uint8_t jpeg[] = {0xff,0xd8,0xff,0xd9}; int captures=0; uint32_t captureDelay=0;
camera_fb_t fb={PIXFORMAT_JPEG,sizeof jpeg,jpeg};
camera_fb_t *esp_camera_fb_get() { ++captures; ticks += captureDelay; return &fb; }
void esp_camera_fb_return(camera_fb_t *) {}
bool psramFound() { return false; }
void *ps_malloc(size_t size) { return malloc(size); }
'''
CASES = r'''
int main() {
 EventData e={1,1,100,0,AccessGranted,1,Password,1,0,200}; uint8_t body[kEventLength];
 networkReady=false; assert(encodeEvent(e,body,sizeof body)); receiveEvent(body,sizeof body,ticks);
 assert(queue.items.empty() && Serial2.bytes.empty()); networkReady=true;
 receiveEvent(body,sizeof body,ticks); assert(pendingPhoto.active && queue.items.empty() && captures==2);
 receiveEvent(body,sizeof body,ticks); assert(captures==2);
 uint8_t proof[26]; memcpy(proof,pendingPhoto.challenge,26); proof[1]=PhotoProof;
 proof[10]^=1; receivePhotoProof(proof,26); assert(pendingPhoto.active);
 proof[10]^=1; receivePhotoProof(proof,26); assert(!pendingPhoto.active && queue.items.size()==1 && queue.items[0].photo);
 receiveEvent(body,sizeof body,ticks); assert(queue.items.size()==1 && captures==2);
 e.messageId=2; assert(encodeEvent(e,body,sizeof body)); receiveEvent(body,sizeof body,ticks);
 ticks+=5000; photoTick(); assert(queue.items.size()==2 && !queue.items[1].photo);
 receivePhotoProof(proof,26); assert(queue.items.size()==2);
 queue.capacity=queue.items.size(); e.messageId=3; assert(encodeEvent(e,body,sizeof body));
 size_t before=Serial2.bytes.size(); receiveEvent(body,sizeof body,ticks); assert(Serial2.bytes.size()==before);
 for (auto &item:queue.items) free(item.photo);
}
'''
class CameraLogicTests(unittest.TestCase):
    def test_capture_duplicate_and_full_queue(self):
        sketch = (CAM / 'Esp32CamRede.ino').read_text()
        body = sketch[sketch.index('struct PendingPhoto'):sketch.index('int request(')]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'test.cpp'; binary = Path(directory) / 'test'
            source.write_text(PREFIX + body + CASES)
            command = [os.environ.get('CXX', 'c++'), '-std=c++11', '-I', str(CAM)]
            sdk = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform == 'darwin' and sdk.exists(): command += ['-isysroot', str(sdk)]
            compiled = subprocess.run(command + [str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
