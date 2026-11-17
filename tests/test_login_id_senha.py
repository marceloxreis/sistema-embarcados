"""B1 a B6: login por ID + senha, bloqueio do teclado, senhas repetidas e textos do LCD.

Compila as funções reais do MegaControlador.ino (mesmo harness de test_cartao_rfid).
"""
import re
import unittest

from test_cartao_rfid import BASE, DUBLES, DUBLES_B, _pecas, _executar, _sketch

PREAMBULO = r'''
static void cadastra(uint16_t id, const char *pin, bool ativo) {
 pendingId = id; firstPin = pin; entry = pin; ui = Ui::ConfirmPin;
 confirmEnrollment(); resetUi(); noticeDuration = 0;
 if (!ativo) assert(changeStatus(id, false));
}
static void dg(const char *s) { for (const char *p = s; *p; ++p) { noticeDuration = 0; handleKey(*p); } }
static void tecla(char k) { noticeDuration = 0; handleKey(k); }
static void entra(const char *id, const char *senha) { dg(id); tecla('#'); dg(senha); tecla('#'); }
static void novaPorta() { door.begin(true, now); resetUi(); noticeDuration = 0; audits.clear(); }
static void erraSenha(const char *id) { dg(id); tecla('#'); dg("000000"); tecla('#'); }
'''


def _rodar(corpo):
    _executar(corpo)


class LoginIdSenhaTests(unittest.TestCase):
    def test_id_mais_senha_certa_libera_e_errada_nega(self):
        _rodar(PREAMBULO + r'''
int main() {
 rfidReady = true; storageReady = true; fingerprintReady = true;
 cadastra(1, "123456", true); cadastra(2, "654321", false); cadastra(3, "123456", true);
 novaPorta(); entra("1", "123456");
 assert(door.state == DoorState::AwaitOpen && door.user == 1 && ui == Ui::Access && entry == "");
 assert(audits.size() == 1 && audits[0] == "access_granted|1|password|");
 novaPorta(); entra("1", "654321");
 assert(door.state == DoorState::Idle && noticeLine1 == "Acesso negado" && noticeLine2 == "Senha incorreta");
 assert(audits.size() == 1 && audits[0] == "access_denied|1|password|invalid_pin");
 // senha repetida entre IDs: o ID 3 entra com a mesma senha do ID 1
 novaPorta(); entra("3", "123456");
 assert(door.state == DoorState::AwaitOpen && door.user == 3);
 // inativo: senha certa cai no tratamento de cadastro inativo; senha errada, invalid_pin
 novaPorta(); entra("2", "654321");
 assert(door.state == DoorState::Idle && noticeLine2 == "Cadastro inativo");
 assert(audits.size() == 1 && audits[0] == "access_denied|2|password|inactive_or_unknown");
 novaPorta(); entra("2", "000000");
 assert(noticeLine2 == "Senha incorreta" && audits.size() == 1 && audits[0] == "access_denied|2|password|invalid_pin");
 return 0;
}
''')

    def test_id_inexistente_pede_senha_e_nega_sem_revelar(self):
        _rodar(PREAMBULO + r'''
int main() {
 rfidReady = true; storageReady = true; fingerprintReady = true;
 cadastra(1, "123456", true);
 novaPorta(); dg("50"); tecla('#'); assert(ui == Ui::AccessPin && pendingId == 50);
 dg("123456"); tecla('#');
 assert(noticeLine2 == "Senha incorreta" && ui == Ui::Access && audits.size() == 1 && audits[0] == "access_denied|50|password|invalid_pin");
 // fora de 1..100 pede a senha também; a auditoria registra user 0
 novaPorta(); dg("150"); tecla('#'); assert(ui == Ui::AccessPin);
 dg("123456"); tecla('#');
 assert(audits.size() == 1 && audits[0] == "access_denied|0|password|invalid_pin");
 novaPorta(); dg("000"); tecla('#'); assert(ui == Ui::AccessPin);
 dg("111111"); tecla('#'); assert(audits.size() == 1 && audits[0] == "access_denied|0|password|invalid_pin");
 return 0;
}
''')

    def test_formatos_de_entrada(self):
        _rodar(PREAMBULO + r'''
int main() {
 rfidReady = true; storageReady = true; fingerprintReady = true;
 cadastra(1, "123456", true);
 novaPorta(); tecla('#');
 assert(noticeLine1 == "Entrada invalida" && noticeLine2 == "ID e # ou admin" && ui == Ui::Access);
 novaPorta(); dg("1234"); tecla('#'); assert(noticeLine1 == "Entrada invalida" && ui == Ui::Access && entry == "");
 novaPorta(); dg("123456"); tecla('#'); assert(noticeLine1 == "Entrada invalida" && ui == Ui::Access);
 // 10 digitos que não são o admin contam como senha errada (ver test_admin_errado_conta_como_falha)
 novaPorta(); dg("0123456789"); tecla('#'); assert(noticeLine1 == "Entrada invalida" && pinFailures == 1);
 // senha com tamanho errado: aviso, continua na senha e não conta como tentativa
 novaPorta(); dg("1"); tecla('#'); dg("12345"); tecla('#');
 assert(noticeLine1 == "Entrada invalida" && noticeLine2 == "Use 6 digitos" && ui == Ui::AccessPin && audits.empty() && pinFailures == 1);
 return 0;
}
''')

    def test_admin_com_10_digitos_abre_menu(self):
        _rodar(PREAMBULO + r'''
int main() {
 rfidReady = true; storageReady = true; fingerprintReady = true;
 cadastra(1, "123456", true);
 novaPorta(); dg("0000000000"); tecla('#');
 assert(ui == Ui::Menu && audits.size() == 1 && audits[0] == "admin_login|0|keypad|");
 return 0;
}
''')

    def test_asterisco_e_timeout_nas_telas_de_id_e_senha(self):
        _rodar(PREAMBULO + r'''
int main() {
 rfidReady = true; storageReady = true; fingerprintReady = true;
 cadastra(1, "123456", true);
 novaPorta();
 // '*' com entrada vazia na senha volta à tela de ID; com dígitos só limpa
 dg("1"); tecla('#'); tecla('*'); assert(ui == Ui::Access && pendingId == 0 && entry == "");
 dg("1"); tecla('#'); dg("12"); tecla('*'); assert(ui == Ui::AccessPin && pendingId == 1 && entry == "");
 tecla('*'); assert(ui == Ui::Access);
 // 30 s sem tecla: senha pendente volta ao repouso e limpa tudo
 dg("1"); tecla('#'); now += 29000; expireEntry(); assert(ui == Ui::AccessPin);
 now += 1000; expireEntry(); assert(ui == Ui::Access && pendingId == 0 && entry == "");
 // ID parcial também expira
 dg("12"); now += 30000; expireEntry(); assert(entry == "" && ui == Ui::Access);
 return 0;
}
''')

    def test_bloqueio_na_quinta_falha_com_cartao_funcionando(self):
        _rodar(PREAMBULO + r'''
int main() {
 rfidReady = true; storageReady = true; fingerprintReady = true;
 cadastra(1, "123456", true);
 CardStore::Tag cartao = {4, {0xde, 0xad, 0xbe, 0xef, 0, 0, 0}};
 assert(CardStore::write(EEPROM, 1, cartao));
 novaPorta();
 for (int i = 0; i < 4; ++i) erraSenha("1");
 assert(!keypadLocked() && pinFailures == 4 && noticeLine2 == "Senha incorreta");
 erraSenha("1");
 assert(keypadLocked() && ui == Ui::Access && pinFailures == 0);
 assert(audits.back() == "keypad_locked|0|keypad|invalid_pin");
 // teclas ignoradas durante o bloqueio
 tecla('1'); assert(entry == "");
 dg("1"); tecla('#'); assert(ui == Ui::Access && entry == "");
 // cartão e digital seguem: o cartão libera a porta durante o bloqueio
 door.begin(true, now); resetUi(); noticeDuration = 0; audits.clear();
 cardAccess(cartao);
 assert(door.state == DoorState::AwaitOpen && door.user == 1 && audits.back() == "access_granted|1|card|");
 // LCD mostra o bloqueio com contagem regressiva em 16 colunas
 door.begin(true, now); resetUi(); noticeDuration = 0;
 tela("Teclado travado", "Aguarde 60 s");
 now += 30000; tela("Teclado travado", "Aguarde 30 s");
 // 60 s depois o teclado volta
 now += 29000; assert(keypadLocked());
 now += 1000; assert(!keypadLocked() && pinFailures == 0);
 return 0;
}
''')

    def test_sucesso_nao_zera_contador_de_falhas(self):
        _rodar(PREAMBULO + r'''
int main() {
 rfidReady = true; storageReady = true; fingerprintReady = true;
 cadastra(1, "123456", true);
 novaPorta();
 for (int i = 0; i < 4; ++i) erraSenha("1");
 assert(pinFailures == 4 && !keypadLocked());
 // senha certa libera a porta, mas não zera o contador: a próxima errada ainda trava
 novaPorta(); entra("1", "123456");
 assert(door.state == DoorState::AwaitOpen && pinFailures == 4);
 novaPorta(); erraSenha("1");
 assert(keypadLocked() && pinFailures == 0 && audits.back() == "keypad_locked|0|keypad|invalid_pin");
 return 0;
}
''')

    def test_decaimento_de_10_minutos_recomeca_a_contagem(self):
        _rodar(PREAMBULO + r'''
int main() {
 rfidReady = true; storageReady = true; fingerprintReady = true;
 cadastra(1, "123456", true);
 // A: 4 falhas e 599999 ms depois a 5a ainda trava (menos de 10 min desde a última)
 novaPorta();
 for (int i = 0; i < 4; ++i) erraSenha("1");
 now += 599999; erraSenha("1");
 assert(keypadLocked() && pinFailures == 0);
 now += 60000; assert(!keypadLocked() && pinFailures == 0);
 // B: 4 falhas e 10 min sem falha: a próxima recomeça em 1 e não trava
 novaPorta();
 for (int i = 0; i < 4; ++i) erraSenha("1");
 now += 600000; erraSenha("1");
 assert(!keypadLocked() && pinFailures == 1 && noticeLine2 == "Senha incorreta");
 for (int i = 0; i < 3; ++i) erraSenha("1");
 assert(!keypadLocked() && pinFailures == 4);
 erraSenha("1"); assert(keypadLocked() && pinFailures == 0);
 now += 60000;
 // C: a contagem parte da última falha, não da primeira: 400 s + 400 s (< 10 min cada) ainda travam
 novaPorta();
 for (int i = 0; i < 3; ++i) erraSenha("1");
 now += 400000; erraSenha("1"); assert(!keypadLocked() && pinFailures == 4);
 now += 400000; erraSenha("1"); assert(keypadLocked() && pinFailures == 0);
 return 0;
}
''')

    def test_admin_errado_conta_como_falha(self):
        _rodar(PREAMBULO + r'''
int main() {
 rfidReady = true; storageReady = true; fingerprintReady = true;
 cadastra(1, "123456", true);
 novaPorta();
 for (int i = 0; i < 4; ++i) {
   dg("1111111111"); tecla('#');
   assert(noticeLine1 == "Entrada invalida" && noticeLine2 == "ID e # ou admin" && ui == Ui::Access && entry == "");
   assert(audits.back() == "access_denied|0|keypad|invalid_pin");
 }
 assert(pinFailures == 4 && !keypadLocked());
 // o admin certo ainda abre o menu sem contar falha
 dg("0000000000"); tecla('#');
 assert(ui == Ui::Menu && pinFailures == 4 && audits.back() == "admin_login|0|keypad|");
 resetUi(); noticeDuration = 0;
 // a 5a entrada errada de 10 digitos trava o teclado
 dg("1111111111"); tecla('#');
 assert(keypadLocked() && pinFailures == 0 && audits.back() == "keypad_locked|0|keypad|invalid_pin");
 return 0;
}
''')

    def test_entrada_curta_nao_conta_como_falha(self):
        _rodar(PREAMBULO + r'''
int main() {
 rfidReady = true; storageReady = true; fingerprintReady = true;
 cadastra(1, "123456", true);
 novaPorta();
 for (int i = 0; i < 6; ++i) { dg("123456789"); tecla('#'); }
 assert(noticeLine1 == "Entrada invalida" && pinFailures == 0 && audits.empty() && !keypadLocked());
 return 0;
}
''')

    def test_prefixo_do_admin_mascarado_e_id_comum_visivel(self):
        _rodar(PREAMBULO + r'''
int main() {
 rfidReady = true; storageReady = true; fingerprintReady = true;
 cadastra(1, "123456", true);
 novaPorta();
 // ADMIN_PIN = 0000000000: prefixos de 1 a 3 digitos viram '*' no LCD
 dg("0"); tela("#Confirma *Limpa", "ID: *");
 dg("0"); tela("#Confirma *Limpa", "ID: **");
 dg("0"); tela("#Confirma *Limpa", "ID: ***");
 // 4 digitos já são mascarados por tamanho
 dg("0"); tela("#Confirma *Limpa", "ID: ****");
 // ID comum (não é prefixo do admin) continua visível
 novaPorta(); dg("1"); tela("#Confirma *Limpa", "ID: 1");
 dg("2"); tela("#Confirma *Limpa", "ID: 12");
 assert(Serial.log.find("LCD| #Confirma *Limpa | ID: 12\n") != std::string::npos);
 // espelho serial: o prefixo do admin nunca aparece como dígito
 assert(Serial.log.find("LCD| #Confirma *Limpa | ID: ***\n") != std::string::npos);
 assert(Serial.log.find("| ID: 0\n") == std::string::npos && Serial.log.find("| ID: 00\n") == std::string::npos);
 return 0;
}
''')

    def test_texto_do_bloqueio_nunca_passa_de_60(self):
        _rodar(PREAMBULO + r'''
int main() {
 rfidReady = true; storageReady = true; fingerprintReady = true;
 cadastra(1, "123456", true);
 door.begin(true, now); resetUi(); noticeDuration = 0;
 const uint32_t t0 = now;
 // Cada passo usa um instante diferente, inclusive logo antes e depois do fim do bloqueio.
 for (uint32_t e = 0; e <= 61000; e += 37) {
   keypadLockActive = true; keypadLockedAt = t0; pinFailures = 0;
   now = t0 + e; lastLcd = 0; lcdPrevA = ""; lcdPrevB = "";
   lcd.linhas[0] = ""; lcd.linhas[1] = "";
   displayTick();
   std::string top(lcd.linhas[0].c_str()), bottom(lcd.linhas[1].c_str());
   if (e < 60000) {
     const unsigned long esperado = (60000 - e + 999) / 1000;
     unsigned long mostrado = 0;
     assert(top.compare(0, 15, "Teclado travado") == 0);
     assert(sscanf(bottom.c_str(), "Aguarde %lu s", &mostrado) == 1);
     if (mostrado != esperado || mostrado < 1 || mostrado > 60) {
       fprintf(stderr, "e=%u mostrado=%lu esperado=%lu\n", (unsigned)e, mostrado, esperado);
       return 1;
     }
   } else {
     assert(top.compare(0, 15, "Teclado travado") != 0 && !keypadLockActive);
   }
 }
 return 0;
}
''')


class CartaoOrfaoTests(unittest.TestCase):
    def test_cartao_orfao_nao_bloqueia_nem_e_herdado_por_cadastro_sem_cartao(self):
        _rodar(PREAMBULO + r'''
int main() {
 rfidReady = true; storageReady = true; fingerprintReady = true;
 cadastra(1, "123456", true);
 CardStore::Tag orfao = {4, {0x11, 0x22, 0x33, 0x44, 0, 0, 0}};
 // A1: slot de cartão do ID 2 sem registro de usuário (cadastro interrompido após gravar o cartão)
 assert(CardStore::write(EEPROM, 2, orfao) && !exists(2));
 // não bloqueia a unicidade nem autoriza acesso
 assert(cardOwner(orfao.uid, 4) == 0);
 novaPorta(); cardAccess(orfao);
 assert(door.state == DoorState::Idle && noticeLine2 == "Cartao desconh.");
 assert(audits.size() == 1 && audits[0] == "access_denied|0|card|unknown_card");
 // cadastro sem cartão no ID 2 apaga o slot órfão e não herda o cartão
 pendingId = 2; cardPending = false; firstPin = "654321"; entry = "654321"; ui = Ui::ConfirmPin;
 confirmEnrollment(); resetUi(); noticeDuration = 0;
 CardStore::Tag lido;
 assert(exists(2) && !CardStore::read(EEPROM, 2, lido));
 assert(cardOwner(orfao.uid, 4) == 0);
 // com o órfão apagado, o mesmo cartão pode ser cadastrado em outro ID
 pendingId = 3; cardPending = true; pendingCard = orfao; firstPin = "777777"; entry = "777777"; ui = Ui::ConfirmPin;
 confirmEnrollment(); resetUi(); noticeDuration = 0;
 assert(exists(3) && cardOwner(orfao.uid, 4) == 3);
 return 0;
}
''')


class TextosLcdTests(unittest.TestCase):
    def test_textos_do_lcd_e_avisos_cabem_em_16_colunas(self):
        src = _sketch()
        # Avisos: notice("linha 1", "linha 2") e failEnrollment(msg, "linha 2") em todo o sketch.
        linhas = [t for par in re.findall(r'notice\(\s*"([^"]*)"\s*,\s*"([^"]*)"', src) for t in par]
        linhas += re.findall(r'failEnrollment\(\s*"[^"]*"\s*,\s*"([^"]*)"', src)
        # Telas do displayTick: todo literal de texto, exceto o espelho "LCD|" e formatos.
        corpo = src[src.index('void displayTick()'):src.index('// Lista circular')]
        literais = [t for t in re.findall(r'"([^"]*)"', corpo)
                    if t and not t.startswith('LCD') and '|' not in t and '%' not in t]
        linhas += literais
        self.assertTrue(len(linhas) >= 30, len(linhas))
        longos = [t for t in linhas if len(t) > 16]
        self.assertEqual(longos, [])
        for esperado in ('Teclado travado', 'Controle acesso', 'ID ou digital', 'Digite o ID', '#Confirma *Limpa', 'Entrada invalida', 'ID e # ou admin', 'Use 6 digitos'):
            self.assertIn(esperado, linhas)
        self.assertIn('"Aguarde %lu s"', corpo)
        self.assertIn('idText(pendingId) + ": "', corpo)
        self.assertNotIn('+ #', corpo)


if __name__ == '__main__':
    unittest.main()
