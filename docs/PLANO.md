# Plano de implementação

**Objetivo:** entregar os fontes e o guia de montagem do escopo em ESCOPO.md.
**Arquitetura:** controle local no loop do ESP32; tarefa de rede separada por filas;
servidor HTTP/SQLite no computador. Hardware físico continua sujeito à bancada.

- [x] 1. Criar lógica portátil da porta e testes de tempos, fechamento e rollover.
- [x] 2. Implementar armazenamento, autenticação, cadastro DY50 e menu LCD/teclado.
- [x] 3. Integrar rede, fila de eventos, NTP e redefinição por USB/web.
- [x] 4. Criar servidor, painel e testes HTTP com banco temporário.
- [x] 5. Compilar ESP32 e revisar de forma independente.
- [x] 6. Documentar materiais, ligações, configuração e roteiro de bancada; empacotar.

Entrega de software concluída e validada localmente; montagem e ensaios físicos
continuam pendentes, conforme docs/TESTES.md e docs/VALIDACAO.md.

Atualização solicitada: lista completa em docs/MATERIAIS.md; buzzer ativo para
prazo de abertura expirado e porta aberta por mais de 5 minutos; sem motor.

Arquivos: firmware/ControleAcesso/{ControleAcesso.ino,Config.h,DoorLogic.h},
servidor/server.py, servidor/static/{index.html,app.js,style.css},
tests/{test_server.py,test_door.cpp}, docs/{MONTAGEM.md,TESTES.md} e README.md.

Verificações: `python3 -m unittest discover -s tests -v`,
`c++ -std=c++11 tests/test_door.cpp -o /tmp/test_door && /tmp/test_door`
e `arduino-cli compile --fqbn esp32:esp32:esp32 firmware/ControleAcesso`.
Não gravar em placa nem afirmar testes físicos sem dispositivo conectado.
