# Materiais e ligações

## Materiais

Consulte a [lista completa com quantidades e indicação do que já está na foto](MATERIAIS.md).
Esta versão mantém a fechadura e acrescenta buzzer; **não usa motor adicional**.

Já identificados: DY50, teclado matricial 4×4, LCD de caracteres, módulo RGB,
dois botões e fechadura 12 V / 2 A. Confirmar que o LCD é 16×2.

Para adquirir/preparar:

| Item | Critério para este projeto |
|---|---|
| ESP32-DevKitC V4 | WROOM-32E, pinos soldados e cabo USB de dados |
| Buzzer e acionamento | Ativo 5 V / até 50 mA, via NPN, resistor 470 Ω e pull-down 10 kΩ; ver lista completa |
| Adaptador I²C do LCD | PCF8574 para LCD 16×2 compatível HD44780 |
| Conversor de nível I²C | Bidirecional, 3,3 V ↔ 5 V, duas vias SDA/SCL |
| Driver da fechadura | MOSFET com entrada compatível **3,3 V**, carga 12 V / 2 A indutiva, com margem de corrente; confirmar ficha do módulo |
| Alternativa ao MOSFET | Relé com entrada comprovadamente acionável em 3,3 V e contatos dimensionados para carga DC indutiva 12 V / 2 A |
| Proteção da bobina | Diodo de roda livre adequado, com corrente nominal de pelo menos 3 A e tensão reversa acima de 12 V, se não integrado |
| Fonte da fechadura | 12 V regulados, pelo menos 3 A para dar margem sobre os 2 A informados |
| Alimentação da lógica | USB adequado ou fonte regulada de 5 V; para fonte única usar conversor buck 12 V → 5 V, com pelo menos 2 A |
| Resistores 10 kΩ | Quatro pull-ups nos GPIO34/35/36/39 e um pull-down no acionamento do buzzer |
| Resistores RGB | Um por canal, se a plaquinha não possuir; dimensionar pelo LED e limitar a corrente a poucos mA por GPIO |
| Montagem | Jumpers, protoboard para sinais, conectores e cabos apropriados para os 2 A da trava |

Não usar a trilha de alimentação da protoboard nem pino do ESP32 para conduzir os
2 A. Não assumir que um módulo relé “5 V” aceita sinal de 3,3 V, ou que um MOSFET
rotulado “Arduino” conduz bem com 3,3 V. Selecionar pela especificação real.

## Mapa de pinos — ESP32 clássico WROOM-32E

| Elemento | Sinal | GPIO / ligação |
|---|---|---|
| LCD via adaptador | SDA | 21, pelo conversor de nível |
| LCD via adaptador | SCL | 22, pelo conversor de nível |
| DY50 | TX do sensor → RX ESP | 16, com nível lógico compatível |
| DY50 | RX do sensor ← TX ESP | 17, com nível lógico compatível |
| Botão 1 | Sinal | 34 + pull-up externo 10 kΩ para 3V3 |
| Botão 2 | Sinal | 35 + pull-up externo 10 kΩ para 3V3 |
| LED RGB | Vermelho | 4, pelo resistor do canal |
| LED RGB | Verde | 18, pelo resistor do canal |
| LED RGB | Azul | 19, pelo resistor do canal |
| Driver fechadura | Entrada | 23, nunca a bobina diretamente |
| Driver do buzzer | Base do NPN pelo resistor 470 Ω | 2, ativo HIGH; pull-down externo base–emissor |
| Teclado | R1 / R2 / R3 / R4 | 27 / 32 / 36 / 39 |
| Teclado | C1 / C2 / C3 / C4 | 13 / 14 / 25 / 26 |

GPIO36 e 39 também precisam de pull-ups externos de 10 kΩ para 3V3. O firmware
adapta a biblioteca Keypad para esses pinos de entrada. Não troque linhas e
colunas no código: a biblioteca lê linhas e aciona colunas.

Não usar os números físicos das posições como se fossem GPIO. Siga a inscrição
na placa. O ESP32 não aceita sinais de 5 V em seus GPIOs.

## Buzzer ativo

```text
GPIO2 ── resistor 470Ω ── base do NPN
                            │
                         resistor 10kΩ
                            │
GND ───────────────────── emissor do NPN

+5V ── buzzer (+)
       buzzer (-) ──────── coletor do NPN
```

Usar buzzer **ativo de 5 V, até 50 mA**. Confirmar C/B/E no datasheet do transistor,
não pela posição visual genérica. Para buzzer eletromagnético, diodo de proteção
em paralelo: faixa/cátodo no +5 V, ânodo no coletor. Se for um módulo com esses
componentes integrados, confirmar sinal ativo HIGH de 3,3 V antes de substituir.

GPIO2 é pino de configuração de boot: o pull-down o mantém em estado compatível
com programação. **Não instalar pull-up de 5 V ou módulo que force HIGH durante
o reset nesse pino.** [Referência Espressif](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/boot-mode-selection.html).

O código gera três bipes de 200 ms, separados por 200 ms, ao expirar o minuto sem
abrir. Depois de 5 minutos aberta, gera um bipe de 250 ms a cada 2 segundos,
parando ao fechar. Não há som nos primeiros 5 minutos de abertura autorizada.
`LOCK_MODE=0` desliga somente o acionamento da fechadura; o buzzer continua
funcionando para testar os avisos.

## Botões da porta

Para cada botão:

```text
3V3 ── resistor 10k ──┬── GPIO34 (ou GPIO35)
                     │
                   botao
                     │
                    GND
```

Solto = HIGH; pressionado = LOW. Porta fechada = ambos LOW por pelo menos 50 ms.
Os dois devem ser pressionados mecanicamente quando a porta estiver encaixada.
Eles não são botões de autorização nem de saída.

## Teclado

Mapeie as oito vias com um multímetro antes de conectar; a ordem varia conforme
o fabricante. Com o teclado na posição de leitura, R1 deve conter `1 2 3 A`,
R2 `4 5 6 B`, R3 `7 8 9 C` e R4 `* 0 # D`. As colunas são verticais.
O teclado é uma matriz de contatos; não há ligação VCC/GND separada.

## LCD e conversor de nível

Solde/encaixe o adaptador I²C nos 16 pinos do LCD. Para o conjunto alimentado em 5 V:

1. VCC do adaptador LCD em 5 V regulados; GND no comum.
2. Conversor: lado LV em 3V3, lado HV em 5 V; GND comum.
3. GPIO21 → canal LV1; HV1 → SDA do adaptador.
4. GPIO22 → canal LV2; HV2 → SCL do adaptador.
5. Confirme endereço I²C (padrão no código: 0x27); ajuste o potenciômetro de contraste.

Não conectar um backpack com pull-ups de 5 V diretamente ao ESP32. Este roteiro
usa conversão de nível, sem depender de uma tentativa de alimentar um LCD de 5 V
em 3,3 V.

## DY50

A página da loja informa 162 modelos, UART/TTL e 57600 bps. Há divergência na faixa
de alimentação entre produto e tutorial (3–6 V/3,3 V versus 3,6–6 V).
**Não deduzir a ordem dos pinos pela cor ou pela imagem genérica.** Confirmar
VCC, GND, TX, RX e orientação do conector na versão física recebida.

Alimentação e nível de sinal são coisas diferentes: alimentar o módulo com 5 V
não prova que seu TX é de 3,3 V. Confirmar nível UART na documentação do lote ou
medir adequadamente antes de ligar ao ESP32. Se necessário, usar conversão
adequada a UART a 57600 bps. Deixar as vias não utilizadas isoladas.

No firmware: TX do leitor vai ao GPIO16; GPIO17 vai ao RX do leitor. A comunicação
usa UART2. A capacidade é consultada no boot; se a comunicação/capacidade falhar,
novos cadastros e leitura biométrica ficam indisponíveis, sem apagar a base.

## LED RGB

Confirme os pinos R/G/B e o comum. Para cátodo comum: comum em GND e
`RGB_COMMON_ANODE=false`. Para ânodo comum, use alimentação compatível com o
acionamento de 3,3 V e `true`; não trazer 5 V para os GPIOs pelo módulo.
Se o módulo exigir corrente maior, inclua transistores de acionamento.

O amarelo usa vermelho + verde. As cores são digitais (ligado/desligado), sem PWM.

## Fechadura com MOSFET — esquema de princípio

```text
Fonte +12V ──────────────── positivo da fechadura
                                   bobina
Negativo fechadura ─────── OUT- / dreno do driver
Fonte GND ──────────────── GND potência do driver
ESP32 GPIO23 ──────────── entrada lógica do driver (3,3 V)
ESP32 GND ─────────────── GND comum de sinal

Diodo em paralelo na bobina:
cátodo (faixa) no +12V; ânodo no negativo da fechadura.
```

Esse é um princípio; os nomes dos bornes dependem do driver comprado. Use módulo
com estado desligado definido também durante reset/boot (pull-down ou circuito
equivalente). Confirme `LOCK_ON`. Se usar relé, os contatos e a ligação mudam;
nunca conectar a bobina ao pino da placa. A proteção deve ficar junto à carga.

Alimente a lógica por USB **ou** pelos pinos conforme o guia da DevKitC. Não ligue
simultaneamente USB e uma alimentação externa nos mesmos barramentos sem circuito
de seleção apropriado. A fonte de 12 V não entra nos GPIOs, 3V3 nem no pino 5 V.

## Ensaio que define o modo da trava

1. Começar com a fechadura desconectada e `LOCK_MODE=0`; verificar toda a lógica.
2. Com driver/fonte/proteção instalados, identificar a duração permitida pelo
   fabricante. Um pulso curto ajuda a observar o mecanismo, mas não comprova que
   a bobina suporta permanecer ligada.
3. Se abrir por pulso: modo 1; configurar o pulso validado. Observar se a lingueta
   só rearma ao fechar. Nesse caso o software não consegue retravá-la sozinho
   quando termina 1 minuto, se ela não tiver sido mecanicamente rearmada.
4. Se ela voltar a travar ao cortar energia e permitir alimentação por até 60 s:
   modo 2. A saída desliga ao abrir ou ao expirar 1 minuto. Nunca energiza durante
   os 5 minutos de espera da porta aberta.
5. Fechar e confirmar ambos os sensores; testar engate real separadamente.

Se a exigência de retravar sem abrir após 1 minuto for indispensável e o mecanismo
não permitir, trocar o tipo de fechadura. Isso não se resolve prolongando o pulso.
