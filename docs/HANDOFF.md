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

- Branch: `feat/mega-esp32cam`. Último commit: `49218bd`. Nenhum commit novo.
- Quase tudo é alteração local não commitada ou arquivo não rastreado
  (`git status` lista ~66 entradas).
- Arquivos da versão DevKit aparecem como apagados (`D`), entre eles
  `firmware/ControleAcesso/*` e `tests/test_firmware.py`.
- Novos diretórios não rastreados: `firmware/MegaControlador/`,
  `firmware/Esp32CamRede/`, `firmware/shared/`, `scripts/`, `tests/fixtures/`
  e dezenas de `tests/test_*.py` / `tests/test_*.cpp`.
- Antes de commitar: stage por arquivo, nunca por diretório. Confirme que
  `Config.h` locais e `__pycache__` ficam fora do commit.

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
| Suíte Python: `CONTROLE_TEST_LIBS=/tmp/controle-test-libs-20261029 CONTROLE_TEST_STRICT=1 python3 -m unittest discover -s tests -q` | 126 testes OK, 0 skipped, 28 s | verificado em host (reexecutado neste handoff) |
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

## 7. Pendências conhecidas (não corrigidas)

- Reset web aplicado dentro do enlace com tráfego intenso pode exceder o
  `linkStash` (128 B) somado ao buffer de 64 B. O CRC rejeita e há retransmissão.
- `holdRetry` da CAM não zera na queda de Wi-Fi (efeito de até 2 s).
- Rota 404 descarta o resultado de reset (rota errada apaga resultados).
- Falta teste de reenvio imediato após erro transitório que segue de rejeição
  permanente.
- UART não autenticada e HTTP sem TLS: fora do modelo de ameaça atual (uso honesto).
- Fila em RAM perde itens em reboot (aceito).
- Dependem de bancada: tempos, UART real, DY50, LCD, câmera, alimentação e pico
  de pilha e heap.

## 8. Próximo passo exato

1. Configuração local, sem versionar:
   - `ADMIN_PIN` (10 dígitos) em `firmware/MegaControlador/Config.h`, arquivo
     ignorado pelo Git.
   - `ADMIN_PIN` e `DEVICE_KEY` (16+ caracteres) no ambiente do servidor.
   - Wi-Fi, URL e chave em `firmware/Esp32CamRede/Config.h`.
2. Na bancada, com `LOCK_MODE=0` e fechadura desconectada: seguir
   `docs/MONTAGEM.md` seção 1 (segurança) e seção 5, passos 1 a 7.
3. Depois: `docs/TESTES.md`, "Ensaios funcionais de bancada".
4. Só então o ensaio da fechadura (`docs/MONTAGEM.md` seção 6).

Nada disso foi executado. Os passos 2 a 4 dependem do dono e do hardware.
