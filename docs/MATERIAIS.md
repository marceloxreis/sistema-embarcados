# Lista de materiais

## Materiais para a arquitetura Mega + ESP32-CAM

| Quantidade | Material | Conferir antes de ligar |
|---|---|---|
| 1 | Arduino Mega 2560 e cabo USB de dados | Placa e cabo compatíveis |
| 1 | ESP32-CAM Ai-Thinker com câmera | Variante e identificação dos pinos reais |
| 1 | Adaptador USB–serial ou placa programadora para a CAM | TX/RX em 3,3 V; a capacidade de alimentação varia conforme o adaptador |
| 1 | Leitor de digital DY50 com cabo | Pinagem, alimentação, níveis lógicos e UART da unidade real |
| 1 | Teclado matricial 4×4 | Identificar a ordem das linhas e colunas |
| 1 | LCD 16×2 com interface I²C | Presença do backpack e endereço; exemplo usa `0x27` |
| 1 | LED ou módulo RGB | Tipo de comum, pinagem e resistores já existentes |
| 2 | Botões ou sensores de contato | Contatos fechados quando a porta está fechada |
| 1 | Buzzer ativo 5 V, até 50 mA | Identificar polaridade e tipo; acionar com transistor |
| 1 | Transistor NPN compatível, resistor de 470 Ω e resistor de 10 kΩ | Conferir pinagem; resistor de base e pull-down para o buzzer |
| Até 3 | Resistores para os canais RGB | Usar somente se o módulo não tiver resistores adequados; dimensionar ao LED |
| 1 | Conversor de nível 3,3 V ↔ 5 V adequado a UART | Confirmar operação nos dois sentidos e tensões dos módulos; não assumir que um conversor I²C sirva |
| Conforme DY50 | Conversão de nível para o UART do sensor | Necessidade depende dos níveis da unidade física |
| 1 | Fonte 5 V regulada para lógica | Dimensionar para Mega, módulos e picos da CAM; conferir se há proteção contra retorno ao usar USB |
| 1 | Fechadura 12 V / 2 A e fonte adequada | Confirmar regime da bobina e forma de retravamento antes de energizar |
| 1 | Driver de potência para a fechadura e proteção indutiva | Entrada compatível com Mega 5 V e carga DC de 12 V / 2 A com margem |
| Conforme montagem | Cabos, conectores e protoboard para sinais | Usar fios e conexões dimensionados para a corrente da fechadura; não conduzir 2 A pela protoboard |

A versão anterior com ESP32 DevKit foi descontinuada.

## Ferramentas e itens de apoio (aprovados pelo dono em 30/10/2026)

| Quantidade | Material | Uso |
|---|---|---|
| 1 | Multímetro | Medições de tensão do roteiro |
| 2 | Jumpers para D30 e D31 a GND na bancada | Acionamento de teste das entradas na bancada |
| 1 | Resistor de 10 kΩ adicional | Pull-down da entrada do driver da fechadura (D35) |
| 1 | Resistor de 220 Ω a 1 kΩ | Teste da entrada do driver sem firmware (seção 6 do MONTAGEM) |
| 1 | Computador com Python 3.9+ na mesma rede | Servidor e testes |
| 1 | Rede Wi-Fi de 2,4 GHz | Conexão do servidor e da ESP32-CAM |
