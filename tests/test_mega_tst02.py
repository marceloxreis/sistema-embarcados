"""TST-02: testes do sketch Mega com as funções reais recortadas do .ino.

Cobre: debounce de 200 ms da porta (doorTick), cores do LED RGB (outputsTick),
textos do LCD com ID (idText/displayTick), teclas D, * e # (handleKey),
pin_in_use (resetPassword) e sequências reais doorTick+outputsTick com o
LOCK_MODE de Config.example.h (variantes 1 e 2 só na cópia de teste).

A variável de ambiente CONTROLE_MEGA_B6 aponta para outra cópia do firmware e
existe só para rodar os mutantes do .ino. Config.h nunca é lido: usa-se
Config.example.h.
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_mega_logic import PREFIX

ROOT = Path(__file__).resolve().parents[1]
MEGA = ROOT / 'firmware/MegaControlador'
FONTE = Path(os.environ.get('CONTROLE_MEGA_B6') or MEGA)
SDK = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')

# Arduino.h mínimo: só o necessário para compilar Config.example.h no host.
ARDUINO_H = '''#pragma once
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#define HIGH 1
#define LOW 0
typedef uint8_t byte;
'''

# Cabeçalho para os testes de porta e LED: hardware simulado + Config.example.h.
PREFIXO_HW = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <string>
#include <vector>
#include "DoorLogic.h"
#include "BuzzerLogic.h"
#include "CardStore.h"
#include "Config.example.h"
class String : public std::string {
 public: using std::string::string; using std::string::operator=;
 String(const std::string &s):std::string(s) {}
};
static uint32_t now = 0;
uint32_t millis() { return now; }
int pinIn[64], pinOut[64];
int digitalRead(uint8_t p) { return pinIn[p]; }
void digitalWrite(uint8_t p, int v) { pinOut[p] = v ? 1 : 0; }
void pinMode(uint8_t, uint8_t) {}
std::vector<std::string> audits;
void queueEvent(const char *t, uint16_t id, const char *m, const char *r) {
 audits.push_back(std::string(t) + "|" + std::to_string(id) + "|" + m + "|" + r);
}
DoorLogic door; BuzzerLogic buzzer;
'''

AJUDANTES_HW = r'''
static void passo(uint32_t t) { now = t; doorTick(); outputsTick(); }
static void fecha(bool fechada) { pinIn[BUTTON_1] = pinIn[BUTTON_2] = fechada ? LOW : HIGH; }
static std::string cor() {
 char b[4]; snprintf(b, sizeof b, "%d%d%d", pinOut[LED_R], pinOut[LED_G], pinOut[LED_B]); return b;
}
static int trava() { return pinOut[LOCK_PIN] == int(LOCK_ON) ? 1 : 0; }
static int buzzerPin() { return pinOut[BUZZER_PIN]; }
'''

# Dublê de LCD que guarda o texto das duas linhas. displayTick real redesenha tudo.
MOCKS_LCD = r'''
#define F(s) s
#define LCD_SERIAL_MIRROR 1
struct SerialLcdMock { std::string log; void print(const char *s) { log += s; } void print(const std::string &s) { log += s; } void println(const std::string &s) { log += s + "\n"; } } Serial;
#include <cstdlib>
struct FakeLCD {
 int row = 0; String linhas[2];
 void begin(int, int) {}
 void print(const char *) {}
 void setCursor(int, int r) { row = r; }
 void write(uint8_t c) { linhas[row] += char(c); }
} lcd;
static std::string pad(const char *s) { std::string r(s); r.resize(16, ' '); return r; }
'''

# Ajudante de tela: força novo desenho e confere as duas linhas de 16 colunas (após displayTick).
TELA_LCD = r'''
// Força um novo desenho (lcdPrevA/B vazios) e confere as duas linhas de 16 colunas.
static void tela(const char *a, const char *b) {
 lcdPrevA = ""; lcdPrevB = ""; lcd.linhas[0] = ""; lcd.linhas[1] = "";
 now += 200; displayTick();
 if (!(lcd.linhas[0] == pad(a) && lcd.linhas[1] == pad(b))) {
  fprintf(stderr, "tela [%s|%s] != [%s|%s]\n", lcd.linhas[0].c_str(), lcd.linhas[1].c_str(), a, b);
  exit(1);
 }
}
'''

# PREFIX das credenciais, com fila de auditoria registrada e substring no String do LCD.
PREFIXO_CRED = PREFIX.replace(
    'void queueEvent(const char *,uint16_t,const char *,const char *) {}',
    '#include <vector>\nstd::vector<std::string> audits;\n'
    'void queueEvent(const char *t,uint16_t id,const char *m,const char *r) {'
    ' audits.push_back(std::string(t)+"|"+std::to_string(id)+"|"+m+"|"+r); }')
assert PREFIXO_CRED != PREFIX, 'PREFIX de credenciais mudou: ajuste o recorte de queueEvent'
PREFIXO_LCD = PREFIXO_CRED.replace(
    'String(const std::string &s):std::string(s) {}',
    'String(const std::string &s):std::string(s) {} '
    'String substring(size_t a,size_t b) const { return String(substr(a,b-a)); }')
assert PREFIXO_LCD != PREFIXO_CRED


def _ler_ino():
    return (FONTE / 'MegaControlador.ino').read_text(encoding='utf-8')


def _trecho(src, ini, fim):
    """Texto do .ino de `ini` (inclusive) até `fim` (exclusive); ambos são marcadores únicos."""
    i = src.index(ini)
    return src[i:src.index(fim, i)]


def _pecas_hw(src):
    """Globais, audit/notice/idText/resetUi, doorTick e rgb/outputsTick, todos reais."""
    return (_trecho(src, 'enum class Ui', 'bool validPin(')
            + _trecho(src, 'void audit(', '// message é')
            + _trecho(src, 'void doorTick() {', '// Religa o DY50')
            + _trecho(src, 'void rgb(', 'void doorTick() {'))


def _executar(fonte_cpp, lock_mode=None, sketch_fonte=None):
    """Compila `fonte_cpp` com Config.example.h (ou com LOCK_MODE trocado na cópia) e executa."""
    with tempfile.TemporaryDirectory() as directorio:
        d = Path(directorio)
        (d / 'Arduino.h').write_text(ARDUINO_H)
        config = (FONTE / 'Config.example.h').read_text(encoding='utf-8')
        if lock_mode is not None:
            config, n = re.subn(r'LOCK_MODE = \d+,', 'LOCK_MODE = %d,' % lock_mode, config, count=1)
            assert n == 1, 'LOCK_MODE não encontrado em Config.example.h'
        (d / 'Config.example.h').write_text(config)
        source = d / 'test.cpp'
        binary = d / 'test'
        source.write_text(fonte_cpp, encoding='utf-8')
        cmd = [os.environ.get('CXX', 'c++'), '-std=c++11', '-I', str(d), '-I', str(FONTE)]
        if sys.platform == 'darwin' and SDK.exists():
            cmd += ['-isysroot', str(SDK)]
        result = subprocess.run(cmd + [str(source), '-o', str(binary)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        result = subprocess.run([str(binary)], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------- item 1: debounce
MAIN_DEBOUNCE = r'''
int main() {
 fecha(true);  // porta começa fechada (botões em LOW)
 rawClosed = stableClosed = true; rawSince = 0; door.begin(true, 0); resetUi(); noticeDuration = 0;
 // (a) porta "abre" por 199 ms e volta: abaixo de 200 ms, nada muda
 fecha(false); passo(1000); passo(1199);
 assert(stableClosed && door.state == DoorState::Idle && audits.empty());
 fecha(true); passo(1199);
 assert(stableClosed && audits.empty());
 passo(1500); assert(stableClosed && door.state == DoorState::Idle && audits.empty());
 // (b) abertura estável: a 199 ms ainda é ignorada; a 200 ms é aceita (porta Idle vira alarme)
 fecha(false); passo(2000); passo(2199);
 assert(stableClosed && audits.empty());
 passo(2200);
 assert(!stableClosed && door.state == DoorState::Alarm);
 assert(audits.size() == 1 && audits[0] == "forced_open|0|sensor|");
 // (c) fechamento estável a 200 ms encerra o alarme
 audits.clear(); fecha(true); passo(3000); passo(3199);
 assert(!stableClosed && door.state == DoorState::Alarm);
 passo(3200);
 assert(stableClosed && door.state == DoorState::Idle);
 assert(audits.size() == 1 && audits[0] == "door_closed|0||");
 // (d) cada borda reinicia a janela: fecha/abre em 30 ms não conta; a janela recomeça em 4040
 audits.clear(); fecha(false); passo(4000); fecha(true); passo(4030); fecha(false); passo(4040);
 passo(4239); assert(stableClosed && audits.empty());
 passo(4240); assert(!stableClosed && audits.size() == 1 && audits[0] == "forced_open|0|sensor|");
 fecha(true); passo(4300); passo(4500); assert(stableClosed && door.state == DoorState::Idle);
}
'''


class DebounceTests(unittest.TestCase):
    def test_debounce_de_200_ms_na_porta(self):
        src = _ler_ino()
        _executar(PREFIXO_HW + _pecas_hw(src) + AJUDANTES_HW + MAIN_DEBOUNCE)


# ---------------------------------------------------------------- item 2: LED RGB
MAIN_LED = r'''
int main() {
 fecha(true);  // porta começa fechada (botões em LOW)
 rawClosed = stableClosed = true; rawSince = 0; door.begin(true, 0); resetUi(); noticeDuration = 0;
 // Ocioso: azul por 200 ms a cada 10 s, apagado no resto
 passo(35000); assert(cor() == "000");
 // Repouso: "001" quando t % 10000 < 200 e "000" fora da janela, em vários ciclos
 for (uint32_t k = 4; k <= 5; ++k) {
  passo(k * 10000);       assert(cor() == "001");
  passo(k * 10000 + 199); assert(cor() == "001");
  passo(k * 10000 + 200); assert(cor() == "000");
  passo(k * 10000 + 5000); assert(cor() == "000");
  passo(k * 10000 + 9999); assert(cor() == "000");
 }
 passo(60100); assert(cor() == "001");
 passo(60200); assert(cor() == "000");
 // Autorizado, aguardando abertura: verde
 door.authorize(7, 61000); authorizationAt = 61000; accessMethod = "password"; buzzer.reset();
 passo(61000); assert(door.state == DoorState::AwaitOpen && cor() == "010");
 // Aberta autorizada: amarelo piscando (aceso quando (t/600)%2 == 1)
 fecha(false); passo(61100); passo(61300);   // 200 ms de debounce
 assert(door.state == DoorState::Open);
 passo(61800); assert(cor() == "110");
 passo(62400); assert(cor() == "000");
 // Fechada: encerra o ciclo e volta ao ocioso
 fecha(true); passo(63000); passo(63200);
 assert(door.state == DoorState::Idle && cor() == "000");
 // Aviso não-erro na tela de acesso: não pinta de vermelho
 passo(64000); notice("Cadastrado", "ID 007"); passo(64100); assert(cor() == "000");
 // Erro (E1): vermelho enquanto o aviso dura (2000 ms), depois apaga
 passo(66000); notice("Acesso negado", "Senha incorreta", true);
 passo(66100); assert(cor() == "100");
 passo(67999); assert(cor() == "100");
 passo(68000); assert(cor() == "000");
 // Administração/cadastro (ui != Access): branco
 ui = Ui::Menu; passo(68100); assert(cor() == "111");
 ui = Ui::FirstFinger; passo(68200); assert(cor() == "111");
 // Erro sobre a tela de cadastro: vermelho tem precedência sobre o branco
 notice("Cadastro falhou", "Erro de leitura", true); passo(68300); assert(cor() == "100");
 passo(70200); assert(cor() == "111");
 ui = Ui::Access; passo(70300); assert(cor() == "000");
 // Porta aberta sem autorização: alarme pisca vermelho (aceso quando (t/350)%2 == 1)
 fecha(false); passo(71000); passo(71200);
 assert(door.state == DoorState::Alarm && cor() == "100");   // 71200/350 = 203 (ímpar): aceso
 passo(71400); assert(cor() == "000");                         // 204 (par): apagado
 // Alarme tem precedência sobre o erro: na fase apagada, o aviso de erro não acende
 notice("Acesso negado", "Senha incorreta", true); passo(71700); assert(cor() == "000");
 // Fechar encerra o alarme; o aviso de fechamento substitui o de erro
 fecha(true); passo(72000); passo(72200);
 assert(door.state == DoorState::Idle);
 passo(73500); assert(cor() == "000");
 // Falha de armazenamento usa o mesmo aviso de erro: vermelho
 passo(74000); notice("Falha memoria", "Acesso negado", true); passo(74100); assert(cor() == "100");
}
'''


class LedTests(unittest.TestCase):
    def test_cores_do_led_rgb_por_estado(self):
        src = _ler_ino()
        _executar(PREFIXO_HW + _pecas_hw(src) + AJUDANTES_HW + MAIN_LED)


# ---------------------------------------------------------------- item 6: sequências reais
MAIN_PORTA = r'''
int main() {
 fecha(true);  // porta começa fechada (botões em LOW)
 rawClosed = stableClosed = true; rawSince = 0; door.begin(true, 0); resetUi(); noticeDuration = 0;
 const int MODO = LOCK_MODE;  // 0: simulação (trava nunca energizada); 1: pulso; 2: manter
 // 1) liberada -> aberta -> fechada -> travada
 passo(1000); assert(trava() == 0 && buzzerPin() == 0 && cor() == "000");
 door.authorize(7, 1000); authorizationAt = 1000; accessMethod = "password"; buzzer.reset();
 passo(1000); assert(door.state == DoorState::AwaitOpen && cor() == "010");
 assert(trava() == (MODO == 0 ? 0 : 1));
 passo(1300); assert(trava() == (MODO == 2 ? 1 : 0) && buzzerPin() == 0);
 fecha(false); passo(1400); assert(door.state == DoorState::AwaitOpen);
 passo(1600);
 assert(door.state == DoorState::Open && door.user == 7 && trava() == 0 && buzzerPin() == 0);
 assert(audits.size() == 1 && audits[0] == "door_opened|7|password|");
 passo(3000); assert(cor() == "110");
 fecha(true); passo(5000); assert(door.state == DoorState::Open);
 passo(5200);
 assert(door.state == DoorState::Idle && trava() == 0 && buzzerPin() == 0);
 assert(audits.size() == 2 && audits[1] == "door_closed|7|password|");
 assert(noticeLine1 == "Porta fechada" && noticeLine2 == "ID 007");
 passo(5300); assert(cor() == "000");
 // 2) forçada -> alarme -> saída do alarme
 audits.clear();
 fecha(false); passo(9850); assert(door.state == DoorState::Idle);
 passo(10050);   // borda em 9850 + 200 ms de debounce
 assert(door.state == DoorState::Alarm && cor() == "000");
 assert(audits.size() == 1 && audits[0] == "forced_open|0|sensor|");
 passo(10400); assert(cor() == "100" && trava() == 0 && buzzerPin() == 0);
 notice("Acesso negado", "Senha incorreta", true);
 passo(10700); assert(cor() == "000");
 audits.clear(); fecha(true); passo(11000); assert(door.state == DoorState::Alarm);
 passo(11200);
 assert(door.state == DoorState::Idle && audits.size() == 1 && audits[0] == "door_closed|0||");
 passo(11300); assert(cor() == "000");
 passo(12500); assert(cor() == "000" && trava() == 0 && buzzerPin() == 0);
 // 3) aberta além de 5 minutos: alarme e bipe de 250 ms a cada 2 s até fechar
 audits.clear(); passo(20000);
 door.authorize(7, 20000); authorizationAt = 20000; accessMethod = "password"; buzzer.reset();
 fecha(false); passo(20100); passo(20300);
 assert(door.state == DoorState::Open && audits.back() == "door_opened|7|password|");
 passo(320299); assert(door.state == DoorState::Open && buzzerPin() == 0);
 passo(320300);
 assert(door.state == DoorState::Alarm && audits.back() == "door_timeout|7|password|");
 assert(buzzerPin() == 1);
 passo(320550); assert(buzzerPin() == 0);
 passo(322300); assert(buzzerPin() == 1 && door.state == DoorState::Alarm);
 fecha(true); passo(322400); passo(322600);
 assert(door.state == DoorState::Idle && buzzerPin() == 0 && audits.back() == "door_closed|7|password|");
 // 4) entrada expirada: três bipes de 200 ms e trava sem energia no modo simulado
 audits.clear(); passo(400000);
 door.authorize(7, 400000); authorizationAt = 400000; accessMethod = "password"; buzzer.reset();
 passo(459999); assert(door.state == DoorState::AwaitOpen && trava() == (MODO == 2 ? 1 : 0));
 passo(460000);
 assert(door.state == DoorState::Idle && audits.back() == "entry_expired|7|password|");
 assert(trava() == 0 && buzzerPin() == 1 && noticeLine1 == "Tempo esgotado");
 passo(460250); assert(buzzerPin() == 0);
 passo(460450); assert(buzzerPin() == 1);
 passo(461250); assert(buzzerPin() == 0);
}
'''


class SequenciasPortaTests(unittest.TestCase):
    def test_sequencias_porta_com_lock_mode_do_config_example(self):
        src = _ler_ino()
        _executar(PREFIXO_HW + _pecas_hw(src) + AJUDANTES_HW + MAIN_PORTA)

    def test_sequencias_porta_com_lock_mode_1_e_2_na_copia_de_teste(self):
        src = _ler_ino()
        for modo in (1, 2):
            with self.subTest(lock_mode=modo):
                _executar(PREFIXO_HW + _pecas_hw(src) + AJUDANTES_HW + MAIN_PORTA, lock_mode=modo)


# ---------------------------------------------------------------- item 7: buzzer na porta forçada
MAIN_BUZZER_FORCADO = r'''
int main() {
 fecha(true);  // porta começa fechada (botões em LOW)
 rawClosed = stableClosed = true; rawSince = 0; door.begin(true, 0); resetUi(); noticeDuration = 0;
 // (a) porta fechada e ociosa: buzzer em silêncio
 passo(1000); assert(buzzerPin() == 0);
 // (b) porta aberta sem autorização: ForcedOpen em 2050 (borda em 1850 + debounce de 200 ms)
 fecha(false); passo(1850); passo(2050);
 assert(door.state == DoorState::Alarm && door.user == 0 && door.since == 2050);
 assert(audits.size() == 1 && audits[0] == "forced_open|0|sensor|");
 passo(2050); assert(buzzerPin() == 1);   // since+0: liga já no evento
 passo(2150); assert(buzzerPin() == 1);   // since+100
 passo(2350); assert(buzzerPin() == 0);   // since+300
 passo(2600); assert(buzzerPin() == 1);   // since+550
 passo(2800); assert(buzzerPin() == 0);   // since+750
 // (c) fechar: encerra o alarme e o buzzer desliga
 audits.clear(); fecha(true); passo(3000); passo(3200);
 assert(door.state == DoorState::Idle && audits.size() == 1 && audits[0] == "door_closed|0||");
 assert(buzzerPin() == 0);
 passo(3600); assert(buzzerPin() == 0);
 // (d) boot com porta aberta: begin já entra em Alarm sem usuário e o bipe rápido começa
 door.begin(false, 4000); rawClosed = stableClosed = false; rawSince = 0; fecha(false);
 passo(4000); assert(door.state == DoorState::Alarm && door.user == 0 && buzzerPin() == 1);
 passo(4250); assert(buzzerPin() == 0);   // 250 ms desligado
 passo(4500); assert(buzzerPin() == 1);   // novo bipe
 fecha(true); passo(4600); passo(4800);
 assert(door.state == DoorState::Idle && buzzerPin() == 0);
 // (e) OpenTooLong (alarme com usuário 7) mantém o bipe de 250 ms a cada 2 s
 door.authorize(7, 5000); authorizationAt = 5000; accessMethod = "password"; buzzer.reset();
 passo(5000); assert(door.state == DoorState::AwaitOpen);
 fecha(false); passo(5100); passo(5300);
 assert(door.state == DoorState::Open && door.user == 7);
 passo(305300);
 assert(door.state == DoorState::Alarm && door.user == 7 && audits.back() == "door_timeout|7|password|");
 passo(305300); assert(buzzerPin() == 1);   // T+0
 passo(305400); assert(buzzerPin() == 1);   // T+100
 passo(305800); assert(buzzerPin() == 0);   // T+500
 passo(307300); assert(buzzerPin() == 1);   // T+2000: repete a cada 2 s
 fecha(true); passo(307350); passo(307550);
 assert(door.state == DoorState::Idle && buzzerPin() == 0);
}
'''


class BuzzerPortaForcadaTests(unittest.TestCase):
    def test_bipe_rapido_em_porta_aberta_sem_autorizacao_e_bipe_lento_no_tempo_esgotado(self):
        src = _ler_ino()
        _executar(PREFIXO_HW + _pecas_hw(src) + AJUDANTES_HW + MAIN_BUZZER_FORCADO)


# ---------------------------------------------------------------- item 3: LCD com ID
MAIN_LCD = r'''
int main() {
 door.begin(true, now); resetUi(); noticeDuration = 0; storageReady = true; fingerprintReady = true;
 // (a) ID com zeros à esquerda
 assert(idText(0) == "ID 000" && idText(7) == "ID 007" && idText(100) == "ID 100");
 // (b) Inativar/Reativar com ID: pior caso de 16 colunas (ID 6 + sufixo 10), sem truncar
 ui = Ui::ConfirmStatus; pendingId = 7; enableRequested = false;
 tela("ID 007 Inativar?", "# Sim D Cancelar");
 pendingId = 100; enableRequested = true;
 tela("ID 100 Reativar?", "# Sim D Cancelar");
 // (c) ID digitado nas telas de Inativar/Reativar
 ui = Ui::DisableId; entry = "007"; tela("Desativar ID:", "007");
 ui = Ui::EnableId; entry = "3"; tela("Reativar ID:", "3");
 // (d) estados da porta com ID
 resetUi(); door.authorize(7, now); tela("Acesso liberado", "ID 007");
 door.state = DoorState::Open; tela("Porta aberta", "ID 007");
 door.begin(false, now); door.user = 100; tela("Feche a porta", "ID 100");
 door.user = 0; tela("Feche a porta", "Sem autorizacao");
 door.begin(true, now); resetUi();
 // (e) aviso de cadastro com ID
 notice("Cadastrado", idText(7)); tela("Cadastrado", "ID 007");
 noticeDuration = 0;
 // (f) ocioso: ID de até 3 dígitos aparece; entrada maior (pode ser o admin) mascara; DY50 e memória
 entry = "12"; tela("#Confirma *Limpa", "ID: 12");
 entry = "1234"; tela("#Confirma *Limpa", "ID: ****");
 // Home animada: a cena de texto ocupa os 3 s iniciais de cada ciclo de 12 s.
 now = (now / 12000 + 1) * 12000;
 entry = ""; tela("Controle acesso", "");  // home: no LCD só o título
 fingerprintReady = false; tela("Controle acesso", ""); fingerprintReady = true;
 storageReady = false; tela("Falha memoria", "ID cartao dedo");
 entry = "1"; tela("#Confirma *Limpa", "ID: 1"); entry = ""; storageReady = true;
 // (f2) tela de senha do ID (B1): mascara com '*'; '*' vazio volta ao ID (teste de texto só)
 ui = Ui::AccessPin; pendingId = 1; entry = "12"; tela("#Confirma *Limpa", "ID 001: **");
 entry = "123456"; tela("#Confirma *Limpa", "ID 001: ******");
 entry = ""; tela("#Confirma *Limpa", "ID 001: ");
 // (f3) teclado travado (B4): texto de contagem em 16 colunas
 resetUi(); keypadLockActive = true; keypadLockedAt = now; tela("Teclado travado", "Aguarde 60 s");
 keypadLockActive = false; pinFailures = 0;
 // (g) cadastro: senha mascarada
 ui = Ui::FirstPin; entry = "123"; tela("Crie senha (6)", "***");
 ui = Ui::ConfirmPin; entry = ""; tela("Repita senha (6)", "");
 resetUi();
}
'''


class LcdComIdTests(unittest.TestCase):
    def test_textos_do_lcd_com_id(self):
        src = _ler_ino()
        corpo = _trecho(src, 'enum class Ui', 'void handleKey(')
        display = _trecho(src, 'void displayTick()', '// Lista circular')
        _executar(PREFIXO_LCD + corpo + MOCKS_LCD + display + TELA_LCD + MAIN_LCD)


# ---------------------------------------------------------------- item 4: teclas D, * e #
MAIN_TECLAS = r'''
int main() {
 door.begin(true, now); resetUi(); noticeDuration = 0; storageReady = true; fingerprintReady = true; audits.clear();
 auto tecla = [](char k) { noticeDuration = 0; handleKey(k); };
 auto digita = [](const char *s) { for (const char *p = s; *p; ++p) { noticeDuration = 0; handleKey(*p); } };
 // usuario 1 com senha 123456 pelo cadastro real
 pendingId = 1; firstPin = "123456"; entry = "123456"; confirmEnrollment(); resetUi(); noticeDuration = 0;
 audits.clear();
 assert(exists(1) && activeUser(1));
 // Access, entrada vazia
 tecla('D'); assert(entry == "" && ui == Ui::Access && audits.empty());
 tecla('*'); assert(entry == "");
 tecla('#'); assert(noticeLine1 == "Entrada invalida" && noticeLine2 == "ID e # ou admin" && noticeError && entry == "");
 // Access, entrada parcial
 digita("12"); assert(entry == "12");
 tecla('*'); assert(entry == "");
 digita("12"); tecla('D'); assert(entry == "" && ui == Ui::Access);
 digita("12345"); tecla('#'); assert(noticeLine1 == "Entrada invalida" && entry == "" && audits.empty());
 // ID 1 pede a senha; senha errada nega com o ID tentado na auditoria (B2)
 digita("1"); tecla('#'); assert(ui == Ui::AccessPin && pendingId == 1 && entry == "");
 digita("999999"); tecla('#');
 assert(noticeLine1 == "Acesso negado" && noticeLine2 == "Senha incorreta" && entry == "" && ui == Ui::Access);
 assert(audits.size() == 1 && audits[0] == "access_denied|1|password|invalid_pin");
 audits.clear();
 // limite de 10 digitos na tela de acesso; 10 que nao sao o admin nao sao PIN valido
 digita("12345678901"); assert(entry == "1234567890");
 tecla('#'); assert(noticeLine1 == "Entrada invalida" && entry == "");
 // 10 digitos que não são o admin contam como falha (com a senha errada anterior: 2)
 assert(audits.size() == 1 && audits[0] == "access_denied|0|keypad|invalid_pin" && pinFailures == 2);
 audits.clear();
 tecla('*');
 // senha correta do ID 1 libera o ciclo
 digita("1"); tecla('#'); digita("123456"); tecla('#');
 assert(door.state == DoorState::AwaitOpen && door.user == 1 && entry == "");
 assert(audits.size() == 1 && audits[0] == "access_granted|1|password|");
 audits.clear();
 // com o ciclo em andamento: a senha correta é ignorada sem aviso; D e * não cancelam o ciclo
 digita("1"); tecla('#'); digita("123456"); tecla('#');
 assert(door.state == DoorState::AwaitOpen && door.user == 1 && entry == "" && audits.empty() && ui == Ui::Access);
 digita("12"); tecla('D'); assert(door.state == DoorState::AwaitOpen && door.user == 1);
 tecla('*'); assert(entry == "" && door.state == DoorState::AwaitOpen);
 digita("0000000000"); tecla('#');
 assert(noticeLine1 == "Feche a porta" && ui == Ui::Access && entry == "");
 door.begin(true, now); resetUi(); noticeDuration = 0; audits.clear();
 // admin pelo teclado: # com 10 digitos abre o menu
 digita("0000000000"); tecla('#');
 assert(ui == Ui::Menu && audits.size() == 1 && audits[0] == "admin_login|0|keypad|");
 audits.clear();
 tecla('*'); assert(ui == Ui::Menu);
 tecla('#'); assert(ui == Ui::Menu);
 tecla('9'); assert(ui == Ui::Menu && entry == "");
 tecla('D'); assert(ui == Ui::Access && noticeLine1 == "Cancelado" && noticeLine2 == "");
 // Menu: 1 inicia cadastro com o proximo ID; D cancela
 ui = Ui::Menu; tecla('1'); assert(ui == Ui::RemoveFinger && pendingId == 2);
 tecla('D'); assert(ui == Ui::Access && pendingId == 0 && noticeLine1 == "Cancelado");
 // cadastro: PIN com 5 digitos é recusado; * limpa; D cancela
 ui = Ui::FirstPin; digita("12345"); tecla('#');
 assert(ui == Ui::FirstPin && noticeLine2 == "Use 6 digitos" && entry == "");
 digita("1234567"); assert(entry == "123456");
 tecla('*'); assert(ui == Ui::FirstPin && entry == "");
 digita("654321"); tecla('#'); assert(ui == Ui::ConfirmPin && firstPin == "654321" && entry == "");
 tecla('D'); assert(ui == Ui::Access && firstPin == "" && entry == "" && noticeLine1 == "Cancelado");
 // confirmação diferente volta a primeira senha
 ui = Ui::ConfirmPin; firstPin = "123456"; digita("123457"); tecla('#');
 assert(ui == Ui::FirstPin && noticeLine1 == "Senhas nao batem" && firstPin == "" && entry == "");
 resetUi(); noticeDuration = 0; audits.clear();
 // Inativar: ID digitado (max 3), ID inexistente, * limpa, digitos ignorados na confirmação, D cancela
 ui = Ui::Menu; tecla('2'); assert(ui == Ui::DisableId && !enableRequested);
 digita("1234"); assert(entry == "123");
 tecla('*'); assert(entry == "");
 digita("009"); tecla('#');
 assert(ui == Ui::DisableId && noticeLine1 == "ID inexistente" && entry == "");
 digita("1"); tecla('#'); assert(ui == Ui::ConfirmStatus && pendingId == 1);
 tecla('*'); assert(ui == Ui::ConfirmStatus);
 digita("5"); assert(ui == Ui::ConfirmStatus && entry == "");
 tecla('D'); assert(ui == Ui::Access && noticeLine1 == "Cancelado" && activeUser(1));
 // Inativar confirmado com #
 ui = Ui::Menu; tecla('2'); digita("1"); tecla('#'); tecla('#');
 assert(!activeUser(1) && ui == Ui::Access && noticeLine1 == "Desativado" && noticeLine2 == "ID 001");
 assert(audits.size() == 1 && audits[0] == "user_disabled|1|admin|");
 audits.clear();
 // Reativar confirmado com #
 ui = Ui::Menu; tecla('3'); assert(ui == Ui::EnableId && enableRequested);
 digita("1"); tecla('#'); tecla('#');
 assert(activeUser(1) && noticeLine1 == "Reativado" && noticeLine2 == "ID 001");
 // Durante um aviso ativo, teclas são ignoradas (comportamento atual, caracterizado aqui)
 resetUi(); audits.clear();
 notice("Acesso negado", "Senha incorreta", true);
 handleKey('1'); assert(entry == "");
 handleKey('#'); assert(audits.empty() && ui == Ui::Access && noticeLine1 == "Acesso negado");
 noticeDuration = 0;
}
'''


class TeclasTests(unittest.TestCase):
    def test_teclas_d_asterisco_e_hash_nos_estados_principais(self):
        src = _ler_ino()
        corpo = _trecho(src, 'enum class Ui', 'void handleKey(')
        teclado = _trecho(src, 'void handleKey(', 'void expireEntry()')
        _executar(PREFIXO_CRED + corpo + teclado + MAIN_TECLAS)


# ---------------------------------------------------------------- item 5 (B5): senha repetida
MAIN_PIN_IN_USE = r'''
int main() {
 door.begin(true, now); resetUi(); noticeDuration = 0; storageReady = true; fingerprintReady = true;
 auto cadastra = [](uint16_t id, const char *pin) {
  pendingId = id; firstPin = pin; entry = pin; confirmEnrollment(); resetUi(); noticeDuration = 0;
 };
 cadastra(1, "111111"); cadastra(2, "222222");
 assert(exists(1) && exists(2));
 UserRecord r;
 // B5: senha de outro ID é aceita no reset (senhas podem repetir); só o registro do ID 1 muda
 assert(!strcmp(resetPassword(1, "222222", "usb", 0), "ok"));
 assert(matches(1, "222222") && matches(2, "222222") && !matches(1, "111111"));
 // mesmo caminho pela web (com token): ok e o token fica no registro do ID 1
 assert(!strcmp(resetPassword(1, "111111", "web", 0x55), "ok"));
 assert(readRecord(1, r) && r.lastWebToken == 0x55 && matches(1, "111111"));
 // B5: cadastro com senha já usada por outro ID também é aceito
 cadastra(3, "222222"); assert(exists(3) && matches(3, "222222"));
 // com a tela ocupada, device_busy
 ui = Ui::Menu;
 assert(!strcmp(resetPassword(1, "222222", "usb", 0), "device_busy"));
 resetUi();
 assert(!strcmp(resetPassword(9, "444444", "usb", 0), "unknown_user"));
 assert(!strcmp(resetPassword(1, "12345", "usb", 0), "invalid_pin"));
}
'''


class PinEmUsoTests(unittest.TestCase):
    def test_reset_e_cadastro_aceitam_senha_ja_usada_por_outro_id(self):
        src = _ler_ino()
        corpo = _trecho(src, 'enum class Ui', 'void handleKey(')
        _executar(PREFIXO_CRED + corpo + MAIN_PIN_IN_USE)

# ---------------------------------------------------------------- registro corrompido (regressão corrigida)
MAIN_CORROMPIDO_RESET = r'''
int main() {
 door.begin(true, now); resetUi(); noticeDuration = 0; storageReady = true; fingerprintReady = true;
 pendingId = 1; firstPin = "111111"; entry = "111111"; confirmEnrollment(); resetUi(); noticeDuration = 0;
 assert(exists(1));
 EEPROM.data[4] ^= 1;                   // registro 1 com checksum inválido (erro de armazenamento)
 assert(!exists(1) && !storageReady);
 storageReady = true;                   // próxima chamada: o armazenamento ainda deve ser reportado como erro
 assert(!strcmp(resetPassword(1, "222222", "usb", 0), "storage_error"));
}
'''

MAIN_CORROMPIDO_DIGITAL = r'''
int main() {
 door.begin(true, now); resetUi(); noticeDuration = 0; storageReady = true; fingerprintReady = true;
 pendingId = 1; firstPin = "111111"; entry = "111111"; confirmEnrollment(); resetUi(); noticeDuration = 0;
 audits.clear();
 EEPROM.data[4] ^= 1;                   // registro 1 com checksum inválido
 assert(!exists(1) && !storageReady);
 storageReady = true; noticeDuration = 0;
 authorize(1, "fingerprint");           // o usuário existe; a falha é do armazenamento
 assert(noticeLine1 == "Falha memoria" && noticeLine2 == "Acesso negado" && noticeError);
}
'''


class RegistroCorrompidoTests(unittest.TestCase):
    # Regressão corrigida (TST-02, B7): resetPassword consulta o registro uma vez e, com
    # registro corrompido (UserStore::load -> -1, storageReady=false), responde "storage_error",
    # e não "unknown_user". Ver resetPassword em firmware/MegaControlador/MegaControlador.ino.
    def test_reset_com_registro_corrompido_retorna_storage_error(self):
        src = _ler_ino()
        corpo = _trecho(src, 'enum class Ui', 'void handleKey(')
        _executar(PREFIXO_CRED + corpo + MAIN_CORROMPIDO_RESET)

    # Regressão corrigida (TST-02, B7): authorize() lê o registro uma vez; com registro
    # corrompido, mostra a falha de memória ("Falha memoria"), e não "Cadastro inativo".
    # Ver authorize em firmware/MegaControlador/MegaControlador.ino.
    def test_digital_com_registro_corrompido_mostra_falha_memoria(self):
        src = _ler_ino()
        corpo = _trecho(src, 'enum class Ui', 'void handleKey(')
        _executar(PREFIXO_CRED + corpo + MAIN_CORROMPIDO_DIGITAL)


if __name__ == '__main__':
    unittest.main()
