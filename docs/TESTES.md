# Roteiro de validação e testes

## Evidência de simulação da arquitetura Mega + CAM

`python3 -m unittest discover -s tests -v` inclui integração de funções reais
dos sketches via UART simulada: cadastro, autorização, captura dublada, perda de
ACK, retransmissão, comando de reset, alteração por USB e repetição após reboot.
Outra prova usa a serialização real da CAM e repassa evento e JPEG sintético a um
servidor HTTP real com SQLite temporário; o transporte da CAM é dublado. Há
testes de interrupções de EEPROM, integridade de quadros, filas, autenticação e
idempotência. Não é um emulador completo dos microcontroladores, não executa
Wi-Fi/câmera físicos e não comprova a temporização de ponta a ponta.
O teste da `networkTask` com rede dublada também cobre reconexão, falhas de
evento e foto, confirmações com ID incorreto e reset confirmado pelo controlador.
Os testes do Mega cobrem abertura durante busca de senha, cadastro de digital e
escrita na EEPROM, além de timeout do LCD. A quantidade de testes muda com a
suíte: consulte a saída de `python3 -m unittest discover -s tests -v`.

O teste `tests/test_frescor_agent.py` exige ausência de foto se houver
atraso de 6 s anterior à leitura UART e verifica o desafio vinculado ao evento.
Outros testes simulam prova tardia, reboot, rollover, reset durante espera do
leitor, prioridade da prova e saturação. O resultado depende de dublês e não
comprova tempo de exposição ou segurança contra atacante na UART.

Testes locais adicionais cobrem permissões de banco novo, nomes SQLite rejeitados,
corpo HTTP incompleto, concorrência de autenticação, backlog e falha de início do
temporizador. O prazo da conexão fecha o socket, mas não interrompe um handler
bloqueado fora da operação de rede. Os testes não garantem segurança contra
troca de caminho, nem protegem backups ou validam a rede física.

A biblioteca Adafruit Fingerprint 2.1.4 real foi exercitada com UART simulada e
o filtro do Mega: ACKs válidos, checksum incorreto, endereço e tipo inválidos,
comprimento incompatível e timeout. Em erro de comunicação, o leitor é
desabilitado até reiniciar. O protocolo não autentica o leitor nem contém ID de
transação; o teste não prova compatibilidade com a unidade DY50 física.

Há registros de retomadas anteriores (simulação simavr e painel em navegador) sem artefato no repositório; não contam como validação.

## Roteiro de bancada

Os ensaios físicos estão **pendentes de execução**. A montagem, as ligações, a
ordem de energização e o roteiro de comunicação (seção 5) estão em
[MONTAGEM.md](MONTAGEM.md). Os ensaios funcionais, que vêm depois desse roteiro,
estão na seção seguinte. Faça o primeiro ensaio com a carga desconectada e
`LOCK_MODE=0`. O código não transforma simulação em evidência real.

Na bancada, anote a fonte utilizada, o modelo do driver, a versão do DY50, o
endereço do LCD, o modo e a duração do acionamento aprovados e o resultado de
cada ensaio.

## Ensaios funcionais de bancada (Mega + CAM)

Execute esta seção somente depois do roteiro de comunicação de
[MONTAGEM.md](MONTAGEM.md) (seção 5), com `LOCK_MODE=0` e a fechadura e o driver
desconectados. "Mega" indica o controle local (teclado, DY50, LCD, LED, buzzer,
botões e EEPROM); "CAM" indica rede, horário, fila de rede e foto. Tempos em
segundos (60 s = um minuto). Registre cada linha como passou, falhou ou não
executado, com data e observação. Os números entre parênteses referem-se aos
requisitos de [ESCOPO.md](ESCOPO.md).

| Ensaio | Procedimento | Resultado esperado |
|---|---|---|
| Roteiro de comunicação (req. 5) | Executar os passos 1 a 7 de MONTAGEM seção 5 e registrar cada resultado | Todos registrados; falha interrompe os ensaios seguintes |
| Componentes (req. 20) | Conferir a montagem com MATERIAIS.md | Sem RTC, microSD, motor extra ou MCP23017 |
| Boot com ambos os botões (req. 14) | Ligar o Mega com os dois botões da porta pressionados | Aguarda credencial; saída desligada |
| Boot com botão solto (req. 14) | Ligar o Mega com um botão solto | Vermelho piscando; "Feche a porta"; não libera |
| Cada tecla (req. 1) | Pressionar cada tecla do teclado 4x4 isoladamente | Dígito ou letra correto; falha indica matriz ou pull-up |
| `*` durante entrada (req. 9) | Digitar três dígitos e pressionar `*` | Apaga todos os dígitos da entrada atual |
| `D` na espera (req. 9) | Digitar dígitos e pressionar `D` na tela de acesso | Limpa a entrada; nenhuma autorização alterada |
| `D` após autorizar (req. 9) | Autorizar por senha e pressionar `D` antes de abrir | Autorização mantida; sem aviso de cancelamento |
| Digital após senha parcial (req. 10) | Digitar três dígitos de uma senha e apresentar digital cadastrada | Autoriza pela digital e limpa a entrada parcial |
| Senha correta (req. 7, 13, 18) | Digitar a senha de 6 dígitos + `#` | Verde; ID correto no LCD; evento `access_granted` com método password |
| Digital correta (req. 7, 13) | Apresentar digital cadastrada | Mesmo ID no LCD; método fingerprint |
| Credencial desconhecida (E1, E7) | Apresentar senha ou digital não cadastradas | Vermelho por 2 s; não aciona; evento `access_denied` sem senha nem modelo |
| Credencial de outra pessoa no ciclo (req. 13) | Com porta aberta por um ID, apresentar outra credencial válida | Não substitui o ID responsável pela abertura |
| Admin correta (req. 8, 9, 18) | Digitar a senha de 10 dígitos + `#` | Roxo; menu com 1, 2, 3 e D; não há opção de redefinir senha |
| Admin incorreta (req. 8) | Digitar outra senha de 10 dígitos + `#` | Não entra no menu; não libera; vermelho |
| `D` no menu/cadastro (req. 9, E2) | Pressionar `D` durante o menu ou um cadastro | Cancela e retorna ao acesso |
| Menu com 1/2/3/D (E2) | Conferir as opções do menu | Cadastrar, desativar, reativar e sair |
| Cadastro com o mesmo dedo (req. 8) | Retirar, colocar, retirar e colocar o mesmo dedo | Avança para criação da senha |
| Dedos diferentes (req. 8) | Cadastrar com dedos diferentes nas duas leituras | Não salva; retorna com erro |
| Erro de leitura no cadastro (E4) | Dedo mal posicionado ou sensor coberto (imagem ilegível); dedos diferentes nas duas leituras; depois, sem tocar o sensor por 60 s | LCD "Cadastro falhou" com motivo "Digital ilegivel", "Erro de leitura" ou "Digitais diferem"; evento `enroll_failed`; ID não consumido; nada salvo; nenhuma liberação. Sem toque por 60 s: "Tempo esgotado" e "Cadastro cancelado" (cortado para 16 colunas) |
| Digital repetida (req. 7, E3) | Cadastrar digital de pessoa ativa ou inativa já existente | Recusa duplicidade; modelo do DY50 não é apagado |
| Senhas diferentes (req. 8) | Digitar senhas diferentes na criação e na confirmação | Pede nova senha e confirmação |
| Senha repetida (req. 7) | Usar senha já cadastrada para ativo ou inativo | Recusa |
| Cadastro completo (req. 6, 8) | Concluir digital, senha e confirmação com `#` | Novo ID sequencial; só então publicado |
| Cancelar cadastro (req. 6, 9) | Cancelar com `D` antes de concluir | Não consome novo ID |
| Desativar ID (req. 11, E2, E3) | Desativar um ID pelo menu | Registro permanece; senha e digital recusadas |
| Reativar ID (req. 11) | Reativar o mesmo ID | Mesmo ID, mesma senha e mesma digital funcionam |
| ID não reutilizado (req. 6) | Desativar o último ID e cadastrar nova pessoa | Recebe o próximo ID; o desativado não é reaproveitado |
| Limite de 100 IDs (req. 6) | Com 100 IDs já usados, inclusive inativos, tentar novo cadastro | Recusado |
| Reiniciar com cadastros (req. 11) | Reiniciar o Mega | IDs, estado e senhas continuam na EEPROM; modelos no DY50 |
| Azul em espera (req. 18) | Observar a sinalização em espera | Uma piscada de 200 ms a cada 60 s; apagado no restante |
| Só um sensor pressionado (req. 14) | Com ciclo ativo e porta aberta, pressionar só um botão da porta (de Idle, um sensor solto dispara `forced_open`) | Continua considerando a porta aberta; o ciclo não é encerrado |
| Toque curto nos dois botões (req. 14) | Tocar os dois botões por menos de 50 ms | Não é considerado fechamento |
| Ambos pressionados por 50 ms (req. 14, 17) | Com a porta aberta, pressionar os dois botões | Encerra o ciclo; saída desligada |
| Sem abertura em 59 s (req. 15) | Autorizar e aguardar 59 s sem abrir | Continua aguardando; sem bipe |
| Sem abertura em 60 s (req. 15) | Autorizar e aguardar 60 s sem abrir | Expira o ciclo; três bipes de 200 ms com 200 ms entre eles; saída desligada; retravamento físico depende da trava |
| Abriu e manteve 4 min 59 s (req. 16, 18) | Abrir a porta após autorizar e aguardar | Amarelo piscando; ID no LCD |
| Abriu e manteve 5 min (req. 16, E1) | Manter a porta aberta por 5 min | Vermelho piscando; "Feche a porta"; bipe de 250 ms a cada 2 s |
| Fechar após alerta (req. 16, 17) | Fechar a porta após o alerta de 5 min | Bipes param; ciclo encerrado; aguarda outra credencial |
| Porta aberta sem autorização (E1) | Abrir a porta sem credencial (ex.: sensor solto) | Alarme: vermelho piscando; não aceita abertura normal |
| Boot e espera normal (req. 15) | Ligar, aguardar sem interação e depois enviar `AUTH <senha de administrador>` e `STATUS` pelo USB | Buzzer desligado na espera; `STATUS` responde depois do AUTH |
| STATUS e BOOT no USB (req. 1, 19) | Abrir o monitor a 115200, enviar `AUTH <senha de administrador de 10 dígitos>` e `STATUS`; ler a linha `BOOT` ao reiniciar | `OK authenticated`; STATUS no formato `last_id=... queued=... dropped=... replies_dropped=... lcd=ok|timeout dy50=ok|indisponivel lock_mode=0`; BOOT com `storage=`, `lcd=`, `dy50=` e `lock_mode=0`; AUTH errado responde `ERR auth`; sem AUTH, `ERR auth_required` |
| Modo da trava (req. 1, 17) | Com `LOCK_MODE=0`, medir a saída de acionamento (D35) durante um ciclo | 0 V; saída não aciona a fechadura |
| Sem internet ao iniciar (req. 19, 21, E8) | Ligar com Wi-Fi/internet indisponível (sem NTP) | Acesso local funciona; eventos sem data (painel mostra "Sem horário", sessão e segundos desde a inicialização). Com Wi-Fi e NTP no ar, parar o servidor não remove a data dos eventos |
| Retornar internet (req. 21) | Restabelecer Wi-Fi e NTP | Novos eventos recebem data e hora; eventos antigos não são reescritos |
| Wi-Fi da CAM desligado (req. 19) | Desligar o Wi-Fi da CAM e acessar | Acesso local funciona; CAM imprime "Fila CAM: rede indisponivel; item mantido para reenvio" |
| Servidor parado com Wi-Fi no ar (req. 19) | Parar o servidor, manter o Wi-Fi e acessar | Acesso local funciona; CAM imprime `Fila CAM: <id> evento: rede/transporte (<status>); item mantido para reenvio`; `queued` do Mega continua 0, porque a CAM envia o ACK ao enfileirar, mesmo sem servidor |
| Fila cheia no Mega (E5) | Só sem ACK da CAM (CAM desligada ou desconectada do Mega): gerar 16 eventos além do `device_boot` | Os 15 primeiros enchem a fila (`queued=16`) e o 16º incrementa `dropped`; eventos já na fila são preservados; ao restaurar a CAM e o servidor, os enfileirados são enviados. Servidor parado sozinho não enche a fila do Mega |
| Retornar servidor (req. 19, E6) | Restabelecer o servidor com fila pendente | Eventos enviados; `queued=0` após o ACK da CAM (a entrega ao servidor se confirma no painel) |
| Reenvio sem duplicação (E6) | Desligar e religar o Wi-Fi com item pendente | Evento aparece uma vez no painel |
| Reiniciar sem enviar fila (req. 19) | Reiniciar o Mega com eventos pendentes | Pendentes perdidos, como previsto no escopo |
| Câmera e Wi-Fi da CAM (req. 2) | Ligar a CAM e observar o monitor a 115200 | `CAM boot <id> camera=ok`; `CAM wifi conectado <ip>` |
| Recepção UART (req. 2) | Gerar um evento com a CAM sem servidor | CAM imprime uma das duas mensagens "Fila CAM: ..." (MONTAGEM seção 5, passo 5); `queued=0` com `dropped=0` e `replies_dropped=0` prova o ACK da CAM |
| Descarte HTTP permanente da CAM | Sem procedimento de bancada simples e seguro para repetir 400/409/413/422 no mesmo item. Verificado só em teste host (`tests/test_camera_network.py`, `test_queue_drop_and_permanent_rejection_counters`) | Teste host: `DESCARTADO apos 5 rejeicoes HTTP permanentes` só após 5 rejeições em 30 s ou mais, com Wi-Fi contínuo. Aviso de descartes no painel (`servidor/static/app.js`) não verificado na bancada |
| Foto em acesso autorizado (req. 3, 4) | Autorizar com CAM e servidor no ar | Uma foto por evento `access_granted`, vinculada ao ID; "Ver foto" carrega a imagem |
| Acesso autorizado sem foto (req. 3, E4) | Ligar a CAM sem a câmera encaixada (CAM desligada ao mexer no flat) e autorizar um acesso | Monitor mostra `CAM boot <id> camera=falha`; evento sem foto (`photo_unavailable`); painel mostra "Foto indisponível" |
| Acesso negado sem foto (req. 3) | Apresentar credencial desconhecida com CAM e servidor no ar | Evento `access_denied` no painel sem foto |
| Sem streaming (req. 3) | Com o painel fechado, observar o tráfego da CAM durante um acesso | Apenas um JPEG por evento autorizado; sem transmissão contínua |
| Página com senha errada (req. 22) | Entrar no painel com senha incorreta | HTTP 401; nenhum histórico exibido |
| Filtrar ID (req. 4) | Filtrar um ID com registros antigos e 200 eventos posteriores de outras pessoas | Busca no SQLite antes do limite; mostra eventos daquele ID |
| Dados no painel (E7) | Conferir o histórico após cadastros e acessos | Nenhuma senha individual nem modelo biométrico visível |
| Reset pela página (req. 12, E6) | Enviar redefinição com Mega e CAM ligados | Pendente até o Mega confirmar; depois aplicada ou recusada conforme o retorno |
| Reset web com senha de outro ID (req. 12) | Pedir senha já usada por outro ID | Mega recusa (senha em uso); senha antiga continua válida |
| Reset USB (req. 12, 22) | `AUTH`, depois `RESET <id> <senha> <senha>` | `OK ok`; novo acesso com a senha nova funciona; a antiga não. Falhas: `ERR <motivo>` (`unknown_user`, `device_busy`, `invalid_pin`, `pin_in_use`, `storage_error`) ou `ERR invalid_or_mismatched` |
| USB sem AUTH (req. 12) | Enviar `RESET` sem autenticar | `ERR auth_required`; comando recusado |
| Reset em pessoa inativa (req. 11, 12) | Redefinir senha de ID inativo | Senha alterada sem reativar a pessoa |
| Reenvio de reset após reboot (E6) | Reiniciar o Mega após reset aplicado e ocorrer reenvio | Confirma sem reaplicar; não sobrescreve reset USB mais novo |

## Comandos de testes locais

Na raiz do projeto:

```sh
python3 -m unittest discover -s tests -v
CONTROLE_TEST_LIBS=<diretorio-das-bibliotecas> CONTROLE_TEST_STRICT=1 python3 -m unittest discover -s tests -v
c++ -std=c++11 tests/test_door.cpp -o /tmp/test_door && /tmp/test_door
node --check servidor/static/app.js
```

Na segunda linha, `<diretorio-das-bibliotecas>` é o diretório preparado pelo
`scripts/bootstrap-test-libs.py`, descrito na seção "Bibliotecas para testes
digitais em computador" do [README](../README.md). `CONTROLE_TEST_STRICT=1` faz
a verificação das bibliotecas falhar o teste, em vez de ser ignorada. Confira
também o total de `skipped` na saída.

O teste de servidor cria banco temporário e servidor em porta local aleatória;
não acessa placa, digitais reais ou banco de demonstração.

`test_buzzer.py` compila a classe real `BuzzerLogic.h` e verifica os dois prazos
junto com `DoorLogic`, os padrões de bipes, parada ao fechar e rollover.

Para compilar os dois sketches via CLI, após instalar os pacotes de placa e as
bibliotecas indicadas no README:

```sh
arduino-cli compile --fqbn arduino:avr:mega firmware/MegaControlador
arduino-cli compile --fqbn esp32:esp32:esp32cam firmware/Esp32CamRede
```
