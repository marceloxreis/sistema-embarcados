# Registro de validação — Mega + ESP32-CAM

Este arquivo registra somente o que foi executado, com a data e o nível de evidência.
Não há ensaio físico: nenhuma placa foi gravada, nenhum sinal elétrico foi medido e
nenhuma comunicação real foi testada. Os ensaios de bancada estão em
[TESTES.md](TESTES.md).

Níveis de evidência:

- **verificado em host**: executado no computador de desenvolvimento, com resultado observado.
- **compilado**: compilado para a placa-alvo com o core indicado; não gravado nem executado.
- **simulado**: executado em simulador (simavr, navegador dublado etc.); não é confirmação física.
- **análise de código**: conclusão tirada da leitura do código; não foi executada.
- **estimativa**: valor calculado a partir de dados de ficha; não medido.
- **não verificado**: não medido nem executado; ou não verificado após mudanças.
- **não verificado após mudanças**: registro anterior, sem nova execução depois das alterações indicadas.

## Registros

| Item | Data | Como foi feito | Resultado | Nível |
|---|---|---|---|---|
| Suíte de testes de software (sessão 1) | 30/10/2026 | Na raiz do projeto: `CONTROLE_TEST_LIBS=<diretório preparado por scripts/bootstrap-test-libs.py> CONTROLE_TEST_STRICT=1 python3 -m unittest discover -s tests -q` | 126 testes, OK, 25,52 s (tempo reportado pelo unittest), 0 skipped | verificado em host |
| Sintaxe do painel | 30/10/2026 | `node --check servidor/static/app.js` (Node.js 22.22.3) | Sem erros (código de saída 0) | verificado em host |
| Firmware ESP32-CAM | 30/10/2026 | Arduino CLI, `esp32:esp32:esp32cam`, core esp32 3.3.12, sobre cópia de `firmware/Esp32CamRede` | Flash 1055069 bytes (33% de 3145728); RAM global 60608 bytes (18% de 327680) | compilado |
| Suíte de testes de software (sessão 2) | 30/10/2026 | Mesmo comando, ao fim da sessão, com `CONTROLE_TEST_LIBS=/tmp/controle-test-libs-20261029` | 145 testes, OK, 28 a 39 s conforme a carga (38,42 s no fim da sessão 2), 0 skipped | verificado em host |
| Testes novos da sessão 2 | 30/10/2026 | Incluídos na suíte acima: `tests/test_lcd_textos.py` (MEGA-07); `tests/test_mega_tst02.py` (9 testes: 7 de TST-02 sobre o código real do `.ino` e 2 de regressão B7 para registro corrompido); testes de MEGA-03, MEGA-04 e REQ-E4 em `tests/test_mega_logic.py`. Teste de mutação do TST-02 com `CONTROLE_MEGA_B6=<pasta>` | Todos passaram; 4 mutantes detectados pelo implementador; 2 reexecutados pelo revisor. MEGA-10 tem 3 testes de boot em `tests/test_reinicio_perifericos_agent.py` (ver linha "MEGA-10 (testes de host)") | verificado em host |
| Correção B7 (REQ-E4) | 30/10/2026 | Análise de código: `authorize` lê o registro uma vez; corrupção detectada na leitura vira "Falha memoria" / "Erro na memoria"; `resetPassword` com registro corrompido responde `storage_error`. Testes: `RegistroCorrompidoTests` em `tests/test_mega_tst02.py` (2 testes). Revisão Sonnet independente: APROVADO (parecer não salvo em arquivo). Build conferido nos logs | Os 2 testes falham no código anterior ao B7 e passam no atual (reexecutado pelo revisor). Nenhum assert enfraquecido. Build 42496 B / 4581 B / 19 avisos. Sem teste para segundo reset com `storageReady` já falso (observação baixa) | verificado em host; análise de código |
| Firmware Mega 2560 (sessão 1) | 30/10/2026 | Arduino CLI em container Linux local, `arduino:avr:mega`, core AVR 1.8.8, sobre cópia de `firmware/MegaControlador` idêntica aos fontes atuais. Tamanhos lidos do ELF gerado (`avr-size`: flash = `.text` + `.data`; RAM global = `.data` + `.bss`). Compilador: avr-gcc 7.3.0 do arduino-cli | Flash 38996 bytes; SRAM global 4510 bytes. Avisos: nenhum com `--warnings` default do arduino-cli, nível que não garante ausência de avisos; não reexecutado com `-Wall -Wextra`. Não comparável com a sessão 2 | compilado |
| Firmware Mega 2560 (sessão 2) | 30/10/2026 | avr-gcc 14.2 da imagem `controle-acesso-avr-probe:local`, core `arduino:avr` 1.8.6 de `~/Library/Arduino15`, bibliotecas externas montadas somente leitura. Cópia do sketch sem `Config.h`, com `Config.example.h` como `Config.h`. `-Wall -Wextra` | Flash 42496 bytes; SRAM global (data + bss) 4581 bytes; 19 avisos: 1 do projeto (`misleading-indentation` em `saveRecord`, pré-existente) e 18 do core e das bibliotecas. Nenhum aviso novo das mudanças | compilado |
| Firmware Mega 2560, HEAD `2c9aa85` (sessão 2, mesmo método) | 30/10/2026 | Mesmo método da linha anterior, sobre o HEAD | Flash 41804 bytes; SRAM global 4554 bytes | compilado |
| Firmware Mega 2560 (histórico) | Registro anterior às mudanças de 30/10/2026 | Arduino CLI, `arduino:avr:mega`, core AVR 1.8.8, em container Linux | Flash 37534 bytes; SRAM global 4384 bytes | não verificado após mudanças |
| Firmware ESP32-CAM (sessão 2) | 30/10/2026 | Não alterado nem recompilado nesta sessão | Último registro: linha "Firmware ESP32-CAM" acima | não se aplica |
| MEGA-10 (testes de host) | 30/10/2026 | `tests/test_reinicio_perifericos_agent.py`: `test_boot_lcd_ausente_nao_e_inicializado`, `test_boot_lcd_presente_inicializa`, `test_boot_com_timeout_fica_sem_lcd`. Compilam `lcdPresent`/`lcdBoot` reais do `.ino`. Passaram na suíte de 145 testes. O mutante com o boot antigo falha (informado na revisão; não reexecutado nesta correção) | verificado em host. LCD real: não verificado |
| Boot sem LCD (MEGA-10), simavr | 30/10/2026 | Imagem `controle-acesso-avr-sim:local`, simavr sem LCD no barramento I²C | Antes: `BOOT boot=1 storage=ok lcd=ok dy50=indisponivel lock_mode=0`. Depois: a mesma linha com `lcd=timeout` | simulado |
| Tempos do Mega, simavr | 30/10/2026 | Imagem `controle-acesso-avr-sim:local`. EEPROM carregada pela seção `.eeprom` do ELF (`-ee` não carregou). Tempos são `micros()` simulados, medidos em cópia instrumentada do HEAD `2c9aa85` (build de 41804 B), não no `.ino` atual; BUTTON_1/2 forçados a LOW | Boot 3,10 s com 0 cadastros e 3,13 s com 100 (quase tudo é a espera pelo DY50 ausente). SHA-256 ~11 ms por hash. Verificação de senha contra 100 registros (`ownerOfPin`/`matches`) ~1,14–1,17 s, com o Mega parado para LCD, teclado e DY50. `saveRecord` 9 ms: artefato, pois o simavr não modela a escrita da EEPROM. Tempo real estimado ~160 ms por `saveRecord` (~48 gravações; ~3,3 ms por byte é valor de datasheet lembrado pelo revisor, não conferido nesta sessão) | simulado; estimativa (o tempo real de escrita não foi verificado) |
| UART da CAM durante o hash | 30/10/2026 | Análise de código: a UART é atendida entre hashes | Margem de ~20 B no buffer de 64 B a 38400 baud. Não medida; a imagem simavr não tem os headers do libsimavr | análise de código; não verificado |
| Painel (`servidor/static`) | 30/10/2026 | Chrome local: 390 px após as correções; 1280 px só na verificação inicial A1, antes das correções. Teclado físico e leitor de tela não verificados (foco testado com `.focus()`/`.click()` por script). Foco preservado ao redesenhar a tabela e ao fechar a foto; resultado do reset em `#reset-status` (some em 15 s ou ao digitar); "PIN incorreto." no login, com campo limpo; `aria-label` distinto em "Ver foto" | Comportamento observado conforme descrito. Fluxo de foto testado no navegador: evento `access_granted` com foto enviada por script pela API do dispositivo; painel mostra o evento e a foto visível (320x240), na verificação A1 e reconfirmado na revisão das mudanças do painel. CAM real não testada | verificado em host (navegador local) |
| Ensaios físicos | - | - | Nenhum executado | - |

Textos do LCD alterados (MEGA-07). Antigo -> novo, conforme `firmware/MegaControlador/MegaControlador.ino`:

| Antigo | Novo |
|---|---|
| "Ciclo em andamento" | "Ciclo em curso" |
| "Verifique DY50/NVS" | "Veja DY50/EEPROM" |
| "100 IDs utilizados" | "100 IDs em uso" |
| "Senhas diferentes" | "Senhas nao batem" |
| "Pessoa cadastrada" | "Cadastrado" |
| "Operacao cancelada" | "Cancelado" |
| "Cadastro cancelado" (segunda linha do "Tempo esgotado" de 60 s) | "Cadastro expirou" |
| "Erro na alteracao" | "Falha ao alterar" |
| "Digital desconhec." | "Dig. desconhec." |
| "1 Novo 2 Inativar" | "1 Novo 2 Inativ." |
| "3 Reativar D Sair" | "3 Reativ. D Sair" |
| "# Sim  D Cancelar" | "# Sim D Cancelar" |
| "DY50 indisponivel" | "DY50 fora do ar" |

Rótulos de LCD novos: "Erro gravar DY" e "Falha na busca". Os valores `dy50=indisponivel`
e `lcd=timeout` do protocolo (BOOT e STATUS) não mudaram de nome.

A RAM informada pelo compilador refere-se às variáveis globais. Filas, pilhas de
tarefas e conexões de rede também usam memória em execução; o consumo máximo real
depende de medição na placa.

Nota sobre a compilação da CAM: em Mac ARM, o ctags x86_64 baixado pelo Arduino
CLI não executa. Para compilar, usou-se um ctags ARM64 indicado pela propriedade
`runtime.tools.ctags.path`. Essa ferramenta não integra o repositório.

## Nota sobre o método de build e os avisos

- As linhas da sessão 1 (38996 B / 4510 B) e da sessão 2 (42496 B / 4581 B) usam
  compiladores e níveis de aviso diferentes. Não são comparáveis entre si.
- Método da sessão 2: passos em `docs/HANDOFF.md`, seção 6. Os scripts ficaram
  numa pasta temporária fora do repositório; não estão versionados.
- Correção: um script usado no início da sessão 2 compilou com `-w`, que suprime
  avisos. Relatos de "sem avisos" daquele script não valem. A medição de 19
  avisos foi feita com `-Wall -Wextra`.
- O "nenhum aviso" da sessão 1 veio do `--warnings` default do arduino-cli. Não
  foi reexecutado com `-Wall -Wextra`.
- Core AVR 1.8.8: há diretórios 1.8.8 em `~/Documents/Codex/2026-10-22/dc/work/`
  (`linux-data` e `arduino-data`), listados e não abertos nesta sessão. O Mac só
  tem o 1.8.6 em `~/Library/Arduino15`. Não se confirmou qual core foi usado na
  compilação da sessão 1; a linha de sessão 1 foi mantida como está.

## Limites

- Nenhum teste físico, gravação, medição elétrica, ensaio de DY50, LCD, UART, câmera,
  Wi-Fi/NTP real ou fechadura foi feito.
- A suíte usa dublês para DY50, EEPROM, relógio, entropia e rede. Ela não comprova
  temporização, níveis de UART, I²C, câmera ou comportamento físico.
- `LOCK_MODE=0` permanece. O acionamento da fechadura não foi testado.
- Os números do Mega são de 30/10/2026. A linha da sessão 2 é a medição atual.
  Eles não substituem a validação física. Os valores globais não medem pico de
  pilha/heap.
- A simulação simavr não modela a escrita da EEPROM nem a UART da CAM. Os tempos são
  simulados e não valem como tempos reais.
- A sonda do LCD no boot (MEGA-10) tem testes de host, mas com a função real
  compilada a partir do `.ino`, não com LCD físico. O boot sem LCD é simulado
  (simavr). LCD real: não verificado.
- Tempos de resposta, entropia e pico de pilha/heap não foram medidos.
