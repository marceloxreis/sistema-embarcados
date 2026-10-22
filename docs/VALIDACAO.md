# Evidências de validação — 22/10/2026

## Firmware

Compilação real para `esp32:esp32:esp32` / **ESP32 Dev Module**, pacote Espressif
**3.3.12**, Arduino CLI **1.5.2-rc.1**. Fontes de aplicação sem substituição de
bibliotecas nem simulação das APIs durante a compilação.

Resultado:

```text
Sketch uses 1006556 bytes (76%) of program storage space. Maximum is 1310720 bytes.
Global variables use 56896 bytes (17%) of dynamic memory, leaving 270784 bytes for local variables. Maximum is 327680 bytes.
```

A RAM informada pelo compilador refere-se às variáveis globais; as filas, pilhas
de tarefas e conexões de rede também alocam memória em execução. O consumo máximo
real requer medição na placa durante o teste de bancada.

Bibliotecas: Adafruit Fingerprint 2.1.4, Keypad 3.1.1, LiquidCrystal I2C 1.1.2,
ArduinoJson 7.4.3. A biblioteca LiquidCrystal I2C gera aviso por declarar `avr`
nos metadados; a compilação para ESP32 terminou com sucesso. Isso ainda não
comprova endereço I²C, contraste nem funcionamento no LCD físico.

### Particularidade do computador usado na validação

O Arduino CLI baixou `ctags` somente x86_64, incompatível com este Mac ARM sem
Rosetta. Para validar, foi compilado o ctags oficial do repositório Arduino em
ARM64, com dois nomes de macros internos ajustados para não colidir com o SDK
macOS. Essa ferramenta foi selecionada por `runtime.tools.ctags.path`, sem
alterar a instalação Arduino do usuário. O firmware foi compilado normalmente
pelo compilador Xtensa do pacote ESP32. Nenhuma dessas ferramentas integra o ZIP.

## Testes locais

- **16 testes HTTP**: autenticação, isolamento de papéis, configuração explícita
  do servidor sem senha pessoal padrão, persistência SQLite,
  confirmação após armazenamento, reenvio sem duplicação, colisão de eventos,
  soft delete/reativação, horário desconhecido, comandos pendentes/aplicados/
  recusados, token estável após reinício do servidor, filtro por ID antes do
  limite de 200 eventos e ausência de senhas no painel.
- **11 testes do firmware no computador**, executando trechos reais do sketch:
  autenticação, senha/digital desconhecida, cadastro com duas capturas e duas
  senhas, duplicidade entre ativos/inativos, falha de gravação, soft delete,
  reativação, limite vitalício de 100 IDs, USB/autenticação/confirmação/timeout,
  replay web após reset USB e os dois problemas encontrados na revisão.
  Leitor, NVS, hash e relógio são dublês de teste explícitos. A retomada recarrega
  os registros no harness, sem executar o `setup()` completo. Não é ensaio da
  persistência física nem da implementação criptográfica.
- **26 verificações C++** da lógica usada pelo firmware: 60 segundos sem abrir,
  5 minutos aberta, fechamento, abertura sem autorização, ID do ciclo e rollover.
- Sintaxe de Python e JavaScript verificadas.
- Painel aberto no navegador; login e estado inicial sem dados conferidos.
  `painel.png` registra essa interface sem dispositivo conectado.
- Revisão independente do código: corrigido reenvio de comando web que poderia
  sobrescrever reset USB após reboot; token e hash passam a ser persistidos juntos.
  Revisão de retorno não identificou outro problema acionável no escopo acadêmico.
- Auditoria posterior de **dois agentes distintos**, cobrindo o projeto inteiro:
  corrigidos bloqueio de digital por senha parcial, falso cancelamento com D e
  filtro incompleto de histórico. Acrescentados os testes de credenciais descritos
  acima. Ambos reavaliaram as correções, executaram os 26 testes e não identificaram
  novo achado acionável. Detalhes em [AUDITORIA.md](AUDITORIA.md).

Comandos de validação (a partir da pasta de trabalho da sessão; caminhos locais
da ferramenta não são requisitos para o computador da montagem):

```sh
python3 -m unittest discover -s outputs/controle-acesso-esp32/tests -v
c++ -std=c++11 -isysroot /Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk outputs/controle-acesso-esp32/tests/test_door.cpp -o work/test_door
work/test_door
node --check outputs/controle-acesso-esp32/servidor/static/app.js
python3 -m py_compile outputs/controle-acesso-esp32/servidor/server.py
work/toolchain/arduino-cli compile --fqbn esp32:esp32:esp32 --config-file work/arduino-config.yaml --build-property runtime.tools.ctags.path=work/toolchain/ctags-master --build-path work/esp32-build outputs/controle-acesso-esp32/firmware/ControleAcesso
```

## Limites desta entrega

### Atualização posterior: buzzer e materiais completos

O usuário descartou o motor adicional e pediu buzzer para prazo de abertura
expirado e porta aberta por mais de 5 minutos. A fechadura elétrica foi mantida.
Adicionados `BuzzerLogic.h`, acionamento no GPIO2, lista `MATERIAIS.md` e teste
portátil que integra os eventos de `DoorLogic` aos padrões de som.

Suíte após o buzzer: **27 testes passaram** (11 de firmware, 15 HTTP e 1 que compila e
executa os cenários C++ do buzzer). Firmware recompilado com sucesso, com os
valores de memória acima. O revisor de integração também executou a suíte e
não identificou bug concreto no buzzer, pinagem ou BOM. A auditoria histórica
de dois agentes em AUDITORIA.md antecede essa atualização.

Alertas: três bipes de 200 ms quando expiram 60 segundos sem abrir; 250 ms a
cada 2 segundos após 5 minutos aberta; para ao fechar. Saída sem `delay()`.
Esses testes verificam os intervalos lógicos; som/volume, transistor, regime
elétrico e comportamento durante boot ainda precisam da bancada.

### Preparação para GitHub e nova revisão

Os dois revisores reexaminaram a versão com buzzer e materiais antes da publicação.
Não identificaram novo defeito funcional. Foi corrigida a dependência dos testes
do arquivo pessoal: usam agora `Config.example.h`. `Config.h` local é ignorado
pelo Git, assim como bancos, variáveis `.env`, logs e binários. O servidor exige
`ADMIN_PIN` e `DEVICE_KEY` no ambiente; nenhuma senha pessoal padrão é distribuída.

Suíte atual: **28 testes passaram**, incluindo a validação da configuração do
servidor. As credenciais efetivas da cópia local não entram no repositório nem
no manifesto/ZIP de distribuição. O modelo usa dados de demonstração e deve ser
copiado/configurado para compilar o firmware de uma nova instalação.

Uma cópia limpa, sem `Config.h` pessoal, passou nos 28 testes. Depois disso, o
modelo foi copiado para `Config.h` somente nessa cópia de validação, e o firmware
compilou com sucesso. Os valores de memória no início deste documento correspondem
a essa compilação com o template. Não houve execução de CI hospedada no GitHub.

### Pendências físicas

Não houve placa conectada, gravação de firmware, cadastro real de digital,
operação elétrica da fechadura, teste de nível UART ou comunicação real ESP32 ↔
servidor. Os testes do servidor usaram requisições sintéticas em banco temporário.
A retomada web/USB também foi exercitada com dublês no computador; o roteiro
físico continua incluindo esse cenário. NTP, tarefa de rede/fila FreeRTOS e
inicialização completa do ESP32 ainda dependem de integração na bancada.

`LOCK_MODE=0` é deliberado. A regra de expirar a autorização em 1 minuto está no
código; retravar fisicamente sem abrir depende do mecanismo da fechadura, ainda
não confirmado. A saída nunca deve ser mantida ligada por 60 segundos sem
confirmação de que a bobina admite esse regime.
