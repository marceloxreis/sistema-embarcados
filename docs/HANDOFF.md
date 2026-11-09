# Handoff: controle de acesso ESP32 (estado em 06/11/2026; sessão 9 em 06/11/2026: teclado novo, RC522, ID+senha, gravação do Mega pela CAM, diodo da fechadura e correções após o pulso; sessão 8 em 06/11/2026: rede da casa, IP fixo e primeira OTA; sessão 7 em 05/11/2026: rede nova e diagramas; sessão 6 em 04/11/2026; sessão 5 em 03/11/2026; sessões 4 e continuação em 02/11/2026, bancada; continuação da tarde de 03/11/2026 na seção 4)

Estado atual único. Substitui os handoffs anteriores. Use este arquivo como
ponto de partida; `docs/HANDOFF-REVISAO-OPUS.md` é histórico da revisão.

Retomada: no Claude Code, use `/sistema-embarcado` (skill do dono em `~/.claude/skills/sistema-embarcado/`), que lê este arquivo e conduz a bancada passo a passo.

## 1. Objetivo e arquitetura

Controle de acesso com biometria, teclado, fechadura e auditoria:

- Arduino Mega 2560: máquina de estados, porta, buzzer, LCD, teclado, DY50
  (leitor de digital), EEPROM e fila de eventos.
- ESP32-CAM Ai-Thinker: tira uma foto por acesso autorizado e envia ao servidor.
  Conversa com o Mega por UART (divisor de tensão).
- Servidor Python + SQLite (`servidor/`): recebe eventos e fotos, guarda auditoria
  e cadastros, expõe o painel web (`servidor/static/`).

Requisitos fixos: `docs/ESCOPO.md`. Materiais fixos: `docs/MATERIAIS.md`.
A versão ESP32 DevKit foi removida em 30/10/2026; é recuperável pelo commit
`49218bd`.

## 2. Regras do dono

- `LOCK_MODE=0` até o ensaio da fechadura (`docs/MONTAGEM.md`, seção 6).
- Não gravar placas, não fazer commit nem push sem coordenar com o dono.
- Marcar toda evidência como: verificado em host, verificado em hardware, compilado, simulado, análise de código, estimativa ou não verificado.
- Em hardware, foram verificados em 30/10/2026 (noite) o passo 3 da bancada (Mega pelo USB, sem LCD) e a matriz do teclado 4x4 por continuidade. A leitura do teclado pelo Mega não foi verificada em 30/10/2026; foi verificada em 02/11/2026 (sessão 4, seção 4). Em 02/11/2026 também foram verificados o buzzer ativo, o circuito do buzzer com BC546 (acionamento pelo firmware verificado depois, na continuação de 02/11/2026) e os resistores medidos. Na mesma continuação: DY50 comunicando (dy50=ok), cadastro, acesso pela digital e pela senha e buzzer pelo firmware, verificados em hardware. Simulação não é confirmação física.
- O agente principal só orquestra: implementadores Haiku, revisores Sonnet,
  um agente distinto por tarefa; arquivos disjuntos podem rodar em paralelo.
- Uma pergunta por vez. Sem emojis (exceto marcas de certo/errado).
- Métricas de contexto só reais (hook, status line, `/context`). Nunca estimar.
- Nunca abrir `firmware/*/Config.h` (pode ter segredos); usar `Config.example.h`.
- Ao delegar, passar o modelo explicitamente (Haiku implementa, Sonnet revisa).

## 3. Estado Git

- Branch `main`, igual a `origin/main` em 30/10/2026; confira o commit atual com
  `git log -1 --oneline`. Commits da sessão 2: `60ddda6` (pendências P2 do Mega,
  painel e docs), `cd2f02f` (handoff), `bf00a96` (simulação Wokwi; CAM-03 e SRV-02
  descartados), `74c79a4` (cenários Wokwi do teclado). O commit anterior `2c9aa85`
  fica como
  histórico, e o commit `6b09569` (arquitetura Mega + CAM) continua no histórico
  da `main`.
- Os testes `tests/test_lcd_textos.py` e `tests/test_mega_tst02.py` já estão
  versionados.
- A cópia de trabalho atual fica na Área de Trabalho do dono
  (`controle-acesso-esp32`). Existe uma cópia antiga em outra pasta do dono que
  não deve mais ser usada.
- `Config.h` locais (Mega e CAM) são ignorados pelo Git e ainda têm valores de
  exemplo, exceto o `ADMIN_PIN` do Mega, definido pelo dono em 30/10/2026. Não versionar.
- Antes de commitar: stage por arquivo, nunca por diretório. Confirme que
  `Config.h`, `*.sqlite3` e `__pycache__` não entram no commit.
- Commits sem linha `Co-Authored-By`.
- 03/11/2026: as mudanças da sessão 5 (LCD em 4 bits, SHOW_TYPED_DIGITS, bipe da porta forçada, testes, Wokwi e docs) foram commitadas em `e6a9263` e enviadas para origin/main a pedido do dono.
- 03/11/2026 (tarde): alterados `firmware/Esp32CamRede/Esp32CamRede.ino` (`WiFi.setSleep(false);` logo após `WiFi.mode(WIFI_STA)` em networkTask()) e `tests/test_camera_network.py` (`setSleep` no mock), commitado no commit da tarde de 03/11 (ver git log).
- 04/11/2026 (sessão 6): alterados `firmware/MegaControlador/MegaControlador.ino`, `firmware/Esp32CamRede/Esp32CamRede.ino`, `firmware/Esp32CamRede/Config.example.h`, `servidor/server.py`, testes (`tests/test_server.py`, `tests/test_camera_network.py`, `tests/test_cam_ota.py` novo) e docs (`HANDOFF.md`, `VALIDACAO.md`, `TESTES.md`, `MONTAGEM.md`). Commit desta sessão: ver git log (feito pelo orquestrador, a pedido do dono).
- 06/11/2026 (sessão 9): commits `160534d` (RC522 como terceiro método de acesso, login por ID + senha e bloqueio do teclado) e `9d3bed2` (gravação do Mega pela ESP32-CAM, STK500v2 pela rede, com `scripts/gravar-mega-pela-cam.py`). Textos novos do LCD e piscada azul do LED em 10 s: mudança em andamento em `firmware/MegaControlador/MegaControlador.ino` por outro agente, não commitada quando este registro foi escrito (git status: `.ino` do Mega e testes `test_login_id_senha.py`, `test_mega_display.py` e `test_mega_tst02.py` modificados pelo outro agente). Docs da sessão 9 (`HANDOFF.md`, `VALIDACAO.md`) não commitados. (Superado na noite de 06/11: ver item seguinte.) O zip `handoff-bancada-2026-11-06` (bancada do amigo do dono) não é versionado.
- 06/11/2026 (sessão 9, noite): `bf608b8` (textos do LCD, LED de repouso a cada 10 s e handoff), `99fcc71` (reinício do RC522 e do DY50 após o pulso da fechadura; debounce de 200 ms nos sensores de porta) e `b50bd0b` (telas do ID, mapa de cores do LED, menu 5 e evento `card_unlinked`). Gravados no Mega: até `bf608b8`. `99fcc71` e `b50bd0b` NÃO gravados no Mega nem na CAM. Docs do fim da sessão 9 em commit próprio (ver git log).

## 4. O que foi feito em 30/10/2026

Linhas de STATUS/BOOT anteriores a 03/11/2026 trazem o campo `lcd=`, removido do firmware em 03/11.

Auditoria completa com 10 frentes. Cada correção foi implementada e revisada.

**Mega**
- Fila não trava com ID maior que 100; evento não codificável é descartado.
- `storage_error` chega ao servidor mesmo com cadastros corrompidos.
- DY50 e LCD se recuperam sozinhos. LCD usa sonda I2C e não bloqueia (sonda de
  barramento no boot e na recuperação: MEGA-10, sessão 2) (obsoleto desde 03/11/2026: LCD em 4 bits, sem I2C e sem o campo `lcd=`; ver seção 4, sessão 5).
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
  LCD real: não verificado. (obsoleto desde 03/11/2026: LCD em 4 bits, sem I2C e sem o campo `lcd=`; ver seção 4, sessão 5)
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

### Sessão 3 (30/10/2026, noite): primeira bancada

Passo 3 de `docs/MONTAGEM.md` (Mega sozinho pelo USB). Níveis em docs/VALIDACAO.md.

- Placa: Arduino Mega 2560 clone com CH340 (`/dev/cu.usbserial-1130`), alimentada só pelo USB do Mac. D30 e D31 ao GND (porta fechada simulada). LCD, teclado, DY50, LED, buzzer, CAM e fechadura desconectados; `LOCK_MODE=0`.
- Gravação pelo dono: Arduino IDE 2.3.10, placa "Arduino Mega or Mega 2560", pacote Arduino AVR Boards; Adafruit Fingerprint 2.1.4, Crypto 0.4.0, Keypad 3.1.1, LiquidCrystal I2C 1.1.2. Upload OK. `ADMIN_PIN` definido no `Config.h` local (não versionado).
- Boot: `BOOT boot=2 storage=ok lcd=timeout dy50=indisponivel lock_mode=0` (provável: um boot após a gravação e outro ao abrir a porta).
- AUTH pelo Serial Monitor: `OK authenticated` (havia bytes de lixo do reinício, sem significado).
- STATUS: `last_id=0 queued=1 dropped=0 replies_dropped=0 lcd=timeout dy50=indisponivel lock_mode=0`. queued=1, esperado pelo docs/MONTAGEM.md passo 3 (device_boot aguardando a CAM).
- Tensões (alicate BOMVINK, 600 V DC, resolução 1 V): D16 "004" (~4 V, medição grosseira); D35 = 0 V.
- LCD não testado: o display é um 1602A sem módulo I2C PCF8574. `lcd=timeout` com LCD ausente foi confirmado em hardware. Decisão do dono: comprar o módulo; se o chip for PCF8574A, o endereço costuma ser 0x3F; ajustar `LCD_ADDRESS` no `Config.h` local. Repetir o passo 3 só para o LCD.
- O adaptador de gravação da ESP32-CAM ainda não foi comprado: os passos 1 e 2 do roteiro (CAM) seguem bloqueados.
- Teclado 4x4 (`docs/MONTAGEM.md` 3.4): teclas rígidas, placa verde, só os 8 furos do meio são contatos (sem pinos soldados). Matriz confirmada por continuidade: furos 1 a 4 = C1 a C4; furos 5 a 8 = R1 a R4 (teclado de frente, furos embaixo, da esquerda para a direita). Teclas testadas: 1, 2, 3, A, 4, 7, * e D.
- Ligação provisória (jumpers macho presos com isopor, sem solda): contato ruim e instável. Teste com o firmware: `STATUS` com `queued=1`; `123456#` e `111111#` não mudaram o queued (continuou 1). Jumper encostado à mão entre D22-D26 (tecla 1) e D25-D28 (#), sem o teclado, também não funcionou. Hipótese (análise de código, não verificada): contato trepidando ou jumper encostado gera vários dígitos; `handleKey` só avalia senha com 6 dígitos (10 no admin), então a entrada vira "Entrada invalida" sem evento nem LCD. Ainda não se sabe se o Mega lê as teclas. (Resolvido em 02/11/2026, ver a subseção da sessão 4: a causa era o contato provisório.)
- Decisão do dono (31/10/2026): manter este teclado; a dupla solda a barra de 8 pinos. Teclado de membrana descartado. Feito em 02/11/2026 (sessão 4).
- LED RGB (`docs/MONTAGEM.md` 3.7): ainda não ligado (em 02/11/2026 o módulo estava ausente; ver sessão 4). Módulo com pinos `R G B GND` (cátodo comum, como `RGB_COMMON_ANODE = false` no `Config.example.h`; conferir no `Config.h` local). Pendente antes de energizar: verificar se o módulo tem resistores na placa; se não tiver, um resistor por canal, valor pela ficha. Pinos: R -> D32, G -> D33, B -> D34, GND -> GND.

### Sessão 4 (02/11/2026): teclado, buzzer e DY50

Bancada com a dupla. O dono executou tudo na placa; o agente orientou. Níveis em docs/VALIDACAO.md.

**Teclado 4x4 (verificado em hardware)**
- Barra de 8 pinos soldada nos furos do meio. Continuidade com alicate BOMVINK: nenhum par de pinos vizinhos conduz sem tecla; tecla 1 conduz pinos 1 a 5; tecla # conduz pinos 3 a 8.
- Ligação: pino 1 = C1 = D26 (laranja); pino 2 = C2 = D27 (amarelo); pino 3 = C3 = D28 (azul); pino 4 = C4 = D29 (roxo); pino 5 = R1 = D22 (cinza); pino 6 = R2 = D23 (branco); pino 7 = R3 = D24 (verde); pino 8 = R4 = D25 (laranja 2). D30 e D31 continuam ao GND.
- Porta serial: `/dev/cu.usbserial-130` (antes `-1130`). Boot: `BOOT boot=13 storage=ok lcd=timeout dy50=indisponivel lock_mode=0`. AUTH feito pelo dono no Serial Monitor; tentativas com PIN errado responderam `ERR auth`, e depois veio `OK authenticated`.
- Sequência: boot queued=1 (device_boot); `123456#` leva a queued=2; `111111#` a queued=3; `789000#` a queued=4 (`STATUS`: `last_id=0 queued=4 dropped=0 replies_dropped=0 lcd=timeout dy50=indisponivel lock_mode=0`). Cada senha errada de 6 dígitos gerou um access_denied na fila. Teclas 0 a 9 e # exercitadas: as senhas cobrem as linhas R1 a R4 e as colunas C1 a C3. A coluna C4 foi verificada depois, com a tecla D (ver abaixo). As teclas A, B, C e * foram exercitadas no diagnóstico de 02/11 (ver abaixo); no modo normal do firmware do projeto, A, B e C não têm efeito observável e * limpa a entrada.
- Resolve a pendência da sessão 3: a causa era o contato provisório. O sketch de diagnóstico previsto na sessão 3 não foi necessário para isso; ele foi gravado depois, em 02/11, para conferir as 16 teclas (ver abaixo).
- Coluna C4 (pino 4, D29, jumper roxo), verificada em 02/11/2026:
  - Primeiro teste `111` + `D` + `123456#` falhou. Os jumpers verdes D30/D31 tinham sido retirados; o Mega viu porta aberta (boot com queued=2: device_boot e forced_open), a porta ficou em Alarme, e a tecla D só limpa a entrada com a porta em repouso (análise de código, `handleKey`). Ao recolocar os verdes, queued subiu para 1 (provável evento de porta fechada; análise de código).
  - Com boot limpo (boot=23, porta fechada, queued=1), `111` + `D` + `123456#` não subiu o queued. O controle `123456#` sozinho subiu para 2 (teclado lido). Continuidade: D conduz pinos 4 a 8; A conduz pinos 4 a 5; o jumper roxo conduz de ponta a ponta e estava no D29. O jumper foi retirado e recolocado firme; após novo boot, `111` + `D` + `123456#` levou queued de 1 para 2: a tecla D foi lida. Causa provável da falha anterior: jumper roxo frouxo no conector do Mega (inferência).
  - Conclusão: as 4 linhas e as 4 colunas do teclado foram verificadas em hardware. A, B, C e * foram exercitadas no diagnóstico de 02/11 (abaixo).
  - Lição: os jumpers verdes D30/D31 ao GND precisam estar presentes em todos os testes de teclado; sem eles a porta é vista aberta.
- Diagnóstico das 16 teclas (02/11/2026, sketch DiagTeclado, fora do repositório e não versionado; mesmo mapa e pinos do projeto; biblioteca Keypad 3.1.1; imprime cada tecla na serial a 115200): as 16 teclas foram lidas com linha e coluna corretas (linhas R1 a R4 = D22 a D25; colunas C1 a C4 = D26 a D29). Teclado 4x4 completo verificado em hardware. A falha anterior da tecla D não era de código: porta vista aberta com os verdes D30/D31 retirados (previsto) e, provavelmente, jumper roxo frouxo (inferência). O MegaControlador foi regravado depois do diagnóstico: linha BOOT `BOOT boot=26 storage=ok lcd=timeout dy50=indisponivel lock_mode=0`; o contador foi de 23 para 26, o que indica (inferência pelo contador) que o diagnóstico não alterou a EEPROM.

**Buzzer (verificado em hardware, salvo onde indicado)**
- Módulo SainSmart de 3 pinos `S V G`: com V em 5 V e G em GND, silêncio; com S no 5 V, silêncio. Não apita com nível fixo. Provavelmente é buzzer passivo (inferência). Não serve com o firmware atual, que só faz HIGH/LOW no D36. Descartado.
- Buzzer solto de 2 pernas, fundo fechado com resina: ligado com + no 5 V e - no GND do Mega, apitou contínuo. É ativo.
- Transistor BC327-25 (marcação `C327-25`, lote `W 7n`): é PNP e não serve no circuito NPN da seção 3.8 (com PNP no lado alto a lógica inverte e o buzzer apitaria em repouso). Em uso: BC546 (NPN; pinagem C-B-E com a face escrita virada para quem olha e pernas para baixo).
- Resistores medidos com o alicate: tira de 4 unidades = 1 kΩ; tira do meio = 10 kΩ; tira de baixo (muitas) = 330 Ω.
- Montagem na protoboard: buzzer + na trilha 5 V; buzzer - no coletor; emissor no GND; base -> 10 kΩ -> GND; base -> 330 Ω (no lugar do 470 Ω; corrente no D36 de cerca de 13 mA) -> fio de teste. Antes de energizar: trilhas + e - sem continuidade.
- Testes: fio de teste no 5 V apita (verificado); fio de teste no D36 com o Mega em repouso fica em silêncio (verificado). Fio no GND isolado não foi testado separadamente (equivalente ao D36 em LOW). Acionamento do D36 em HIGH pelo firmware: não verificado nesta sessão; verificado depois, na continuação de 02/11/2026 (EntryExpired, 3 bipes).
- Análise de código (`DoorLogic.h` e `BuzzerLogic.h`, sem execução): o buzzer só toca em EntryExpired (3 bipes: acesso autorizado sem abrir a porta em 60 s) e em OpenTooLong (bipe a cada 2 s, só a partir do estado Open, isto é, após acesso autorizado e porta aberta por 5 min). ForcedOpen (tirar o jumper de D30/D31) não toca o buzzer; o BuzzerLogic até reseta nesse evento. (obsoleto desde 03/11/2026: ForcedOpen e boot com porta aberta bipam 250 ms / 250 ms; ver seção 4, 03/11) Logo, o teste do buzzer pelo firmware depende de um usuário cadastrado no DY50 (verificado depois, na continuação de 02/11/2026: EntryExpired, 3 bipes).
- O buzzer fica montado, com o fio de teste no D36.

**LED RGB (pendência de material)**
- O módulo não está com o dono (peça ausente). O firmware funciona sem ele. O passo 3 da seção 9 fica bloqueado por material.

**DY50 (adiado no fim da sessão 4; resolvido na continuação, abaixo)**
- Anúncio Eletrogate: alimentação de 3 a 6 V, corrente < 120 mA, pico < 140 mA, UART TTL 57600 padrão. Não informa nível lógico nem pinagem.
- A placa desta unidade tem 6 pinos rotulados `GND`, `RX`, `TX`, `3V3`, `T_OUT` e `T_3V3`. Pela marcação 3V3, alimentar com 3,3 V e não com 5 V. UART provavelmente em 3,3 V (inferência pela marcação; não medida).
- Cabo de 6 fios, todos vermelhos, com conector de passo ~1 mm (JST SH/1.25) que não encaixa em jumper. Decisão do dono (02/11/2026): cortar o conector da ponta solta, identificar cada fio por continuidade contra os rótulos da placa e soldar jumpers machos (GND preto; 3V3 em cor exclusiva, não vermelha, marcada "3V3"; TX e RX em cores distintas). T_OUT e T_3V3 isolados, sem uso.
- (superado; ver continuação) Ligação planejada: 3V3 em fonte de 3,3 V separada, com GND comum; GND no GND; TX do DY50 no D19 direto; D18 -> 1 kΩ -> RX do DY50; RX do DY50 -> dois 1 kΩ em série -> GND (divisor).
- Ponto em aberto: a especificação oficial do Mega 2560 cita 50 mA para o pino 3.3V; o DY50 pede menos de 120 mA (pico menos de 140 mA). Não usar o pino 3.3V do Mega para o DY50; usar fonte de 3,3 V separada com GND comum.
- (superado; ver continuação) Adiado (02/11/2026, fim da sessão): sem fonte de 3,3 V utilizável hoje. O dono achou a fonte de protoboard YwRobot MB102 (reguladores AMS1117 de 3,3 V e 5 V; jumper por lado 3.3 / OFF / 5V; entrada P4 6,5 a 12 V ou USB-A), mas não há como alimentá-la. Um módulo Hi-Link HLK-PM12 (entrada 100 a 240 V AC, saída 12 V 0,25 A) foi recusado por segurança: lado da tomada com fios e emendas expostos em caixa aberta, com risco de choque. Um módulo Bluetooth HC-05/ZS-040 e um módulo RTC com suporte de bateria de botão apareceram e não servem. O cabo do DY50 já está cortado e preparado com jumpers (mapa fio -> rótulo feito pelo dono; cores não informadas ao agente).
- (superado; ver continuação) Primeiro: alimentar só 3V3 e GND e medir o TX com o alicate. Esperado "002" ou "003" (o alicate lê cerca de 1 V abaixo). Parar se der "004" ou mais. Na continuação de 02/11/2026 este passo foi pulado: a medição do TX não foi executada.
- Decisão (02/11/2026): a ordem da MONTAGEM 3.9 (ligar o DY50 só depois do passo 7 da CAM) foi adiantada, porque a CAM aguarda bateria e step-down e a ligação do DY50 não depende da CAM.

### Sessão 4, continuação (02/11/2026): DY50, espelho do LCD, cadastro e acessos

Bancada com a dupla. Níveis em docs/VALIDACAO.md (registros de 02/11/2026).

**Alimentação e divisor do DY50 (verificado em hardware, salvo indicação)**
- Fonte: fonte de parede de 7 V (valor informado pelo dono; etiqueta não fotografada), com plugue P4 no DC-in da fonte de protoboard YwRobot MB102. Um adaptador 5 V 1 A (F05W-050100SPAE) também apareceu; não foi usado.
- Saída de 3,3 V medida fora da protoboard: "003" no alicate BOMVINK (medição grosseira).
- Ponta da protoboard: a MB102 só encaixa na ponta "0" (lado do Mega). Trilhas de baixo com jumper em 3.3 (metade esquerda = 3,3 V). Trilhas de cima (5 V e GND do Mega): o jumper ficou em 3.3 por engano (medido "003" na trilha de cima com a USB desconectada) e foi corrigido retirando o jumper amarelo desse lado (OFF). Antes de ligar a USB: trilha de cima "000", trilha de baixo "003".
- O GND da MB102 encosta na trilha azul de cima e faz o GND comum com o Mega. O Mega segue alimentado só pela USB. Nunca ligar o 5V do Mega na trilha de 3,3 V.
- Trilhas de cima cortadas no meio, perto da coluna 30; usar só a metade esquerda.
- Divisor montado (medido desligado): 1 kΩ em 18c-21c; 1 kΩ em 21b-24b; 1 kΩ em 24c-27c; jumper 27a à trilha azul de cima. Coluna 18 até GND = 3 kΩ; coluna 21 até GND = 2 kΩ; trilha vermelha de cima até azul de cima = 3 kΩ (caminho pelo Mega desligado; sem curto).
- Ligação: D18 na coluna 18e; RX do DY50 na 21e; TX do DY50 direto no D19; GND do DY50 na trilha azul de cima; 3V3 do DY50 na trilha vermelha de baixo. O cabo do DY50 foi emendado por um conector branco a fios coloridos e jumpers.
- Medição do TX do DY50 com o alicate: não registrada nesta continuação.

**Pinos 18 e 19 do clone**: a serigrafia diz "RX1 18" e "TX1 19" (trocada). Medido com o firmware rodando e pinos livres: pino 18 = "005" (TX em repouso alto); pino 19 = "000". Logo pino 18 = TX1 e pino 19 = RX1, como no ATmega2560. Seguir os números, não o texto.

**Resultado**: `BOOT boot=33 storage=ok lcd=timeout dy50=ok lock_mode=0`. DY50 comunicando com o Mega. A alimentação veio da MB102, não do pino 3.3V do Mega.

**Espelho do LCD na serial (código; verificado em host, compilado e visto em hardware)**
- Mudança em `firmware/MegaControlador/MegaControlador.ino` e em `Config.example.h` (ver a seção 6). Implementado por Haiku, revisado e aprovado por Sonnet. O dono regravou o Mega com essa versão.
- Suíte: 147 testes, 146 OK. Falha pré-existente, pendência separada: `tests/test_server.py::test_deeply_nested_json_reports_400` (espera "JSON inválido ou corpo muito grande.", recebe "Dispositivo inválido."). O orquestrador confirmou a mesma falha no commit HEAD a6ff44a, sem a mudança. `servidor/` não foi alterado.
- Compilação (arduino-cli do Arduino IDE, core arduino:avr do Mac, sobre `Config.example.h`): 39624 B de flash, 4549 B de RAM, zero avisos no .ino (21 avisos de core e bibliotecas). Método diferente do build da sessão 2; não comparável.
- Nota da revisão: o espelho sai sem exigir AUTH e mostra textos como "Acesso liberado | ID n" (a mesma informação do LCD); linhas `LCD|` podem se intercalar com respostas de comando.

**Cadastro e acessos (verificado em hardware)**
- Cadastro pelo teclado: PIN de administrador + #, tecla 1, digital duas vezes, senha de 6 dígitos duas vezes (escolhida pelo dono; não registrada). Espelho: `LCD| Cadastrado | ID 001`. STATUS `last_id=1 queued=3` (device_boot, admin_login, user_enrolled). LIST `ID 1 ativo`.
- Acesso pela digital: `LCD| Acesso liberado | ID 001`; queued 3 -> 4 (access_granted).
- Sem abrir a porta (verdes D30/D31 no GND), após 60 s: 3 bipes curtos (EntryExpired), ouvidos pelo dono. Buzzer pelo firmware verificado.
- Depois do EntryExpired: `LCD| Tempo esgotado | Acesso encerrado`, depois `LCD| Senha ou digital | # OK * Limpar`. Ao digitar a senha de 6 dígitos do ID 1, o espelho mostrou só `*` até `******` (máscara confirmada); com `#`: `LCD| Acesso liberado | ID 001`. Acesso pela senha do usuário cadastrado verificado.
- Teclas soltas geraram "Entrada invalida | 6 ou 10 digitos", sem efeito.

**Ciclo de porta com os verdes D30/D31 (02/11/2026, verificado em hardware)**
- Digital do ID 1 com os verdes ao GND: `LCD| Acesso liberado | ID 001`. Verdes retirados do GND: `LCD| Porta aberta | ID 001`. Verdes recolocados: `LCD| Porta fechada | ID 001`, e o LCD volta a `Senha ou digital`.
- Durante o manuseio na bancada, apareceu duas vezes `LCD| Feche a porta | Sem autorizacao`, seguido de `LCD| Porta fechada | ID 000`. Causa informada pelo dono: ele mexeu sem querer no jumper verde D30/D31; a porta foi vista aberta sem autorização (forced_open, comportamento esperado). "ID 000" ao fechar é o P3 já conhecido.
- Também apareceu `LCD| Falha no leitor | Tente novamente`, depois `LCD| Senha ou digital | DY50 fora do ar`, e logo voltou sozinho a `# OK * Limpar`: queda momentânea do DY50 e recuperação automática, observadas em hardware. Causa informada pelo dono: ele mexeu sem querer no fio do DY50.
- STATUS depois: `last_id=1 queued=14 dropped=0 replies_dropped=0 lcd=timeout dy50=ok lock_mode=0` (fila acumulando eventos sem a CAM, esperado).
- Pendências: medição do pino 35 (saída da fechadura) não foi feita; firmar a ligação do DY50 (solda ou termorretrátil na emenda do cabo).

**Ensaios de bancada de 02/11/2026 (verificado em hardware, salvo indicação; números em docs/VALIDACAO.md)**
- Porta aberta por 5 min após acesso autorizado: bipe a cada 2 s, parando ao fechar (relato do dono: "teste 2 ok"). O STATUS do momento não ficou registrado, porque o Mega reiniciou. Com isso, OpenTooLong deixa de estar não exercitado (por relato do dono).
- Reinício com cadastros: `last_id=1` mantido (EEPROM); fila zerada (`queued=1`), como previsto.
- Reinício acidental: `LCD| Feche a porta | Sem autoriz` cortado por `BOOT boot=37`, no momento em que o jumper verde saiu do GND. Causa provável (inferência): a ponta solta do verde encostou na trilha vermelha (5 V) colada à azul. Recomendação: para simular porta aberta, tirar a ponta do verde do pino D30/D31 no Mega ou levá-la a uma coluna livre; nunca deixar solta perto da trilha de 5 V.
- Fila cheia sem CAM: 15 senhas erradas `123456#` levaram `queued` de 1 a 16 (`dropped=0`); mais uma, `queued=16 dropped=1` (evento novo descartado, fila preservada).
- Cadastro com dedos diferentes: falhou sem consumir ID (relato do dono, saída não colada). Cadastro com dedo já cadastrado: recusado (relato do dono, saída não colada).
- DY50 instável durante os ensaios: várias quedas (`Falha no leitor`, `DY50 fora do ar`, `Cadastro falhou | Erro de leitura`, `Indisponivel | Veja DY50/EEPROM`), com recuperação automática na maioria; o dono reiniciou o Mega algumas vezes (boot 38 a 42). Detalhes e ponto de melhoria na seção 7.
- Cadastro do ID 2 com o mesmo fluxo: `LCD| Cadastrado | ID 002` (senha mascarada com `*`). Os sub-testes "senhas diferentes" e "senha já usada" não foram executados (o dono digitou senhas iguais e novas).
- PIN de administrador errado (10 dígitos): `Entrada invalida | 6 ou 10 digitos`, menu não aberto. Tecla `D` no menu de desativar (após digitar 222): `Cancelado`.
- Desativar ID 2 (menu 2, ID 2, `#`): `Desativado | ID 002`; credencial do ID 2: `Acesso negado | Cadastro inativo` (uma credencial testada). Um dedo apresentado depois deu `Dig. desconhec.` (provável dedo diferente ou leitura ruim; inferência). LIST antes: ID 1 e ID 2 ativos.
- Reativar ID 2 (menu 3, ID 2, `#`): `Reativado | ID 002`; depois `Acesso liberado | ID 002` (uma credencial).
- Não executados: ver seção 7.

### ESP32-CAM, 02/11/2026 (integração; gravação não concluída)

Bancada com o dono. Níveis em docs/VALIDACAO.md (linha "ESP32-CAM: compilação e tentativas de gravação").

- Ambiente (Arduino IDE 2 do Mac): pacote "esp32 by Espressif Systems" 3.3.12 (em `~/Library/Arduino15/packages/esp32`) e biblioteca ArduinoJson 7.4.3 instalados. A placa AI Thinker ESP32-CAM (`esp32:esp32:esp32cam`) não tem menu "Upload Speed" no 3.3.12; o `boards.txt` fixa `upload.speed=460800`.
- Config.h local da CAM preenchido pelo dono (Wi-Fi 2,4 GHz, URL do servidor com o IP do Mac na rede, chave e ID do dispositivo). Valores não registrados aqui; o agente não abriu esse arquivo.
- Compilação (compilado): 1055085 B de flash e 60608 B de RAM pelo IDE; 1054989 B de flash e 60608 B de RAM pelo arduino-cli com `--build-path`. A pasta de build contém os segredos compilados do Config.h local; apagar (seção 7).
- Alimentação: adaptador de parede AF 4191, 7 V / 500 mA (centro positivo), no DC-in da MB102. Corrente no limite para CAM + DY50 (estimativa; não medida).
- Passo A feito (decisão do dono): fio 5V do Mega retirado da trilha vermelha de cima; jumper de cima da MB102 em 5V; medido trilha de cima "005" e de baixo "003" (alicate BOMVINK). O Mega segue só pela USB, com GND comum. A trilha de cima (5 V da MB102) passou a alimentar o buzzer.
- Gravação pelo IDE, primeira tentativa, com a CAM alimentada pela MB102: falhou por porta errada (`usbserial-130` era do Mega); depois a fonte foi desligada; depois conectou (chip ESP32-D0WD-V3 rev 3.1, MAC no log, aviso de cristal de 41 MHz), mas falhou ao trocar para 460800 baud.
- Gravação pelo arduino-cli com `--upload-property upload.speed=115200` (comandos na seção 6). Falhas intermitentes: "No serial data received", "Serial data stream stopped: Possible serial noise", "Invalid head of packet (0x00)".
- Decisão do dono (02/11/2026): usar o 5V do PL2303 SÓ para gravar a CAM, com a CAM fora da protoboard (5 V, GND, TXD -> U0R, RXD -> U0T, jumper IO0-GND na própria CAM). Nunca junto com a MB102. Com isso, uma tentativa gravou bootloader e partições ("Hash verified") e falhou em boot_app0 ("Packet content transfer stopped"); outras falharam no início; a 57600 não conectou.
- O nome da porta do PL2303 muda conforme a entrada USB (-10, -130, -1230). Há um hub USB no caminho (ioreg mostrou "USB2.0 HUB").
- Estado: CAM ainda NÃO gravada com sucesso. Hipóteses (inferência): ruído ou mau contato nos jumpers, hub USB, adaptador PL2303 clone. Próximo passo na seção 9.

Fatos novos (02/11/2026, fim da sessão 4; ver também seção 9):

- A gravação pelo PL2303 continuou falhando mesmo com o adaptador direto no Mac (porta `/dev/cu.usbserial-110`) e com `--no-stub` pelo esptool 5.3.1. Conectava sempre e caía ao enviar o stub ou no começo da escrita ("Serial data stream stopped", "No more data to read"). O esptool detectou cristal de 41,07 a 41,59 MHz, variando a cada tentativa. Hipóteses (inferência): erro de baud do PL2303 clone (cerca de 4%) e/ou queda do 5V do PL2303 durante a escrita da flash.
- Decisão do dono (02/11/2026): usar o Mega como adaptador USB-serial (CH340) para gravar a CAM, no lugar de comprar a base ESP32-CAM-MB. Ponte planejada: RESET -> GND no Mega (para o ATmega; o firmware não é apagado); 5V e GND do Mega -> 5V e GND da CAM (só para gravar; mesma exceção autorizada para o PL2303); IO0-GND na CAM; divisor de 9 resistores de 330 Ω na metade de baixo da protoboard (colunas 40 a 49: 3 em série 40-43 e 6 em série 43-49); pino 0 (RX0) -> coluna 40; coluna 49 -> GND; coluna 43 -> U0R da CAM só depois da medição; U0T da CAM -> pino 1 (TX0) direto.
- Regra da medição (Mega na USB, RESET no GND, sem o fio 43 -> U0R, medir coluna 43 -> GND): "002" = ok (cerca de 3,3 V); "001" = a placa tem resistor interno de cerca de 1 kΩ na linha, e é preciso tirar os 3 primeiros resistores (pino 0 direto na coluna 43); "003" ou mais = parar.
- Estado da ponte: a montagem foi iniciada pelo dono (fios no conector POWER do Mega e na CAM), mas a medição do ponto do meio NÃO foi feita e a CAM NÃO foi gravada. O agente não conseguiu confirmar pelas fotos a posição dos 9 resistores. Mega ligado por um hub USB. Fonte YwRobot: chave desligada durante a gravação pelo Mega.
- Diagramas SVG desta sessão (protoboard completa, projeto completo, gravação pelo PL2303 e pelo Mega) ficaram só no scratchpad da sessão: efêmeros e não versionados. Sugerir ao dono versioná-los em `docs/` numa próxima sessão, se ele quiser.

### Sessão 5 (03/11/2026): LCD em 4 bits, alarme da porta forçada, remontagem

Bancada com o dono e alterações de código ainda não commitadas (seção 3). Níveis em docs/VALIDACAO.md (registros de 03/11/2026). O agente não abriu nenhum `Config.h`; nenhuma senha, PIN, chave ou credencial de Wi-Fi foi registrada.

**Código (análise de código; compilado e verificado em host onde indicado)**
- LCD 1602 só em modo 4 bits (decisão do dono, 03/11/2026). Biblioteca LiquidCrystal 1.0.7 (embutida na IDE). Pinos padrão: RS = D37, E = D38, D4 a D7 = D39 a D42; RW no GND; V0 no potenciômetro de 10 kΩ; A por resistor de 220 Ω. Podem ser trocados por `#define LCD_PIN_*` no `Config.h` local. Removidos: I2C, Wire, `lcdPresent`, `lcdReady`, `lcdRecoveryTick` e o campo `lcd=` de STATUS e BOOT. PCF8574 não é mais necessário. Um `Config.h` antigo com `LCD_ADDRESS` ou `LCD_PARALLEL` deve continuar compilando (não testado com um `Config.h` antigo; não verificado). `tests/test_lcd_4bits.py` novo e testes de I2C removidos (verificado em host).
- Wokwi: os três `diagram*.json` passaram ao LCD paralelo; `build.sh` usa LiquidCrystal (sem Wire); `ARDUINO_LIBS` padrão agora é `~/Documents/Arduino/libraries`, porque o caminho antigo em `~/Documents/Codex/...` não existe. Wokwi NÃO executado (Docker desligado): não verificado.
- `SHOW_TYPED_DIGITS` (opt-in, padrão 0): com `#define SHOW_TYPED_DIGITS 1` no `Config.h` local, só o espelho serial `LCD|` mostra os dígitos digitados; o LCD físico continua mascarado. Não colar logs com essa flag em conversas. Em hardware: não verificado; no boot=59 o espelho ainda estava mascarado, e a conferência por grep do dono mostrou que o define não estava no `Config.h` local.
- Alarme de porta forçada (decisão do dono, 03/11/2026, bipe rápido): em Alarme sem usuário autorizado ("Feche a porta / Sem autorizacao": ForcedOpen, ou boot com a porta aberta), o buzzer bipa 250 ms ligado e 250 ms desligado, imediatamente, até a porta fechar. Os demais padrões não mudaram. Teste `BuzzerPortaForcadaTests` em `tests/test_mega_tst02.py` (verificado em host). Em hardware: relato do dono, não verificado pelo agente (ver abaixo).
- Revisões independentes (Sonnet) das três mudanças: sem achados bloqueantes (análise de código; parecer não salvo em arquivo).

**Verificação em host e compilação**
- Suíte: 152 testes, 151 OK, 1 falha pré-existente em `tests/test_server.py::test_deeply_nested_json_reports_400` ('Dispositivo inválido.' em vez de 'JSON inválido ou corpo muito grande.'). A mesma falha ocorre num worktree limpo de `f44a926`, sem as mudanças de 03/11 (verificado em host; não investigada).
- Compilação `arduino:avr:mega` sobre `Config.example.h` (cópia de trabalho, `--libraries ~/Library/Arduino15/libraries`): 37524 B de flash, 4327 B de RAM, 0 avisos (compilado).

**Bancada de 03/11/2026**
- Protoboard: o dono refez a montagem principal com fios organizados, numa protoboard diferente (60 ou mais colunas, pelas fotos). As colunas dos registros de 02/11 e dos diagramas 01 e 03 não valem mais (análise de fotos).
- Lado de cima da YwRobot em uso: NÃO CONFIRMADO, a confirmar com o dono. As instruções de hoje seguiram o diagrama 03 (jumper de cima OFF, 5 V do Mega nas trilhas de cima, 3,3 V embaixo), diferente do "Passo A" de 02/11 (jumper de cima em 5 V, fio 5 V do Mega fora das trilhas). Nunca os dois ao mesmo tempo.
- Medições sem alimentação (alicate BOMVINK, verificado em hardware): trilha vermelha de cima até azul de cima 1 kΩ; vermelha de baixo até azul de baixo 0,75 kΩ; vermelha de cima até vermelha de baixo 1,75 kΩ (soma das duas; inferência: sem ligação direta entre 5 V e 3,3 V); azul de cima até azul de baixo 2 Ω (GND comum). Continuidade sem apito: lê-se o valor.
- Divisor do DY50: nas colunas antigas, a leitura até GND foi de 110k (verificado em hardware, leitura). Isso contradiz os 3 kΩ medidos em 02/11 e não foi explicado. Nas colunas novas não foi medido (não verificado). O dono afirma que a ligação do DY50 está correta (não verificado por medição).
- Mega 1 gravado pelo dono com o firmware de 4 bits (boots 51, 52 e 59 vistos; a gravação exata por boot não foi separada). STATUS sem o campo `lcd=`: `last_id=2 queued=1 dropped=0 replies_dropped=0 dy50=indisponivel lock_mode=0`; depois `BOOT boot=59 storage=ok dy50=ok lock_mode=0` (verificado em hardware).
- Ciclo com o firmware novo (verificado em hardware): acesso liberado ID 001 pela digital; porta aberta e fechada; "Tempo esgotado"; fila crescendo sem CAM (queued=3); senha mascarada na serial.
- Alarme de porta forçada: "Feche a porta / Sem autorizacao" com bipe rápido, parando ao fechar a porta. Relato do dono, não verificado pelo agente ("o aviso com a porta aberta funcionou bem"). O padrão 250 ms / 250 ms não foi cronometrado.
- DY50: "Falha no leitor / Tente novamente" e `dy50=indisponivel` durante o uso; voltou após RESET do Mega (`BOOT ... dy50=ok`), verificado em hardware. Recuperação automática (a cada 10 s, só com a tela de acesso livre, entrada vazia, porta fechada e sem aviso) não confirmada: o dono estava digitando na checagem (não verificado). Hipótese: mau contato na emenda do cabo (inferência). Teste pendente: com "DY50 fora do ar", esperar 15 s sem tocar e mandar STATUS.
- Teclado: o dono achou a ligação errada depois da remontagem e está refazendo. Ordem correta: tabela de 02/11 (pinos 1 a 4 = C1 a C4 = D26 a D29; pinos 5 a 8 = R1 a R4 = D22 a D25). Um desenho da Área de Trabalho do dono (protoboard-completa.svg/png, fora do repositório) mostra a ordem dos pinos errada (linhas antes das colunas); vale a tabela. Não verificado nesta data.
- LCD: não conectado nesta data. Não verificado em hardware.
- CAM: o dono decidiu gravar pelo segundo Mega como ponte USB-serial, com o mesmo método do diagrama 02 (RESET -> GND no Mega 2; 5 V e GND do Mega 2 só para gravar; IO0-GND; divisor 3+6 x 330 Ω; U0R só depois de medir "002"; U0T no pino 1). O dono informa a fiação pronta; a medição do ponto do meio não foi informada; CAM NÃO gravada (não verificado).
- Rede da CAM: o Mac está num hotspot do iPhone em 5 GHz e só com IPv6 (IPv4 192.0.0.2/32 via clat46). A CAM (2,4 GHz, IPv4 em SERVER_URL) provavelmente não alcança o servidor assim (inferência). Para testar: iPhone em "Maximizar Compatibilidade"; confirmar o IP do Mac na faixa 172.20.10.x e usar esse IP na URL do `Config.h` da CAM; servidor com `--host 0.0.0.0` (não verificado).
- Skill `/sistema-embarcado` (do dono, fora do repositório) ainda lista "LiquidCrystal I2C 1.1.2" entre as bibliotecas do Mega; deve passar a LiquidCrystal 1.0.7. Não alterada: depende de autorização do dono.

### Sessão 5, continuação (03/11/2026, tarde): ESP32-CAM gravada e na rede

Bancada com o dono. Níveis em docs/VALIDACAO.md (registros de 03/11/2026, tarde). O agente não abriu nenhum `Config.h`; nenhum nome ou senha de Wi-Fi, PIN ou chave foi registrado.

**Ponte pelo segundo Mega (verificado em hardware)**
- Porta do Mega 2: `/dev/cu.usbmodem101` ou `usbmodem1101` (o nome muda ao replugar). Chip USB 16U2, não o CH340 do Mega 1. Conferir com `ls /dev/cu.usbmodem*` antes de cada tentativa.
- Ligação: RESET -> GND no Mega 2; 5 V e GND do Mega 2 -> 5 V e GND da CAM (só para gravar); IO0 -> GND na CAM; pino 0 (RX0) -> 2 x 330 Ω -> meio (U0R) -> 6 x 330 Ω -> GND; U0T da CAM -> pino 1 direto.
- Eco do Mega 2 (jumper pino 0 com pino 1, RESET no GND, monitor 115200): o texto voltou. Verificado em hardware.

**Divisor da ponte (verificado em hardware, com ressalvas)**
- Primeira cadeia (3 + 6 x 330 Ω) mal encaixada: meio ~0,33 V; coluna 16 -> GND = 985 Ω (só 3 resistores contando). Refeita.
- Pino 0 direto no meio (0 resistores em cima): 4,4 V, acima de 3,6 V. O pino 0 desta placa tem resistência interna pequena; "0 resistores em cima" NÃO serve.
- Cadeia refeita: coluna 16 -> 34 = 2 kΩ; usados 2 x 330 Ω em cima.
- Medido com o multímetro Fluke 17B+ (leitura direta): as leituras desta tarde (0,33 V, 4,4 V, 985 Ω e 2 kΩ), não o alicate BOMVINK. Estimativa com 2 em cima: 4,4 V x 1980 / (660 + 1980) ~ 3,3 V (estimativa, não medida).
- Não verificado depois da remontagem: medir o meio com 2 em cima antes de reutilizar (alvo 2,5 a 3,3 V).

**Gravação (verificado em hardware)**
- Monitor com IO0 em GND e RST: `rst:0x1 (POWERON_RESET),boot:0x3 (DOWNLOAD_BOOT...)` e `waiting for download`.
- Chip ESP32-D0WD-V3 rev 3.1, cristal 40 MHz.
- Pela IDE falhou após "Changing baud rate to 460800" (a ponte não aguenta). Funcionou a 115200 pela linha de comando (cerca de 60 s, 4 partes com "Hash of data verified"):
  - compilar: `arduino-cli compile --fqbn esp32:esp32:esp32cam:PartitionScheme=min_spiffs --build-path /tmp/camb firmware/Esp32CamRede` (desde 04/11/2026; antes: esp32:esp32:esp32cam)
  - gravar: `arduino-cli upload -p /dev/cu.usbmodemXXXX --fqbn esp32:esp32:esp32cam:PartitionScheme=min_spiffs --input-dir /tmp/camb --upload-property upload.speed=115200 firmware/Esp32CamRede` (desde 04/11/2026; antes: esp32:esp32:esp32cam)
  - arduino-cli em "/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli".
  - Antes: IO0 em GND e RST; fechar o Monitor Serial da IDE (ele prende a porta).
- `/tmp/camb` contém segredos compilados: apagada pelo orquestrador após cada gravação.

**Boot e rede (verificado em hardware, salvo onde indicado)**
- Boot: `CAM boot ... camera=ok` e `CAM wifi conectado <IP>`.
- O hotspot do iPhone é só IPv6 (Mac recebe 192.0.0.2/32, clat46; verificado em host), então a CAM não o usa direto. Solução adotada: iPhone no cabo USB e Compartilhamento de Internet do macOS de "iPhone USB" para Wi-Fi em 2,4 GHz (canal 11). Mac em 192.168.2.1 e CAM em 192.168.2.2. O dono ajustou no Config.h local da CAM a rede e o SERVER_URL http://192.168.2.1:8080 (valores não registrados).
- Na rede de casa o IP do Mac mudou de .17 para .20 ao reconectar: o SERVER_URL da CAM precisa acompanhar.
- Painel: "ESP32 conectado" (16:56).

**Problema e correção (verificado em hardware; suíte em host; análise de código)**
- Sintoma: na rede do Mac a CAM fazia 2 requisições e parava (sem ping, sem heartbeat), ainda dizendo "conectado".
- Correção: `WiFi.setSleep(false);` logo após `WiFi.mode(WIFI_STA)` em networkTask() (`firmware/Esp32CamRede/Esp32CamRede.ino`) e `setSleep` no mock de `tests/test_camera_network.py`.
- Depois da gravação: painel "ESP32 conectado" (último contato 17:32:24), ping ~4 ms, conexões contínuas, banco do servidor atualizando. Verificado em hardware.
- Suíte: 152 testes, 1 falha pré-existente (`test_server` deeply_nested). Verificado em host.
- Compilação (sobre Config.example.h): 1055133 B de flash. Compilado.
- Revisão Sonnet: aprovada como mitigação de baixo risco. Análise de código.
- Consumo da CAM sobe (Wi-Fi sem economia de energia). Não medido: usar 5 V firme.

**Pendências novas desta continuação**
- (a) Relógio sem sincronização: a rede do Mac não tem internet IPv4 e o NTP falha (falha verificada em hardware; causa: inferência). Os eventos sairão sem horário real até decidir: o servidor fornece a hora, ou rede com internet.
- (b) PIN de administrador e chave do dispositivo foram expostos no chat em 03/11/2026 (valores não registrados). Trocar ADMIN_PIN no Config.h do Mega 1, DEVICE_KEY no Config.h da CAM e no comando do servidor. Não verificado.
- (c) Medir o meio do divisor (2 em cima) antes de reusar.
- (d) Montagem de uso da CAM no Mega 1: ver seção 9, passo 3.
- (e) Servidor no Terminal do Mac, com os valores no ambiente (não colar no chat): ver checklist abaixo.
- Desenhos de apoio na Mesa do dono, fora do repositório e não versionados: mega2-divisor-cam.png, divisor-protoboard.png, ponte-mega2-*.png.

#### Como religar a rede de testes (iPhone + Mac)
1. Plugar o iPhone no Mac pelo cabo USB, iPhone desbloqueado; Ajustes > Acesso Pessoal > "Permitir Que Outros Acessem" ligado (tocar "Confiar" se pedir).
2. No Mac: System Settings > General > Sharing > Internet Sharing (i): "Share your connection from" = o "iPhone USB" que estiver ativo (há dois na lista; em 03/11 foi en8); "To devices using" = só Wi-Fi; Wi-Fi Options: canal 1, 6 ou 11 (2,4 GHz, não "Automatic"), WPA2/WPA3 Personal; ligar Internet Sharing. Para mudar opções, desligar o Internet Sharing antes (o botão Wi-Fi Options fica cinza com ele ligado).
3. Conferir: `ifconfig bridge100 | grep "inet "` deve mostrar 192.168.2.1.
4. Servidor no Terminal do Mac: `cd ~/Desktop/controle-acesso-esp32 && ADMIN_PIN='...' DEVICE_KEY='...' python3 servidor/server.py --host 0.0.0.0 --port 8080` (valores só no Terminal; os `...` são placeholders). Painel: http://127.0.0.1:8080. No Mac do dono existe o atalho `~/Desktop/rodar-servidor-controle.command` (fora do repositório, com os valores locais); dois cliques sobem o servidor. Quem não tiver o atalho usa o comando com os próprios valores.
5. CAM: IO0 solto, apertar RST; esperado "CAM wifi conectado 192.168.2.x"; no painel "ESP32 conectado" e último contato atualizando a cada ~10 s. Conferência no Mac: `ping 192.168.2.2`.
- Ao desconectar o iPhone: a rede 192.168.2.x cai e a CAM perde o servidor (nada estraga; o firmware continua gravado). Para o Mac voltar à internet normal, desligar o Internet Sharing e reconectar o Wi-Fi do Mac à rede de casa. Na rede de casa o IP do Mac muda e o SERVER_URL da CAM teria de acompanhar; por isso a rede de testes padrão é a do Mac (192.168.2.1 fixo).

### Sessão 6 (04/11/2026): LCD, CAM no Mega 1, hora do servidor e OTA

Bancada com o dono e alterações de código. Níveis em docs/VALIDACAO.md (registros de 04/11/2026). O agente não abriu nenhum `Config.h`; nenhuma senha, PIN, chave ou credencial de Wi-Fi foi registrada.

**LCD 1602 em 4 bits (verificado em hardware)**
- Ligado pelos colegas pela MONTAGEM 3.5. Conferido desligado com Fluke 17B+: continuidade de cada fio LCD -> Mega ok; pinos 1 e 2 = 3 kΩ (sem curto); pares 6-11, 11-12, 12-13 e 13-14 em MΩ.
- Corrigido: pino 5 (RW) sem fio (estava no GND); potenciômetro mal encaixado (contraste); resistor de 220 Ω da luz de fundo na trilha de 3,3 V da YwRobot (desligada), movido para o 5V do Mega. Luz acendeu.
- Texto igual ao espelho serial.
- Uma vez a linha de baixo saiu corrompida ("Digita)lyndis9on") com o LCD na mão; após RESET saiu limpa. Causa provável: mau contato com o LCD sendo manuseado (inferência).

**Textos do LCD trocados (decisão do dono; verificado em hardware)**
- "DY50 fora do ar" -> "Digital indispon"; "Veja DY50/EEPROM" -> "Veja digital/mem" (16 colunas). Haiku implementou, Sonnet aprovou.
- Mega 1 regravado pelo dono: `BOOT boot=81 storage=ok dy50=indisponivel lock_mode=0`; espelho "Senha ou digital | Digital indispon".

**DY50 (verificado em hardware, salvo indicação)**
- Ao ligar a chave da YwRobot, o espelho voltou sozinho a "# OK * Limpar", sem novo BOOT. Recuperação automática verificada; fecha a pendência de 03/11.
- Acesso pela digital: "Acesso liberado" (relato do dono; não verificado pelo agente).

**YwRobot, lado de cima (pendência de 03/11 resolvida; medição em Ω pelo dono)**
- Estado final: jumper de cima em 5V; nenhum fio do 5V do Mega nas trilhas de cima (medido sem ligação); trilha de cima alimenta buzzer e CAM; LCD alimentado direto no 5V do Mega 1; jumper de baixo em 3.3 (DY50). Fonte de parede de 7 V no P4.
- Diagrama novo fora do repositório (scratchpad, efêmero). O desenho da Área de Trabalho (protoboard-completa) segue com a ordem do teclado errada; vale a tabela de 02/11.
- Teclado não reconferido nesta sessão (não verificado).

**CAM no Mega 1, montagem de uso (verificado em hardware)**
- Ligação: D16 -> 3 x 330 Ω -> meio -> 6 x 330 Ω -> GND; meio -> IO13; IO14 -> D17; 5V da CAM na trilha de cima (YwRobot); GND comum.
- Meio do divisor medido com Fluke: 3,3 V.
- Primeiro os fios estavam em U0R/U0T (errado): painel conectado, sem eventos e queued=1. Trocados para IO13/IO14: eventos e cadastros chegaram.
- Atenção: com 2 resistores em cima, o IO13 ficaria perto de 3,75 V (estimativa). Com 3 em cima, a ponte do Mega 2 também gravou.

**Rede de teste (verificado em host)**
- Internet Sharing de "iPhone USB" para Wi-Fi. Foi preciso desconectar o Wi-Fi do Mac do hotspot e trocar para o outro "iPhone USB" da lista.
- bridge100 192.168.2.1; CAM 192.168.2.2.
- iPhone pelo cabo entrega só IPv6/clat (192.0.0.2); por isso o NTP falha.

**Hora do servidor (código; decisão do dono, opção 2)**
- O servidor responde `server_time` no heartbeat. A CAM (`applyServerTime`) acerta o relógio se não estiver sincronizada e o valor for >= 1700000000. NTP mantido. A CAM já repassa a hora ao Mega.
- Testes novos em `tests/test_server.py` e `tests/test_camera_network.py` (verificado em host). Precisão de cerca de 1 s, a do relógio do Mac (estimativa).
- Atenção operacional: o servidor precisa ser reiniciado depois de atualizado. O que rodava desde 09:30 não mandava server_time.
- Depois de reiniciar: `devices.clock_synced=1` e access_granted com horário 2026-11-04 10:16:57 (verificado em hardware, consulta ao banco).

**Foto fim a fim (verificado em hardware)**
- Foto do acesso recebida pelo servidor (4619 B). Fluxo Mega -> CAM -> servidor com foto verificado.

**Boot e mDNS da CAM (verificado em hardware; mDNS em host)**
- `CAM boot ... camera=ok`; ping ok; anúncio mDNS `_arduino._tcp` "controle-cam" visto no Mac.

**Gravação da CAM pela ponte do Mega 2 (verificado em hardware)**
- Porta `/dev/cu.usbmodem101`. Duas falhas "No serial data received", porque o fio laranja (meio do divisor -> U0R) não estava ligado.
- Depois, 4 partes com "Hash of data verified" (bootloader, partitions, boot_app0 e app de 1115376 B (imagem .bin gravada pelo esptool; inclui cabeçalhos e alinhamento) em 63 s a 115200).
- Compilação com o Config.h local: 1115232 B (tamanho do sketch informado pela compilação) de 1966080; RAM 65204 B (compilado).
- Esquema de partição: "Minimal SPIFFS (1.9MB APP with OTA/128KB SPIFFS)", fqbn `esp32:esp32:esp32cam:PartitionScheme=min_spiffs`.
- `/tmp/camb` apagada pelo orquestrador.

**OTA (código; decisão do dono)**
- ArduinoOTA sob a guarda de `OTA_PASSWORD` (Config.h local; 8 ou mais caracteres). Sem a macro, a OTA fica desligada.
- Hostname `controle-cam`. Esquema de partição obrigatório: min_spiffs.
- `tests/test_cam_ota.py` novo (verificado em host, por texto).
- Revisão Sonnet: aprovado com ressalvas, nada bloqueante (análise de código). Bloco compilado com senha de teste: 1115264 B (compilado).
- Gravação pela rede (OTA) não verificada ainda.

**Suíte e compilação (verificado em host; compilado)**
- Suíte: 159 testes; 1 falha pré-existente em `tests/test_server.py::test_deeply_nested_json_reports_400` (verificado em host).
- Mega compilado: 37524 B de flash, 4327 B de RAM, 0 avisos no .ino (compilado).

**Decisões do dono**
- DEVICE_KEY e ADMIN_PIN não foram trocados agora; pendência (b) segue aberta.
- Mega 2 sai do projeto de uso. Fica só como ponte de gravação; a OTA poderá substituí-la depois do primeiro teste. Até lá, o caminho garantido é a ponte serial do Mega 2 (seção 6).

### Sessão 8 (06/11/2026): rede da casa, IP fixo e primeira OTA

Bancada e rede com o dono. Níveis em docs/VALIDACAO.md (registros de 06/11/2026). Nenhuma senha, PIN, chave ou senha de Wi-Fi foi registrada. O agente não abriu nenhum `Config.h`; a conferência de SSID e senha foi feita por script, sem exibir valores.

**Roteador da casa (relato do dono (telas do roteador))**
- Roteador TIM Live em 192.168.1.1. A internet sai por 4G Vivo; o lado WAN tem só IPv6 (IPv4 da WAN: "Desconhecido").
- O dono entrou no painel com o usuário admin. Não há reserva de DHCP: Rede > DHCP mostra só a faixa 192.168.1.100 a 192.168.1.200 e o lease. Funcionalidades: Firewall, Filtro MAC, Filtro IP, Redirecionamento de Portas e DMZ.

**IP fixo do Mac (decisão do dono; verificado em host)**
- Só na rede MARCILIO&PATY: Wi-Fi > Detalhes > TCP/IP manual, 192.168.1.50/255.255.255.0, roteador 192.168.1.1, DNS 192.168.1.1 orientado (não conferido; o Mac resolveu nomes pelos DNS IPv6 do 4G). Fora da faixa DHCP. Substitui o 192.168.1.170 antigo, que era DHCP.
- Conferido: en0 em 192.168.1.50, gateway 192.168.1.1, internet ok (HTTP 200).

**Configuração da CAM (verificado em host, parcial)**
- O dono editou o SERVER_URL do `Config.h` local da CAM para http://192.168.1.50:8080 (o orquestrador conferiu só essa linha).
- Por script, sem exibir valores: WIFI_SSID e WIFI_PASSWORD do `Config.h` conferem com a rede salva no Keychain do Mac.
- Firmware compilado às 14:10 em /tmp/camb (1115376 B, min_spiffs); pasta apagada depois.

**OTA (verificado em hardware: primeira OTA do projeto)**
- `arduino-cli upload --protocol network --port 192.168.2.2` falhou com "Error getting port metadata: port not found: 192.168.2.2 network". Numa execução avulsa o arduino-cli não encontra a porta de rede. Nada foi gravado.
- Funcionou com espota.py direto no IP da CAM, porta 3232, com a senha lida de forma oculta (`read -s`). Comando na seção 9.
- Primeira tentativa: autenticou, mas deu timeout no primeiro bloco (0%). Nada foi gravado.
- Segunda tentativa, com orientação para manter o DY50 desligado, das 15:45:54 às 15:46:17: 100%, "Result: OK", "Success".
- Feita pela rede de testes: Internet Sharing de "iPhone USB" para Wi-Fi, Mac em 192.168.2.1 e CAM em 192.168.2.2. Foi preciso escolher o outro "iPhone USB" (en7) para o bridge100 aparecer.
- Avisos: (a) passar a senha por `-a` deixa a senha visível em `ps`; (b) `-d` imprime a senha na linha "Options: Namespace(... auth=...)". Não usar `-d` e não colar essa linha em lugar nenhum.

**CAM na rede da casa (verificado em hardware)**
- Depois da OTA, a CAM apareceu em 192.168.1.162 (`dns-sd -G v4 controle-cam.local`). O IP pode mudar.
- O servidor (atalho rodar-servidor-controle.command, escutando 0.0.0.0:8080) registrou o device porta01 com seen_at 15:48:00 e 15:48:10: clock_synced=1, queued=0, dropped=0, rejected=0; heartbeat a cada ~10 s; o dono confirmou no painel 'ESP32 conectado' (verificado em hardware).

**Ping alto (verificado em host; causa: inferência)**
- Ping Mac -> CAM: 3,2 a 4,0 s na rede da casa. Antes da OTA, na rede de testes: 20 ms a 2,7 s, com perdas.
- Suspeita: alimentação da CAM no limite (inferência; não medido).

**Reconexão automática (análise de código; não verificado em hardware)**
- `WiFi.setAutoReconnect(true)` e `WiFi.reconnect()` a cada 15 s em networkTask(). Falta testar o reinício do modem.

**Teclado**: as 16 teclas continuam sem reconferência após a remontagem de 04/11/2026. (Superado em 06/11/2026, sessão 9: o teclado antigo quebrou e foi trocado; ver abaixo.)

### Sessão 9 (06/11/2026, tarde/noite): teclado novo, RC522, ID+senha e gravação do Mega pela CAM

Bancada com o dono, mais implementação por agentes (Opus implementou a gravação pela CAM a pedido do dono; Sonnet revisou). Níveis em docs/VALIDACAO.md (registros de 06/11/2026, sessão 9). Nenhuma senha, PIN, chave ou senha de Wi-Fi foi registrada; o agente que escreveu este registro não abriu nenhum `Config.h` nem `.env`.

**Teclado novo (verificado em hardware no Uno; no Mega: não verificado)**
- O teclado 4x4 antigo quebrou internamente (relato do dono). Substituído por um teclado de membrana de 8 pinos.
- Mapeado no Uno com sketch de varredura (fora do repositório): 16/16 teclas; pinos 1 a 4 = R1 a R4, pinos 5 a 8 = C1 a C4 (ordem inversa do antigo, que era C1 a C4 nos furos 1 a 4) (verificado em hardware).
- No Mega: pino N do teclado no D(21+N) (1 -> D22 ... 8 -> D29). O firmware não muda de pinos. As 16 teclas no Mega ainda não foram reconferidas formalmente (não verificado).
- Descartados: teclado Dell SK-8175 por USB (o Mega não é host USB; análise); teste PS/2 nos fios do cabo cortado deu só "linhas CLK=1 DATA=1", sem scan codes, ou seja, não fala PS/2 (verificado em hardware); Bluetooth (análise). A matriz da membrana do Dell (aberto; contatos em dois grupos, ~26 a 30 linhas) ficou como alternativa não usada.

**RC522 como terceiro método de acesso**
- No Uno: MFRC522 1.4.12, VersionReg 0x82 (clone); cartão MIFARE 1KB com UID de 4 bytes lido. A falha inicial era pinos sem solda (verificado em hardware).
- No Mega: SDA/SS D53, SCK D52, MOSI D51, MISO D50, RST D49; alimentação no 3.3V do Mega (o DY50 fica no 3,3 V da MB102). Ligado DIRETO, sem divisores, por decisão do dono (risco aceito: fora da especificação do chip). Leitura no Mega: não verificado.
- Firmware (commit `160534d`; análise de código): `CardStore.h` (área da EEPROM 3148..4047, slots de 9 bytes, CRC-8 com o id, UID sem sal); passo opcional "Aproxime cartao / # pula" no cadastro; menu 4 vincula cartão; LIST com `cartao=sim/nao`; BOOT com `rfid=ok/indisponivel` e recuperação a cada 15 s; sondagem a cada 200 ms com linkTick antes. Método e eventos novos no fim das listas: método `card`, eventos `card_linked` e `keypad_locked`, motivo `unknown_card` (Mega, os 3 `MessageProtocol.h`, CAM, servidor e `app.js`).

**Login por ID + senha (decisão do dono; commit `160534d`)**
- ID (1 a 3 dígitos) + `#`, depois senha de 6 dígitos + `#`. Senhas podem repetir entre IDs (sem `pin_in_use`). ID inexistente também pede a senha e nega. 10 dígitos = ADMIN_PIN.
- Bloqueio do teclado por 60 s na 5a falha seguida; sucesso não zera o contador; decaimento em 10 min; admin errado conta. Prefixo do ADMIN_PIN mascarado. Magenta no LED durante a senha (mantido pelo dono).
- Revisado por Sonnet (2 rodadas) (análise de código). No hardware: o dono relata "Acesso liberado" com a senha e a fechadura abrindo (relato do dono).

**Gravação do Mega pela ESP32-CAM (commit `9d3bed2`)**
- Rota POST `/mega` na porta 8081 (Digest + `X-Image-MAC` = HMAC-SHA256(OTA_PASSWORD, sha256 em hex)); imagem em PSRAM, SHA-256, STK500v2 a 115200 com verificação por página e até 3 tentativas (análise de código).
- UART1: IO15 (RX) pelo divisor do D1; IO2 (TX) DIRETO no D0. Risco aceito pelo dono: o CH340 do Mega põe 5 V por 1 kΩ no IO2; o diodo 1N4007 foi sugerido e recusado.
- Reset: IO12 -> 1 kΩ -> base do BC337, 10 kΩ de IO12 ao GND, coletor no RESET, emissor no GND. Reset testado pelo dono com um fio no 3.3V (relato do dono). Divisor D1 -> IO15 medido em 3,3 V (verificado em hardware).
- Script: `python3 -I scripts/gravar-mega-pela-cam.py --compilar --host 192.168.1.162` (senha por getpass; build em pasta temporária apagada depois).
- Suíte: 206 testes, 1 falha pré-existente (`test_server.test_deeply_nested_json_reports_400`) (verificado em host).
- OTA da CAM com o código novo: 2 falhas (timeout em 2%; broken pipe em 14%), sucesso na 3a às ~19:27, com o Wi-Fi estável logo após um reinício (verificado em hardware). CAM em 192.168.1.162; `/mega` responde 401 sem credenciais (verificado em host).
- Primeira gravação do Mega pela CAM: a 1a tentativa perdeu a resposta (Connection reset) e o Mega voltou com o firmware antigo intacto; a 2a, depois de reiniciar a CAM, deu HTTP 200 ok, 43688 bytes, 11296 ms, 1 tentativa (verificado em hardware). O LCD passou a mostrar o texto novo (relato do dono).
- Firmware gravado com LOCK_MODE=1: o dono editou o `Config.h` do Mega; o valor foi confirmado pelo comportamento da fechadura (relato do dono). A regra "LOCK_MODE=0 até o ensaio da fechadura" (seção 2) foi superada pela decisão do dono de iniciar o ensaio.
- Diagramas novos fora do repositório: `~/Desktop/Sistemas embarcados/montagem-mega-cam-gravacao.svg` e `ligacao-mega-cam-gravacao.svg`.

**Wi-Fi da CAM instável**
- Ping de 1 a 6 s, perdas e heartbeats espaçados; melhora depois de reiniciar a CAM (verificado em host). Retirar os fios novos não resolveu: sem eles também oscila, ou seja, não são os fios (verificado em hardware). Causa provável: alimentação ou antena (inferência). Roteador mudou para o canal 2. Mac -> roteador: 3,7 ms (verificado em host).

**Bancada do amigo do dono (05 e 06/11; relato do dono pelo handoff do amigo, zip `handoff-bancada-2026-11-06` recebido pelo WhatsApp, não versionado)**
- Fonte 12 V (3 a 6 A) -> LM2596 em 7,0 V (medido pelo amigo) -> MB102. Mega pelo VIN em 12 V; 5V e 3.3V do Mega sem ligação com a protoboard.
- LCD: contraste por 1,5 kΩ fixo; RW no GND.
- Relé GBK P5, 1 canal, ativo em HIGH, com 10 kΩ de D35 ao GND. Fechadura: +12 V -> C; NA -> + da fechadura; - da fechadura direto no - da fonte. Diodo 1N4007 da fechadura NÃO instalado.
- LED RGB 5 mm solto, 330 Ω por canal; cátodo ou ânodo comum a confirmar (padrão do firmware: RGB_COMMON_ANODE=false).
- CAM no 5 V da MB102; divisor do link 3 x 330 Ω / 6 x 330 Ω; ACS712 opcional não instalado.
- Buzzer com polaridade invertida (correção indicada; não verificada). Serigrafia TX1/RX1 trocada no Mega.

**Fechadura (em andamento; superado pela continuação abaixo: 1N4007 instalado)**
- Abriu com LOCK_MODE=1 (relato do dono), MAS o Mega reinicia quando a fechadura solta (relato do dono). Causa provável: falta do diodo 1N4007 (pico da bobina no GND/12 V, que também alimenta o Mega pelo VIN) (inferência). Diagrama: `~/Desktop/Sistemas embarcados/diodo-fechadura.svg` (faixa no + da fechadura).

**LED e LCD (em andamento, outro agente; não commitado; superado: commitado em `bf608b8` e gravado, ver continuação abaixo)**
- Piscada azul de repouso de 60 s para 10 s. Textos do LCD: repouso "Controle acesso" / "ID cartao dedo"; digitando "#confirma *limpa"; senha "ID 00X: ******". Não verificado.

**Segurança**: a senha do Wi-Fi, a senha admin do roteador e a OTA_PASSWORD apareceram no chat desta sessão. Trocar OTA_PASSWORD, DEVICE_KEY e ADMIN_PIN (ADMIN_PIN e DEVICE_KEY já estavam pendentes).

### Sessão 9, continuação (06/11/2026, ~20:00 a 21:30): diodo da fechadura, acessos e correções após o pulso

Bancada com o dono. Níveis em docs/VALIDACAO.md (registros de 06/11/2026, noite). Nenhuma senha registrada; o agente não abriu `Config.h` nem `.env`.

**Diodo 1N4007 na fechadura**
- 1a montagem: o Mega ficou em "Iniciando..." e reiniciando em ciclo; o diodo estava invertido em relação ao fio que vai ao NA (a cor do fio da fechadura não indica polaridade) (relato do dono).
- Corrigido: FAIXA no fio da fechadura ligado ao NA do relé; o outro lado no fio que vai ao − da fonte 12 V. O Mega passou a iniciar e a fechadura funciona sem reiniciar o Mega (relato do dono). Isso supera o desenho anterior "faixa no + da fechadura" descrito no bloco da sessão 9.
- Lição: o ciclo indica que o relé chega a fechar no boot apesar do 10 kΩ de D35 ao GND; investigar (não verificado).
- Esquemas do amigo `passo11_fechadura.png` e `esquema_geral.png` copiados para `~/Desktop/Sistemas embarcados/` (fora do repositório); diagrama `~/Desktop/Sistemas embarcados/diodo-fechadura.svg`.

**Gravações do Mega pela CAM**
- 2a e 3a gravações de firmware: HTTP 200, 1 tentativa; 43688 B e depois 43818 B (11331 ms), com os textos "Controle acesso" / "ID cartao dedo" (verificado em hardware; LCD por relato do dono).
- Gravação feita com a alavanca dos 12 V LIGADA, por decisão do dono (sem incidente relatado).
- A primeira tentativa às vezes dá "Connection reset by peer" (Wi-Fi da CAM); reiniciar a CAM antes resolve.

**Servidor**
- O servidor antigo (iniciado às 15:47, antes da mudança de `server.py` às 17:53) rejeitava eventos novos: painel "Descartados após rejeição definitiva: 4". O contador é acumulado e não zera sozinho; zerar rejected/rejected_prev em devices (com backup) fica para decisão do dono.
- Servidor reiniciado às 20:30:24 pelo agente (kill do processo e atalho rodar-servidor-controle.command) (verificado em host). Regra: reiniciar o servidor sempre que `server.py` mudar.

**LED**: tinha parado (fio frouxo provável) e voltou (relato do dono).

**Ensaios com o firmware novo (20:28 a 20:37; relato do dono + eventos do servidor)**
- Acesso por senha (ID+senha), por cartão e por digital liberados; fechadura pulsando.
- PROBLEMA: depois de um acesso (pulso da fechadura), o RC522 e o DY50 deixam de ler (nenhum evento) até reiniciar o Mega.
- Sensores de porta (jumpers fixos no GND) geraram door_opened/door_closed/forced_open em ~1 s logo após acessos (ruído do pulso; inferência).
- Correção em firmware, commit `99fcc71` (análise de código; NÃO gravado no Mega): reinício automático do RC522 e do DY50 1 s e 4 s após a fechadura desenergizar; debounce dos sensores de porta de 50 para 200 ms. Sugestão de hardware pendente: pull-up externo 4,7 kΩ + capacitor 100 nF em D30 e D31.

**Commit `b50bd0b` (NÃO gravado no Mega nem na CAM; análise de código)**
- LCD "#Confirma *Limpa" nas telas de ID e senha; "ID: 12" ao digitar o ID.
- Menu admin em 2 telas: "1 Novo 2 Inativ." / "3 Reativ. D Sair" e "4 Vincula cartao" / "5 Remove cartao".
- Menu 5 desvincula cartão com confirmação "Remover cartao?" / "#Sim *Nao" e evento novo `card_unlinked` (Mega, os 3 `MessageProtocol.h`, CAM, servidor e painel "Cartão desvinculado").
- Mapa de cores do LED aprovado pelo dono: alarme vermelho piscando rápido; teclado travado vermelho piscando a cada 1 s; erro vermelho fixo; flash ciano de 150 ms ao ler cartão/digital; menus e cadastro branco; senha magenta; digitando o ID ciano; porta aberta amarelo piscando; liberado verde; repouso azul por 200 ms a cada 10 s.
- Suíte: 214 testes, 1 falha pré-existente (`test_server.test_deeply_nested_json_reports_400`) (verificado em host). Mega compila com 44852 B / RAM 4771 B; CAM compila com 1156112 B (compilado).

**Ao parar**: o Mac saiu da rede MARCILIO&PATY (foi para outra rede 10.0.0.x, longe da bancada). A pasta `/tmp/camb` sumiu: recompilar antes da OTA.

### Sessão 10 (09/11/2026): Mega gravado pela USB, terra do DY50 e LED com resistores

Bancada com o dono, Mega 1 pela USB do Mac (`/dev/cu.usbserial-310`). Nenhuma senha registrada aqui.

**Gravação**
- Mega gravado pela USB com `feat/deploy-nuvem-https` (inclui `99fcc71` e `b50bd0b`): 44642 B, depois 44692 B com o diagnóstico abaixo (verificado em hardware). Bibliotecas instaladas no `arduino-cli` do Mac: Crypto 0.4.0, Adafruit Fingerprint 2.1.4, Keypad 3.1.1, MFRC522 1.4.12.
- `Config.h` local do Mega refeito a partir do exemplo: `ADMIN_PIN` novo de 6 dígitos (o antigo não estava no Mac; item (b) da seção 7 resolvido para o Mega), `LOCK_MODE = 1`, resto igual ao exemplo.
- A primeira tentativa pela USB deu timeout: o IO2 da CAM fica direto no RX0 e, com a CAM desligada, segura a linha. Com o fio do RX0 solto o bootloader respondeu (assinatura 1E 98 01) (verificado em hardware).

**Loops em "Iniciando..."**
- Dois episódios, contador de boot de 81 (06/11) para 476 e depois de 535 para 676. O primeiro parou ao prender o botão de cima da porta, que estava solto; o segundo veio logo após montar os resistores do LED e parou com a fiação acomodada (relato do dono). Causa provável: curto ou mau contato durante a mexida (inferência).
- Descartados por teste: os fios da CAM (RX0, TX0 e RESET religados um a um, boot normal em todos) e o buzzer com a porta aberta (porta aberta 15 s sem nenhum reboot, contador 676 para 677) (verificado em hardware).
- Leitura da serial no macOS: configurar a velocidade DEPOIS de abrir a porta. `stty` antes do `open` volta a 9600 e o texto sai como lixo, o que levou a um diagnóstico errado de "Mega preso em reset" nesta sessão.

**DY50: falha a cada 10 s**
- Sintoma: "Falha no leitor / Tente novamente" sozinho, LED vermelho. Diagnóstico novo no firmware: `DY50 err=0x..` na serial (só na placa, `#ifdef ARDUINO`). Resultado: `err=0x1` (pacote corrompido) exatamente na piscada azul de repouso (`millis() % 10000 < 200`); o handshake da recuperação passava (verificado em hardware).
- Prova: build de teste sem a piscada azul, 63 s sem erro (verificado em hardware).
- Causa: LED RGB ligado direto nos pinos 32 a 34 SEM resistor; a corrente do azul fazia o GND do Mega oscilar em relação à calha da MB102, que alimenta o DY50 (inferência apoiada no teste).
- Correção de hardware: 2 fios extras de GND do Mega para a calha do DY50 e para a calha oposta; com isso, 55 s sem erro já com a piscada azul (verificado em hardware). Depois, 330 Ω em cada cor do LED (cátodo comum, perna maior no GND) (relato do dono).

**Ensaio dos leitores após o pulso (resolve o PROBLEMA da sessão 9)**
- Digital, cartão, ID + senha, cartão de novo e digital de novo, em sequência: todos liberaram (relato do dono). `99fcc71` confirmado em hardware.

**Pendente**
- CAM com o firmware HTTPS (`Esp32CamRede`) ainda não gravada.
- Sensor de porta leu "aberta" duas vezes sozinho em 30 s (23 s após o boot); conferir os botões. Sugestão da sessão 9 continua: pull-up externo 4,7 kΩ + 100 nF em D30 e D31.

## 5. Verificação (30/10/2026, 02/11/2026, 03/11/2026, 04/11/2026 e 06/11/2026, sessões 8 e 9)

| Verificação | Resultado | Evidência |
|---|---|---|
| Suíte Python: `CONTROLE_TEST_LIBS=<pasta das libs de teste> CONTROLE_TEST_STRICT=1 python3 -m unittest discover -s tests -q` | 145 testes OK, 0 skipped, 28 a 39 s conforme a carga (38,4 s no fim da sessão 2; 28,3 s na reexecução da revisão R1; sessão 1: 126 testes, 25,5 s; ~28 s em outra execução) | verificado em host (reexecutado no fim da sessão 2) |
| Mega `arduino:avr:mega`, método da sessão 2 (avr-gcc 14.2, `-Wall -Wextra`) | 42496 B de flash, 4581 B de SRAM global, 19 avisos (1 do projeto, pré-existente) | compilado, container Linux local |
| Mega `arduino:avr:mega`, sessão 1 (histórico) | 38996 B de flash, 4510 B de SRAM global | compilado; não comparável com a linha acima |
| CAM `esp32:esp32:esp32cam` | 1055069 B de flash, 60608 B de RAM global (sessão 1; não recompilada na sessão 2) | compilado |
| `node --check` do painel | OK | verificado em host |
| Painel no Chrome local | 390 px após as correções; 1280 px só na verificação inicial A1, antes das correções. Teclado físico e leitor de tela não verificados | verificado em host (navegador local) |
| simavr do Mega (boot, hash, senha, EEPROM) | Tempos e boot sem LCD em VALIDACAO.md | simulado |
| Ensaio físico: passo 3 (Mega pelo USB, sem LCD), 30/10/2026 noite | Boot, AUTH e STATUS conforme o esperado; D16 ~4 V (medição grosseira); D35 0 V; LCD não testado (display sem módulo I2C) | verificado em hardware; LCD: não verificado |
| Teclado 4x4: matriz e ordem dos furos (sessão 3), 30/10/2026 noite | Matriz confirmada por continuidade (C1 a C4 = furos 1 a 4, R1 a R4 = furos 5 a 8); teclas 1, 2, 3, A, 4, 7, * e D testadas | verificado em hardware (alicate BOMVINK) |
| Teclado 4x4 lido pelo Mega (sessão 3), 30/10/2026 noite | Ligação provisória sem solda; `123456#`, `111111#` e jumper à mão D22-D26 / D25-D28: queued continuou 1. Causa provável (hipótese por análise de código): contato instável ou trepidação. Resolvido em 02/11/2026 (sessão 4): a causa era o contato provisório | não verificado (registro de 30/10/2026; resolvido em 02/11/2026) |
| Teclado 4x4 soldado e lido pelo Mega (sessão 4), 02/11/2026 | Barra de 8 pinos soldada; continuidade com alicate; firmware: boot, `123456#`, `111111#`, `789000#`, queued 1 -> 4; cada senha errada gerou access_denied; teclas 0 a 9 e #; linhas R1 a R4 e colunas C1 a C3 pelas senhas. A, B, C e * exercitadas no diagnóstico de 02/11 (ver a linha das 16 teclas). Resolve a pendência da sessão 3 | verificado em hardware |
| Teclado 4x4, coluna C4 (pino 4, D29), 02/11/2026 | Primeiro teste falhou com os jumpers verdes D30/D31 retirados (porta vista aberta). Com boot limpo, `111` + `D` + `123456#` não subiu o queued; após recolocar o jumper roxo firme e novo boot, queued 1 -> 2 (tecla D lida). Causa provável da falha: jumper roxo frouxo (inferência) | verificado em hardware |
| Teclado 4x4, diagnóstico das 16 teclas (sketch DiagTeclado, fora do repositório), 02/11/2026 | 16 de 16 teclas lidas com linha e coluna corretas; teclado 4x4 completo. A, B, C e * exercitadas (com o firmware do projeto, A, B e C não têm efeito observável no modo normal) | verificado em hardware (ver seção 4, sessão 4) |
| Buzzer: módulo S V G e buzzer de 2 pernas (sessão 4), 02/11/2026 | Módulo S V G: silêncio com S em GND e com S em 5 V; descartado (provavelmente passivo, inferência). Buzzer de 2 pernas ligado direto ao 5 V e GND apitou contínuo: é ativo | verificado em hardware |
| Circuito do buzzer com BC546 (sessão 4), 02/11/2026 | Protoboard conforme MONTAGEM 3.8, com 330 Ω na base; fio de teste no 5 V apita; no D36 com o Mega em repouso fica em silêncio. Acionamento pelo firmware (D36 em HIGH): não verificado nesta sessão; verificado depois, na continuação de 02/11/2026 (EntryExpired, 3 bipes). Comportamento do firmware (EntryExpired, OpenTooLong): análise de código | verificado em hardware (acionamento pelo firmware: não verificado nesta sessão; verificado depois, na continuação de 02/11/2026) |
| Resistores medidos (sessão 4), 02/11/2026 | Alicate BOMVINK: tira de 4 = 1 kΩ; tira do meio = 10 kΩ; tira de baixo = 330 Ω (valores conforme a medição) | verificado em hardware |
| Suíte Python (sessão 4, continuação), mesmo comando da linha da suíte | 147 testes, 146 OK; 1 falha pré-existente em `tests/test_server.py::test_deeply_nested_json_reports_400` (mesma no HEAD a6ff44a, sem a mudança do espelho) | verificado em host |
| Mega com espelho do LCD, `arduino:avr:mega`, arduino-cli do Arduino IDE (sobre `Config.example.h`), 02/11/2026 | 39624 B de flash, 4549 B de RAM, zero avisos no .ino (21 de core e bibliotecas); não comparável com a linha da sessão 2 | compilado |
| Espelho do LCD na serial (`LCD_SERIAL_MIRROR`), 02/11/2026 | Testes de host com mocks (2 novos); linhas `LCD\|` vistas no cadastro e no acesso | verificado em host; verificado em hardware |
| DY50 alimentado pela MB102 e comunicando, 02/11/2026 | `BOOT boot=33 storage=ok lcd=timeout dy50=ok lock_mode=0`; saída 3,3 V da MB102 ("003"; medição grosseira); pino 18 = TX1 e 19 = RX1 medidos; TX do DY50 não medido com o alicate | verificado em hardware |
| Cadastro e acessos (digital e senha do ID 1), 02/11/2026 | `Cadastrado` e `Acesso liberado` no espelho; STATUS queued 1 -> 4; LIST `ID 1 ativo`; senha mascarada com `*` | verificado em hardware |
| Buzzer pelo firmware (EntryExpired), 02/11/2026 | 3 bipes após 60 s sem abrir a porta, ouvidos pelo dono | verificado em hardware |
| Ciclo de porta com verdes D30/D31 e espelho do LCD, 02/11/2026 | Digital do ID 1: `LCD\| Acesso liberado \| ID 001`; verdes retirados: `LCD\| Porta aberta \| ID 001`; verdes recolocados: `LCD\| Porta fechada \| ID 001` e volta a `Senha ou digital`. forced_open por verde mexido sem querer (informado pelo dono); queda do DY50 por fio mexido sem querer, com recuperação automática; STATUS depois `queued=14`, `dy50=ok`. Medição do pino 35 não feita (pendente) | verificado em hardware |
| Porta aberta por 5 min após acesso autorizado, 02/11/2026 | Bipe a cada 2 s, parando ao fechar (relato do dono: "teste 2 ok"); STATUS do momento não registrado (o Mega reiniciou) | não verificado pelo agente (relato do dono; sem STATUS nem saída serial) |
| Reinício com cadastros e reinício acidental, 02/11/2026 | Após reboot: `last_id=1` mantido e `queued=1`. Reinício acidental: `LCD\| Feche a porta \| Sem autoriz` cortado por `BOOT boot=37` (jumper verde saiu do GND); causa provável: inferência | verificado em hardware |
| Fila cheia sem CAM, 02/11/2026 | 15 senhas erradas: `queued` 1 -> 16, `dropped=0`; mais uma: `queued=16 dropped=1` (evento novo descartado, fila preservada) | verificado em hardware |
| Cadastro com dedos diferentes e com dedo já cadastrado, 02/11/2026 | Dedos diferentes: falhou sem consumir ID; dedo já cadastrado: recusado (relato do dono, saída não colada) | não verificado pelo agente (relato do dono) |
| Cadastro, PIN errado, desativação e reativação do ID 2, 02/11/2026 | Cadastro: `LCD\| Cadastrado \| ID 002`; PIN de 10 dígitos errado: `Entrada invalida \| 6 ou 10 digitos`; `D` no menu de desativar: `Cancelado`; desativado: `Acesso negado \| Cadastro inativo`; reativado: `Acesso liberado \| ID 002` | verificado em hardware |
| DY50 instável durante os ensaios, 02/11/2026 | Várias quedas (`Falha no leitor`, `DY50 fora do ar`, `Cadastro falhou \| Erro de leitura`, `Indisponivel \| Veja DY50/EEPROM`), com recuperação automática na maioria; reinícios do dono (boot 38 a 42). Causa provável: inferência (mau contato na emenda/jumpers) | verificado em hardware (ocorrências); causa: inferência |
| ESP32-CAM: compilação e gravação, 02/11/2026 | Compilada: 1055085 B de flash e 60608 B de RAM (IDE); 1054989 B e 60608 B (arduino-cli com `--build-path`). Gravação NÃO concluída: chip ESP32-D0WD-V3 identificado; uma tentativa gravou bootloader e partições e falhou em boot_app0; as demais falharam no início ou ao trocar de velocidade | compilado; gravação não verificada (chip identificado em hardware) |
| Suíte Python (sessão 5), 03/11/2026: `CONTROLE_TEST_LIBS=<pasta das libs de teste> CONTROLE_TEST_STRICT=1 python3 -m unittest discover -s tests -q`. A pasta das libs de teste é temporária; se não existir, regenere com `python3 scripts/bootstrap-test-libs.py` (ver seção 6). | 152 testes: 151 OK, 1 falha pré-existente em `tests/test_server.py::test_deeply_nested_json_reports_400` (a mesma em worktree limpo do HEAD `f44a926`; não investigada) | verificado em host |
| Mega `arduino:avr:mega`, arduino-cli, 03/11/2026 (sobre `Config.example.h`, cópia de trabalho) | 37524 B de flash, 4327 B de RAM, 0 avisos | compilado |
| CAM gravada pela ponte do Mega 2, 115200, 03/11/2026 (tarde) | 4 partes com "Hash of data verified", cerca de 60 s; eco do Mega 2 OK; IDE falhou em 460800 | verificado em hardware |
| Divisor da ponte, 03/11/2026 (tarde) | 0 em cima: 4,4 V (medido com o multímetro Fluke 17B+, leitura direta; reprovado). 2 em cima: não medido após remontagem (estimativa ~3,3 V) | verificado em hardware (leituras); 2 em cima: não verificado |
| Boot e Wi-Fi da CAM, 03/11/2026 (tarde) | `CAM boot ... camera=ok`; `CAM wifi conectado` | verificado em hardware |
| Rede de teste (iPhone USB + Compartilhamento), 03/11/2026 (tarde) | Painel "ESP32 conectado" (16:56) | verificado em hardware |
| Correção setSleep: conexão contínua, 03/11/2026 (tarde) | Ping ~4 ms, último contato 17:32:24, conexões contínuas, banco atualizando | verificado em hardware |
| Correção setSleep: suíte Python, 03/11/2026 (tarde) | 152 testes, 151 OK, 1 falha pré-existente em `test_deeply_nested_json_reports_400` | verificado em host |
| Correção setSleep: compilação, 03/11/2026 (tarde) | 1055133 B de flash (sobre Config.example.h) | compilado |
| Correção setSleep: revisão independente (Sonnet), 03/11/2026 (tarde) | Aprovada como mitigação de baixo risco | análise de código |
| NTP na rede do Mac, 03/11/2026 (tarde) | Falha (rede sem internet IPv4) | verificado em hardware (falha); causa: inferência |
| Foto da CAM ao servidor e UART com o Mega de uso, 03/11/2026 (tarde) | Não executado | não verificado |
| LCD 1602 em 4 bits, continuidade e ligação, 04/11/2026 | Fluke 17B+ desligado: continuidade de cada fio ok; pinos 1 e 2 = 3 kΩ; pares 6-11, 11-12, 12-13, 13-14 em MΩ; RW corrigido; luz de fundo com o resistor no 5V do Mega; texto igual ao espelho | verificado em hardware |
| LCD: linha corrompida uma vez, 04/11/2026 | "Digita)lyndis9on" com o LCD na mão; limpa após RESET; causa provável: mau contato (inferência) | verificado em hardware (ocorrência); causa: inferência |
| Textos do LCD trocados, 04/11/2026 | `BOOT boot=81 storage=ok dy50=indisponivel lock_mode=0`; espelho "Senha ou digital \| Digital indispon" | verificado em hardware |
| Recuperação automática do DY50, 04/11/2026 | Espelho voltou a "# OK * Limpar" ao ligar a chave da YwRobot, sem novo BOOT | verificado em hardware |
| Acesso pela digital, 04/11/2026 | "Acesso liberado" (relato do dono) | não verificado pelo agente (relato do dono) |
| YwRobot, lado de cima, 04/11/2026 | Jumper de cima em 5V; sem ligação entre o 5V do Mega e as trilhas de cima (Ω); trilha de cima alimenta buzzer e CAM | verificado em hardware (medição em Ω pelo dono) |
| Divisor da CAM no Mega 1, 04/11/2026 | D16 -> 3 x 330 Ω -> meio -> 6 x 330 Ω -> GND; meio medido 3,3 V (Fluke 17B+) | verificado em hardware |
| Integração IO13/IO14 da CAM, 04/11/2026 | Com U0R/U0T: painel conectado, sem eventos, queued=1. Com IO13/IO14: eventos e cadastros chegaram | verificado em hardware |
| Gravação da CAM com min_spiffs, 04/11/2026 | Porta `/dev/cu.usbmodem101`; duas falhas "No serial data received" (fio do meio não ligado); depois 4 partes "Hash of data verified"; app 1115376 B (imagem .bin gravada pelo esptool; inclui cabeçalhos e alinhamento) em 63 s a 115200 | verificado em hardware |
| Compilação da CAM com min_spiffs, 04/11/2026 | 1115232 B (tamanho do sketch informado pela compilação) de 1966080; RAM 65204 B (Config.h local) | compilado |
| Boot e mDNS da CAM, 04/11/2026 | `CAM boot ... camera=ok`; ping ok; `_arduino._tcp` "controle-cam" visto no Mac | verificado em hardware (boot, ping); verificado em host (mDNS) |
| Rede de teste, 04/11/2026 | bridge100 192.168.2.1; CAM 192.168.2.2; iPhone pelo cabo só entrega IPv6/clat (192.0.0.2), por isso o NTP falha | verificado em host |
| Hora do servidor no banco, 04/11/2026 | `devices.clock_synced=1`; access_granted com horário 2026-11-04 10:16:57, depois de reiniciar o servidor | verificado em hardware (consulta ao banco) |
| Foto do acesso fim a fim, 04/11/2026 | Foto de 4619 B recebida pelo servidor (Mega -> CAM -> servidor) | verificado em hardware |
| Suíte Python, 04/11/2026 | 159 testes; 1 falha pré-existente em `tests/test_server.py::test_deeply_nested_json_reports_400` | verificado em host |
| Mega `arduino:avr:mega`, 04/11/2026 | 37524 B de flash, 4327 B de RAM, 0 avisos no .ino (sobre Config.example.h) | compilado |
| OTA da CAM (código), 04/11/2026 | ArduinoOTA sob `OTA_PASSWORD`; hostname `controle-cam`; `tests/test_cam_ota.py` (por texto); bloco compilado com senha de teste: 1115264 B; revisão Sonnet: aprovado com ressalvas | verificado em host (texto); compilado; análise de código |
| OTA pela rede (gravação), 04/11/2026 | Não executada. Superado em 06/11/2026: feita por espota.py (linhas de 06/11) | não verificado em 04/11; verificado em hardware em 06/11/2026 |
| Teclado 16 teclas após remontagem, 04/11/2026 | Não reconferido nesta sessão | não verificado |
| Roteador da casa, sem reserva DHCP, 06/11/2026 | Sem reserva; faixa DHCP 192.168.1.100 a .200 com lease; Funcionalidades: Firewall, Filtro MAC, Filtro IP, Redirecionamento de Portas, DMZ | relato do dono (telas do roteador) |
| IP fixo do Mac na MARCILIO&PATY, 06/11/2026 | en0 192.168.1.50; gateway 192.168.1.1; internet ok (HTTP 200) | verificado em host |
| SSID e senha de Wi-Fi da CAM x Keychain, 06/11/2026 | Iguais (script, valores não exibidos); SERVER_URL http://192.168.1.50:8080 (linha conferida pelo orquestrador) | verificado em host |
| Compilação da CAM com min_spiffs (OTA), 06/11/2026 | 1115376 B; /tmp/camb apagada depois | compilado |
| OTA via arduino-cli `--protocol network`, 06/11/2026 | Falhou: "port not found: 192.168.2.2 network"; nada gravado | verificado em host (falha) |
| OTA via espota.py, 1a tentativa, 06/11/2026 | Autenticou; timeout em 0%; nada gravado | verificado em hardware (falha) |
| OTA via espota.py, 2a tentativa, 06/11/2026 (15:45:54 a 15:46:17) | 100%, "Result: OK", "Success". Primeira OTA do projeto | verificado em hardware |
| CAM na rede da casa e servidor, 06/11/2026 | CAM em 192.168.1.162; porta01 seen_at 15:48:00 e 15:48:10; clock_synced=1; queued=0; dropped=0; rejected=0; heartbeat a cada ~10 s; o dono confirmou no painel 'ESP32 conectado' (verificado em hardware) | verificado em hardware |
| Ping Mac -> CAM, 06/11/2026 | 3,2 a 4,0 s (antes da OTA, rede de testes: 20 ms a 2,7 s, com perdas) | verificado em host (medição); causa suspeita (alimentação): inferência |
| Reconexão automática da CAM, 06/11/2026 | Código: setAutoReconnect(true) e reconnect() a cada 15 s | análise de código; não verificado em hardware |
| Teclado 16 teclas após remontagem, 06/11/2026 | Não reconferido (continua pendente). Superado em 06/11/2026 (sessão 9): teclado antigo quebrado e substituído | não verificado |
| Teclado novo de membrana no Uno (sketch de varredura), 06/11/2026 (sessão 9) | 16/16; pinos 1 a 4 = R1 a R4, 5 a 8 = C1 a C4 | verificado em hardware |
| Teclado novo no Mega (pino N em D(21+N)), 06/11/2026 | 16 teclas não reconferidas formalmente | não verificado |
| Teclado Dell SK-8175 em PS/2, 06/11/2026 | Só "linhas CLK=1 DATA=1", sem scan codes; não fala PS/2 (USB e Bluetooth descartados por análise) | verificado em hardware |
| RC522 no Uno, 06/11/2026 | MFRC522 1.4.12; VersionReg 0x82 (clone); MIFARE 1KB, UID de 4 bytes lido | verificado em hardware |
| RC522 no Mega (D49 a D53, 3.3V do Mega, sem divisores), 06/11/2026 | Ligado; leitura no Mega não ensaiada | não verificado |
| Firmware RC522, ID+senha e bloqueio (`160534d`), 06/11/2026 | Revisão Sonnet (2 rodadas) | análise de código |
| Acesso por ID+senha no Mega, 06/11/2026 | "Acesso liberado" e fechadura abrindo | relato do dono |
| Suíte Python após `9d3bed2`, 06/11/2026 | 206 testes, 1 falha pré-existente em `test_server.test_deeply_nested_json_reports_400` | verificado em host |
| OTA da CAM com o código novo, 06/11/2026 | 2 falhas (timeout 2%, broken pipe 14%); sucesso na 3a às ~19:27 | verificado em hardware |
| Rota `/mega` da CAM, 06/11/2026 | 401 sem credenciais | verificado em host |
| Divisor D1 -> IO15, 06/11/2026 | 3,3 V | verificado em hardware |
| Reset do Mega pelo BC337 (fio no 3.3V), 06/11/2026 | Reiniciou | relato do dono |
| Gravação do Mega pela CAM, 1a tentativa, 06/11/2026 | Connection reset; Mega com o firmware antigo intacto | verificado em hardware (falha) |
| Gravação do Mega pela CAM, 2a tentativa, 06/11/2026 | HTTP 200 ok, 43688 bytes, 11296 ms, 1 tentativa; LCD com o texto novo (relato do dono) | verificado em hardware |
| Wi-Fi da CAM, 06/11/2026 (noite) | Ping 1 a 6 s, perdas, heartbeats espaçados; melhora após reinício; sem os fios novos também oscila; Mac -> roteador 3,7 ms | verificado em host (ping); verificado em hardware (teste sem fios); causa: inferência |
| Fechadura com LOCK_MODE=1, 06/11/2026 | Abriu; o Mega reinicia quando ela solta (sem 1N4007) | relato do dono; causa: inferência |

Os mesmos números estão registrados em docs/VALIDACAO.md.

## 6. Ferramentas

- Diagramas (02/11/2026): `docs/diagramas/` (SVGs e `LEIAME.md`) e geradores Python em `scripts/diagramas/` (rodar na pasta de saída; caminhos relativos).
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
  Compila todo `cores/arduino`, Wire, EEPROM, Keypad, LiquidCrystal_I2C (obsoleto desde 03/11/2026: LCD em 4 bits, sem I2C e sem o campo `lcd=`; ver seção 4, sessão 5),
  Adafruit_Fingerprint, Crypto (SHA256, Hash, Crypto) e SoftwareSerial. Link com
  `-Os -flto -Wl,--gc-sections -lm`. Tamanho por `avr-size` (flash = .text + .data;
  SRAM = .data + .bss). Não é o arduino-cli.
  Scripts de simavr e o `build_in_docker.sh` acima (pasta temporária, não versionada;
  o build do Mega para o Wokwi é outro, em `simulacao/wokwi/build.sh`):
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
- Simulação Wokwi: `simulacao/wokwi/` (`diagram.json`, `diagram-porta-aberta.json`,
  `wokwi.toml`, `build.sh`, `scenario-boot.yaml`, `scenario-porta-aberta.yaml`,
  `LEIAME.md`). `build.sh` compila o Mega com `Config.example.h` e é o método de
  build do Wokwi, versionado nesse script. `build/` é ignorado pelo Git.
- `wokwi-cli` 0.29.1 em `~/.wokwi/bin`. O token fica no Keychain do Mac (item
  `wokwi-cli-token`), nunca em arquivo. Não ler nem exibir o token.
- Uso do `wokwi-cli`: plano gratuito, 50 min/mês, sessões até 5 min. Consumo total
  aproximado no mês: ~10 de 50 min (30/10/2026). Captura
  (`--screenshot-*`) só numa execução sem cenário, com `--timeout 6000
  --timeout-exit-code 0 --screenshot-time 5000`; junto com cenário, a sessão ficou
  aberta até o limite de 5 min. O atributo `value` do `wokwi-slide-switch` não
  existe (o CLI avisa), e a chave não tem controle documentado para `set-control`.
- Leitura da serial do Mega pelo terminal, sem pyserial (não instalado): script Python com `termios`, porta `/dev/cu.usbserial-1130` (em 02/11/2026 apareceu como `/dev/cu.usbserial-130`; o nome pode variar), 115200. O Serial Monitor do IDE precisa estar fechado. AUTH sempre pelo dono (senha nunca no chat).
- Espelho do LCD na serial: o Mega imprime `LCD| <linha 1> | <linha 2>` sempre que o texto do LCD muda, inclusive sem LCD ligado (`LCD_SERIAL_MIRROR`, padrão 1; pode ser 0 no `Config.h` local). Senhas aparecem só como `*`. Sai sem AUTH, e as linhas podem se intercalar com respostas de comando. Use para acompanhar cadastro e acesso sem display.
- Pinos do clone Mega: a serigrafia desta placa diz "RX1 18" e "TX1 19", mas medido: pino 18 = TX1 e pino 19 = RX1 (como no ATmega2560). Seguir os números. Vale para o DY50: TX do DY50 no D19; D18 no RX pelo 1 kΩ.
- Alicate amperímetro BOMVINK: só 600 V DC (resolução 1 V) para tensão contínua; continuidade sem apito para contatos de teclado (a leitura muda ao apertar a tecla). Pontas: preta em COM, vermelha em VΩ. Usado também para medir resistores (02/11/2026).
- Multímetro Fluke 17B+: o instrumento para medir divisores de tensão (leitura direta). Nas medições de divisor, usar este e não o alicate BOMVINK.

- ESP32-CAM (02/11/2026): comandos do arduino-cli. Os caminhos reais ficam em pastas de trabalho fora do repositório. Trocar os marcadores `<...>` pelos caminhos. A pasta de build contém os segredos do `Config.h` local e deve ser apagada ao fim.
  1. Compilar, sem gravar, sobre a cópia do sketch `firmware/Esp32CamRede` feita pelo dono em pasta fora do repositório (com `--build-path` para pasta fora do repositório):
     `arduino-cli compile --fqbn esp32:esp32:esp32cam:PartitionScheme=min_spiffs --build-path <pasta-de-build> <pasta-da-copia-do-sketch>` (desde 04/11/2026; antes: esp32:esp32:esp32cam)
  2. Gravar, com a CAM ligada só pelo PL2303 (5 V e GND), TXD -> U0R, RXD -> U0T, IO0-GND na própria CAM, fora da protoboard e nunca junto com a MB102:
     `arduino-cli upload -p <porta> --fqbn esp32:esp32:esp32cam:PartitionScheme=min_spiffs --input-dir <pasta-de-build> --upload-property upload.speed=115200 <pasta-da-copia-do-sketch>` (desde 04/11/2026; antes: esp32:esp32:esp32cam)
  3. Porta: listar com `ls /dev/cu.usbserial-*` antes de cada tentativa. O nome muda conforme a entrada USB (`-10`, `-130`, `-1230`). A `-130` era do Mega; não reutilizar nome de outra sessão sem conferir.
  4. Velocidade: o padrão do boards.txt (460800) falhou; em uso 115200; 57600 não conectou.
  5. Evitar hub USB no caminho (ioreg mostrou "USB2.0 HUB"): plugar o PL2303 direto no Mac.
  6. Depois de gravar: tirar IO0-GND e ler a serial da CAM a 115200 (fechar o Serial Monitor do IDE). Esperado: "CAM boot ... camera=ok" e "CAM wifi conectado".

## 7. Pendências abertas (priorizadas)

- 06/11/2026 (sessão 9, atual; noite):
  - (1) Instalar o 1N4007 na fechadura (faixa no +) e confirmar que o Mega não reinicia quando ela solta (em andamento; causa provável: inferência).
  - (2) Commitar os textos do LCD e a piscada do LED (outro agente) e regravar o Mega pela CAM.
  - (3) Ensaios do firmware novo no Mega: 16 teclas, ID+senha, bloqueio na 5a falha, cartão (menu 4 e acesso), digital, eventos e foto no painel, cor do LED (cátodo ou ânodo comum).
  - (4) Decidir o LOCK_MODE final (o Mega está com LOCK_MODE=1 desde a sessão 9).
  - (5) Trocar OTA_PASSWORD, DEVICE_KEY e ADMIN_PIN (senhas apareceram no chat em 06/11/2026). Prioritário.
  - (6) Atualizar README, MONTAGEM, MATERIAIS e TESTES (RC522, ID+senha, gravação pela CAM, montagem do amigo); corrigir a falha pré-existente do teste do servidor.
  - (7) Wi-Fi e alimentação da CAM (adaptador 5 V / 1 A próprio).
  - Riscos aceitos pelo dono: RC522 sem divisores no Mega; IO2 da CAM direto no D0 do Mega (5 V por 1 kΩ do CH340).
- 06/11/2026 (sessão 8; superado em parte pela sessão 9):
  - (1) Passo A (medir o divisor da CAM) antes de ligar o IO13: o registro de 04/11 (meio em 3,3 V, Fluke 17B+) refere-se ao divisor ANTIGO (3 x 330 Ω + 6 x 330 Ω); em 05/11 o divisor foi trocado para 1 kΩ + 2 x 1 kΩ e o meio do divisor NOVO nunca foi medido. Manter o IO13 solto até medir com o Fluke 17B+.
  - (2) Trocar OTA_PASSWORD e DEVICE_KEY (a senha OTA apareceu no chat em 06/11/2026; valores nunca no chat). Prioritário. ADMIN_PIN segue pendente (item (b) de 04/11).
  - (3) Reconferir as 16 teclas do teclado (não verificado desde a remontagem de 04/11). (Superado em 06/11/2026, sessão 9: teclado trocado; reconferir o teclado novo no Mega.)
  - (4) Testar o reinício do modem (reconexão automática da CAM; não verificado).
  - (5) Investigar o ping alto (3,2 a 4,0 s) e a alimentação da CAM (suspeita, inferência).
- 05/11/2026: (i) [superado em 06/11/2026: feito] trocar a CAM para o roteador MARCILIO&PATY por OTA (seção 9, passo B; primeira OTA pela rede); (ii) medir o meio do novo divisor da CAM (1 kΩ + 2 x 1 kΩ) antes de ligar o IO13; (iii) resistor base-GND do BC546 trocado pelo dono de 10 kΩ para 1 kΩ (análise: funciona, ~13 mA no D36; não verificado em hardware); (iv) LCD alimentado por uma trilha solta separada (+ = 5V do Mega, - = GND do Mega), potenciômetro por cabos; medir continuidade da trilha de ponta a ponta (não verificado); (v) diagramas novos 05 (atualizado) e 06 e geradores gen_eletrico.py/gen_montagem_visual.py ainda sem commit; (vi) atalho do servidor na Mesa corrigido para o novo caminho do repositório (~/Desktop/Sistemas embarcados/controle-acesso-esp32).

Bancada (bloqueios de material). Inventário completo e conferências em `docs/MATERIAIS.md`, "Situação do material do dono (31/10/2026)".
- Atualizações de 04/11/2026 (sessão 6, seção 4):
  - Fechadas: (a) relógio, resolvido pela hora do servidor (verificado em hardware); (c) divisor medido (3,3 V com 3 x 330 Ω em cima, Fluke 17B+); (d) montagem de uso da CAM no Mega 1, com IO13/IO14 (verificado em hardware); (e) servidor e teste fim a fim, com hora real e foto; lado de cima da YwRobot; LCD em 4 bits (verificado em hardware); recuperação automática do DY50 (verificado em hardware).
  - Mantidas abertas: (b) trocar ADMIN_PIN e DEVICE_KEY (prioritário; a CAM poderá ser regravada por OTA depois do primeiro teste; até lá, o caminho garantido é a ponte serial do Mega 2, seção 6); teclado 16 teclas após a remontagem (não verificado hoje); `SHOW_TYPED_DIGITS` (não verificado); medir o divisor do DY50 nas colunas novas (não verificado); firmar a emenda do cabo do DY50 (solda ou termorretrátil); Wokwi com LCD paralelo (não executado); falha pré-existente em `tests/test_server.py::test_deeply_nested_json_reports_400`; LED RGB ausente; fechadura (MONTAGEM seção 6); medição do pino 35.
  - Novas: [superado em 06/11/2026: OTA feita por espota.py, seção 4, sessão 8] testar a primeira gravação por OTA (Arduino IDE, porta de rede "controle-cam", ou `arduino-cli upload --protocol network`, com min_spiffs); eventos criados antes do primeiro heartbeat após ligar saem "sem horário" (aceito); lembrar de reiniciar o servidor após atualizar `server.py`; o servidor é a fonte da hora (relógio do Mac); corrigir o desenho da Área de Trabalho (ordem do teclado) se for usado de novo.
- Atualizações de 03/11/2026 (tarde, seção 4, "Sessão 5, continuação"):
  - (a) Relógio sem sincronização: decidir (servidor fornece a hora, ou rede com internet IPv4 para NTP). Pendente.
  - (b) Trocar ADMIN_PIN (Config.h do Mega 1) e DEVICE_KEY (Config.h da CAM e comando do servidor): expostos no chat em 03/11/2026. Pendente, prioritário.
  - (c) Medir o meio do divisor da ponte com 2 em cima antes de reusar. Pendente.
  - (d) Montagem de uso da CAM no Mega 1 (D16 -> divisor -> IO13; IO14 -> D17; 5 V da CAM pelo pino 5V; lado de cima da YwRobot a confirmar). Pendente.
  - (e) Servidor no Terminal do Mac com ADMIN_PIN e DEVICE_KEY no ambiente, e teste fim a fim. Pendente.
  - CAM gravada, boot e rede: verificados em hardware (seção 4, continuação). Este item substitui os de CAM abaixo.
- Atualizações de 03/11/2026 (sessão 5, seção 4):
  - Superado em 04/11/2026 (resolvido, seção 4, sessão 6): confirmar o lado de cima da YwRobot em uso (OFF com 5 V do Mega nas trilhas, ou jumper em 5 V sem o fio 5 V do Mega; nunca os dois). A confirmar com o dono.
  - DY50: falhas intermitentes (`dy50=indisponivel`). Superado em 04/11/2026 quanto à recuperação automática (verificada em hardware; seção 4, sessão 6); a emenda do cabo segue aberta. Testar a recuperação automática (com "DY50 fora do ar", esperar 15 s sem tocar e mandar STATUS); firmar a emenda do cabo (causa provável: inferência). Medir o divisor nas colunas novas: a leitura de 110k de 03/11 nas colunas antigas contradiz os 3 kΩ de 02/11, e a causa não foi identificada.
  - Teclado 4x4: refazer a ligação pela tabela de 02/11 (C1 a C4 = pinos 1 a 4 = D26 a D29; R1 a R4 = pinos 5 a 8 = D22 a D25) e conferir as 16 teclas. Não verificado.
  - Superado em 04/11/2026 (LCD ligado e conferido em hardware; seção 4, sessão 6): LCD 1602 em 4 bits, ligar pela MONTAGEM 3.5, conferir que os pinos 1 e 2 do LCD não estão em curto (a leitura não pode dar 0) e ajustar o contraste no potenciômetro. Não verificado.
  - Espelho com os dígitos digitados: `#define SHOW_TYPED_DIGITS 1` no `Config.h` local (só bancada) e regravação do Mega 1. Não verificado.
  - CAM pela ponte do segundo Mega: medir o ponto do meio antes de ligar o U0R; gravar; ver o boot (`CAM boot ... camera=ok`, `CAM wifi conectado`). Superado em 03/11/2026 (tarde): gravada, boot e rede verificados (seção 4, continuação).
  - Rede da CAM: hotspot do iPhone em 5 GHz e Mac só com IPv6 (inferência: a CAM não alcança o servidor como está). Testar com 2,4 GHz ("Maximizar Compatibilidade"), usar o IP do Mac na faixa 172.20.10.x na URL do `Config.h` da CAM e subir o servidor com `--host 0.0.0.0`. Superado em 03/11/2026 (tarde): rede de teste do Mac em 192.168.2.x, painel conectado (seção 4, continuação; checklist na seção 9).
  - Wokwi com LCD paralelo: rodar a simulação quando o Docker estiver ligado. Não verificado.
  - Investigar a falha pré-existente em `tests/test_server.py::test_deeply_nested_json_reports_400` (também ocorre no HEAD `f44a926` limpo).
  - Skill `/sistema-embarcado` (fora do repositório, do dono): trocar "LiquidCrystal I2C 1.1.2" por "LiquidCrystal 1.0.7". Depende de autorização do dono.
  - Commit das mudanças de 03/11/2026 (seção 3): feito em `e6a9263`, enviado para origin/main a pedido do dono.
- CAM (bloqueio de 02/11/2026; superado em 03/11/2026 tarde: gravada e na rede, seção 4, continuação). Texto histórico: gravação com sucesso não concluída (seção 4, "ESP32-CAM, 02/11/2026"). Hipóteses por inferência: jumpers, hub USB, adaptador PL2303 clone. Próximo passo: seção 9.
- Pasta de build da CAM com os segredos do Config.h compilados: apagada pelo orquestrador em 02/11/2026. Amanhã é preciso recompilar (seção 9, passo 3) e apagar a pasta nova depois da gravação, sem abrir os arquivos.
- Organização física da bancada: fixar as placas, agrupar os fios, usar jumpers curtos e etiquetar. O dono achou a montagem bagunçada (02/11/2026).
- Alimentação definitiva da CAM: adaptador 9 a 12 V / 1 A na YwRobot, ou bateria 12 V com LM2596 em 5,0 V. Decisão do dono.
- Corrente da alimentação: adaptador 7 V / 500 mA no limite para CAM + DY50 (estimativa). Medir ou ter fonte com folga antes de ligar os dois juntos; a decisão é do dono.
- LCD sem módulo I2C: comprar o PCF8574 (atenção ao endereço, 0x27 ou 0x3F; repetir o passo 3 para o LCD). Superado em 03/11/2026: LCD em 4 bits, sem PCF8574 (seção 4, sessão 5).
- Adaptador da CAM resolvido (31/10/2026): USB-serial PL2303 do dono, reconhecido no Mac (`/dev/cu.usbserial-10`), TX em nível de 3,3 V; passo 1 do roteiro feito (ver `docs/VALIDACAO.md`). A base ESP32-CAM-MB não é mais necessária.
- Decisão pendente (dono e dupla, na bancada): se a bateria de 12 V e o step-down não chegarem, a única forma de alimentar a CAM seria o pino 5V do adaptador. Isso é exceção à regra da seção 1 do `docs/MONTAGEM.md` (CAM só com fonte própria); serve no máximo para gravar e ver o boot, e a porta USB pode não aguentar o pico do Wi-Fi. Não usar junto com o step-down.
- Proposta em avaliação (02/11/2026; não executada): alimentar a CAM e o buzzer pela fonte de protoboard YwRobot MB102, com o adaptador de parede de 7 V (corrente do adaptador ainda não informada). Jumper do lado das trilhas de cima em 5V e retirar o fio 5V do Mega da trilha vermelha de cima; o Mega segue só pela USB, com GND comum. Assim a CAM tem fonte própria (regra da seção 1 do `docs/MONTAGEM.md`) e o 5V do adaptador PL2303 não é usado. Condição: corrente do adaptador suficiente (picos da CAM ~500 mA, estimativa; não medidos). A decisão é do dono. Atualizado em 02/11/2026: o passo A foi executado (seção 4, "ESP32-CAM, 02/11/2026"); o fio 5V do Mega saiu da trilha vermelha de cima, e o 5V dessa trilha alimenta o buzzer. A decisão de manter a MB102 como fonte da CAM segue pendente do dono.
- Decisões de 31/10/2026: (a) conversor de nível trocado por divisor de tensão (1 kΩ em série e 2 kΩ ao GND, do D16 ao GPIO13; GPIO14 direto no D17), documentado em `docs/MONTAGEM.md` seção 3.3 e passos 4 a 6; (b) energia: bateria 12 V 5200 mAh para a fechadura e step-down LM2596 ajustado em 5,0 V para a CAM; (c) fica o alicate como multímetro (resolução 1 V; brownout observado pela serial); (d) buzzer: usar o módulo de 3 pinos do dono (conferir se é ativo e se tem transistor); atualizado em 02/11/2026: o módulo S V G é passivo e foi descartado; o buzzer solto de 2 pernas é ativo e está em uso com BC546; (e) driver da fechadura: candidato o módulo relé 5 V do dono.
- Atualizações de 02/11/2026 (sessão 4):
  - LED RGB: módulo ausente (não está com o dono). Pendência de material; o firmware funciona sem ele.
  - Divisor da CAM: o DY50 usa 3 resistores de 1 kΩ (1 em série no D18 e 2 no divisor do RX), sobrando 1 de 1 kΩ. Para o divisor da CAM, usar 330 Ω: 3 em série (~1 kΩ) no lugar do 1 kΩ e 6 em série (~2 kΩ) no lugar do 2 kΩ (mesma proporção).
  - Transistor: BC327-25 (PNP) não serve; em uso, BC546 (NPN).
  - Continuação de 02/11/2026: DY50, espelho do LCD, cadastro e acessos (digital e senha) resolvidos (seção 4, continuação). Pendências novas: falha pré-existente em `tests/test_server.py::test_deeply_nested_json_reports_400` (fora do espelho; `servidor/` não alterado) e o próximo commit. Commit f461412 feito e enviado em 02/11/2026; os registros posteriores de 02/11 entram no próximo commit (antes: 12 arquivos não commitados, aguardando o dono; superado).
  - Ciclo de porta de 02/11/2026 (seção 4, continuação): pendentes a medição do pino 35 (não feita) e firmar a ligação do DY50 (solda ou termorretrátil na emenda do cabo).
  - Ponto de melhoria do DY50 (não bloqueante; decisão do dono em 02/11/2026: não soldar agora): "soldar as emendas do cabo do DY50 e isolar; prender o cabo". Causa provável das quedas: mau contato na emenda ou nos jumpers (inferência).
  - Ensaios não executados (02/11/2026): reset de senha pela USB (RESET); senhas diferentes e senha repetida no cadastro (o ID 2 usou senhas iguais e novas); medição do pino 35; `*` durante a entrada; digital após senha parcial; credencial de outra pessoa no ciclo; só um sensor pressionado; toque curto; 59 s.
- Lista de compras consolidada:
  1. Superado em 03/11/2026 (LCD em 4 bits): Módulo I2C PCF8574 para LCD 1602 (endereço 0x27; se for PCF8574A, 0x3F, e ajustar `LCD_ADDRESS` no `Config.h` local). O dono achou um no Mercado Livre ("placa adaptadora PCF8574 I2C para display LCD 16x2/20x4"). Superado em 03/11/2026: LCD em 4 bits, sem PCF8574; item não mais necessário.
  2. Carregador da bateria de 12 V, se não vier junto (conferir também descarga contínua de 3 A ou mais).
  3. No carrinho do dono: bateria 12 V 5200 mAh e 2 step-down LM2596 com display.
Fechadas na sessão 2 (ver seção 4): MEGA-03, MEGA-04, REQ-E4, TST-02 e MEGA-07.

Descartados pelo dono (30/10/2026): CAM-03 (campo `camera_ready` no heartbeat da
CAM), SRV-02 (índice em `events(received_at)` e política de retenção do banco).

P2:
- Verificação de senha bloqueia o Mega ~1,17 s com 100 cadastros (simulado,
  simavr): LCD, teclado e DY50 param nesse intervalo. Decidir se vale a pena
  uma verificação incremental. Margem da UART da CAM durante o hash: ~20 B no
  buffer de 64 B a 38400 baud, por análise de código; não medida.

P3:
- `lcd=timeout` também aparece com LCD ausente (confirmado em hardware em 30/10/2026). É texto livre: só
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

- Wokwi (simulado, na nuvem do Wokwi; `simulacao/wokwi/`): Mega com LCD I2C (obsoleto desde 03/11/2026: LCD em 4 bits, sem I2C e sem o campo `lcd=`; ver seção 4, sessão 5; desde 03/11/2026 os três diagramas estão em paralelo e ainda não foram executados),
  EEPROM, USB e leitura da porta (D30) em dois cenários. Boot com porta fechada:
  `queued=1`. Boot com porta aberta: `queued=2` (device_boot e forced_open). Captura
  do LCD: "Senha ou digital" / "DY50 fora do ar". Teclado com 16 botões em matriz
  (`diagram-teclado-botoes.json`, no lugar do keypad de membrana, que não tem
  controle de automação): senha errada `123456#` mostra "Acesso negado" com canal
  vermelho do LED RGB em D32; PIN admin `0000000000#` abre o menu (D32 e D34 em 1) e
  a tecla D cancela. Os dois cenários passaram. Buzzer (D36) só checado em repouso,
  não exercitado; saída D35 (fechadura) lida em 0, não acionada. DY50 e ESP32-CAM
  ausentes; o Wokwi não aceita duas placas programáveis no mesmo diagrama. Números
  em docs/VALIDACAO.md.

Pendente:
- Wokwi: só o buzzer (cenário de porta aberta por tempo ou entrada expirada, se
  útil). DY50 e ESP32-CAM seguem fora da simulação.
- Co-simulação Mega (simavr) + ESP32 (QEMU da Espressif): estudada e não feita.
  Viável com ressalvas, 2 a 4 dias; sem Wi-Fi, câmera e periféricos no QEMU; ganho
  pequeno frente à simulação integrada existente. Decisão do dono: não fazer agora.
- simavr: tempo real de escrita na EEPROM (o simavr não modela; o valor de 9 ms
  do `saveRecord` é artefato, e o tempo real estimado é ~160 ms, estimativa:
  ~48 gravações por `saveRecord`, com ~3,3 ms por byte, valor de datasheet
  lembrado pelo revisor e não conferido nesta sessão) e
  estouro da UART da CAM durante o hash (não medido; a imagem não tem os headers
  do libsimavr, que também são necessários para injetar bytes na UART).
- Pico de pilha e heap do Mega: `-fstack-usage` e análise de `String`.
- Painel: fluxo de foto com a CAM real (o fluxo pela API já foi testado no
  navegador; depende da bancada).
- Tudo de hardware continua pendente (bancada), exceto o passo 3 e a matriz do teclado por continuidade (30/10/2026), e exceto o teclado lido pelo Mega, o diagnóstico das 16 teclas, o circuito do buzzer e os resistores medidos (02/11/2026, sessão 4), e na continuação de 02/11/2026 o DY50, o espelho do LCD, o cadastro, os acessos (digital e senha) e o buzzer pelo firmware. Pendentes: LED RGB, CAM, LCD e fechadura. Porta forçada e porta aberta por tempo foram feitas em 02/11/2026 (seção 4, continuação; a porta aberta por tempo é relato do dono).

## 9. Próximo passo exato

Próximo passo exato (06/11/2026, fim da sessão 9), em ordem:
Estado: Mega com o firmware de `bf608b8` gravado pela CAM (LOCK_MODE=1; 1N4007 instalado; fechadura sem reiniciar o Mega); `99fcc71` e `b50bd0b` commitados, NÃO gravados no Mega nem na CAM; CAM em 192.168.1.162; servidor reiniciado às 20:30:24 (antes de `b50bd0b`); Mac fora da MARCILIO&PATY; `/tmp/camb` apagada.
  (1) Mac na MARCILIO&PATY (IP fixo 192.168.1.50); conferir a CAM: `ping 192.168.1.162` e o painel.
  (2) Recompilar a CAM: `"/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli" compile --fqbn esp32:esp32:esp32cam:PartitionScheme=min_spiffs --build-path /tmp/camb firmware/Esp32CamRede`; OTA no Terminal do dono (reiniciar a CAM antes; repetir se der timeout ou broken pipe): `read -s "OTA?Senha OTA: " && echo && python3 ~/Library/Arduino15/packages/esp32/hardware/esp32/3.3.12/tools/espota.py -i 192.168.1.162 -p 3232 -a "$OTA" -f /tmp/camb/Esp32CamRede.ino.bin -r; unset OTA`; depois `rm -rf /tmp/camb`. Conferir a rota: `curl -X POST http://192.168.1.162:8081/mega` -> 401.
  (3) Gravar o Mega pela CAM (alavanca dos 12 V desligada; reiniciar a CAM antes): `cd ~/Desktop/"Sistemas embarcados"/controle-acesso-esp32 && python3 -I scripts/gravar-mega-pela-cam.py --compilar --host 192.168.1.162`; esperado ok:true e LCD "Controle acesso".
  (4) Reiniciar o servidor (Ctrl+C e atalho rodar-servidor-controle.command), porque `server.py` mudou (`card_unlinked`).
  (5) Ensaios: 16 teclas; ID+senha certa e errada; bloqueio na 5a falha (LED vermelho piscando devagar, "Teclado travado"); cartão desconhecido; menu 4 vincular; acesso por cartão; menu 5 remover; digital; depois de cada acesso, cartão e digital devem voltar a ler sem reiniciar o Mega (valida o reinício automático); nenhum forced_open falso; cores do LED pelo mapa; painel sem novos descartes.
  (6) Investigar por que o relé fecha no boot (medir D35 durante o reset; conferir o 10 kΩ no sinal do relé); hardware opcional: 4,7 kΩ + 100 nF em D30/D31.
  (7) Decidir o LOCK_MODE final (`docs/MONTAGEM.md`, seção 6); trocar OTA_PASSWORD, DEVICE_KEY e ADMIN_PIN (valores nunca no chat); atualizar README, MONTAGEM, MATERIAIS e TESTES; Wi-Fi e alimentação da CAM; corrigir a falha pré-existente do teste do servidor.
  (8) A skill `/sistema-embarcado` aponta para o caminho antigo `~/Desktop/controle-acesso-esp32`; o repositório está em `~/Desktop/Sistemas embarcados/controle-acesso-esp32` (o dono decide corrigir).

Próximo passo exato (06/11/2026, noite; sessão 9; superado pelo bloco do fim da sessão 9 acima: itens 1 e 2 concluídos; mantido como histórico), em ordem:
Estado: Mega gravado pela CAM com o firmware de `160534d` e LOCK_MODE=1 (fechadura abre, mas o Mega reinicia quando ela solta); CAM em 192.168.1.162 com a rota `/mega` (porta 8081); Wi-Fi da CAM instável; textos do LCD e piscada do LED em andamento (outro agente, não commitados).
  (1) Instalar o 1N4007 na fechadura com os 12 V desligados, faixa no + da fechadura (`~/Desktop/Sistemas embarcados/diodo-fechadura.svg`), e confirmar que o Mega não reinicia quando a fechadura solta. Se reiniciar, separar a alimentação do Mega ou pôr capacitor no VIN.
  (2) Commitar os textos do LCD e do LED se ainda não estiverem commitados e regravar o Mega pela CAM (12 V desligados durante a gravação): `python3 -I scripts/gravar-mega-pela-cam.py --compilar --host 192.168.1.162` (reiniciar a CAM antes se o Wi-Fi estiver lento).
  (3) Ensaios do firmware novo no Mega: 16 teclas, ID+senha certa e errada, bloqueio na 5a falha, cadastro de cartão (menu 4) e acesso por cartão, digital, eventos e foto no painel, cor do LED (confirmar cátodo ou ânodo comum).
  (4) Decidir o LOCK_MODE final (`docs/MONTAGEM.md`, seção 6).
  (5) Trocar OTA_PASSWORD, DEVICE_KEY e ADMIN_PIN (CAM por OTA; Mega pela CAM). Valores nunca no chat.
  (6) Atualizar README, MONTAGEM, MATERIAIS e TESTES com o RC522, o ID+senha, a gravação pela CAM e a montagem do amigo; corrigir a falha pré-existente do teste do servidor.
  (7) Investigar o Wi-Fi e a alimentação da CAM (adaptador 5 V / 1 A próprio).

Próximo passo exato (06/11/2026, sessão 8; superado pelo bloco da noite acima; mantido como histórico), em ordem:
Estado: CAM na rede MARCILIO&PATY (192.168.1.162 em 06/11; o IP pode mudar); servidor no Mac em 192.168.1.50 (escutando 0.0.0.0:8080); heartbeats com clock_synced=1. O passo B de 05/11 foi concluído em 06/11 (primeira OTA, verificada em hardware).
- Rede padrão: MARCILIO&PATY, com o Mac em 192.168.1.50 fixo (Wi-Fi > Detalhes > TCP/IP manual; fora da faixa DHCP 100 a 200). A rede de testes do iPhone (192.168.2.x) fica só como plano B para OTA.
- OTAs futuras: espota.py direto no IP da CAM na rede da casa, achado com `dns-sd -G v4 controle-cam.local` (o IP pode mudar). `arduino-cli upload --protocol network` numa execução avulsa falhou em 06/11; não usar. Compilar com min_spiffs em pasta fora do repositório e depois rodar, numa linha:
  `read -s "OTA?Senha OTA: " && echo && python3 ~/Library/Arduino15/packages/esp32/hardware/esp32/3.3.12/tools/espota.py -i <IP da CAM> -p 3232 -a "$OTA" -f <pasta-de-build>/Esp32CamRede.ino.bin -r; unset OTA`
  A senha OTA é digitada escondida, nunca no chat. Não usar `-d`. Apagar a pasta de build depois.
- Ordem:
  (1) Passo A (medir o divisor da CAM) antes de ligar o IO13: o registro de 04/11 (meio em 3,3 V, Fluke 17B+) refere-se ao divisor ANTIGO (3 x 330 Ω + 6 x 330 Ω); em 05/11 o divisor foi trocado para 1 kΩ + 2 x 1 kΩ e o meio do divisor NOVO nunca foi medido. Manter o IO13 solto até medir com o Fluke 17B+.
  (2) Trocar OTA_PASSWORD e DEVICE_KEY por OTA (DEVICE_KEY também no comando do servidor). Valores nunca no chat. ADMIN_PIN, do Mega, segue pendente (seção 7, item b).
  (3) Reconferir as 16 teclas (espelho serial, porta fechada, verdes D30/D31 ao GND).
  (4) Testar o reinício do modem: a CAM deve voltar sozinha ("CAM wifi conectado" e heartbeat voltando).
  (5) Ensaios funcionais de bancada de `docs/TESTES.md`, ainda não executados.
  (6) Fechadura por último (`docs/MONTAGEM.md`, seção 6), com LOCK_MODE=0 até lá.
- Fora da ordem: investigar o ping alto (3,2 a 4,0 s) e a alimentação da CAM (fonte 7 V / 500 mA).
- Estado ao parar (06/11/2026): CAM na MARCILIO&PATY com heartbeat e clock_synced=1; OTA_PASSWORD, DEVICE_KEY e ADMIN_PIN a trocar; 16 teclas por reconferir; LOCK_MODE=0 (regra da seção 2). Docs desta sessão não commitados.

Próximo passo exato (05/11/2026; passo B superado em 06/11/2026, ver bloco acima; mantido como histórico), assim que a bancada for religada (antes dos itens de 04/11 abaixo):
A) Religar pela montagem nova (docs/diagramas/06-montagem-visual.svg e 05-esquema-eletrico.svg; imagens também na Mesa do dono). Com o Mega ligado e o fio do IO13 SOLTO, medir o meio do divisor da CAM (agora 1 kΩ do D16 ao meio + 2 x 1 kΩ do meio ao GND; coluna 26 no desenho): esperado ~3,3 V. (o D16 fica em nível alto em repouso com o firmware do Mega rodando e o link parado; medir entre o meio e o GND). Só então ligar o IO13.
B) [CONCLUÍDO em 06/11/2026: CAM em 192.168.1.162 e servidor em 192.168.1.50] Trocar a CAM para o roteador novo (MARCILIO&PATY, 2,4 GHz canal 10, WPA/WPA2) por OTA. Estado: Config.h local da CAM já editado pelo dono (WIFI_SSID, WIFI_PASSWORD, SERVER_URL http://192.168.1.170:8080); cópia do Config.h antigo em ~/Desktop/Sistemas embarcados/Config-cam-rede-mac.h (fora do repo); firmware compilado em /tmp/camb às 09:48 de 05/11 (imagem Esp32CamRede.ino.bin de 1115376 B, por ls; se /tmp/camb sumir, recompilar da raiz do repositório com `"/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli" compile --fqbn esp32:esp32:esp32cam:PartitionScheme=min_spiffs --build-path /tmp/camb firmware/Esp32CamRede`). Pré-testes feitos em 05/11: senha do Config.h conferida pelo dono no iPhone (relato do dono; na CAM, não verificado); servidor em *:8080 respondeu ao iPhone na MARCILIO&PATY (verificado em hardware); Mac em 192.168.1.170 com endereço Wi-Fi privado Fixo (verificado em host); firewall do macOS libera o Python (verificado em host). Sem acesso ao roteador TIM (superado em 06/11/2026: acesso obtido; o roteador não tem reserva de DHCP) (senha da etiqueta não funcionou): sem reserva de DHCP; se o IP do Mac mudar, regravar SERVER_URL por OTA.
   Passos: (1) parar o servidor (Ctrl+C); (2) iPhone no cabo USB; Compartilhamento de Internet de "iPhone USB" para só Wi-Fi, canal 1/6/11; (3) ligar a CAM (IO0 solto); conferir no Mac `ifconfig bridge100 | grep "inet "` = 192.168.2.1 e `ping 192.168.2.2`; (4) enviar por OTA para 192.168.2.2: no Terminal do dono, numa linha: `cd ~/Desktop/"Sistemas embarcados"/controle-acesso-esp32 && read -s "OTA?Senha OTA: " && echo && "/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli" upload --fqbn esp32:esp32:esp32cam:PartitionScheme=min_spiffs --port 192.168.2.2 --protocol network --upload-field password="$OTA" --input-dir /tmp/camb firmware/Esp32CamRede; unset OTA` (a senha OTA é digitada escondida, nunca no chat); (5) desligar o Compartilhamento, reconectar o Mac na MARCILIO&PATY, rodar o atalho do servidor; (6) achar a CAM na rede nova (`dns-sd -B _arduino._tcp`, "controle-cam") (encerrar com Ctrl+C) e conferir painel "ESP32 conectado" e devices.clock_synced=1; (7) apagar /tmp/camb. Plano B: se o envio falhar, a CAM continua com o firmware antigo na rede do Mac; repetir. Se o envio concluir mas a CAM não aparecer na MARCILIO&PATY em 2 minutos: regravar pela ponte do Mega 2 (seção 6); para insistir na rede nova, corrigir WIFI_SSID/WIFI_PASSWORD no Config.h atual; para voltar à rede do Mac, copiar ~/Desktop/Sistemas embarcados/Config-cam-rede-mac.h por cima de firmware/Esp32CamRede/Config.h (o dono faz) e recompilar.

Próximo passo exato (04/11/2026), em ordem:
0) Antes de qualquer passo: `LOCK_MODE=0` no Config.h local do Mega, fechadura desconectada; USB e chave da YwRobot desligadas ao mexer na fiação.
1) Trocar ADMIN_PIN (Config.h do Mega 1) e DEVICE_KEY (Config.h da CAM e comando do servidor). A CAM poderá ser regravada por OTA depois do primeiro teste (passo 3); até lá, o caminho garantido é a ponte serial do Mega 2 (seção 6). Pendente (seção 7, item b). Valores nunca no chat.
2) Conferir as 16 teclas do teclado após a remontagem (espelho serial, porta fechada, verdes D30/D31 ao GND). Não verificado.
3) (Substituído pelo passo B de 05/11 acima; OTA feita em 06/11/2026, seção 4, sessão 8.) Testar a OTA de verdade (executável sem esta conversa; pré-requisito: `OTA_PASSWORD` definido no Config.h local da CAM):
   a) Compilar com o Config.h local (a /tmp/camb foi apagada; recompilar): `"/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli" compile --fqbn esp32:esp32:esp32cam:PartitionScheme=min_spiffs --build-path /tmp/camb firmware/Esp32CamRede`.
   b) Enviar pela rede: na Arduino IDE, escolher a porta de rede "controle-cam"; ou `arduino-cli upload --fqbn esp32:esp32:esp32cam:PartitionScheme=min_spiffs --port 192.168.2.2 --protocol network --upload-field password=<senha OTA do Config.h> --input-dir /tmp/camb firmware/Esp32CamRede`. A senha é digitada só no Terminal, nunca no chat.
   c) Sucesso = envio concluído; a CAM reinicia e volta a responder ping em 192.168.2.2; painel "ESP32 conectado" e relógio sincronizado (`devices.clock_synced=1`).
   d) Depois, apagar /tmp/camb.
   e) Se falhar, usar a ponte serial (seção 6) e ver `docs/MONTAGEM.md`, "Partição e OTA".
   Registrar o resultado em docs/VALIDACAO.md.
4) Ensaios funcionais de bancada de `docs/TESTES.md` ainda não executados (seção "Ensaios funcionais de bancada").
5) Só depois, o ensaio da fechadura (`docs/MONTAGEM.md`, seção 6).

Como religar a rede de testes (atualizado em 04/11/2026):
- iPhone no cabo USB, "Permitir Que Outros Acessem" ligado.
- Mac: se o Wi-Fi estiver no hotspot do iPhone, desconectar. Internet Sharing de "iPhone USB" para Wi-Fi, 2,4 GHz, só Wi-Fi. Se o bridge100 não aparecer, trocar para o outro "iPhone USB" da lista. `ifconfig bridge100 | grep "inet "` deve mostrar 192.168.2.1.
- Servidor: reiniciar se `servidor/server.py` mudou. Um servidor anterior à atualização não manda server_time. ADMIN_PIN e DEVICE_KEY só no ambiente, nunca no chat.
- CAM: "CAM wifi conectado 192.168.2.x" e painel "ESP32 conectado" com último contato atualizando. Hora: `devices.clock_synced=1`.

Estado ao parar (04/11/2026): tudo funcionando fim a fim, com hora real e foto; `LOCK_MODE=0`, fechadura desconectada; ADMIN_PIN e DEVICE_KEY ainda a trocar; OTA não testada pela rede; commit desta sessão: ver git log.

Blocos anteriores, mantidos como histórico.

Próximo passo exato anterior (03/11/2026, fim da tarde), em ordem:
0) Antes de qualquer passo: `LOCK_MODE=0` no Config.h local do Mega, fechadura desconectada; USB e chave da YwRobot desligadas ao mexer na fiação.
1) Trocar ADMIN_PIN (Config.h do Mega 1) e DEVICE_KEY (Config.h da CAM e comando do servidor); regravar as placas afetadas (Mega 1 pela IDE; CAM pelo método da seção 6, com o divisor medido). Pendente (seção 7, item b). Valores nunca no chat.
2) Decidir o relógio: o servidor fornece a hora, ou rede com internet IPv4 para NTP (seção 7, item a).
3) Montagem de uso da CAM no Mega 1 (seção 7, item d), seguindo `docs/MONTAGEM.md` e o passo 5 do bloco de 02/11 (D16 -> divisor -> IO13; IO14 -> D17). Antes, medir o divisor: meio entre 2,5 e 3,3 V (lembrar que o alicate pode ler baixo, seção 4). Sem 5 V em GPIO; 5 V da CAM só pelo pino 5V; lado de cima da YwRobot ainda a confirmar; Mega 2 fora da montagem.
4) Servidor e rede do Mac: seguir o checklist "Como religar a rede de testes" (seção 4, sessão 5 continuação), passos 1 a 5. Depois, teste fim a fim: `docs/MONTAGEM.md` seção 5, passos 5 a 7.

Como religar a rede de testes (checklist anterior, 03/11/2026; detalhe na seção 4):
- iPhone no cabo USB, "Permitir Que Outros Acessem" ligado.
- Mac: Internet Sharing de "iPhone USB" para Wi-Fi, 2,4 GHz (canal 1, 6 ou 11), só Wi-Fi; `ifconfig bridge100 | grep "inet "` mostra 192.168.2.1.
- Servidor no Terminal, com ADMIN_PIN e DEVICE_KEY no ambiente (valores fora do chat).
- CAM: "CAM wifi conectado 192.168.2.x" e painel "ESP32 conectado" com último contato atualizando.

Ainda pendentes do bloco da manhã (não executados): teclado 16 teclas (refazer pela tabela de 02/11 e conferir as 16 teclas); DY50 (teste "DY50 fora do ar" com 15 s sem tocar, e divisor nas colunas novas); LCD 1602 em 4 bits.

Estado ao parar (03/11/2026, tarde): CAM gravada, com boot e Wi-Fi verificados e conexão contínua na rede de teste; NTP falha; PIN e chave expostos (a trocar); foto da CAM ao servidor e UART de uso não verificadas; setSleep commitado no commit da tarde de 03/11 (seção 3; ver git log); `LOCK_MODE=0`.

Próximo passo anterior (03/11/2026, manhã), em ordem:
Antes de qualquer passo: `LOCK_MODE=0` no Config.h local, fechadura desconectada, USB e chave da YwRobot desligadas ao mexer na fiação.
1. Terminar a ligação do teclado pela tabela de 02/11 (seção 4, sessão 4): pinos 1 a 4 = C1 a C4 = D26 a D29; pinos 5 a 8 = R1 a R4 = D22 a D25. Com a USB desligada. Não seguir o desenho da Área de Trabalho.
2. Confirmar a configuração do lado de cima da YwRobot: jumper OFF com o 5 V do Mega nas trilhas de cima (diagrama 03), ou jumper em 5 V com a fonte e sem o fio 5 V do Mega. Nunca o jumper de cima em 5V E o fio 5V do Mega nas trilhas de cima ao mesmo tempo; nunca o 5V do Mega na trilha de 3,3 V. Leituras esperadas com o alicate BOMVINK (lê cerca de 1 V abaixo): com o jumper de cima OFF, USB desconectada e chave da YwRobot ligada, trilha de baixo "003" e trilha de cima "000"; depois de ligar a USB, trilha de cima "004" ou "005". Conferir com o alicate antes de ligar a USB.
3. Acrescentar `#define SHOW_TYPED_DIGITS 1` no `Config.h` local (só bancada; não versionar) e regravar o Mega 1 pela IDE (placa "Arduino Mega or Mega 2560"). Conferir no espelho `LCD|` da serial que os dígitos aparecem; o LCD físico segue mascarado. Não colar esses logs no chat. Com a flag ligada, não digitar o PIN de administrador real nem senhas de uso; usar valores de teste. Depois do ensaio, remover a linha do Config.h local e regravar.
4. Conferir as 16 teclas pelo espelho serial, com a porta fechada (verdes D30/D31 ao GND).
5. Porta forçada: feito em 03/11/2026 (relato do dono; ver seção 4, sessão 5). Não repetir sem motivo.
6. DY50: medir o divisor nas colunas novas (valores esperados por cálculo [1 kΩ + 2 kΩ; medidos em 02/11 nas colunas antigas]: coluna do D18 até GND ~3 kΩ; coluna do RX até GND ~2 kΩ) e explicar a leitura de 110k de 03/11; firmar a emenda do cabo; depois, com "DY50 fora do ar", esperar 15 s sem tocar e mandar STATUS.
7. LCD 1602 em 4 bits pela MONTAGEM 3.5 (pinos 1 e 2 do LCD sem curto: a leitura não pode dar 0; contraste no potenciômetro de 10 kΩ). Não verificado.
8. (superado pelo bloco da tarde, acima) CAM pelo segundo Mega, conforme o bloco de 02/11 mais abaixo (medir o ponto do meio antes de ligar o U0R). Rede: iPhone em "Maximizar Compatibilidade" (2,4 GHz), IP do Mac 172.20.10.x na URL da CAM, servidor com `--host 0.0.0.0`. Só ligar o U0R com leitura "002" no meio do divisor; com "003" ou mais, nunca ligar à CAM. Nunca 5 V em GPIO da CAM; a CAM recebe 5 V só no pino 5V.
9. Registrar os resultados em `docs/VALIDACAO.md` e `docs/HANDOFF.md`. Commit das mudanças de 03/11 só quando o dono pedir (stage por arquivo).

Estado ao parar (03/11/2026, sessão 5): Mega 1 com o firmware de 4 bits gravado (LCD ainda não ligado); alarme de porta forçada verificado pelo relato do dono; DY50 intermitente, voltou após RESET; teclado sendo refeito pela tabela; lado de cima da YwRobot não confirmado; CAM não gravada (fiação da ponte pelo segundo Mega feita, medição não informada); mudanças não commitadas sobre `f44a926`; `SHOW_TYPED_DIGITS` ainda não ativo na bancada; Wokwi não executado; `LOCK_MODE=0`.

- Remontagem/organização dos cabos: usar `docs/diagramas/` (LEIAME.md). Os SVGs e os geradores em `scripts/diagramas/` servem de base para o dono refazer as conexões.

Próximo passo anterior (CAM, ponte pelo Mega, 02/11/2026; ainda vigente para a CAM (passos 1 a 6, ponte pelo Mega — agora o Mega 2); superado só no restante pelo bloco de 03/11/2026, acima):
1. Conferir a montagem da ponte pelo desenho e pela lista da seção 4 (fios no conector POWER do Mega e na CAM; RESET -> GND; IO0-GND; 9 resistores de 330 Ω nas colunas 40 a 49; pino 0 -> coluna 40; coluna 49 -> GND; U0T -> pino 1; fio coluna 43 -> U0R ainda NÃO ligado). Chave da YwRobot desligada.
2. MEDIÇÃO OBRIGATÓRIA ANTES DE LIGAR O U0R (não pular):
   - Montagem: Mega na USB; RESET no GND; fio coluna 43 -> U0R DESLIGADO; medir coluna 43 -> GND com o alicate BOMVINK.
   - Os valores abaixo são ESTIMATIVA por cálculo, não verificada em hardware. Limites da ESP32: nível alto ≥ ~2,47 V; máximo 3,6 V.
   - Tabela (placa do Mega x montagem):

     | Placa do Mega | Montagem | Tensão no U0R | Ação |
     |---|---|---|---|
     | sem resistor interno | 3+6 x 330 Ω | 3,33 V ("002") | ok, ligar o U0R |
     | com 1 kΩ interno (comum em Mega/clones) | 3+6 x 330 Ω | 2,49 V ("001") | no limite: tirar os 3 primeiros (pino 0 direto na coluna 43) e medir de novo |
     | com 1 kΩ interno | só 6 x 330 Ω | 3,32 V ("002") | ok |
     | sem resistor interno | só 6 x 330 Ω | 5,0 V ("004"/"005") | NUNCA ligar à CAM |

   - Regra: só ligar o U0R com leitura "002" (ou a linha "ok" da tabela). Em "003" ou mais, parar. Nunca ligar a coluna 43 a U0R com "004"/"005".
   - Outras estimativas (não verificadas): U0T -> pino 1 direto é seguro (CH340 reconhece alto a partir de ~2 V; pela ficha). 5V do Mega via USB ~4,8 V basta ao regulador da CAM (precisa ≥ 4,4 V). Com RESET no GND, os pinos 0/1 do ATmega ficam em alta impedância e o firmware do Mega não é apagado.
   - Diagnóstico na gravação: o aviso "Detected crystal freq" do esptool deve ficar perto de 40 MHz com o CH340 (com o PL2303 deu 41,07-41,59). O alicate BOMVINK lê cerca de 1 V abaixo (3,3 V aparece como "002"; 5 V como "004"/"005").
3. SÓ COM A MEDIÇÃO "002" (passo 2): ligar o fio coluna 43 -> U0R e recompilar a CAM (`arduino-cli compile --fqbn esp32:esp32:esp32cam --build-path <pasta temporária> firmware/Esp32CamRede`, com o Config.h local) e gravar pela porta do Mega (CH340), primeiro com o upload normal a 115200 (`ls /dev/cu.usbserial-*` antes). Apagar a pasta temporária depois.
4. Ver o boot: a 115200 na porta do Mega, com RESET ainda no GND e IO0 fora. Esperado: "CAM boot ... camera=ok" e "CAM wifi conectado".
5. Converter para a montagem de uso, reaproveitando o divisor: tirar RESET-GND e IO0-GND; pino 0 sai; D16 -> coluna 40; coluna 43 -> IO13 (no lugar de U0R); U0T/pino 1 sai; IO14 -> D17; 5V e GND da CAM nas trilhas de cima (5 V da YwRobot).
6. Iniciar o servidor (`python3 servidor/server.py --host 0.0.0.0 --port 8080`, com `ADMIN_PIN` e `DEVICE_KEY` no ambiente) e seguir `docs/MONTAGEM.md` seção 5, passos 4 a 7. Mega só pela USB; GND comum.

Retomada: a combinar com a dupla do dono (hardware).

Estado ao parar anterior (02/11/2026, sessão 4): Mega gravado com o firmware atual (Config.h local com ADMIN_PIN do dono e LOCK_MODE=0); teclado 4x4 soldado e ligado conforme a tabela da seção 4, sessão 4; D30 e D31 ao GND pela trilha azul de cima da protoboard (GND do Mega), não direto ao pino GND; buzzer montado no circuito com BC546 e fio de teste no D36; LED RGB ausente; DY50 energizado pela MB102 (fonte de parede de 7 V; saída 3,3 V) e comunicando (`dy50=ok`); cadastro do ID 1 feito e acessos pela digital e pela senha verificados (seção 4, continuação); espelho do LCD na serial gravado pelo dono; CAM sem bateria e sem step-down; mudanças do espelho e dos docs commitadas em f461412. Ciclo de porta verificado em 02/11/2026 (seção 4, continuação); pendentes: medição do pino 35 (não feita) e firmar a ligação do DY50.

Estado da CAM ao parar anterior (02/11/2026): compilada (IDE e arduino-cli; ver seção 4); não gravada com sucesso. Config.h local preenchido pelo dono (valores não registrados). Passo A da alimentação feito: fio 5V do Mega retirado da trilha vermelha de cima (registrado aqui; não voltar a ligar nela); jumper de cima da MB102 em 5V (trilha de cima "005", de baixo "003"); trilha de 5 V de cima alimenta o buzzer. Mega só pela USB. Adaptador 7 V / 500 mA. PL2303 com 5 V só para gravar a CAM, fora da protoboard, nunca junto com a MB102 (decisão do dono). Pasta de build da CAM com segredos no scratchpad: apagada pelo orquestrador em 02/11/2026 (seção 7); recompilar amanhã (seção 9). Ponte pelo Mega: medição do ponto do meio não feita; CAM não gravada (seção 4, "Fatos novos"). Commits do dia: f461412 e f75e6cc enviados; as atualizações posteriores de HANDOFF/VALIDACAO (estado da CAM) ainda não commitadas. Nada foi gravado na CAM nem a fechadura foi acionada nesta data.

Teclado: o diagnóstico das 16 teclas foi feito em 02/11/2026 com um sketch temporário (DiagTeclado, fora do repositório, não versionado): 16 de 16 teclas OK (seção 4, sessão 4). O MegaControlador foi regravado depois do diagnóstico: linha BOOT `BOOT boot=26 storage=ok lcd=timeout dy50=indisponivel lock_mode=0`; o contador foi de 23 para 26, o que indica (inferência pelo contador) que o diagnóstico não alterou a EEPROM. Lição: os jumpers verdes D30/D31 ao GND precisam estar presentes em todos os testes de teclado; sem eles a porta é vista aberta. Conferir se o USB está conectado antes de mexer na fiação. Convenção combinada: preto = GND; vermelho = 5 V (nunca sinal); verde = sensores da porta D30/D31 (e R3 do teclado); demais cores para sinais conforme as tabelas.

Ordem sugerida anterior (a partir de 02/11/2026):
1. Ensaios de `docs/TESTES.md` ainda não executados (os itens marcados como não executados e os ensaios funcionais de bancada), exceto porta forçada e porta aberta por tempo, feitas em 02/11/2026 (seção 4, continuação; `docs/TESTES.md` pode ainda marcá-las como não executadas). Manter os verdes D30/D31 ao GND em todos os testes de porta; sem eles a porta é vista aberta. Conferir `dy50=ok` no STATUS após qualquer reinício.
   - Lado das trilhas de cima da MB102: OFF, medido `000` antes de ligar a USB (ver seção 4, continuação, e `docs/MONTAGEM.md` 3.9). Nunca ligar o 5V do Mega na trilha de 3,3 V. Superado em 02/11/2026 (passo A da CAM): jumper de cima em 5V, com o fio 5V do Mega retirado dessa trilha (ver Estado ao parar).
2. LED RGB (`docs/MONTAGEM.md` 3.7; módulo ausente em 02/11/2026): quando houver a peça, antes de energizar, verificar se o módulo tem resistores na placa; se não tiver, um resistor por canal, valor pela ficha. Conferir `RGB_COMMON_ANODE` no `Config.h` local (cátodo comum = `false`, como no `Config.example.h`). Pinos: R -> D32, G -> D33, B -> D34, GND -> GND. Checar: boot com LED apagado; em repouso, pisca azul 200 ms a cada 60 s; tirar um jumper de D30 ou D31 (porta aberta sem autorização) deve levar a alarme com vermelho piscando (350 ms) e `forced_open` (queued +1); só o LED, o buzzer não toca nesse caso. Comportamento esperado por análise de código do firmware, não verificado em hardware.
3. CAM (próximo passo, a combinar com a dupla): integração da ESP32-CAM. Atualizado em 02/11/2026: pacote esp32 3.3.12 e ArduinoJson 7.4.3 instalados no IDE; CAM compilada; gravação não concluída (ver o próximo passo no topo desta seção). Antes (superado): instalar o pacote esp32 3.3.12 no Arduino IDE; alimentação de 5 V com folga (ver a decisão pendente na seção 7); `Config.h` local da CAM preenchido pelo dono (Wi-Fi, URL e chave; o agente não abre esse arquivo); servidor rodando no Mac. Depois, seguir os passos 2, 4 a 7 da seção 5 de `docs/MONTAGEM.md`. O passo 1 já foi feito com o adaptador PL2303. Divisor da CAM com resistores de 330 Ω (seção 7). Alimentação da CAM: proposta pela MB102 (seção 7); passo A executado em 02/11/2026, a decisão final segue com o dono.
4. LCD: quando o PCF8574 chegar, repetir o passo 3 da seção 5 de `docs/MONTAGEM.md` só para o LCD. Superado em 03/11/2026: LCD em 4 bits (passo 7 do bloco de 03/11/2026).
5. Depois, os itens antigos: revisão elétrica opcional (`docs/MONTAGEM.md` e `docs/MATERIAIS.md`), Wokwi com só o buzzer pendente, P2 de verificação de senha, e a falha pré-existente de `tests/test_server.py::test_deeply_nested_json_reports_400`.
6. Próximo commit: commit f461412 feito e enviado em 02/11/2026; os registros posteriores de 02/11 entram no próximo commit (antes: decisão pendente sobre 12 arquivos não commitados; superado). Stage por arquivo; nada de commit sem o dono decidir.

Depois, o roteiro de bancada existente:
1. Configuração local, sem versionar:
   - `ADMIN_PIN` (10 dígitos) em `firmware/MegaControlador/Config.h`, arquivo
     ignorado pelo Git.
   - `ADMIN_PIN` e `DEVICE_KEY` (16+ caracteres) no ambiente do servidor.
   - Wi-Fi, URL e chave em `firmware/Esp32CamRede/Config.h`.
2. Na bancada, com `LOCK_MODE=0` e fechadura desconectada: seguir
   `docs/MONTAGEM.md` seção 1 (segurança) e seção 5, passos 1 a 7.
3. Depois: `docs/TESTES.md`, "Ensaios funcionais de bancada".
4. Só então o ensaio da fechadura (`docs/MONTAGEM.md` seção 6).

Ensaios físicos: passo 3 (Mega pelo USB, sem LCD), em 30/10/2026; teclado 4x4 lido pelo Mega (02/11/2026, verificado em hardware); circuito do buzzer com BC546 e buzzer pelo firmware, DY50 comunicando, cadastro e acessos pela digital e pela senha (02/11/2026, verificado em hardware). A bancada depende do dono e do hardware.
