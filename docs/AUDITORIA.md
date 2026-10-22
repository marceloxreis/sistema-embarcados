# Auditoria do projeto completo — dois agentes independentes

Data: 22/10/2026. Pedido: verificar o projeto inteiro e possíveis ideias iniciais
não abrangidas. Os dois agentes receberam os requisitos da conversa, inclusive
as simplificações aprovadas, e avaliaram a mesma versão inicial sem editar arquivos.

Este documento registra a auditoria da versão sem buzzer. A atualização posterior
solicitada pelo usuário acrescenta o alerta sonoro e a lista completa de materiais,
sem motor adicional. Seus testes/compilação estão em VALIDACAO.md; não atribuir
automaticamente a atualização inteira à auditoria histórica dos dois agentes.

## Resultado

Não foi identificada uma função aprovada inteiramente ausente nem um defeito P1.
Foram encontrados e corrigidos dois problemas de interação, uma limitação da
consulta de histórico e uma lacuna de testes. Ambos revisaram a versão corrigida
e não identificaram nova falha concreta no escopo acadêmico.

Isso não atesta funcionamento físico: o regime/mecanismo da fechadura e as
ligações da versão física do DY50 continuam abertos para a montagem.

## Revisores

1. **auditoria_requisitos** — rastreabilidade conversa → escopo → código → testes,
   examinando firmware, servidor, painel, materiais e documentação.
2. **auditoria_integracao** — integração entre firmware/servidor/hardware,
   fluxos de entrada, estados da porta, persistência, filas e compatibilidade.

Os agentes trabalharam separadamente e entregaram seus próprios achados.
Após as correções, cada um executou novamente os 26 testes da suíte.

## Achados e tratamento

| Prioridade | Problema observado | Correção / evidência |
|---|---|---|
| P2 | Digitar parte de uma senha bloqueava leitura digital indefinidamente | Removido bloqueio por `entry` em `fingerprintTick()`; `authorize()` limpa entrada somente após autorização. Teste reproduziu falha antes e passou depois. |
| P2 | `D` dizia “Operacao cancelada”, mas autorização continuava ativa | Cancelamento restrito ao cadastro/administração; em espera limpa a entrada; durante autorização não anuncia cancelamento. Documentação e teste ajustados. |
| P2 | Testes não executavam cadastro/autenticação/reset do próprio firmware | Novo `tests/test_firmware.py` executa as funções reais com dublês explícitos: 11 cenários de políticas e persistência simulada. |
| P3 | Filtro por ID procurava apenas dentro dos últimos 200 eventos globais | Filtro levado ao SQL, antes do limite. Painel consulta servidor; teste encontra ID antigo após 200 registros posteriores de outra pessoa. |

Não foi acrescentado cancelamento físico de acesso por D: essa função não havia
sido solicitada e poderia prometer retravamento impossível para uma trava por pulso.

## Cobertura das ideias iniciais

| Ideia / decisão | Situação na versão revisada |
|---|---|
| ESP32 sozinho, sem Mega | Implementado; mapa para WROOM-32E clássico |
| Acesso por senha OU digital da mesma pessoa | Implementado; funciona inclusive após entrada parcial de senha |
| Senha individual de 6 dígitos e admin de 10 no código | Implementado |
| Digital duas vezes, senha duas vezes, ambas conferidas | Implementado e exercitado com dublês |
| Credenciais exclusivas | Recusa digital/senha de ativos e inativos; teste de política incluído |
| IDs 001–100, total inclui inativos, sem reutilização | Implementado; teste de limite e retomada simulada incluído |
| Soft delete, auditoria e reativação com mesmas credenciais | Implementado e testado na lógica do firmware e projeção do servidor |
| Redefinição só pelo computador, USB ou web, mesma senha admin | Implementado; parser/auth USB e políticas de reset exercitados |
| Admin informa nova senha | Implementado com confirmação e validação no ESP32 |
| ID no LCD ao autorizar e ao abrir | Implementado; apresentação física pendente |
| Mesma porta, fechada só com dois botões pressionados | Implementado com debounce de 50 ms; bancada pendente |
| Não abriu em 1 minuto: expira acesso | Lógica testada; retravamento físico depende da fechadura |
| Abriu: até 5 minutos antes de alerta | Lógica testada |
| Fechou: encerra e trava | Comando desliga/encerra; engate mecânico pendente de ensaio |
| Azul uma piscada/minuto, demais estados por cor | Implementado; ensaio visual pendente |
| Wi-Fi/NTP e servidor no computador | Implementado; comunicação com ESP32 físico pendente |
| Acesso sem rede e fila temporária | Implementado; integração FreeRTOS/rede física pendente |
| Fila pode ser perdida em reboot; sem RTC/microSD | Decisão respeitada; não foi tratada como defeito |
| Página para histórico e redefinição autenticada | Implementado e testes HTTP aprovados |
| Histórico com ID, data/hora e método | Implementado; sem NTP registra sessão/tempo ligado em vez de inventar data |
| Projeto acadêmico simples | Preservado; sem nuvem, fila durável ou exigências comerciais |

## Validação executada

- 26 testes automatizados passaram: **11 do firmware com dublês + 15 HTTP**.
- 26 verificações C++ da máquina de estados passaram.
- Dois problemas do teclado e o filtro foram reproduzidos em testes antes dos
  ajustes; os mesmos testes passaram depois das correções.
- JavaScript passou na verificação de sintaxe.
- Firmware recompilado para `esp32:esp32:esp32`, core **3.3.12**:
  **1.006.352 bytes de programa (76%) e 56.888 bytes de variáveis globais (17%)**.
- Pacote ZIP e manifesto de arquivos regenerados após a revisão.

Detalhes, versões e limites em [VALIDACAO.md](VALIDACAO.md).

## O que permanece aberto

1. **Fechadura:** confirmar pulso versus alimentação mantida, duração permitida
   e possibilidade real de retravar após 1 minuto sem abrir. `LOCK_MODE=0` continua
   desabilitando o acionamento até esse ensaio. Se o mecanismo não permitir, será
   necessário mudar a fechadura ou revisar essa exigência, não apenas o código.
2. **Eletrônica:** confirmar pinagem/alimentação/níveis UART do DY50, endereço e
   contraste LCD, comum do RGB, driver de potência/proteção e fontes.
3. **Integração física:** executar o roteiro com ESP32, Wi-Fi/NTP, leitor, sensores,
   fila/reconexão, persistência real e fechadura conectados.

Os testes de firmware executam o código de políticas, mas usam memória, leitor,
hash e relógio simulados e não executam o `setup()` completo. Nenhum ensaio físico
ou biometria real foi utilizado para fechar estes itens.
