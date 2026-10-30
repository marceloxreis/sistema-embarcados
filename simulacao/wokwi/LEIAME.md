# Simulação Wokwi: Arduino Mega 2560 (MegaControlador)

Simulação de bancada do firmware `firmware/MegaControlador` no Wokwi. Não substitui o teste com hardware.

## O que cobre

- Mega 2560 com o firmware compilado com `Config.example.h` (copiado como `Config.h` só na cópia de build).
- LCD 16x2 I²C em `0x27` (SDA = D20, SCL = D21).
- Teclado 4x4 (linhas D22–D25, colunas D26–D29), mesmo keymap do `.ino`.
- LED RGB catodo comum em D32/D33/D34, com resistores de 220 Ω.
- Buzzer no D36 (direto, sem transistor).
- LED vermelho com resistor de 220 Ω no D35, como representação da entrada do driver da fechadura.
- Dois slide-switches em D30 e D31 como sensores da porta (LOW nos dois = porta fechada).
- Serial principal (USB, Serial0) a 115200, com o protocolo `BOOT`, `AUTH`, `STATUS`, `LIST`.

## O que não cobre

- DY50 (leitor de digital, Serial1): ausente no diagrama. O firmware trata o sensor como indisponível.
- ESP32-CAM (Serial2): ausente no diagrama.
- Buzzer sem transistor NPN (no real há NPN + 470 Ω + 10 kΩ). Aqui é só lógica.
- Fechadura real e driver de 12 V: apenas o LED no D35.
- `LOCK_MODE = 0` (padrão de bancada, a fechadura nunca energiza).
- Tempos reais (o Wokwi roda em tempo simulado próprio).

## Como compilar

```bash
bash simulacao/wokwi/build.sh
```

O script copia `firmware/MegaControlador` para uma pasta temporária sem `Config.h`, usa `Config.example.h` na cópia, compila na imagem Docker `controle-acesso-avr-probe:local` e gera:

- `simulacao/wokwi/build/MegaControlador.ino.hex`
- `simulacao/wokwi/build/MegaControlador.ino.elf`
- `simulacao/wokwi/build/build.log`

Variáveis opcionais: `AVR_CORE`, `ARDUINO_LIBS`, `AVR_IMAGE`.

## Como rodar com wokwi-cli

Rodado em 30/10/2026 (wokwi-cli 0.29.1); resultados em docs/VALIDACAO.md. Requer conta e token do Wokwi. O token fica no Keychain (item `wokwi-cli-token`) e não é exibido. Rodar a partir da raiz do repositório.

Porta fechada no boot (diagrama padrão, `queued=1` esperado):

```bash
WOKWI_CLI_TOKEN="$(security find-generic-password -s wokwi-cli-token -w)" ~/.wokwi/bin/wokwi-cli simulacao/wokwi --scenario scenario-boot.yaml --timeout 60000 --serial-log-file simulacao/wokwi/build/serial-boot.log
```

Porta aberta no boot (`queued=2` esperado: `device_boot` + `forced_open`):

```bash
WOKWI_CLI_TOKEN="$(security find-generic-password -s wokwi-cli-token -w)" ~/.wokwi/bin/wokwi-cli simulacao/wokwi --diagram-file diagram-porta-aberta.json --scenario scenario-porta-aberta.yaml --timeout 60000 --serial-log-file simulacao/wokwi/build/serial-porta-aberta.log
```

Caminhos: segundo a doc do wokwi-cli (https://docs.wokwi.com/wokwi-ci/cli-usage), `--scenario` e `--diagram-file` são relativos à pasta do projeto (o argumento posicional `simulacao/wokwi`), não à raiz do repositório. Por isso o comando usa `scenario-boot.yaml`, e não `simulacao/wokwi/scenario-boot.yaml`. Rodado em 30/10/2026 (wokwi-cli 0.29.1); resultados em docs/VALIDACAO.md.

Confirmado em execução: o LCD respondeu com mega:5V.

Atenção: o firmware compilado (`.hex`/`.elf`) é enviado aos servidores do Wokwi para rodar a simulação. O `Config.example.h` (PIN de exemplo `0000000000`) é o que vai junto, nunca o `Config.h` real.

Arquivos: `diagram.json` (porta fechada), `diagram-porta-aberta.json` (sem o fio D30 <-> sw1, então D30 fica só com o pull-up = HIGH = porta aberta), `scenario-boot.yaml`, `scenario-porta-aberta.yaml`. O passo `set-control` foi removido: a doc do slide-switch não documenta controle de simulação. O atributo `value` também foi removido dos slide-switches: o wokwi-cli acusou "Unknown attribute value" para wokwi-slide-switch; a posição padrão já liga 1-2 (GND).

Capturas do LCD (opções do `wokwi-cli --help`: `--screenshot-part <id>`, `--screenshot-time <ms>`, `--screenshot-file <path>`). O id da parte do LCD no diagrama é `lcd1`. Captura em 4000 ms, uma execução para cada captura:

```bash
WOKWI_CLI_TOKEN="$(security find-generic-password -s wokwi-cli-token -w)" ~/.wokwi/bin/wokwi-cli simulacao/wokwi --scenario scenario-boot.yaml --timeout 60000 --screenshot-part lcd1 --screenshot-time 4000 --screenshot-file simulacao/wokwi/build/lcd-boot.png
```

```bash
WOKWI_CLI_TOKEN="$(security find-generic-password -s wokwi-cli-token -w)" ~/.wokwi/bin/wokwi-cli simulacao/wokwi --diagram-file diagram-porta-aberta.json --scenario scenario-porta-aberta.yaml --timeout 60000 --screenshot-part lcd1 --screenshot-time 4000 --screenshot-file simulacao/wokwi/build/lcd-porta-aberta.png
```

Não verificado: se `--screenshot-file` resolve o caminho a partir do diretório atual (raiz do repo, como os comandos acima) ou do projeto. Os comandos usam o caminho a partir da raiz; se a captura não aparecer, conferir o local real.

## Diagrama com botões em matriz (teclado e cenários)

Por que existe: o `wokwi-membrane-keypad` não tem controle de automação (`set-control`), então um cenário não consegue "apertar" uma tecla. O `diagram-teclado-botoes.json` troca o keypad por 16 `wokwi-pushbutton` (ids `k1`...`kD`, rótulos com a tecla). A fiação em matriz é eletricamente a mesma: o botão da linha r e coluna c liga D22..D25 (R1..R4) a D26..D29 (C1..C4), com o keymap do `.ino`. Mapa tecla -> botão: `1`=k1, `2`=k2, `3`=k3, `A`=kA, `4`=k4, `5`=k5, `6`=k6, `B`=kB, `7`=k7, `8`=k8, `9`=k9, `C`=kC, `*`=kS, `0`=k0, `#`=kH, `D`=kD. Pinos do botão: `1.l` na linha e `2.l` na coluna.

Cenários (usam o diagrama de botões):

- `scenario-teclado-senha-errada.yaml`: digita `123456#` e espera o aviso "Acesso negado" (canal vermelho do LED RGB em D32). Captura `build/erro.png`.
- `scenario-teclado-admin.yaml`: digita `0` x10 + `#` (PIN do `Config.example.h`), espera o menu (magenta: D32 e D34 em 1), depois `D` cancela (D32 em 0). Captura `build/menu.png`.

Rodados em 30/10/2026 (wokwi-cli 0.29.1): os dois terminaram com "Scenario completed successfully" (exit=0), com todos os expect-pin avaliados (`build/run-teclado-*.txt`). O `save-to` é relativo à pasta do projeto: as capturas ficaram em `simulacao/wokwi/build/erro.png` e `simulacao/wokwi/build/menu.png`. Tudo é simulado no Wokwi (teclado trocado por botões), não é teste em hardware. A captura sai do passo `take-screenshot` do cenário (não use `--screenshot-*` junto com cenário).

```bash
WOKWI_CLI_TOKEN="$(security find-generic-password -s wokwi-cli-token -w)" ~/.wokwi/bin/wokwi-cli simulacao/wokwi --diagram-file diagram-teclado-botoes.json --scenario scenario-teclado-senha-errada.yaml --timeout 30000 --serial-log-file simulacao/wokwi/build/serial-teclado-senha-errada.log
```

```bash
WOKWI_CLI_TOKEN="$(security find-generic-password -s wokwi-cli-token -w)" ~/.wokwi/bin/wokwi-cli simulacao/wokwi --diagram-file diagram-teclado-botoes.json --scenario scenario-teclado-admin.yaml --timeout 30000 --serial-log-file simulacao/wokwi/build/serial-teclado-admin.log
```

## Versionamento

A pasta `simulacao/wokwi/build/` não deve ser versionada. O `.gitignore` da raiz já cobre `build/`, `*.hex` e `*.elf`, então ela fica fora do git. Esta etapa não editou o `.gitignore`.
