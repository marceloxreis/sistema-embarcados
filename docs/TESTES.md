# Roteiro de validação na bancada

Esta lista está **pendente de execução física**. Fazer primeiro com a carga
desconectada e `LOCK_MODE=0`. O código não transforma simulação em evidência real.

| Ensaio | Resultado esperado |
|---|---|
| Boot com ambos os botões pressionados | Aguarda credencial; saída desligada |
| Boot com algum botão solto | Vermelho piscando; “Feche a porta”; não libera |
| Cada tecla isoladamente | Dígito/letra correta; verificar matriz e pull-ups |
| `*` durante entrada | Apaga todos os dígitos atuais |
| `D` no menu/cadastro | Cancela e retorna ao acesso |
| `D` após autorizar acesso | Mantém autorização; não anuncia cancelamento |
| Digital válida após digitar parte de uma senha | Autoriza pela digital e limpa a entrada parcial |
| Senha admin correta + `#` | Menu roxo; opções 1/2/3/D |
| Senha admin incorreta | Não entra no menu e não libera |
| Cadastro com mesmo dedo duas vezes | Avança para criação da senha |
| Dedos diferentes | Não salva; retorna com erro |
| Digital de pessoa ativa ou inativa repetida | Recusa duplicidade |
| Senhas diferentes na confirmação | Pede nova senha e confirmação |
| Senha já usada por ativo ou inativo | Recusa |
| Cadastro completo | Novo ID sequencial; só então publicado |
| Cancelar cadastro antes de concluir | Não consome novo ID |
| Acesso por senha correta | Verde; ID correto no LCD e no histórico |
| Acesso por digital correta | Mesmo ID, método digital |
| Senha/digital desconhecida | Vermelho por 2 segundos; não aciona |
| Algum sensor solto sem autorização | Alarme; não aceita abertura normal |
| Autorizou, esperou 59 s sem abrir | Continua aguardando |
| Autorizou, esperou 60 s sem abrir | Expira ciclo e desliga saída; retrava físico depende da trava |
| Não abriu após 1 minuto | Três bipes de 200 ms; depois para |
| Abriu e manteve 4 min 59 s | Amarelo piscando; ID no LCD |
| Abriu e manteve 5 min | Vermelho piscando; “Feche a porta” |
| Alerta de 5 minutos | Um bipe de 250 ms a cada 2 segundos; para ao fechar |
| Boot e espera normal | Buzzer desligado; não interfere em programação USB |
| Só um sensor pressionado | Continua considerando porta aberta |
| Ambos pressionados por 50 ms | Encerra ciclo e saída desligada |
| Credencial de outra pessoa durante ciclo | Não substitui ID responsável pela abertura |
| Desativar ID | Continua existindo; ambas credenciais recusadas |
| Reativar ID | Mesmo ID, mesma senha, mesma digital funcionam |
| ID 100 já utilizado | Novo cadastro recusado mesmo com inativos |
| Reiniciar com cadastros | IDs, estado e senha continuam na flash; modelos no DY50 |
| Azul em espera | Uma piscada de 200 ms a cada minuto; apagado no restante |
| Sem internet ao iniciar | Acesso local funciona; eventos sem data, com sessão/uptime |
| Retornar internet | Relógio sincroniza; novos eventos recebem data |
| Parar servidor ou desligar Wi-Fi | Acesso local funciona; fila cresce |
| Retornar servidor | Eventos enviados; confirmação antes de retirar; sem duplicação |
| Reiniciar sem enviar fila | Eventos pendentes são perdidos, como previsto |
| Página com senha errada | HTTP 401; nenhum histórico exposto |
| Filtrar ID com registros antigos e 200 eventos posteriores de outras pessoas | Busca no SQLite antes do limite; mostra eventos daquele ID |
| Reset pela página | Pendente até ESP32; aplicada/recusada conforme retorno |
| Reset web com senha repetida de outro ID | ESP32 recusa; senha antiga continua válida |
| Reset USB | AUTH, RESET com duas senhas iguais; novo acesso funciona |
| USB sem AUTH | Comando recusado |
| Reset em pessoa inativa | Altera senha sem reativar pessoa |
| Reenvio de reset aplicado após reboot | Confirma sem reaplicar; não sobrescreve reset USB mais novo |

## Comandos de testes locais

Na raiz do projeto:

```sh
python3 -m unittest discover -s tests -v
c++ -std=c++11 tests/test_door.cpp -o /tmp/test_door
/tmp/test_door
node --check servidor/static/app.js
```

O teste de servidor cria banco temporário e servidor em porta local aleatória;
não acessa placa, digitais reais ou banco de demonstração.

`test_firmware.py` requer compilador C++11. Extrai as funções reais de cadastro,
autenticação, teclado, leitura biométrica e parser USB do sketch, executando-as
com leitor/NVS/hash/relógio simulados. São testes das políticas e transições,
não do protocolo elétrico nem da criptografia. O helper de reinicialização dos
testes recarrega os registros, mas não executa `setup()` nem a tarefa FreeRTOS.
`test_buzzer.py` compila a classe real `BuzzerLogic.h` e verifica os dois prazos
junto com `DoorLogic`, os padrões de bipes, parada ao fechar e rollover.
Os dois testes de regressão de entrada parcial e tecla D foram observados
falhando antes das correções e passando depois. O teste do filtro por ID também.

Para compilar via CLI, após instalar o pacote de placas e bibliotecas:

```sh
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/ControleAcesso
```

Na bancada, anotar fonte utilizada, modelo do driver, versão do DY50, endereço
LCD, modo e duração do acionamento aprovados e resultados de cada ensaio.
