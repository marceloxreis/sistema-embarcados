# Handoff: controle de acesso ESP32 (estado em 30/10/2026)

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

## 3. Estado Git

- Branch `feat/mega-esp32cam` com o commit `6b09569` ("Arquitetura Mega 2560 +
  ESP32-CAM com foto por acesso autorizado"), enviado a origin.
- Esse commit será incorporado à `main` por merge fast-forward logo após esta
  atualização do handoff.
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
- DY50 e LCD se recuperam sozinhos. LCD usa sonda I2C e não bloqueia.
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
- Suíte: de ~54 s para ~28 s.

**Documentação**
- `MONTAGEM.md`: fio a fio, roteiro de bancada de 7 passos, ensaio seguro da
  fechadura.
- `TESTES.md`: ensaios funcionais de bancada.
- `README`, `ESCOPO`, `PLANO`, `VALIDACAO`, `MATERIAIS`
  atualizados. Versão DevKit removida.

## 5. Verificação (30/10/2026)

| Verificação | Resultado | Evidência |
|---|---|---|
| Suíte Python: `CONTROLE_TEST_LIBS=<pasta das libs de teste> CONTROLE_TEST_STRICT=1 python3 -m unittest discover -s tests -q` | 126 testes OK, 0 skipped, 28 s | verificado em host (reexecutado neste handoff) |
| Mega `arduino:avr:mega` | 38996 B de flash, 4510 B de SRAM global, sem avisos | compilado, container Linux local |
| CAM `esp32:esp32:esp32cam` | 1055069 B de flash, 60608 B de RAM global | compilado |
| `node --check` do painel | OK | verificado em host |
| Ensaio físico | nenhum | não verificado |

Os mesmos números estão registrados em docs/VALIDACAO.md.

## 6. Ferramentas

- Arduino CLI e cores ESP32/AVR ficam em uma pasta de trabalho externa
  (`work/`, fora do repositório).
- ctags ARM64 configurado via `runtime.tools.ctags.path`.
- Mega compilado em container Linux local, imagem `controle-acesso-avr-probe:local`.
- Bibliotecas de teste: `scripts/bootstrap-test-libs.py`.
- Os testes C++ recortam trechos do `.ino` por marcadores de texto. Se mudar
  assinatura ou marcador, confira `tests/` antes.

## 7. Pendências abertas (priorizadas)

P2:
- MEGA-03: corte de energia entre gravar o modelo no DY50 e salvar o registro
  na EEPROM deixa digital órfã; a mesma pessoa não consegue recadastrar
  ("Slot DY orfao"). `firmware/MegaControlador/MegaControlador.ino` (fluxo de
  cadastro, `fingerFastSearch` na primeira digital).
- MEGA-04: qualquer retorno não-OK de `getImage` (IMAGEFAIL/TIMEOUT) aborta o
  cadastro inteiro; tolerar algumas falhas transitórias.
- REQ-E4: com `storageReady=false` a digital mostra "Acesso negado / Cadastro
  inativo" (enganoso) e `confirmEnrollment` retorna sem mensagem até o timeout;
  E4 exige mensagem explícita de erro de armazenamento.
- CAM-03: falha da câmera não chega ao servidor; acrescentar campo
  `camera_ready` ao heartbeat (CAM + `server.py` + painel).
- TST-02: faltam testes do Mega para debounce de 50 ms, cores do RGB
  (`outputsTick`), texto do LCD com ID, tecla D/`*`/`#` e `pin_in_use`;
  `outputsTick` e `doorTick` reais não são compilados nos testes.
- SRV-02: banco sem índice em `events(received_at)` e sem política de retenção.

P3:
- MEGA-07: 9 textos do LCD com 17–18 colunas são cortados (inclui o menu E2
  "1 Novo 2 Inativar"/"3 Reativar D Sair", "Operacao cancelada", "Cadastro
  cancelado", "Verifique DY50/NVS", este com resíduo "NVS").
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
  192 para 32 (~1,5–2 KB de SRAM; hoje 4510 B = 55%); fundir ~37 arquivos de
  teste em ~10.
- Fora do modelo de ameaça (uso honesto): UART não autenticada, HTTP sem TLS,
  salt previsível.
- Aceito: fila em RAM perde itens em reboot.

## 8. Simulações ainda não feitas

Nenhuma destas foi executada. Simulação não é confirmação física.

- Wokwi (Mega + ESP32 por UART, LCD I2C, teclado, LEDs, buzzer, botões; sem
  câmera e sem DY50): teste integrado mais próximo do real. Requer conta e
  token do Wokwi CLI (serviço externo; pedir autorização ao dono).
- simavr com o firmware completo do Mega: medir tempo real do hash de 100
  registros, escrita em EEPROM e estouro da UART. Há imagem Docker local com
  avr-gcc: `controle-acesso-avr-sim:local`; a compilação do Mega usa
  `controle-acesso-avr-probe:local`.
- Pico de pilha e heap do Mega: `-fstack-usage` e análise de `String`.
- Painel em navegador real: 390 px, foco, fluxo de foto e reset.
- Tudo de hardware continua pendente (bancada).

## 9. Próximo passo exato

Ordem sugerida antes da bancada:
1. Painel em navegador real e simavr (rápidos, locais).
2. MEGA-07, REQ-E4, MEGA-03, MEGA-04 e TST-02.
3. CAM-03 e SRV-02.
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
