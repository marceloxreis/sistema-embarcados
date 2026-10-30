# Handoff: controle de acesso ESP32 (estado em 30/10/2026, sessão 2)

Estado atual único. Substitui os handoffs anteriores. Use este arquivo como
ponto de partida; `docs/HANDOFF-REVISAO-OPUS.md` é histórico da revisão.

## 1. Objetivo e arquitetura

Controle de acesso com biometria, teclado, fechadura e auditoria:

- Arduino Mega 2560: máquina de estados, porta, buzzer, LCD, teclado, DY50
  (leitor de digital), EEPROM e fila de eventos.
- ESP32-CAM Ai-Thinker: tira uma foto por acesso autorizado e envia ao servidor.
  Conversa com o Mega por UART (conversor de nível).
- Servidor Python + SQLite (`servidor/`): recebe eventos e fotos, guarda auditoria
  e cadastros, expõe o painel web (`servidor/static/`).

Requisitos fixos: `docs/ESCOPO.md`. Materiais fixos: `docs/MATERIAIS.md`.
A versão ESP32 DevKit foi removida em 30/10/2026; é recuperável pelo commit
`49218bd`.

## 2. Regras do dono

- `LOCK_MODE=0` até o ensaio da fechadura (`docs/MONTAGEM.md`, seção 6).
- Não gravar placas, não fazer commit nem push sem coordenar com o dono.
- Marcar toda evidência como: verificado em host, compilado ou não verificado.
- Nada foi testado em hardware. Simulação não é confirmação física.
- O agente principal só orquestra: implementadores Haiku, revisores Sonnet,
  um agente distinto por tarefa; arquivos disjuntos podem rodar em paralelo.
- Uma pergunta por vez. Sem emojis (exceto marcas de certo/errado).
- Métricas de contexto só reais (hook, status line, `/context`). Nunca estimar.
- Nunca abrir `firmware/*/Config.h` (pode ter segredos); usar `Config.example.h`.
- Ao delegar, passar o modelo explicitamente (Haiku implementa, Sonnet revisa).

## 3. Estado Git

- Branch `main` em `2c9aa85` ("Atualiza handoff com pendencias abertas e
  simulacoes nao feitas"), igual a `origin/main` (verificado em host,
  `git status -sb`, 30/10/2026). O commit `6b09569` (arquitetura Mega + CAM)
  está no histórico da `main`.
- Mudanças da sessão 2 **não commitadas**. Nada foi commitado; o commit só
  acontece quando o dono pedir:
  - modificados: `firmware/MegaControlador/MegaControlador.ino`,
    `servidor/static/app.js`, `servidor/static/index.html`,
    `servidor/static/style.css`, `tests/test_mega_logic.py`,
    `tests/test_reinicio_perifericos_agent.py`, `docs/HANDOFF.md`,
    `docs/MONTAGEM.md`, `docs/TESTES.md`, `docs/VALIDACAO.md`;
  - novos (não rastreados): `tests/test_lcd_textos.py` e
    `tests/test_mega_tst02.py`. Precisam entrar no commit.
- A cópia de trabalho atual fica na Área de Trabalho do dono
  (`controle-acesso-esp32`). Existe uma cópia antiga em outra pasta do dono que
  não deve mais ser usada.
- `Config.h` locais (Mega e CAM) são ignorados pelo Git e ainda têm valores de
  exemplo. Não versionar.
- Antes de commitar: stage por arquivo, nunca por diretório. Confirme que
  `Config.h`, `*.sqlite3` e `__pycache__` não entram no commit.
- Commits sem linha `Co-Authored-By`.

## 4. O que foi feito em 30/10/2026

Auditoria completa com 10 frentes. Cada correção foi implementada e revisada.

**Mega**
- Fila não trava com ID maior que 100; evento não codificável é descartado.
- `storage_error` chega ao servidor mesmo com cadastros corrompidos.
- DY50 e LCD se recuperam sozinhos. LCD usa sonda I2C e não bloqueia (sonda de
  barramento no boot e na recuperação: MEGA-10, sessão 2).
- Linha `BOOT` e campo `dy50=` no `STATUS`.
- UART da CAM é atendida durante hash, EEPROM e LCD, com proteção contra
  reentrância e buffer `linkStash` de 128 B durante reset web.
- Senha parcial expira em 30 s.

**CAM**
- Buffer de RX de 1024 B.
- Logs de boot, câmera e Wi-Fi.
- Espera de 2 s entre reenvios de item rejeitado permanentemente. O descarte
  após 5 rejeições em 30 s ou mais foi mantido.
- Resultado de reset com HTTP 400 ou 404 não trava mais.
- Contador `photoMisses` removido.

**Servidor**
- Reset pendente expira em 24 h. Se o Mega confirmar depois, vira `applied`.
- JSON aninhado responde 400. Arquivo estático ausente responde 404.

**Painel**
- HTTP 401 e 429 voltam ao login sem loop de bloqueio.
- Mensagens em português, foco preservado, foto visível.
- Sessão anterior ignorada; rótulo "Pendente no Mega".

**Testes**
- Porta e buzzer testados no código do Mega.
- `test_door` incluído na suíte.
- Suíte (sessão 1): de ~54 s para ~28 s.

**Documentação**
- `MONTAGEM.md`: fio a fio, roteiro de bancada de 7 passos, ensaio seguro da
  fechadura.
- `TESTES.md`: ensaios funcionais de bancada.
- `README`, `ESCOPO`, `PLANO`, `VALIDACAO`, `MATERIAIS`
  atualizados. Versão DevKit removida.

### O que foi feito nesta sessão (sessão 2, 30/10/2026)

Itens fechados. Cada um foi implementado pelo Haiku e revisado e aprovado pelo
Sonnet. Níveis de evidência e números estão em docs/VALIDACAO.md.

**Mega**
- MEGA-07 (fechado): todos os textos do LCD com até 16 colunas.
  `failEnrollment(codigoAuditoria, textoLcd)` separa o código de auditoria
  (inalterado, casado com a CAM) do texto do LCD. Mapeamento antigo -> novo em
  docs/VALIDACAO.md. Teste: `tests/test_lcd_textos.py`.
- REQ-E4 (fechado): com armazenamento indisponível ou registro corrompido na
  leitura, digital e senha mostram "Falha memoria" / "Acesso negado" e auditam
  `access_denied` com motivo "Erro na memoria". `confirmEnrollment` com falha de
  memória avisa; `resetPassword` com registro corrompido responde
  `storage_error`. Testes em `tests/test_mega_logic.py`, e para registro
  corrompido (B7) em `tests/test_mega_tst02.py` (classe `RegistroCorrompidoTests`).
- Correção B7 (REQ-E4): `authorize` lê o registro uma vez; corrupção detectada na
  leitura vira "Falha memoria" / "Erro na memoria"; `resetPassword` com registro
  corrompido responde `storage_error`. Confirmado por análise de código. Os 2
  testes de regressão falham no código anterior ao B7 e passam no atual
  (verificado em host pelo revisor); nenhum assert foi enfraquecido; build
  conferido nos logs (42496 B / 4581 B / 19 avisos). Revisão Sonnet independente:
  APROVADO (o parecer não foi salvo em arquivo). Observação baixa: não há teste
  para um segundo reset com `storageReady` já falso.
- MEGA-03 (fechado): digital órfã (slot do DY50 sem registro na EEPROM, IDs 1 a
  100, armazenamento OK) é apagada no primeiro dedo do cadastro, com aviso
  "Slot orfao limpo" / "Recoloque o dedo" e nova busca após recolocar o dedo.
  Falha no apagamento ou ID fora da faixa mantém "Slot DY orfao". A limpeza não
  é auditada. Testes em `tests/test_mega_logic.py`.
- MEGA-04 (fechado): até 3 falhas consecutivas transitórias de `getImage` são
  toleradas no cadastro; a 4ª aborta. `PACKETRECIEVEERR` aborta na primeira.
  Acesso não muda. Testes em `tests/test_mega_logic.py`.
- MEGA-10 (novo, achado nesta sessão): o boot só sondava timeout I2C e reportava
  `lcd=ok` sem LCD. Agora sonda o barramento (`endTransmission()==0`) antes de
  `lcd.init` (`lcdPresent` / `lcdBoot`). LCD ausente: `lcdReady=false`, e a
  recuperação a cada 30 s funciona. Testes de host em
  `tests/test_reinicio_perifericos_agent.py` (`test_boot_lcd_ausente_nao_e_inicializado`,
  `test_boot_lcd_presente_inicializa`, `test_boot_com_timeout_fica_sem_lcd`),
  que compilam `lcdPresent`/`lcdBoot` reais do `.ino`. Boot simulado no simavr.
  LCD real: não verificado.
- TST-02 (fechado): `tests/test_mega_tst02.py` (9 testes sobre o código real do
  `.ino`: 7 de TST-02 e 2 de regressão de REQ-E4/B7 para registro corrompido):
  debounce de 50 ms, cores do LED RGB, LCD com ID, teclas D, `*` e `#`,
  `pin_in_use` e sequências reais `doorTick` + `outputsTick`. Com
  `CONTROLE_MEGA_B6=<pasta>`, os testes rodam contra outra cópia do firmware
  (teste de mutação); 4 mutantes detectados pelo implementador; 2 reexecutados
  pelo revisor.

**Painel (`servidor/static`)**
- Foco preservado ao redesenhar a tabela e ao fechar a foto; resultado do reset
  em `#reset-status`, junto ao formulário (some em 15 s ou ao digitar); "PIN
  incorreto." no login, com campo limpo; `aria-label` distinto em "Ver foto".
  Testado no Chrome local: 390 px após as correções (C, C2); 1280 px só na
  verificação inicial A1, antes das correções. Teclado físico e leitor de tela:
  não verificados (foco testado com `.focus()`/`.click()` por script). Verificado
  em host, navegador local.

**Build e testes**
- Suíte: 145 testes OK (sessão 1: 126).
- Build do Mega com o método novo (seção 6): 42496 B de flash, 4581 B de SRAM,
  19 avisos (1 do projeto, pré-existente; 18 do core e das bibliotecas). Não é
  comparável com os 38996 B / 4510 B da sessão 1.
- Correção: um script usado no início da sessão compilou com `-w` (avisos
  suprimidos). Relatos de "sem avisos" daquele script não valem.
- CAM não alterada nem recompilada nesta sessão.

## 5. Verificação (30/10/2026)

| Verificação | Resultado | Evidência |
|---|---|---|
| Suíte Python: `CONTROLE_TEST_LIBS=<pasta das libs de teste> CONTROLE_TEST_STRICT=1 python3 -m unittest discover -s tests -q` | 145 testes OK, 0 skipped, 28 a 39 s conforme a carga (38,4 s no fim da sessão 2; 28,3 s na reexecução da revisão R1; sessão 1: 126 testes, 25,5 s; ~28 s em outra execução) | verificado em host (reexecutado no fim da sessão 2) |
| Mega `arduino:avr:mega`, método da sessão 2 (avr-gcc 14.2, `-Wall -Wextra`) | 42496 B de flash, 4581 B de SRAM global, 19 avisos (1 do projeto, pré-existente) | compilado, container Linux local |
| Mega `arduino:avr:mega`, sessão 1 (histórico) | 38996 B de flash, 4510 B de SRAM global | compilado; não comparável com a linha acima |
| CAM `esp32:esp32:esp32cam` | 1055069 B de flash, 60608 B de RAM global (sessão 1; não recompilada na sessão 2) | compilado |
| `node --check` do painel | OK | verificado em host |
| Painel no Chrome local | 390 px após as correções; 1280 px só na verificação inicial A1, antes das correções. Teclado físico e leitor de tela não verificados | verificado em host (navegador local) |
| simavr do Mega (boot, hash, senha, EEPROM) | Tempos e boot sem LCD em VALIDACAO.md | simulado |
| Ensaio físico | nenhum | não verificado |

Os mesmos números estão registrados em docs/VALIDACAO.md.

## 6. Ferramentas

- Arduino CLI e cores ESP32/AVR ficam em uma pasta de trabalho externa
  (`work/`, fora do repositório).
- ctags ARM64 configurado via `runtime.tools.ctags.path`.
- Mega compilado em container Linux local, imagem `controle-acesso-avr-probe:local`.
- Método de build do Mega usado na sessão 2 (passos essenciais):
  1. copiar o sketch `firmware/MegaControlador` para uma pasta temporária, sem
     `Config.h`;
  2. na cópia, copiar `Config.example.h` como `Config.h` (o `Config.h` local
     nunca foi lido);
  3. compilar com `avr-gcc` 14.2 da imagem `controle-acesso-avr-probe:local`,
     core `arduino:avr` 1.8.6 de `~/Library/Arduino15` e as bibliotecas da
     pasta de trabalho externa (`work/arduino-user/libraries`), montadas somente
     leitura, com `-Wall -Wextra`;
  4. ler os avisos (não suprimir com `-w`).
  Flags reais (lista completa do script de build da sessão 2, `build_in_docker.sh`,
  que usa `-w`; a variante de avisos troca `-w` por `-Wall -Wextra`):
  `-mmcu=atmega2560 -DF_CPU=16000000L -DARDUINO=10819 -DARDUINO_AVR_MEGA2560 -DARDUINO_ARCH_AVR -Os -g -ffunction-sections -fdata-sections -flto -fno-fat-lto-objects -Wall -Wextra`.
  C++ com `-std=gnu++11 -fpermissive -fno-exceptions -fno-threadsafe-statics`.
  Compila todo `cores/arduino`, Wire, EEPROM, Keypad, LiquidCrystal_I2C,
  Adafruit_Fingerprint, Crypto (SHA256, Hash, Crypto) e SoftwareSerial. Link com
  `-Os -flto -Wl,--gc-sections -lm`. Tamanho por `avr-size` (flash = .text + .data;
  SRAM = .data + .bss). Não é o arduino-cli.
  Scripts atuais (pasta temporária, não versionada):
  `/private/tmp/claude-501/-Users-marceloreis/f04675c4-326a-41f8-a313-d6d37b520e19/scratchpad/a2-simavr/scripts/`
  (`build_in_docker.sh`, `make_instr.py`, `gen_eeprom.py`, `make_elf_eep.sh`,
  `run_sims.sh`, `parse_out.py`) e `.../scratchpad/b7/` (`build.log`). Recomenda-se,
  com autorização do dono, versionar esses scripts em `scripts/`.
- Core AVR 1.8.8 (usado como referência na sessão 1): há diretórios 1.8.8 em
  `~/Documents/Codex/2026-10-22/dc/work/` (`linux-data` e `arduino-data`). O Mac
  só tem o 1.8.6 em `~/Library/Arduino15`. Não se confirmou nesta sessão qual
  core foi usado na compilação da sessão 1.
- `CONTROLE_MEGA_B6=<pasta>` faz `tests/test_mega_tst02.py` rodar contra outra
  cópia do firmware (teste de mutação). Sem a variável, usa o firmware do
  repositório.
- Bibliotecas de teste: `scripts/bootstrap-test-libs.py`. Se
  `/tmp/controle-test-libs-20261029` sumir, regenere com esse script.
- Os testes C++ recortam trechos do `.ino` por marcadores de texto. Se mudar
  assinatura ou marcador, confira `tests/` antes.

## 7. Pendências abertas (priorizadas)

Fechadas na sessão 2 (ver seção 4): MEGA-03, MEGA-04, REQ-E4, TST-02 e MEGA-07.

P2:
- CAM-03: falha da câmera não chega ao servidor; acrescentar campo
  `camera_ready` ao heartbeat (CAM + `server.py` + painel).
- SRV-02: banco sem índice em `events(received_at)` e sem política de retenção.
- Verificação de senha bloqueia o Mega ~1,17 s com 100 cadastros (simulado,
  simavr): LCD, teclado e DY50 param nesse intervalo. Decidir se vale a pena
  uma verificação incremental. Margem da UART da CAM durante o hash: ~20 B no
  buffer de 64 B a 38400 baud, por análise de código; não medida.

P3:
- `lcd=timeout` também aparece com LCD ausente. É texto livre: só
  `docs/TESTES.md` e `docs/MONTAGEM.md` citam; nenhum teste, servidor ou CAM lê.
- Painel sem rótulo para os motivos 8 a 16 de `reasonNames` (ex.: "Erro na
  memoria", "Erro de hash"); aparecem crus.
- Painel: resposta de reset em voo após logout pode mostrar mensagem antiga por
  até 15 s depois de novo login.
- Inativar/Reativar com registro corrompido mostra "ID inexistente". No primeiro
  dedo do cadastro, registro corrompido mostra "Slot DY orfao" (não apaga). LIST
  USB omite o ID (`exists()` falso).
- `resetPassword` com `storageReady` já falso e registro corrompido responde
  `unknown_user`.
- Nomes: o menu diz "Inativ." e as telas dizem "Desativar".
- Faltam testes: caso mudo de porta aberta durante busca de senha no cadastro;
  `FirstFinger` com `storageReady` falso.
- A2: respostas ao desafio de foto (janela de 5 s) podem expirar durante um reset
  web de ~1,2 s (linkStash não processado até o fim).
- A2: LCD ausente: `displayTick` continua escrevendo no vazio (CPU), sem impacto
  de segurança.
- B2: em `confirmEnrollment`, com a porta ocupada (+1) a UI fica em ConfirmPin
  com entry cheia até D/timeout; ramo mudo sem teste.
- B3: se `deleteModel` falha, o slot continua órfão e o recadastro falha de novo.
- B4: `enrollReadFails` não zera em pausa por porta não-Idle sem ForcedOpen (info).
- A1: o limite 429 é por origem e bloqueia também o administrador legítimo por até
  60 s (decisão de projeto).
- Ensaios de bancada dos comportamentos novos (órfão limpo, falha de memória,
  tolerância de getImage) estão em `docs/TESTES.md` marcados como não executados.
- `tests/test_mega_tst02.py` fixa o SDK `/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk`
  (só funciona em macOS com esse SDK).
- MEGA-08: tecla D ignorada por 2 s durante aviso. MEGA-09: senha com sistema
  ocupado não mostra mensagem. Porta forçada ao fechar mostra "ID 000".
- Reset web dentro do enlace com tráfego intenso pode exceder o `linkStash`
  (128 B) somado ao buffer de 64 B. O CRC rejeita e há retransmissão.
- CAM: `holdRetry` não zera na queda de Wi-Fi (até 2 s); HTTP 404 descarta o
  resultado de reset; `cam_boot_id` gerado por `esp_random` antes do Wi-Fi
  (entropia); falta teste de reenvio imediato após erro transitório que segue
  de rejeição permanente.
- Tabelas de nomes de eventos e motivos triplicadas (Mega, CAM, servidor).
- Otimizações: Mega com `F()`/PROGMEM nos textos e `SerialFrame::kMaxBody` de
  192 para 32 (~1,5–2 KB de SRAM; hoje 4581 B = 56%, medido na sessão 2 com o
  método novo); fundir ~37 arquivos de teste em ~10.
- Fora do modelo de ameaça (uso honesto): UART não autenticada, HTTP sem TLS,
  salt previsível.
- Aceito: fila em RAM perde itens em reboot.

## 8. Simulações

Feito na sessão 2 (simulado ou verificado em host; nada disso é confirmação
física). Números em docs/VALIDACAO.md.

- simavr com o firmware do Mega (imagem `controle-acesso-avr-sim:local`, cópia
  instrumentada): boot, hash, verificação de senha com 100 registros e boot sem
  LCD (`lcd=timeout`). Não cobre tempo de escrita da EEPROM nem a UART da CAM.
- Painel em navegador (Chrome: 390 px após as correções; 1280 px só na verificação inicial A1, antes das correções): foco, resultado de reset e
  "PIN incorreto.". Fluxo de foto também testado no navegador: evento
  `access_granted` com foto enviada por script pela API do dispositivo; o painel
  mostra o evento e a foto visível (320x240), na verificação A1 e reconfirmado
  na revisão das mudanças do painel (verificado em host, navegador local).

Pendente:
- Wokwi (Mega + ESP32 por UART, LCD I2C, teclado, LEDs, buzzer, botões; sem
  câmera e sem DY50): teste integrado mais próximo do real. Requer conta e
  token do Wokwi CLI (serviço externo; pedir autorização ao dono).
- simavr: tempo real de escrita na EEPROM (o simavr não modela; o valor de 9 ms
  do `saveRecord` é artefato, e o tempo real estimado é ~160 ms, estimativa:
  ~48 gravações por `saveRecord`, com ~3,3 ms por byte, valor de datasheet
  lembrado pelo revisor e não conferido nesta sessão) e
  estouro da UART da CAM durante o hash (não medido; a imagem não tem os headers
  do libsimavr, que também são necessários para injetar bytes na UART).
- Pico de pilha e heap do Mega: `-fstack-usage` e análise de `String`.
- Painel: fluxo de foto com a CAM real (o fluxo pela API já foi testado no
  navegador; depende da bancada).
- Tudo de hardware continua pendente (bancada).

## 9. Próximo passo exato

Ordem sugerida antes da bancada:
1. O dono decide o commit desta sessão (stage por arquivo; incluir
   `tests/test_lcd_textos.py` e `tests/test_mega_tst02.py`).
2. CAM-03 e SRV-02.
3. P2 de verificação de senha: decidir se faz verificação incremental.
4. Wokwi, se o dono autorizar.

Depois, a bancada conforme o roteiro existente:
1. Configuração local, sem versionar:
   - `ADMIN_PIN` (10 dígitos) em `firmware/MegaControlador/Config.h`, arquivo
     ignorado pelo Git.
   - `ADMIN_PIN` e `DEVICE_KEY` (16+ caracteres) no ambiente do servidor.
   - Wi-Fi, URL e chave em `firmware/Esp32CamRede/Config.h`.
2. Na bancada, com `LOCK_MODE=0` e fechadura desconectada: seguir
   `docs/MONTAGEM.md` seção 1 (segurança) e seção 5, passos 1 a 7.
3. Depois: `docs/TESTES.md`, "Ensaios funcionais de bancada".
4. Só então o ensaio da fechadura (`docs/MONTAGEM.md` seção 6).

Nada disso foi executado. A bancada depende do dono e do hardware.
