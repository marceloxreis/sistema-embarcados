# Registro de validação — Mega + ESP32-CAM

Este arquivo registra somente o que foi executado, com a data e o nível de evidência.
Não há ensaio físico: nenhuma placa foi gravada, nenhum sinal elétrico foi medido e
nenhuma comunicação real foi testada. Os ensaios de bancada estão em
[TESTES.md](TESTES.md).

Níveis de evidência:

- **verificado em host**: executado no computador de desenvolvimento, com resultado observado.
- **compilado**: compilado para a placa-alvo com o core indicado; não gravado nem executado.
- **não verificado após mudanças**: registro anterior, sem nova execução depois das alterações indicadas.

## Registros

| Item | Data | Como foi feito | Resultado | Nível |
|---|---|---|---|---|
| Suíte de testes de software | 30/10/2026 | Na raiz do projeto: `CONTROLE_TEST_LIBS=<diretório preparado por scripts/bootstrap-test-libs.py> CONTROLE_TEST_STRICT=1 python3 -m unittest discover -s tests -q` | 126 testes, OK, 25,52 s (tempo reportado pelo unittest), 0 skipped | verificado em host |
| Sintaxe do painel | 30/10/2026 | `node --check servidor/static/app.js` (Node.js 22.22.3) | Sem erros (código de saída 0) | verificado em host |
| Firmware ESP32-CAM | 30/10/2026 | Arduino CLI, `esp32:esp32:esp32cam`, core esp32 3.3.12, sobre cópia de `firmware/Esp32CamRede` | Flash 1055069 bytes (33% de 3145728); RAM global 60608 bytes (18% de 327680) | compilado |
| Firmware Mega 2560 | 30/10/2026 | Arduino CLI em container Linux local, `arduino:avr:mega`, core AVR 1.8.8, sobre cópia de `firmware/MegaControlador` idêntica aos fontes atuais. Tamanhos lidos do ELF gerado (`avr-size`: flash = `.text` + `.data`; RAM global = `.data` + `.bss`) | Flash 38996 bytes; SRAM global 4510 bytes. Avisos de compilação: nenhum com `--warnings` default | compilado |
| Firmware Mega 2560 (histórico) | Registro anterior às mudanças de 30/10/2026 | Arduino CLI, `arduino:avr:mega`, core AVR 1.8.8, em container Linux | Flash 37534 bytes; SRAM global 4384 bytes | não verificado após mudanças |
| Ensaios físicos | - | - | Nenhum executado | - |

A RAM informada pelo compilador refere-se às variáveis globais. Filas, pilhas de
tarefas e conexões de rede também usam memória em execução; o consumo máximo real
depende de medição na placa.

Nota sobre a compilação da CAM: em Mac ARM, o ctags x86_64 baixado pelo Arduino
CLI não executa. Para compilar, usou-se um ctags ARM64 indicado pela propriedade
`runtime.tools.ctags.path`. Essa ferramenta não integra o repositório.

## Limites

- Nenhum teste físico, gravação, medição elétrica, ensaio de DY50, LCD, UART, câmera,
  Wi-Fi/NTP real ou fechadura foi feito.
- A suíte usa dublês para DY50, EEPROM, relógio, entropia e rede. Ela não comprova
  temporização, níveis de UART, I²C, câmera ou comportamento físico.
- `LOCK_MODE=0` permanece. O acionamento da fechadura não foi testado.
- Os números do Mega são da compilação de 30/10/2026, feita após as alterações do dia.
  Eles não substituem a validação física. Os valores globais não medem pico de
  pilha/heap.
- Tempos de resposta, entropia e pico de pilha/heap não foram medidos.
