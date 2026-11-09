"""Telas de digitação ("#Confirma *Limpa" / "ID: "), mapa de cores do LED RGB e menu 5 (remover cartão).

Usa as funções reais recortadas do .ino com os dublês de test_mega_tst02 (LED) e
test_cartao_rfid (teclado, cartão, digital e LCD). Config.h nunca é lido.
"""
import re
import unittest

import test_cartao_rfid as cartao
import test_mega_tst02 as tst02


# ---------------------------------------------------------------- LED RGB
MAIN_CORES = r'''
static void reinicia() { door.begin(true, now); resetUi(); noticeDuration = 0; readFlashOn = false; keypadLockActive = false; }
int main() {
 fecha(true); rawClosed = stableClosed = true; rawSince = 0;
 passo(100000); reinicia();
 // Repouso: azul 200 ms a cada 10 s
 passo(110000); assert(cor() == "001"); passo(110200); assert(cor() == "000");
 // Digitando o ID: ciano; digitando a senha: magenta
 entry = "1"; passo(110300); assert(cor() == "011");
 ui = Ui::AccessPin; entry = ""; passo(110400); assert(cor() == "101");
 entry = "12"; passo(110500); assert(cor() == "101");
 // Menu admin, cadastro (todos os estados), menus 2 a 5: branco
 const Ui brancos[] = {Ui::Menu, Ui::RemoveFinger, Ui::FirstFinger, Ui::SecondFinger, Ui::FirstPin,
   Ui::ConfirmPin, Ui::CardEnroll, Ui::DisableId, Ui::EnableId, Ui::ConfirmStatus, Ui::LinkId,
   Ui::CardLink, Ui::UnlinkId, Ui::ConfirmUnlink};
 for (Ui estado : brancos) { ui = estado; passo(now + 10); assert(cor() == "111"); }
 reinicia();
 // Flash de leitura: ciano por 150 ms sobre repouso, branco, magenta e verde
 passo(120300); startReadFlash();
 passo(120300); assert(cor() == "011"); passo(120449); assert(cor() == "011");
 passo(120450); assert(cor() == "000" && !readFlashOn);
 ui = Ui::CardEnroll; startReadFlash(); passo(120500); assert(cor() == "011");
 passo(120650); assert(cor() == "111");
 ui = Ui::AccessPin; startReadFlash(); passo(120700); assert(cor() == "011");
 passo(120850); assert(cor() == "101");
 passo(121000); reinicia(); door.authorize(3, 121000); authorizationAt = 121000; startReadFlash();
 passo(121001); assert(cor() == "011"); passo(121150); assert(cor() == "010");
 // Erro com aviso ativo vence o flash
 reinicia(); startReadFlash(); notice("Acesso negado", "Cartao desconh.", true);
 passo(now + 1); assert(cor() == "100");
 // Digitando o ID vence porta aberta e acesso liberado
 reinicia(); door.authorize(3, now); authorizationAt = now; entry = "4"; passo(now + 1); assert(cor() == "011");
 entry = ""; passo(now + 1); assert(cor() == "010");
 // Teclado travado: vermelho 1 s aceso / 1 s apagado durante os 60 s, acima de erro, flash e digitação
 reinicia(); passo(200000); keypadLockActive = true; keypadLockedAt = 200000;
 passo(200000); assert(cor() == "100"); passo(200999); assert(cor() == "100");
 passo(201000); assert(cor() == "000"); passo(201999); assert(cor() == "000");
 passo(202000); assert(cor() == "100");
 notice("Acesso negado", "Senha incorreta", true); startReadFlash(); entry = "5";
 passo(203100); assert(cor() == "000");   // fase apagada: nem erro nem flash acendem
 passo(204100); assert(cor() == "100");
 noticeDuration = 0; readFlashOn = false; entry = "";
 passo(258500); assert(cor() == "100");
 passo(259999); assert(cor() == "000");   // 59999 % 2000 >= 1000
 passo(260000); assert(!keypadLockActive && cor() == "001");   // fim do bloqueio: repouso (260000 % 10000 < 200)
 // Alarme vence o bloqueio: pisca rápido (350 ms)
 keypadLockActive = true; keypadLockedAt = 261000; fecha(false); passo(261000); passo(261200);
 assert(door.state == DoorState::Alarm);
 passo(261450); assert(cor() == ((261450 / 350) % 2 ? "100" : "000"));
 passo(261800); assert(cor() == ((261800 / 350) % 2 ? "100" : "000"));
 assert(((261450 / 350) % 2) != ((261800 / 350) % 2));
 return 0;
}
'''


class CoresLedTests(unittest.TestCase):
    def test_mapa_de_cores_e_prioridades(self):
        src = tst02._ler_ino()
        tst02._executar(tst02.PREFIXO_HW + tst02._pecas_hw(src) + tst02.AJUDANTES_HW + MAIN_CORES)


# ---------------------------------------------------------------- telas, flash na leitura e menu 5
def _timeout():
    src = cartao._sketch()
    return 'constexpr uint32_t UI_TIMEOUT_MS = 60000;\n' + cartao._trecho(src, '// Telas de administração (menu', 'void loop() {')


def _rodar(corpo):
    cartao._executar(_timeout() + corpo)


TELAS = r'''
int main() {
 storageReady = true; fingerprintReady = true; rfidReady = true;
 door.begin(true, now); resetUi(); noticeDuration = 0;
 now = (now / 12000 + 1) * 12000; tela("Controle acesso", "");
 entry = "1"; tela("#Confirma *Limpa", "ID: 1");
 entry = "12"; tela("#Confirma *Limpa", "ID: 12");
 entry = "123"; tela("#Confirma *Limpa", "ID: 123");
 entry = "0"; tela("#Confirma *Limpa", "ID: *");            // prefixo do ADMIN_PIN
 entry = "000"; tela("#Confirma *Limpa", "ID: ***");
 entry = "1234"; tela("#Confirma *Limpa", "ID: ****");
 entry = "1234567890"; tela("#Confirma *Limpa", "ID: **********");   // 14 colunas
 assert(Serial.log.find("LCD| #Confirma *Limpa | ID: 12\n") != std::string::npos);
 assert(Serial.log.find("| ID: 0\n") == std::string::npos);
 entry = ""; ui = Ui::AccessPin; pendingId = 1; tela("#Confirma *Limpa", "ID 001: ");
 entry = "123456"; tela("#Confirma *Limpa", "ID 001: ******");
 resetUi(); ui = Ui::Menu;
 now = 20000; tela("1 Novo 2 Inativ.", "3 Reativ. D Sair");
 now = 22500; tela("4 Vincula cartao", "5 Remove cartao");
 now = 25000; tela("1 Novo 2 Inativ.", "3 Reativ. D Sair");
 ui = Ui::UnlinkId; entry = "7"; tela("Desvincular ID:", "7");
 ui = Ui::ConfirmUnlink; pendingId = 7; tela("Remover cartao?", "#Sim *Nao");
 resetUi();
 return 0;
}
'''

FLASH = r'''
int main() {
 storageReady = true; fingerprintReady = true; rfidReady = true;
 UserRecord a = {}; a.active = 1; assert(saveRecord(1, a));
 // cartão lido (mesmo desconhecido): flash começa no instante da leitura
 door.begin(true, now); resetUi(); noticeDuration = 0; readFlashOn = false;
 apresenta({9, 8, 7, 6}); now += 200; cardTick();
 assert(readFlashOn && readFlashAt == now && noticeLine2 == "Cartao desconh.");
 // mesmo UID em menos de 2 s é ignorado: sem novo flash
 readFlashOn = false; noticeDuration = 0; apresenta({9, 8, 7, 6}); now += 200; cardTick();
 assert(!readFlashOn);
 // digital capturada no acesso: flash antes do resultado
 door.begin(true, now); resetUi(); noticeDuration = 0; readFlashOn = false; waitFingerRemoval = false;
 finger.imageStatus = FINGERPRINT_OK; finger.fingerID = 1; now += 1000; fingerprintTick();
 assert(readFlashOn && readFlashAt == now && door.state == DoorState::AwaitOpen);
 // sem dedo: nenhum flash
 door.begin(true, now); resetUi(); readFlashOn = false; finger.imageStatus = FINGERPRINT_NOFINGER;
 now += 1000; fingerprintTick(); assert(!readFlashOn);
 return 0;
}
'''

MENU5 = r'''
int main() {
 rfidReady = true; storageReady = true; fingerprintReady = true;
 UserRecord a = {}; a.active = 1; assert(saveRecord(1, a)); assert(saveRecord(2, a));
 UserRecord b = {}; b.active = 0; assert(saveRecord(3, b));
 CardStore::Tag t1 = {4, {1, 2, 3, 4, 0, 0, 0}}, t3 = {4, {5, 6, 7, 8, 0, 0, 0}};
 assert(CardStore::write(EEPROM, 1, t1) && CardStore::write(EEPROM, 3, t3));
 CardStore::Tag lido;
 // '5' no menu abre o pedido do ID (até 3 dígitos)
 door.begin(true, now); resetUi(); noticeDuration = 0; audits.clear();
 ui = Ui::Menu; handleKey('5');
 assert(ui == Ui::UnlinkId && entry == "");
 digita("0012"); assert(entry == "001");
 // ID inexistente: aviso de erro e continua pedindo
 entry = ""; digita("9"); handleKey('#');
 assert(ui == Ui::UnlinkId && noticeLine1 == "ID inexistente" && noticeError && audits.empty());
 // ID sem cartão: "Sem cartao" / "ID 002" e continua pedindo
 noticeDuration = 0; digita("2"); handleKey('#');
 assert(ui == Ui::UnlinkId && noticeLine1 == "Sem cartao" && noticeLine2 == "ID 002" && noticeError && audits.empty());
 // ID com cartão: confirmação; dígitos são ignorados
 noticeDuration = 0; digita("1"); handleKey('#');
 assert(ui == Ui::ConfirmUnlink && pendingId == 1);
 tela("Remover cartao?", "#Sim *Nao");
 handleKey('7'); assert(ui == Ui::ConfirmUnlink && entry == "");
 // '#' confirma: apaga o slot, audita card_unlinked (admin) e avisa
 handleKey('#');
 assert(ui == Ui::Access && !CardStore::read(EEPROM, 1, lido) && CardStore::read(EEPROM, 3, lido));
 assert(audits.size() == 1 && audits[0] == "card_unlinked|1|admin|");
 assert(noticeLine1 == "Cartao removido" && noticeLine2 == "ID 001" && !noticeError);
 tela("Cartao removido", "ID 001");
 assert(exists(1) && activeUser(1));   // só o cartão sai; o usuário continua
 // '*' cancela sem apagar nem auditar (usuário inativo também pode ter o cartão removido)
 door.begin(true, now); resetUi(); noticeDuration = 0; audits.clear();
 ui = Ui::Menu; handleKey('5'); digita("3"); handleKey('#');
 assert(ui == Ui::ConfirmUnlink && pendingId == 3);
 handleKey('*');
 assert(ui == Ui::Access && noticeLine1 == "Cancelado" && audits.empty() && CardStore::read(EEPROM, 3, lido));
 // 'D' também cancela
 noticeDuration = 0; ui = Ui::Menu; handleKey('5'); digita("3"); handleKey('#');
 assert(ui == Ui::ConfirmUnlink); handleKey('D');
 assert(ui == Ui::Access && noticeLine1 == "Cancelado" && audits.empty() && CardStore::read(EEPROM, 3, lido));
 // timeout de UI: sem tecla por UI_TIMEOUT_MS volta ao repouso sem apagar
 noticeDuration = 0; ui = Ui::Menu; handleKey('5'); digita("3"); handleKey('#');
 assert(ui == Ui::ConfirmUnlink);
 now += UI_TIMEOUT_MS - 1; uiTimeoutTick(); assert(ui == Ui::ConfirmUnlink);
 now += 1; uiTimeoutTick();
 assert(ui == Ui::Access && noticeLine1 == "Tempo esgotado" && audits.empty() && CardStore::read(EEPROM, 3, lido));
 // timeout também na tela do ID
 noticeDuration = 0; ui = Ui::Menu; handleKey('5'); assert(ui == Ui::UnlinkId);
 now += UI_TIMEOUT_MS; uiTimeoutTick(); assert(ui == Ui::Access);
 // o leitor de digital não é consultado nas telas do menu 5
 noticeDuration = 0; ui = Ui::UnlinkId; int antes = finger.scans; now += 1000; fingerprintTick();
 assert(finger.scans == antes);
 ui = Ui::ConfirmUnlink; now += 1000; fingerprintTick(); assert(finger.scans == antes);
 return 0;
}
'''


class TelasMenu5Tests(unittest.TestCase):
    def test_telas_de_digitacao_e_menu(self):
        _rodar(TELAS)

    def test_flash_ao_ler_cartao_e_capturar_digital(self):
        _rodar(FLASH)

    def test_menu_5_remove_cartao(self):
        _rodar(MENU5)

    def test_textos_novos_cabem_em_16_colunas(self):
        src = cartao._sketch()
        for texto in ('#Confirma *Limpa', 'ID: ', '5 Remove cartao', '4 Vincula cartao', 'Desvincular ID:',
                      'Remover cartao?', '#Sim *Nao', 'Cartao removido', 'Sem cartao', 'Cartao mantido'):
            self.assertIn('"%s"' % texto, src, texto)
            self.assertLessEqual(len(texto), 16, texto)
        self.assertLessEqual(len('ID: ') + 10, 16)
        self.assertNotIn('#confirma *limpa', src)
        corpo = src[src.index('void displayTick()'):src.index('// Lista circular')]
        self.assertEqual([t for t in re.findall(r'"([^"]*)"', corpo) if len(t) > 16 and not t.startswith('LCD')], [])


if __name__ == '__main__':
    unittest.main()
