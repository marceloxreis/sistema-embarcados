"""Exercita a interrupção de atualizações do LCD se o I²C expirar."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_mega_logic import PREFIX

MEGA = Path(__file__).resolve().parents[1] / 'firmware/MegaControlador'
MOCKS = r'''
bool lcdReady=true;
struct FakeWire {
 bool failed=false;
 void clearWireTimeoutFlag() { failed=false; }
 bool getWireTimeoutFlag() { return failed; }
} Wire;
struct FakeLCD {
 int cursors=0,writes=0; bool failOnWrite=true;
 void setCursor(int,int) { ++cursors; }
 void write(uint8_t) { ++writes; if(failOnWrite) Wire.failed=true; }
} lcd;
'''
CASES = r'''
int main() {
 door.begin(true,now); resetUi(); noticeDuration=0;
 displayTick(); assert(!lcdReady && lcd.writes==1);
 int before=lcd.writes; now+=500; displayTick(); assert(lcd.writes==before);
}
'''
class MegaDisplayTests(unittest.TestCase):
    def test_bus_timeout_stops_lcd_writes(self):
        sketch=(MEGA/'MegaControlador.ino').read_text()
        logic=sketch[sketch.index('enum class Ui'):sketch.index('void handleKey(')]
        display=sketch[sketch.index('void displayTick()'):sketch.index('// Lista circular')]
        prefix=PREFIX.replace('String(const std::string &s):std::string(s) {}',
                              'String(const std::string &s):std::string(s) {} String substring(size_t a,size_t b) const { return String(substr(a,b-a)); }')
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'test.cpp'; binary=Path(directory)/'test'
            source.write_text(prefix+logic+MOCKS+display+CASES)
            cmd=[os.environ.get('CXX','c++'),'-std=c++11','-I',str(MEGA)]
            sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform=='darwin' and sdk.exists(): cmd+=['-isysroot',str(sdk)]
            result=subprocess.run(cmd+[str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
