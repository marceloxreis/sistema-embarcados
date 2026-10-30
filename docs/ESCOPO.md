# Controle de acesso — escopo aprovado (Mega 2560 + ESP32-CAM)

Protótipo acadêmico com Arduino Mega 2560 como controlador local, leitor DY50,
teclado 4×4, LCD 16×2 I²C, LED RGB, buzzer ativo, dois botões na mesma porta,
fechadura de 12 V / 2 A e ESP32-CAM Ai-Thinker para rede e captura de foto.
Não há motor adicional para mover a porta ou a trava.

Os números de requisito (1–23 e E1–E8) identificam os itens aprovados e são
mantidos para rastreio. A versão anterior com ESP32 DevKit não faz parte da entrega.

## Requisitos gerais e papel de cada placa

- [1] Mega 2560 controla teclado, DY50, LCD, RGB, dois botões da porta, buzzer e
  fechadura; valida credenciais localmente e funciona sem internet.
- [2] ESP32-CAM recebe eventos do Mega por UART, conecta-se ao Wi-Fi, sincroniza
  horário por NTP, envia a auditoria ao servidor e mantém a câmera ativa.
- [3] Uma foto por acesso autorizado, salva no servidor. Sem reconhecimento facial,
  sem streaming e sem foto de acesso negado.
- [4] Servidor no computador grava a auditoria, permite redefinir senha e vincula
  cada foto ao evento e ao ID.
- [5] Guia de montagem e conexões passo a passo, com os dois programas (Mega e CAM).
- [22] Servidor na mesma LAN; histórico e redefinição de senha são autenticados.
- [23] Projeto acadêmico: sem plataforma comercial, nuvem ou streaming.
- [20] Sem RTC, sem microSD, sem motor extra e sem MCP23017.

## Credenciais e administração

- [6] Até 100 pessoas ao longo da vida da instalação: IDs 001 a 100, automáticos,
  incluindo inativos. Um ID nunca é reutilizado.
- [7] Uma digital e uma senha exclusiva de 6 dígitos por pessoa; qualquer uma libera
  acesso. Credenciais de pessoas inativas permanecem reservadas.
- [8] Cadastro com administrador de 10 dígitos: digital lida duas vezes, com retirada
  do dedo entre as leituras; senha digitada duas vezes. O cadastro só é salvo depois
  de validar as duas credenciais.
- [E3] Impedir digital repetida, inclusive de pessoa inativa, e não apagar os modelos
  de inativos do DY50.
- Impedir senha repetida, inclusive de pessoa inativa.
- Administrador configurado no código com os 10 dígitos escolhidos na conversa.
  Na distribuição GitHub, o valor fica no `Config.h` local ignorado pelo Git;
  o repositório contém somente `Config.example.h`, sem a senha pessoal.
- [9] `#` confirma; `*` limpa a entrada; `D` cancela cadastro/administração e volta.
  Em espera, `D` limpa a entrada e não altera uma autorização já concedida.
- [E2] Menu: cadastrar, desativar, reativar e sair.
- [11] Desativação é soft delete. Reativação mantém ID, senha e digital.
- [10] Senha parcialmente digitada não bloqueia a leitura de digital.
- [12] Redefinir senha somente pelo computador, por USB ou pela página do servidor,
  com a mesma senha de administrador, mantendo a unicidade das senhas.
  A mesma senha de administrador autentica as três interfaces.
- Cadastros persistem na EEPROM do Mega; modelos biométricos persistem no DY50.
- [13] LCD informa o ID autorizado e mantém o ID responsável enquanto a porta está aberta.
- [E4] Erro de leitura ou armazenamento: mensagem explícita; não cadastrar nem liberar
  acesso por erro.

## Porta e sinalização

- [14] Porta fechada somente com os dois botões pressionados e estabilizados por
  debounce de 50 ms.
- [15] Sem abertura após autorização: a janela expira em 60 segundos; então três bipes
  de 200 ms, com 200 ms entre eles.
- [16] Após abrir: aguardar até 5 minutos; depois, vermelho piscando e “Feche a porta”,
  com bipe de 250 ms a cada 2 segundos até fechar.
- [17] Ao fechar: encerrar o ciclo, desligar o acionamento e aguardar outra credencial.
- [18] Azul: uma piscada de 200 ms a cada minuto em espera. Verde: autorização,
  aguardando abertura. Amarelo piscando: aberta autorizada. Vermelho: erro ou alarme.
  Roxo: administração/cadastro.
- [E1] Vermelho por 2 segundos quando a credencial é recusada. Vermelho piscando quando
  a porta é aberta sem autorização.
- Buzzer: avisa a expiração e a porta aberta por 5 minutos. Nenhum som durante a espera
  normal. O buzzer avisa; não move a porta nem substitui a fechadura.

**Limite mecânico:** o tempo da bobina não é a janela de acesso. O acionamento
físico será habilitado após o ensaio da fechadura. Há modos de pulso e de manter
energizada até abrir/expirar. O segundo só pode ser usado se o fabricante permitir.
Se a trava por pulso só retravar ao encaixar a lingueta, expirar os 60 segundos
não a retrava fisicamente. Os botões medem a porta, não o engate da lingueta.

## Rede, fila e servidor

- [2] A CAM entra no Wi-Fi de 2,4 GHz e sincroniza horário por NTP.
- [19] Acesso continua funcionando sem Wi-Fi, sem internet e sem computador.
  Fila em RAM com reenvio: o Mega retira o evento após a CAM aceitá-lo; a CAM retira após a confirmação do servidor.
  Reinício perde as pendências, decisão aceita para o protótipo.
- [E5] Fila cheia descarta o evento novo e conta a perda.
- [21] Sem horário sincronizado: registrar o tempo desde a inicialização (sessão e
  uptime), sem inventar data. Depois da sincronização, os novos eventos recebem data.
- [E8] Sem horário sincronizado, o evento mostra tempo desde a inicialização, sem data
  inventada.
- Histórico com ID quando conhecido, tipo de evento, método, horário e sessão.
- [E6] Servidor deduplica reenvios por chave de evento. Comandos web ficam pendentes
  até o Mega confirmar a aplicação; a interface distingue pendente de aplicado.
- [E7] Nenhuma senha individual nem modelo biométrico é gravado nos eventos.
- Página permite consultar histórico, ver IDs recebidos e solicitar nova senha.

## Fora do escopo

Aplicativo móvel, nuvem pública, OTA (atualização remota de firmware), fila durável,
recuperação de senha sem administrador, garantia de integridade contra ataque físico
e uso comercial. HTTP fica restrito à rede local de demonstração; não publicar esse
servidor na internet.

## Decisões de implementação

Confirmadas pelo código em `firmware/MegaControlador` e `firmware/Esp32CamRede`:

- **Mega:** cadastros em EEPROM com 100 registros de 31 bytes cada e área de journal
  para escrita segura. Cada senha é guardada como SHA-256 truncado em 16 bytes, com
  salt de 4 bytes por registro (`UserStore.h`). Senhas e hashes não são exibidos nem
  exportados.
- **Mega:** fila de 16 eventos em RAM (`outbound[16]`). Fila cheia descarta o evento
  novo e incrementa o contador de perdas.
- **CAM:** fila de 8 itens em RAM (`xQueueCreate(8, ...)`). Cada item pode levar uma
  foto JPEG de até 256 KiB; a foto só é mantida após prova de frescor do Mega.
- **UART Mega ↔ CAM:** 38400 bps, com conversão de nível 5 V ↔ 3,3 V. Os quadros têm
  CRC-16/CCITT-FALSE. A UART não é autenticada.
- **UART do DY50:** 57600 bps no Mega, com filtro de resposta do leitor.
- **Servidor:** Python sem dependências externas (biblioteca padrão), banco SQLite
  e interface HTML/CSS/JavaScript local.
- **Bibliotecas do Mega:** Crypto 0.4.0 (SHA-256), Adafruit Fingerprint 2.1.4,
  Keypad 3.1.1 e LiquidCrystal I2C 1.1.2. **CAM:** ArduinoJson 7.4.3.
- LCD I²C de 5 V ligado direto ao Mega (D20/D21), sem conversão de nível. Buzzer ativo de 5 V acionado por transistor,
  com pull-down e sem pull-up de 5 V no pino do controlador.

## Validação antes da demonstração

Compilar os dois programas; testar servidor, autenticação, reenvios e comandos;
testar a máquina de estados com relógio simulado. Na bancada, validar pinagens,
níveis elétricos, capacidade do DY50, duplicidade de digital, mecanismo da trava,
reinicialização, LEDs, LCD, sensores, cadastro, soft delete/reativação, operação sem
rede e captura de foto pela CAM. A montagem e o roteiro de
comunicação estão em [MONTAGEM.md](MONTAGEM.md) (seção 5); os ensaios funcionais de
bancada estão em [TESTES.md](TESTES.md).
