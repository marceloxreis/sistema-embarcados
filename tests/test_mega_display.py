"""Exercita o espelho serial do LCD e a máscara de senha em displayTick do sketch Mega."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_mega_logic import PREFIX

MEGA = Path(__file__).resolve().parents[1] / 'firmware/MegaControlador'
MOCKS = r'''
#define F(s) s
#define LCD_SERIAL_MIRROR 1
#define SHOW_TYPED_DIGITS 0
struct SerialLcdMock { std::string log; void print(const char *s) { log += s; } void print(const std::string &s) { log += s; } void println(const std::string &s) { log += s + "\n"; } } Serial;
struct FakeLCD {
 int cursors=0,writes=0; std::string written;
 void begin(int,int) {}
 void print(const char *) {}
 void setCursor(int,int) { ++cursors; }
 void write(uint8_t c) { ++writes; written += char(c); }
} lcd;
'''
MOCKS_TYPED_DIGITS = MOCKS.replace('#define SHOW_TYPED_DIGITS 0', '#define SHOW_TYPED_DIGITS 1')
class MegaDisplayTests(unittest.TestCase):
    def _compile_and_run(self, source_text):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'test.cpp'; binary=Path(directory)/'test'
            source.write_text(source_text)
            cmd=[os.environ.get('CXX','c++'),'-std=c++11','-I',str(MEGA)]
            sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform=='darwin' and sdk.exists(): cmd+=['-isysroot',str(sdk)]
            result=subprocess.run(cmd+[str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_bancada_mostra_digitos_so_no_espelho(self):
        sketch=(MEGA/'MegaControlador.ino').read_text()
        logic=sketch[sketch.index('enum class Ui'):sketch.index('void handleKey(')]
        display=sketch[sketch.index('void displayTick()'):sketch.index('// Lista circular')]
        prefix=PREFIX.replace('String(const std::string &s):std::string(s) {}',
                              'String(const std::string &s):std::string(s) {} String substring(size_t a,size_t b) const { return String(substr(a,b-a)); }')
        cases=r'''
int main() {
 door.begin(true,now); resetUi(); noticeDuration=0;
 // (a) digitacao em Access: espelho mostra os digitos, LCD recebe so '*'
 entry="12"; ui=Ui::Access; lcd.written.clear(); now+=500; displayTick();
 assert(Serial.log.find("LCD| #Confirma *Limpa | ID: 12\n")!=std::string::npos);
 assert(lcd.written.find("12")!=std::string::npos && lcd.written.find("**")==std::string::npos);
 // (b) digitacao em FirstPin: mesmo comportamento
 ui=Ui::FirstPin; entry="123456"; lcd.written.clear(); now+=500; displayTick();
 assert(Serial.log.find("LCD| Crie senha (6) | 123456\n")!=std::string::npos);
 assert(lcd.written.find("123456")==std::string::npos && lcd.written.find("******")!=std::string::npos);
 // (c) tela de senha do ID: espelho mantém o prefixo "ID 001: " e troca so os '*'
 ui=Ui::AccessPin; pendingId=1; entry="12"; lcd.written.clear(); now+=500; displayTick();
 assert(Serial.log.find("LCD| #Confirma *Limpa | ID 001: 12\n")!=std::string::npos);
 assert(lcd.written.find("ID 001: **")!=std::string::npos);
 return 0;
}
'''
        self._compile_and_run(prefix+logic+MOCKS_TYPED_DIGITS+display+cases)


    def test_espelho_serial_sem_vazar_senha(self):
        sketch=(MEGA/'MegaControlador.ino').read_text()
        logic=sketch[sketch.index('enum class Ui'):sketch.index('void handleKey(')]
        display=sketch[sketch.index('void displayTick()'):sketch.index('// Lista circular')]
        prefix=PREFIX.replace('String(const std::string &s):std::string(s) {}',
                              'String(const std::string &s):std::string(s) {} String substring(size_t a,size_t b) const { return String(substr(a,b-a)); }')
        cases=r'''
int main() {
 door.begin(true,now); resetUi(); noticeDuration=0;
 // (a) primeira chamada: o texto sai na serial e o LCD é desenhado (16+16 colunas)
 displayTick();
 assert(Serial.log=="LCD| Controle acesso | ID ou digital\n" && lcd.writes==32);
 // (b) sem mudanca no texto, nada e reimpresso
 now+=500; displayTick();
 assert(Serial.log=="LCD| Controle acesso | ID ou digital\n" && lcd.writes==32);
 // (c) senha em digitacao aparece so como '*'
 entry="12"; now+=500; displayTick();
 assert(Serial.log.find("LCD| #Confirma *Limpa | ID: 12\n")!=std::string::npos);
 // ID de 1 a 3 digitos aparece no espelho (nao e segredo); a senha nunca aparece.
 size_t antes=Serial.log.size();
 ui=Ui::FirstPin; entry="123456"; now+=500; displayTick();
 assert(Serial.log.find("LCD| Crie senha (6) | ******\n")!=std::string::npos);
 assert(Serial.log.substr(antes).find("1")==std::string::npos);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'test.cpp'; binary=Path(directory)/'test'
            source.write_text(prefix+logic+MOCKS+display+cases)
            cmd=[os.environ.get('CXX','c++'),'-std=c++11','-I',str(MEGA)]
            sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform=='darwin' and sdk.exists(): cmd+=['-isysroot',str(sdk)]
            result=subprocess.run(cmd+[str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
