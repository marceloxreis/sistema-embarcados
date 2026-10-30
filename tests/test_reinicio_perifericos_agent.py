"""Exercita a religação do LCD (timeout I2C) e do DY50 (falha de UART) no sketch Mega."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_mega_logic import PREFIX

MEGA = Path(__file__).resolve().parents[1] / 'firmware/MegaControlador'
PREFIX = PREFIX.replace('String(const std::string &s):std::string(s) {}',
                        'String(const std::string &s):std::string(s) {} String substring(size_t a,size_t b) const { return String(substr(a,b-a)); }')
PREFIX = PREFIX.replace('uint8_t deleteModel(uint16_t id) { deleted=id; return 0; }',
                        'uint8_t deleteModel(uint16_t id) { deleted=id; return 0; }'
                        ' bool verifyOk=false; int verifyCalls=0; uint16_t capacity=200;'
                        ' bool verifyPassword() { ++verifyCalls; return verifyOk; }'
                        ' uint8_t getParameters() { return FINGERPRINT_OK; }')
MOCKS = r'''
bool lcdReady=true;
constexpr uint8_t LCD_ADDRESS = 0x27;
// Sonda do LCD: beginTransmission/endTransmission. Barramento com timeout ou LCD ausente (NACK).
struct FakeWire {
 bool failed=false, busBroken=false, lcdPresent=true; int probes=0;
 void clearWireTimeoutFlag() { failed=false; }
 bool getWireTimeoutFlag() { return failed; }
 void beginTransmission(uint8_t) { ++probes; }
 uint8_t endTransmission() { if (busBroken) { failed=true; return 5; } return lcdPresent ? 0 : 2; }
} Wire;
struct FakeLCD {
 int inits=0, backlights=0, writes=0, cursors=0; bool failOnWrite=false;
 void init() { ++inits; if (Wire.busBroken) Wire.failed=true; }
 void backlight() { ++backlights; }
 void setCursor(int,int) { ++cursors; }
 void write(uint8_t) { ++writes; if (failOnWrite) Wire.failed=true; }
} lcd;
'''
# Trecho com as funções de religação e displayTick (todas ficam entre doorTick e a lista de UART).
RECOVERY_SLICE = ('// Religa o DY50', '// Lista circular')


class ReinicioPerifericosTests(unittest.TestCase):
    def _compile_and_run(self, body, cases):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'test.cpp'
            binary = Path(directory) / 'test'
            source.write_text(PREFIX + MOCKS + body + cases)
            cmd = [os.environ.get('CXX', 'c++'), '-std=c++11', '-I', str(MEGA)]
            sdk = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform == 'darwin' and sdk.exists(): cmd += ['-isysroot', str(sdk)]
            result = subprocess.run(cmd + [str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def _sketch_body(self):
        sketch = (MEGA / 'MegaControlador.ino').read_text()
        logic = sketch[sketch.index('enum class Ui'):sketch.index('void handleKey(')]
        recovery = sketch[sketch.index(RECOVERY_SLICE[0]):sketch.index(RECOVERY_SLICE[1])]
        return logic + recovery

    def test_lcd_volta_apos_timeout_quando_barramento_recupera(self):
        cases = r'''
int main() {
 door.begin(true,now); resetUi(); noticeDuration=0;
 lcd.failOnWrite=true; displayTick(); assert(!lcdReady && lcd.writes==1);
 // Dentro de 30 s nenhuma tentativa de religar
 now+=10000; lcdRecoveryTick(); assert(!lcdReady && lcd.inits==0 && Wire.probes==0);
 // 30 s depois, barramento ainda com timeout: a sonda falha e o LCD não é iniciado
 now+=20000; Wire.busBroken=true; lcdRecoveryTick(); assert(!lcdReady && lcd.inits==0 && Wire.probes==1);
 // Barramento recuperado: na próxima janela de 30 s o LCD volta e é redesenhado por completo
 Wire.busBroken=false; lcd.failOnWrite=false; now+=30000; lcdRecoveryTick();
 assert(lcdReady && lcd.inits==1 && lcd.backlights==1 && Wire.probes==2);
 int before=lcd.writes; now+=500; displayTick();
 assert(lcd.writes==before+32 && lcdPrevA=="Senha ou digital");
 return 0;
}
'''
        self._compile_and_run(self._sketch_body(), cases)

    def test_lcd_redesenha_tela_apos_recuperacao(self):
        cases = r'''
int main() {
 door.begin(true,now); resetUi(); noticeDuration=0;
 // Desenho completo com sucesso preenche lcdPrevA/lcdPrevB
 displayTick(); assert(lcdReady && lcd.writes==32 && lcdPrevA=="Senha ou digital");
 // Entrada parcial muda a segunda linha; a falha ocorre na primeira escrita
 now+=200; entry="1"; lcd.failOnWrite=true; displayTick(); assert(!lcdReady && lcd.writes==33);
 // Após 30 s, com teclado vazio e barramento livre, o LCD volta
 entry=""; lcd.failOnWrite=false; now+=30000; lcdRecoveryTick(); assert(lcdReady && lcd.inits==1);
 // A tela é igual à anterior, mas precisa ser redesenhada por completo (lcdPrev limpo)
 int before=lcd.writes; now+=200; displayTick();
 assert(lcd.writes==before+32);
 return 0;
}
'''
        self._compile_and_run(self._sketch_body(), cases)

    def test_lcd_ausente_nao_e_religado(self):
        cases = r'''
int main() {
 door.begin(true,now); resetUi(); noticeDuration=0;
 lcdReady=false; Wire.lcdPresent=false;
 // LCD ausente (NACK): a sonda falha, lcd.init não é chamado e o LCD não é considerado religado
 now+=30000; lcdRecoveryTick(); assert(!lcdReady && Wire.probes==1 && lcd.inits==0);
 // Presença voltou, mas a janela de 30 s recomeçou na tentativa anterior
 Wire.lcdPresent=true; now+=10000; lcdRecoveryTick(); assert(!lcdReady && Wire.probes==1);
 now+=20000; lcdRecoveryTick(); assert(lcdReady && Wire.probes==2 && lcd.inits==1);
 return 0;
}
'''
        self._compile_and_run(self._sketch_body(), cases)

    def test_dy50_volta_quando_verifypassword_responde(self):
        cases = r'''
int main() {
 door.begin(true,now); resetUi(); noticeDuration=0;
 fingerprintReady=false; finger.verifyOk=false;
 // Dentro de 10 s nenhuma tentativa
 fingerprintRecoveryTick(); assert(!fingerprintReady && finger.verifyCalls==0);
 // 10 s depois, sensor ainda mudo: tentativa falha
 now+=10000; fingerprintRecoveryTick(); assert(!fingerprintReady && finger.verifyCalls==1);
 // Sensor responde, mas a janela de 10 s ainda não passou
 now+=2000; finger.verifyOk=true; fingerprintRecoveryTick(); assert(!fingerprintReady && finger.verifyCalls==1);
 // Após 10 s, a mesma expressão do setup confirma o DY50
 now+=8000; fingerprintRecoveryTick(); assert(fingerprintReady && finger.verifyCalls==2);
 // Com o DY50 já ativo, não há novas tentativas
 now+=20000; fingerprintRecoveryTick(); assert(fingerprintReady && finger.verifyCalls==2);
 // Fora da tela de acesso não tenta (cadastro em andamento)
 fingerprintReady=false; ui=Ui::Menu; now+=20000; fingerprintRecoveryTick();
 assert(!fingerprintReady && finger.verifyCalls==2);
 ui=Ui::Access; now+=20000; fingerprintRecoveryTick(); assert(fingerprintReady && finger.verifyCalls==3);
 return 0;
}
'''
        self._compile_and_run(self._sketch_body(), cases)

    def test_recuperacao_respeita_guardas(self):
        cases = r'''
// Cada caso: com a condição ativa nenhuma tentativa; sem ela, a mesma chamada tenta (controle).
void limpa() {
 door.begin(true,now); resetUi(); noticeDuration=0; buzzer.reset();
 entry=""; fingerprintReady=false; lcdReady=false; finger.verifyOk=false;
 lcd.failOnWrite=false; Wire.busBroken=false; now+=30000;
}
void bloqueado(const char *caso) {
 fprintf(stderr,"%s\n",caso);
 const int v=finger.verifyCalls, p=Wire.probes, i=lcd.inits;
 fingerprintRecoveryTick(); lcdRecoveryTick();
 assert(finger.verifyCalls==v && Wire.probes==p && lcd.inits==i);
}
void liberado() {
 const int v=finger.verifyCalls, i=lcd.inits;
 fingerprintRecoveryTick(); lcdRecoveryTick();
 assert(finger.verifyCalls==v+1 && lcd.inits==i+1 && lcdReady);
}
int main() {
 limpa(); door.authorize(1,now); assert(door.state==DoorState::AwaitOpen);
 bloqueado("porta em AwaitOpen"); door.begin(true,now); liberado();
 limpa(); door.authorize(1,now); door.tick(false,now,1000,1000); assert(door.state==DoorState::Open);
 bloqueado("porta aberta"); door.begin(true,now); liberado();
 limpa(); notice("Aviso","",false,5000); assert(noticeActive());
 bloqueado("notice ativo"); noticeDuration=0; liberado();
 limpa(); entry="1";
 bloqueado("entry nao vazio"); entry=""; liberado();
 limpa(); ui=Ui::Menu;
 bloqueado("tela fora de Access"); resetUi(); liberado();
 // Buzzer ativo bloqueia só o LCD (o DY50 não depende do buzzer)
 limpa(); buzzer.onEvent(DoorEvent::EntryExpired,now);
 fprintf(stderr,"buzzer ativo (somente LCD)\n");
 { const int p=Wire.probes, i=lcd.inits; lcdRecoveryTick(); assert(Wire.probes==p && lcd.inits==i && !lcdReady);
   buzzer.reset(); lcdRecoveryTick(); assert(lcdReady && lcd.inits==i+1); }
 return 0;
}
'''
        self._compile_and_run(self._sketch_body(), cases)


if __name__ == '__main__':
    unittest.main()
