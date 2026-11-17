"""Cartão RFID (RC522) no sketch Mega: acesso, cadastro e menu sem cartão, textos e protocolo.

As funções reais do .ino são recortadas e compiladas com dublês (EEPROM, millis,
porta, MFRC522 e Serial). Config.h nunca é lido: usa-se Config.example.h.
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
CAM = ROOT / 'firmware/Esp32CamRede'

# PREFIX das credenciais com auditoria registrada, String.substring e macros do LCD.
BASE = PREFIX.replace(
    'void queueEvent(const char *,uint16_t,const char *,const char *) {}',
    '#include <vector>\nstd::vector<std::string> audits;\n'
    'void queueEvent(const char *t,uint16_t id,const char *m,const char *r) {'
    ' audits.push_back(std::string(t)+"|"+std::to_string(id)+"|"+m+"|"+r); }')
BASE = BASE.replace(
    'String(const std::string &s):std::string(s) {}',
    'String(const std::string &s):std::string(s) {} '
    'String substring(size_t a,size_t b) const { return String(substr(a,b-a)); }')
BASE = BASE.replace('#include <string>\n', '#include <string>\n#include <vector>\n#include <initializer_list>\n'
                    '#include <cstdlib>\n#define F(s) s\n#define LCD_SERIAL_MIRROR 1\n#define SHOW_TYPED_DIGITS 0\n', 1)
# Dublê de linkTick com contador e ordem: registra "link" a cada chamada, para checar que
# a porta da CAM é atendida antes da leitura do RC522 (cardTick). "rfid" vem do dublê do MFRC522.
BASE = BASE.replace(
    'void linkTick(bool) {}',
    'std::vector<std::string> ordem; int linkTicks = 0, linkSensorWait = 0;\n'
    'void linkTick(bool sensorWait) { ++linkTicks; linkSensorWait += sensorWait; ordem.push_back("link"); }')
assert BASE.count('initializer_list') == 1 and 'substring(size_t' in BASE and 'audits' in BASE and 'ordem' in BASE

# Dublês do hardware que o trecho novo usa: RC522 (MFRC522), Serial e LCD.
DUBLES = r'''
struct MFRC522 {
 enum PCD_Register { VersionReg = 0x37 << 1 };
 struct Uid { uint8_t size; uint8_t uidByte[10]; } uid;
 bool present = false;
 int newChecks = 0, reads = 0, halts = 0, stops = 0, inits = 0;
 uint8_t version = 0x82;
 MFRC522(uint8_t, uint8_t) {}
 bool PICC_IsNewCardPresent() { ++newChecks; ordem.push_back("rfid"); return present; }
 bool PICC_ReadCardSerial() { ++reads; return true; }
 uint8_t PICC_HaltA() { ++halts; present = false; return 0; }
 void PCD_StopCrypto1() { ++stops; }
 void PCD_Init() { ++inits; }
 uint8_t PCD_ReadRegister(PCD_Register) { return version; }
} rfid(53, 49);
static void apresenta(std::initializer_list<uint8_t> uid) {
 rfid.uid.size = uint8_t(uid.size()); uint8_t i = 0;
 for (uint8_t b : uid) rfid.uid.uidByte[i++] = b;
 rfid.present = true;
}
struct SerialLcdMock { std::string log; void print(const char *s) { log += s; } void print(const std::string &s) { log += s; } void println(const std::string &s) { log += s + "\n"; } } Serial;
struct FakeLCD {
 int row = 0; String linhas[2];
 void begin(int, int) {}
 void print(const char *) {}
 void setCursor(int, int r) { row = r; }
 void write(uint8_t c) { linhas[row] += char(c); }
} lcd;
'''

# Ajudantes que chamam displayTick/handleKey: vêm depois do trecho do .ino.
DUBLES_B = r'''
static void tela(const char *a, const char *b) {
 lcdPrevA = ""; lcdPrevB = ""; lcd.linhas[0] = ""; lcd.linhas[1] = "";
 now += 200; displayTick();
 std::string ea(a), eb(b); ea.resize(16, ' '); eb.resize(16, ' ');
 if (!(lcd.linhas[0] == ea && lcd.linhas[1] == eb)) {
  fprintf(stderr, "tela [%s|%s] != [%s|%s]\n", lcd.linhas[0].c_str(), lcd.linhas[1].c_str(), ea.c_str(), eb.c_str());
  exit(1);
 }
}
static void digita(const char *s) { for (; *s; ++s) handleKey(*s); }
'''


def _sketch():
    return (MEGA / 'MegaControlador.ino').read_text(encoding='utf-8')


def _trecho(src, ini, fim):
    i = src.index(ini)
    return src[i:src.index(fim, i)]


def _pecas():
    """Estado e lógica (Ui..handleKey), teclas, digital, bloco do cartão e tela. Tudo real do .ino."""
    src = _sketch()
    return (_trecho(src, 'enum class Ui', 'void handleKey(')
            + _trecho(src, 'void handleKey(', 'void fingerprintTick()')
            + _trecho(src, 'void fingerprintTick()', 'void rgb(')
            + _trecho(src, '// Cartão RFID (RC522).', 'void setup() {')
            + _trecho(src, 'void displayTick()', '// Lista circular'))


def _executar(corpo):
    fonte = BASE + DUBLES + _pecas() + DUBLES_B + corpo
    with tempfile.TemporaryDirectory() as directorio:
        d = Path(directorio)
        source, binary = d / 'test.cpp', d / 'test'
        source.write_text(fonte, encoding='utf-8')
        cmd = [os.environ.get('CXX', 'c++'), '-std=c++11', '-I', str(MEGA)]
        sdk = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
        if sys.platform == 'darwin' and sdk.exists():
            cmd += ['-isysroot', str(sdk)]
        result = subprocess.run(cmd + [str(source), '-o', str(binary)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr[:4000]
        result = subprocess.run([str(binary)], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------- acesso por cartão
ACESSO = r'''
int main() {
 rfidReady = true; storageReady = true; fingerprintReady = true;
 UserRecord ativo = {}; ativo.active = 1; assert(saveRecord(1, ativo));
 UserRecord inativo = {}; inativo.active = 0; assert(saveRecord(2, inativo));
 CardStore::Tag t1 = {4, {0xde, 0xad, 0xbe, 0xef, 0, 0, 0}}, t2 = {7, {1, 2, 3, 4, 5, 6, 7}};
 assert(CardStore::write(EEPROM, 1, t1) && CardStore::write(EEPROM, 2, t2));
 // (a) cartão de usuário ativo libera a porta, com método card
 door.begin(true, now); resetUi(); noticeDuration = 0; audits.clear();
 apresenta({0xde, 0xad, 0xbe, 0xef}); now += 200; cardTick();
 assert(door.state == DoorState::AwaitOpen && door.user == 1);
 assert(audits.size() == 1 && audits[0] == "access_granted|1|card|");
 assert(rfid.halts == 1 && rfid.stops == 1 && !rfid.present);
 // (b) cadastro inativo: mesmo tratamento e auditoria de hoje, com método card
 door.begin(true, now); resetUi(); noticeDuration = 0; audits.clear();
 apresenta({1, 2, 3, 4, 5, 6, 7}); now += 200; cardTick();
 assert(door.state == DoorState::Idle && noticeLine1 == "Acesso negado" && noticeLine2 == "Cadastro inativo");
 assert(audits.size() == 1 && audits[0] == "access_denied|2|card|inactive_or_unknown");
 // (c) cartão desconhecido
 door.begin(true, now); resetUi(); noticeDuration = 0; audits.clear();
 apresenta({9, 9, 9, 9}); now += 200; cardTick();
 assert(door.state == DoorState::Idle && noticeLine1 == "Acesso negado" && noticeLine2 == "Cartao desconh." && noticeError);
 assert(audits.size() == 1 && audits[0] == "access_denied|0|card|unknown_card");
 // (d) UID de 10 bytes não cabe no armazenamento: conta como desconhecido
 door.begin(true, now); resetUi(); noticeDuration = 0; audits.clear();
 apresenta({1, 2, 3, 4, 5, 6, 7, 8, 9, 10}); now += 200; cardTick();
 assert(audits.size() == 1 && audits[0] == "access_denied|0|card|unknown_card");
 // (e) mesmo UID dentro de 2 s do último aceito é ignorado; depois de 2 s, aceito de novo
 door.begin(true, now); resetUi(); noticeDuration = 0; audits.clear();
 apresenta({0xde, 0xad, 0xbe, 0xef}); now += 200; cardTick();
 assert(audits.size() == 1 && audits[0] == "access_granted|1|card|");
 door.begin(true, now); resetUi(); noticeDuration = 0;
 now += 500; apresenta({0xde, 0xad, 0xbe, 0xef}); cardTick();
 assert(audits.size() == 1 && door.state == DoorState::Idle);
 now += 2000; apresenta({0xde, 0xad, 0xbe, 0xef}); cardTick();
 assert(audits.size() == 2 && audits[1] == "access_granted|1|card|" && door.state == DoorState::AwaitOpen);
 // (f) sondagem a cada 200 ms (A2), com a porta em repouso
 door.begin(true, now); resetUi(); noticeDuration = 0;
 rfid.newChecks = 0; lastRfidPoll = 0; rfid.present = false;
 now = 10000; cardTick();
 now += 100; cardTick();
 now += 100; cardTick();
 assert(rfid.newChecks == 2);
 // (g) porta aberta ou aviso ativo: nenhuma sondagem
 door.begin(false, now); rfid.newChecks = 0; now += 200; cardTick();
 assert(rfid.newChecks == 0);
 door.begin(true, now); resetUi(); noticeDuration = 2000; noticeSince = now; now += 200; cardTick();
 assert(rfid.newChecks == 0);
 noticeDuration = 0;
 // (h) RC522 indisponível: nenhuma sondagem
 rfidReady = false; now += 200; cardTick();
 assert(rfid.newChecks == 0);
 return 0;
}
'''

# ---------------------------------------------------------------- cadastro sem cartão
CADASTRO = r'''
int main() {
 storageReady = true; fingerprintReady = true; rfidReady = true;
 door.begin(true, now); resetUi(); noticeDuration = 0; audits.clear(); waitFingerRemoval = false; pendingId = 3;
 // 2a digital confirmada: segue direto para a senha, sem passo de cartão
 ui = Ui::SecondFinger; finger.imageStatus = FINGERPRINT_OK; now += 1000; fingerprintTick();
 assert(ui == Ui::FirstPin && entry == "");
 tela("Crie senha (6)", "");
 // na senha o leitor de cartão não é consultado
 int antes = rfid.newChecks; now += 200; lastRfidPoll = 0; cardTick();
 assert(ui == Ui::FirstPin && rfid.newChecks == antes);
 // senha e confirmação cadastram o usuário
 digita("654321"); handleKey('#'); digita("654321"); handleKey('#');
 assert(ui == Ui::Access && exists(3) && lastId == 3);
 assert(audits.size() == 1 && audits[0] == "user_enrolled|3|admin|");
 return 0;
}
'''

# ---------------------------------------------------------------- menu sem cartão
MENU_SEM_CARTAO = r'''
int main() {
 storageReady = true; fingerprintReady = true; rfidReady = true;
 door.begin(true, now); resetUi(); noticeDuration = 0; audits.clear();
 ui = Ui::Menu;
 // teclas 4 e 5 não fazem nada: nem vinculação nem remoção de cartão
 handleKey('4'); assert(ui == Ui::Menu && entry == "");
 handleKey('5'); assert(ui == Ui::Menu && entry == "");
 digita("9"); handleKey('#'); assert(ui == Ui::Menu && entry == "" && audits.empty());
 // a tela do menu é fixa, sem alternância
 tela("1 Novo 2 Inativ.", "3 Reativ. D Sair");
 now += 2500; tela("1 Novo 2 Inativ.", "3 Reativ. D Sair");
 return 0;
}
'''

# ---------------------------------------------------------------- textos do LCD
TELAS = r'''
int main() {
 storageReady = true; fingerprintReady = true; rfidReady = true;
 door.begin(true, now); resetUi(); noticeDuration = 0;
 ui = Ui::Menu; now = 20000; tela("1 Novo 2 Inativ.", "3 Reativ. D Sair");
 now = 22500; tela("1 Novo 2 Inativ.", "3 Reativ. D Sair");
 ui = Ui::Access; resetUi(); noticeDuration = 0;
 notice("Cartao em uso", "Use outro", true); tela("Cartao em uso", "Use outro");
 noticeDuration = 0;
 notice("Cartao vinculado", "ID 002"); tela("Cartao vinculado", "ID 002");
 noticeDuration = 0;
 return 0;
}
'''

# ---------------------------------------------------------------- RC522 indisponível
RECUPERACAO = r'''
int main() {
 rfidReady = false; lastRfidRecovery = now; rfid.version = 0x00; rfid.inits = 0;
 now += 14000; rfidRecoveryTick();
 assert(rfid.inits == 0 && !rfidReady);
 now += 1000; rfidRecoveryTick();
 assert(rfid.inits == 1 && !rfidReady);
 now += 5000; rfidRecoveryTick();
 assert(rfid.inits == 1);
 rfid.version = 0xff; now += 10000; rfidRecoveryTick();
 assert(rfid.inits == 2 && !rfidReady);
 rfid.version = 0x82; now += 15000; rfidRecoveryTick();
 assert(rfid.inits == 3 && rfidReady);
 now += 15000; rfidRecoveryTick();
 assert(rfid.inits == 3);
 // A3: RC522 que estava pronto e deixa de responder é marcado indisponível; a recuperação seguinte religa.
 rfid.version = 0x00; now += 15000; rfidRecoveryTick();
 assert(!rfidReady && rfid.inits == 3);
 rfid.version = 0x82; now += 15000; rfidRecoveryTick();
 assert(rfid.inits == 4 && rfidReady);
 return 0;
}
'''


def _literais(texto):
    return re.findall(r'"((?:[^"\\]|\\.)*)"', texto)


def _tabela(src, nome):
    m = re.search(r'const char \* const %s\[\] = \{(.*?)\};' % nome, src, re.S)
    assert m, 'tabela %s não encontrada' % nome
    return _literais(m.group(1))


# cardTick chama linkTick(true) antes de PICC_IsNewCardPresent, com ou sem cartão no campo.
LINK_ANTES_RFID = r'''
int main() {
 rfidReady = true; storageReady = true; fingerprintReady = true;
 door.begin(true, now); resetUi(); noticeDuration = 0;
 now += 1000; lastRfidPoll = 0;
 cardTick();
 assert(linkTicks == 1 && linkSensorWait == 1 && rfid.newChecks == 1);
 assert(ordem.size() == 2 && ordem[0] == "link" && ordem[1] == "rfid");
 ordem.clear(); now += 1000;
 apresenta({0x11, 0x22, 0x33, 0x44});
 cardTick();
 assert(ordem.size() >= 2 && ordem[0] == "link" && ordem[1] == "rfid");
 assert(rfid.reads == 1 && noticeLine2 == "Cartao desconh.");
 return 0;
}
'''


class CartaoRfidTests(unittest.TestCase):
    def test_link_tick_roda_antes_da_leitura_do_rc522(self):
        _executar(LINK_ANTES_RFID)

    def test_acesso_por_cartao(self):
        _executar(ACESSO)

    def test_cadastro_segue_direto_para_senha(self):
        _executar(CADASTRO)

    def test_teclas_4_e_5_nao_fazem_nada_no_menu(self):
        _executar(MENU_SEM_CARTAO)

    def test_telas_novas_cabem_em_16_colunas(self):
        _executar(TELAS)

    def test_recuperacao_do_rc522(self):
        _executar(RECUPERACAO)


class CartaoProtocoloTests(unittest.TestCase):
    def test_nomes_de_mega_e_cam_batem_com_o_protocolo(self):
        mega = _sketch()
        cam = (CAM / 'Esp32CamRede.ino').read_text(encoding='utf-8')
        for nome in ('eventNames', 'methodNames', 'reasonNames'):
            self.assertEqual(_tabela(mega, nome), _tabela(cam, nome), nome)
        eventos = _tabela(mega, 'eventNames')
        metodos = _tabela(mega, 'methodNames')
        motivos = _tabela(mega, 'reasonNames')
        self.assertEqual(len(eventos), 20)
        self.assertEqual(eventos[19], 'card_unlinked')
        self.assertEqual(eventos[17], 'card_linked')
        self.assertEqual(eventos[18], 'keypad_locked')
        self.assertEqual(eventos[16], 'enroll_failed')
        self.assertEqual(metodos[9], 'card')
        self.assertEqual(metodos[8], 'web')
        self.assertEqual(motivos[17], 'unknown_card')
        self.assertEqual(motivos[16], 'Digitais diferem')
        # Contagens usadas pelo nameIndex (Mega) e pela CAM devem cobrir as tabelas novas.
        self.assertIn('nameIndex(type, eventNames, 20)', mega)
        self.assertIn('nameIndex(method, methodNames, 10)', mega)
        self.assertIn('nameIndex(reason, reasonNames, 18)', mega)
        self.assertIn('item.event.reason < 18 ? reasonNames', cam)
        protocolo = (ROOT / 'firmware/shared/MessageProtocol.h').read_text(encoding='utf-8')
        self.assertIn('EnrollFailed,\n  CardLinked, KeypadLocked, CardUnlinked\n', protocolo)
        self.assertIn('Usb, Web, Card };', protocolo)
        self.assertIn('e.kind <= CardUnlinked', protocolo)
        self.assertIn('e.method <= Card', protocolo)

    def test_list_e_boot_mostram_cartao_e_rfid(self):
        mega = _sketch()
        self.assertIn('" cartao=sim" : " cartao=nao"', mega)
        self.assertIn('F(" rfid=")', mega)
        self.assertIn('rfidReady ? F("ok") : F("indisponivel")', mega)

    def test_textos_novos_cabem_no_lcd(self):
        mega = _sketch()
        textos = ['Cartao em uso', 'Use outro', 'Cartao lido', 'Crie senha (6)', 'Cartao vinculado',
                  'Cartao invalido', 'Erro na memoria', 'Cartao nao salvo', 'Cartao desconh.',
                  '1 Novo 2 Inativ.', '3 Reativ. D Sair', 'Cancelado', 'ID inexistente']
        for texto in textos:
            self.assertLessEqual(len(texto), 16, texto)
            self.assertIn('"%s"' % texto, mega, texto)
        # Cadastro sem cartão e menu sem vinculação: essas telas não existem mais.
        self.assertNotIn('"Aproxime cartao"', mega)
        self.assertNotIn('4 Vincula cartao', mega)

    def test_config_example_documenta_pinos_do_rc522(self):
        exemplo = (MEGA / 'Config.example.h').read_text(encoding='utf-8')
        self.assertIn('// #define RFID_SS_PIN 53', exemplo)
        self.assertIn('// #define RFID_RST_PIN 49', exemplo)
        self.assertIn('#ifndef RFID_SS_PIN', _sketch())
        self.assertIn('#define RFID_RST_PIN 49', _sketch())


if __name__ == '__main__':
    unittest.main()
