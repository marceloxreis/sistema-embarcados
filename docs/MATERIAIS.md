# Lista completa de materiais — versão com buzzer, sem motor

Esta lista corresponde ao ESP32-DevKitC V4 com WROOM-32E e à montagem-base
com driver MOSFET para a fechadura e buzzer ativo de 5 V via transistor.
O Mega não é usado. A fechadura elétrica de 12 V continua no projeto.

## Componentes que já aparecem na foto

| Quantidade | Componente | Observação |
|---|---|---|
| 1 | Leitor biométrico DY50 com cabo | Modelo confirmado pelo link enviado; conferir orientação/pinagem física |
| 1 | Teclado matricial 4×4 | 16 teclas, com números, A–D, `*` e `#` |
| 1 | LCD de caracteres, aparentemente 16×2 | Confirmar dimensões; acrescentar adaptador I²C se não estiver no verso |
| 1 | Módulo LED RGB | Identificar comum e resistores integrados |
| 2 | Botões de pressão | Mesma porta, pressionados quando ela está fechada |
| 1 | Fechadura elétrica 12 V / 2 A, modelo 201 | Regime de acionamento e retravamento a confirmar na bancada |

A existência de componentes adicionais fora da foto não foi presumida. O cabo
azul USB-A/USB-B do Mega não serve no conector Micro-USB da DevKitC V4 escolhida.

## Lista para adquirir ou conferir no estoque

| Quantidade | Componente / especificação | Função |
|---|---|---|
| 1 | ESP32-DevKitC V4 com ESP32-WROOM-32E, pinos soldados | Controlador com Wi-Fi |
| 1 | Cabo USB de dados compatível com a placa; Micro-USB para a DevKitC V4 oficial | Programação e consulta USB |
| 1 | Buzzer **ativo**, 5 V, dois terminais, consumo nominal de até 50 mA | Gera som ao receber DC; não comprar piezo passivo para este código |
| 1 | Transistor NPN P2N2222A ou equivalente adequado ao buzzer | Acionamento do buzzer; conferir pinagem do fabricante |
| 1 | Resistor 470 Ω, ¼ W | Base do transistor do buzzer |
| 5 | Resistores 10 kΩ, ¼ W | Quatro pull-ups (34/35/36/39) e um pull-down base–emissor do buzzer |
| 3, se necessário | Resistores 330 Ω, ¼ W | Um por canal RGB, somente se o módulo não tiver limitação de corrente |
| 1 | Diodo 1N4007 | Proteção em paralelo com buzzer eletromagnético; dispensável se a proteção estiver integrada ou buzzer não indutivo |
| 1 | Adaptador I²C PCF8574 para LCD 16×2 HD44780 | Reduz o uso de pinos do LCD; não comprar outro se já houver no verso |
| 1 | Conversor de nível bidirecional 3,3 V ↔ 5 V, 4 canais | Usar dois canais em SDA/SCL; demais disponíveis conforme análise do UART do DY50 |
| 1 | Módulo driver MOSFET, entrada **documentada para 3,3 V**, carga 12 V / 2 A com margem | Acionamento da fechadura; escolher corrente contínua de pelo menos 3 A e adequação a carga indutiva |
| 1, se não integrado | Diodo de roda livre 1N5408, 3 A | Proteção da bobina da fechadura |
| 1 | Fonte DC regulada 12 V / 3 A ou maior, adequada à rede elétrica local | Alimentação do conjunto |
| 1 | Conversor DC-DC buck, entrada 12 V e saída **ajustada para 5 V**, capacidade de pelo menos 2 A | Alimentar ESP32 e periféricos sem depender do USB do computador |
| 1 | Protoboard de 830 pontos | Somente circuito de sinais/baixa corrente |
| 20 | Jumpers macho–macho | Ligações de sinais |
| 20 | Jumpers macho–fêmea | Ligações de módulos |
| 20 | Jumpers fêmea–fêmea | Ligações de módulos |
| 1, conforme fonte | Adaptador do conector da fonte para borne; por exemplo P4 fêmea se a fonte usar P4 | Entrada de 12 V |
| 2 pares | Conectores/bornes de duas vias compatíveis com a corrente | Conexões removíveis de alimentação e fechadura; descontar os já integrados ao driver/buck |
| 2 m no total | Fio de cobre flexível 0,5 mm²; cerca de 1 m vermelho e 1 m preto | Trechos curtos da alimentação e fechadura |
| 1 conjunto | Parafusos, porcas/espaçadores e suportes adequados | Fixar eletrônica, botões, fechadura e contra-peça |
| 1 conjunto | Porta/armário de demonstração e contra-peça compatível com a fechadura | Montagem mecânica |

O uso de 60 jumpers é uma quantidade de compra sugerida com sobra de montagem,
não uma exigência exata de 60 ligações. Resistores normalmente são vendidos em
pacotes; não é necessário comprar exatamente as unidades listadas.

**Não comprar motor, servo ou driver de motor.** Também não são necessários
módulo Wi-Fi separado, Arduino Mega, RTC ou microSD.

### Alternativas e itens condicionais

- Um relé pode substituir o MOSFET, desde que tenha entrada comprovadamente
  compatível com 3,3 V e contatos apropriados para 12 V / 2 A DC indutivos.
  Comprar **um tipo de acionamento**, não ambos. A pinagem física será diferente.
- Um módulo de buzzer pode substituir buzzer + NPN + resistores + proteção,
  **somente** se for ativo, aceitar comando HIGH de 3,3 V e não aplicar pull-up
  de 5 V ao pino do ESP32. GPIO2 deve permanecer LOW ou flutuante no reset.
- As duas vias extras do conversor não devem ser conectadas ao DY50 sem conferir
  seus níveis lógicos. O TX/RX pode já ser compatível com 3,3 V. Alimentação em
  5 V não comprova tolerância a sinais de 5 V.
- O conjunto elétrico-base usa uma fonte de 12 V e o buck para a lógica.
  Alimentação USB é alternativa para programação, não uma segunda fonte ligada
  simultaneamente aos mesmos barramentos sem seleção/isolamento adequado.

## Ferramentas e infraestrutura

| Item | Uso |
|---|---|
| Computador com Python 3.9+ e Arduino IDE | Programação, servidor e painel |
| Rede Wi-Fi de 2,4 GHz com roteador e acesso à internet | Comunicação local e horário NTP |
| Multímetro | Ajustar 5 V do buck e conferir continuidade/polaridade |
| Ferro de solda, solda e termo-retrátil ou fita isolante | Adaptador LCD, conectores e isolamento |
| Alicate de corte/decapador e chave de fenda | Montagem |

Multímetro não substitui documentação ou instrumento adequado para verificar
formas de onda/níveis UART quando houver dúvida sobre o leitor.

## Referências de componentes e pinagem

- [DevKitC V4 e conector USB — Espressif](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html)
- [GPIO2 na inicialização/programação — Espressif](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/boot-mode-selection.html)
- [Diodo 1N5408 / família de 3 A — Vishay](https://www.vishay.com/docs/88516/1n5400.pdf)
- [Transistor P2N2222A — onsemi](https://www.onsemi.com/pdf/datasheet/p2n2222a-d.pdf)

Não foram verificados anúncios/estoque/preços de cada peça. A compatibilidade do
driver comprado deve ser confirmada pela ficha técnica, não apenas pelo título.
