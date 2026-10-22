# Controle de acesso — escopo aprovado

Protótipo acadêmico autônomo em ESP32, com leitor DY50, teclado 4×4, LCD 16×2,
LED RGB, buzzer ativo, dois botões na mesma porta e fechadura de 12 V / 2 A.
Não há motor adicional para mover a porta ou a trava.

## Credenciais e administração

- Até 100 pessoas ao longo da vida da instalação: IDs 001 a 100, nunca reutilizados.
- Uma digital e uma senha exclusiva de 6 dígitos por pessoa; qualquer uma libera acesso.
- Digital lida duas vezes, com retirada do dedo entre leituras; senha digitada duas vezes.
- Impedir digital repetida e senha repetida, inclusive pertencentes a inativos.
- Salvar o cadastro somente depois de validar as duas credenciais.
- Administrador configurado no código com os 10 dígitos escolhidos na conversa.
  Na distribuição GitHub, o valor fica no `Config.h` local ignorado pelo Git;
  o repositório contém somente `Config.example.h`, sem a senha pessoal.
- `#` confirma; `*` limpa a entrada; `D` cancela cadastro/administração e volta.
  Em espera limpa a entrada; não altera uma autorização já concedida.
- Menu: cadastrar, desativar, reativar e sair. Desativação é soft delete.
- Reativação mantém ID, senha e digital. Não apagar modelos de inativos do DY50.
- Redefinir senha somente pelo computador, por USB ou página do servidor.
- A mesma senha de administrador autentica as três interfaces.
- Cadastros persistem na flash do ESP32; modelos biométricos persistem no DY50.
- LCD informa o ID autorizado e o ID responsável ao detectar abertura.

## Porta e sinalização

- Fechada somente com os dois botões pressionados e estabilizados por debounce.
- Sem abertura após autorização: expirar a janela de acesso após 60 segundos.
- Após abrir: aguardar até 5 minutos; depois, vermelho piscando e “Feche a porta”.
- Ao fechar: terminar o ciclo, desligar o acionamento e aguardar outra credencial.
- Azul: uma piscada curta a cada minuto em espera (apagado no restante do minuto).
- Verde: autorização, aguardando abertura. Amarelo piscando: aberta autorizada.
- Vermelho por 2 segundos: credencial recusada. Vermelho piscando: abertura sem
  autorização ou porta aberta por mais de 5 minutos. Roxo: administração/cadastro.
- Erro de leitura/armazenamento: mensagem explícita; não cadastrar nem liberar por erro.
- Buzzer: três bipes curtos quando expirar 1 minuto sem abrir. Se a porta ficar
  aberta por 5 minutos, bipes periódicos até fechar. Nenhum som durante os 5 minutos
  de espera normais. O buzzer avisa; não move a porta nem substitui a fechadura.

**Limite mecânico:** o tempo da bobina não é a janela de acesso. O acionamento
físico será habilitado após o ensaio da fechadura. Há modos de pulso e de manter
energizada até abrir/expirar. O segundo só pode ser usado se o fabricante permitir.
Se a trava por pulso só retravar ao encaixar a lingueta, expirar os 60 segundos
não a retrava fisicamente. Os botões medem a porta, não o engate da lingueta.

## Rede e servidor

- ESP32 entra no Wi-Fi de 2,4 GHz e sincroniza horário por NTP.
- Acesso continua funcionando sem Wi-Fi, internet ou computador.
- Servidor Python no computador da mesma rede; banco SQLite e página web.
- Histórico com ID quando conhecido, tipo de evento, método, horário e sessão.
- Sem horário sincronizado: registrar tempo desde a inicialização, sem inventar data.
- Fila limitada em RAM, retirada após confirmação do servidor; perde pendências no reboot.
- Para simplificar o protótipo, fila cheia descarta o evento novo e conta a perda.
- Servidor usa chave de evento para não duplicar reenvios. Comandos web ficam
  pendentes até o ESP32 confirmar aplicação; interface distingue pendente e aplicado.
- Nenhuma senha individual nem modelo biométrico é gravado nos eventos.
- Página permite consultar histórico, ver IDs recebidos e solicitar nova senha.

## Fora do escopo

Aplicativo móvel, nuvem pública, OTA, fila durável, recuperação de senha sem
administrador, garantia de integridade contra ataque físico e uso comercial.
HTTP fica restrito à rede local de demonstração; não publicar esse servidor na internet.

## Decisões de implementação

Servidor em Python sem dependências externas; interface HTML/CSS/JavaScript local.
Arduino framework no ESP32 clássico WROOM-32E. Biblioteca Adafruit Fingerprint,
Keypad e LiquidCrystal I2C. LCD I²C de 5 V com conversão de nível para o ESP32.
Buzzer ativo de 5 V acionado por transistor no GPIO2, com pull-down no reset.
Fila de 128 eventos e cadastro em registros NVS individuais. Senhas individuais
guardadas como SHA-256 com salt, sem serem exibidas nem exportadas.

## Validação antes da demonstração

Compilar o firmware; testar servidor/autenticação/reenvios/comandos; testar a máquina
de estados com relógio simulado. Na bancada validar pinagens, níveis elétricos,
capacidade do DY50, duplicidade de digital, mecanismo da trava, reinicialização,
LEDs, LCD, sensores, cadastro, soft delete/reativação e operação sem rede.
