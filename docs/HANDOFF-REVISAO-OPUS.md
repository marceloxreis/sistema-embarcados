# Handoff para o agente Opus — revisão de ponta a ponta

**Concluído em 30/10/2026.** Auditoria e correções feitas; estado atual em docs/HANDOFF.md.

Você assume o projeto Sistema Embarcados (controle de acesso: Arduino Mega +
ESP32-CAM + servidor Python + painel web). Seu trabalho é auditar o projeto
inteiro, não só as mudanças recentes, e entregar um relatório completo.

## Regras inegociáveis (herdadas do dono)

- Ler primeiro o CLAUDE.md global do dono (fora do repositório) e `docs/HANDOFF.md`.
- Análise e relatório são somente leitura. Não edite arquivos do projeto,
  nem corrija achados, sem aprovação explícita do dono depois do relatório.
- `LOCK_MODE=0` em `firmware/MegaControlador/Config.h` e
  `firmware/ControleAcesso/Config.h`. Não grave placas, não acione a fechadura,
  não faça commit nem push, sem coordenar com o dono. Nenhum teste físico foi
  feito até agora; o adaptador USB–serial da ESP32-CAM chega em 30/10/2026.
- Nunca equipare simulação com confirmação física. Marque cada afirmação como
  verificada em host, compilada ou não verificada.
- Um agente distinto por tarefa; não reaproveite agentes. Revisores não editam.
- Métricas de contexto só reais (hook, status line, `/context`). Avise ao dono
  em ~40% e escreva handoff em ~55%.
- Sem emojis (exceto marcas de certo/errado). Texto ao dono em português.
  Uma pergunta por vez.

## Fase 1 — Perguntas (antes de auditar)

Leia o repositório e os documentos (`README.md`, `docs/*.md`) e faça ao dono as
perguntas que precisar sobre o que não entendeu: modelo de ameaça, o que é
requisito versus desejo, ambiente de implantação (rede, quem acessa o painel),
política de retenção de fotos e dados pessoais. Uma pergunta por vez. Quando
estiver satisfeito, diga que vai começar a Fase 2.

## Fase 2 — Auditoria completa

Você tem liberdade para despachar agentes (revisores, exploradores, analisadores
de segurança) em paralelo, com escopo claro e somente leitura. Sugestão de
frentes, ajuste como julgar melhor:

1. Firmware do Mega (`firmware/MegaControlador/`): máquina de estados, porta,
   buzzer, DY50 (filtro de ACK), EEPROM/UserStore/BootCounter, display LCD,
   serviço da UART, orçamento de memória e tempos.
2. Firmware da CAM (`firmware/Esp32CamRede/`): captura, fila de 8 itens com
   JPEG, desafio de frescor, rede/HTTP, contadores, `cam_boot_id`.
3. Protocolo UART compartilhado (`firmware/shared/`, cópias em cada firmware):
   enquadramento, CRC, mensagens, divergência entre cópias.
4. Servidor (`servidor/server.py`): autenticação, limites, SQLite, migração,
   fotos, comandos de reset, permissões de arquivo, concorrência.
5. Painel (`servidor/static/`): XSS, acessibilidade, 390 px, tratamento de erro.
6. Testes (`tests/`): poder de detecção (mutação), flakiness, dependência de
   bibliotecas, testes duplicados ou redundantes, tempo total (~50 s).
7. Documentação e scripts (`README.md`, `docs/`, `scripts/`): contradições com
   o código, avisos de versões antigas, passos de montagem/segurança elétrica.
8. Excesso e otimização: código morto, duplicação (inclusive a pasta legada
   `firmware/ControleAcesso/` — avalie se ainda é necessária), complexidade
   desnecessária, custo de flash/RAM, trabalho redundante nos testes.

Para cada achado informe: severidade (P0–P3), arquivo:linha, cenário concreto,
como reproduzir (comando ou teste), e nível de evidência. Procure também o que
falta (requisitos sem teste, modos de falha sem tratamento).

## Fase 3 — Relatório ao dono

Apresente: (a) resumo executivo, (b) achados por severidade, (c) itens em
excesso/otimizações com ganho estimado e risco, (d) pendências conhecidas que
você confirmou ou refutou, (e) o que você não conseguiu verificar e por quê,
(f) ordem sugerida de correção. Não corrija nada antes do dono aprovar.

## Estado verificado em 29/10/2026 (fim desta retomada)

- Arquitetura aprovada: Mega + ESP32-CAM, uma foto por acesso autorizado,
  enviada ao servidor. Branch Git `feat/mega-esp32cam`; só 1 commit
  (`49218bd`); quase tudo é alteração local não commitada ou arquivo não
  rastreado (por isso não há `git diff` útil para o firmware novo e os testes).
- Suíte: `CONTROLE_TEST_LIBS=/tmp/controle-test-libs-20261029
  CONTROLE_TEST_STRICT=1 python3 -m unittest discover -s tests -q` -> 113 testes
  OK (~51 s). Se `/tmp/controle-test-libs-20261029` não existir, veja
  `scripts/bootstrap-test-libs.py` e o README. `node --check
  servidor/static/app.js` e `git diff --check` OK. São testes de host e
  emulação, não hardware nem rede real.
- Compilação real da CAM (`esp32:esp32:esp32cam`): 1054325 bytes de flash,
  60608 de RAM global, exit 0. Mega no último registro do handoff:
  37534 flash / 4384 SRAM (não recompilado nesta retomada). Valores globais
  não medem pico de pilha/heap. Comando da CAM (toolchain fora do repo, em
  pasta de trabalho externa (`work/`, fora do repositório); use uma cópia do
  sketch em pasta de rascunho): a partir de `.../dc`, `work/toolchain/arduino-cli
  --config-file work/arduino-config.yaml compile --fqbn esp32:esp32:esp32cam
  --build-path <rascunho>/build --build-property
  runtime.tools.ctags.path=work/toolchain/ctags-master <cópia do sketch>`.
  O ctags embutido do core é x86_64 e falha neste Mac arm64; por isso a
  propriedade apontando para `ctags-master`.
- Hashes sha256 dos arquivos tocados nesta retomada:
  - `firmware/Esp32CamRede/Esp32CamRede.ino` abaae106b0592f31ec174a90bbeb57005a8591d64a6edea04fedc0eaeacdbdf1
  - `servidor/server.py` 92995ec64115ad26a6010f2c9fda9665b944b4bbb27ac7f65c41d45bfa5c6994
  - `servidor/static/app.js` e5e9e526051b718de9e2a17778cc9deb6c3c7688dd04d2e6e6fb9b9d6dfc792b
  - `tests/test_server.py` 1c2d310dba583261cc7c5e269b7f85ad0e942cf606884ce83f7109e91b5b78fa
  - `tests/test_camera_network.py` 6ebf0103bc47f1be4696bc17be721728b2cd6e65200145e0fa0d6f185032c93c

## O que foi feito nesta retomada (e já revisado por agentes independentes)

Visibilidade remota de perdas e política de HTTP permanente:

- CAM: rejeição permanente = HTTP 400/409/413/422; descarte da cabeça da fila
  só após 5 rejeições consecutivas e pelo menos 30 s, com conectividade contínua
  (a série zera ao cair o Wi-Fi). 401/403/404 e demais 4xx são tratados como
  erro de configuração/transitório (item mantido). Contadores saturantes
  `rejected` (descarte no estágio evento), `photo_rejected` (descarte no estágio
  foto, evento já aceito) e `dropped` (reservado: hoje sempre 0, porque quando a
  fila da CAM está cheia a CAM não envia ACK e o Mega retransmite). Heartbeat
  envia `dropped`, `rejected`, `photo_rejected`, `queued`, `boot_id` (boot do
  Mega) e `cam_boot_id` (8 hex gerados no boot da CAM por `esp_random()`).
- Servidor: colunas `dropped`, `rejected`, `photo_rejected`, `*_prev` e
  `cam_boot_id` com migração atômica (BEGIN IMMEDIATE) de bancos antigos;
  acúmulo de totais anteriores quando o `cam_boot_id` muda ou algum contador cai;
  mudança só de `boot_id` não acumula; conexões SQLite agora fechadas; erro de
  banco na inicialização sai com mensagem clara. Painel mostra totais e aviso
  persistente (perdas/descartes e eventos aceitos sem foto).
- Cada implementação teve revisão independente; houve 3 rodadas de correção
  (P1 de 401/403/404 descartando a fila; P1 de `boot_id` do Mega usado como boot
  da CAM; lacunas de teste confirmadas por mutação). Última revisão: sem
  P0/P1.

## Pendências e limitações conhecidas (confirme ou refute na auditoria)

- UART Mega<->CAM não é autenticada: quem acessa o enlace pode falsificar
  mensagens. O desafio de frescor de 128 bits não é segurança criptográfica.
- Perdas do Mega por fila cheia (16 eventos) só aparecem por USB (`dropped` do
  Mega); a fila da CAM está em RAM, então um reboot da CAM perde itens já
  confirmados, sem contador.
- Quatro resets distintos podem ocupar a fila de respostas e descartar uma prova.
- Corrida de caminho/symlink na criação do banco; backups não herdam proteção
  0600; permissões só valem para bancos novos.
- Servidor: sem proteção total contra DoS e sem transporte cifrado (HTTP simples);
  o prazo interrompe o socket, não um handler bloqueado fora de I/O de rede.
- Acúmulo de contadores: (P3) uma queda de contador com o mesmo `cam_boot_id`
  (heartbeat fora de ordem) é tratada como reinício e pode duplicar a soma;
  (P3) na primeira transição para `cam_boot_id` pode haver subcontagem se a CAM
  reiniciou sem queda visível de contadores.
- Sem backoff no reenvio de item rejeitado: ~300 requisições em 30 s por item.
- `tests/test_verificacao_deps_agent.py` agora aceita `failures>=2` em vez de
  exatamente 2 (revisor considerou enfraquecimento pequeno).
- Comentário "sempre 0" de `dropped` fica frágil se alguém passar a incrementar.
- Todos os tempos, UART real, sensor DY50, LCD, entropia real, EEPROM e picos de
  pilha/heap dependem de teste físico.

## Primeira ação

Confirme que leu `CLAUDE.md` e `docs/HANDOFF.md`, rode a suíte para validar o
estado acima, e então faça a primeira pergunta da Fase 1.
