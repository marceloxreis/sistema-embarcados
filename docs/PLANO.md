# Plano de implementação

## Retomada Mega + CAM — andamento

- [x] Preparar recebimento de fotos no servidor, limitado a 256 KiB por JPEG,
  autenticado e idempotente por evento `access_granted` previamente registrado.
  As imagens ficam na tabela `photos` do banco SQLite local; não há arquivo de foto
  no repositório. Consulta exige `X-Admin-Pin`. Testes usam imagens sintéticas.
- [x] Implementar enquadramento serial, sequência persistente e armazenamento
  compacto com journal; testar recuperação e replay em componentes simulados.
- [x] Criar sketches iniciais Mega e CAM, com controle local, câmera, filas,
  rede, NTP, reset web e USB. Ambos ainda requerem validação integrada.
- [x] Integrar consulta autenticada de foto no painel e indicar captura ausente.
- [x] Exercitar funções reais dos sketches juntas em UART simulada e repassar
  payloads reais da CAM, por transporte dublado, ao servidor HTTP de teste.
- [ ] Verificar ponta a ponta com as placas, câmera e rede reais; conferir tempos,
  níveis elétricos e operação do conjunto. Concluir roteiro fio por fio após
  identificar os módulos reais e o conversor de nível.

Contrato inicial do servidor: enviar o evento primeiro a `/api/device/events`;
após confirmação, enviar o JPEG por POST a `/api/device/photo`, com cabeçalhos
`X-Device-Key`, `X-Event-Id` e `Content-Type: image/jpeg`. A confirmação indica
transação SQLite concluída. Retransmissão idêntica é aceita; conteúdo diferente
para o mesmo evento retorna 409. Consultar por GET `/api/admin/photo?event_id=...`
com `X-Admin-Pin`. A validação JPEG confere tamanho e marcadores inicial/final,
não decodifica a imagem. A CAM implementa esse contrato, mas a comunicação real
com câmera e servidor ainda não foi validada em hardware.
HTTP na LAN não cifra credenciais nem imagens. O Mega mantém até 16 eventos em
RAM e a CAM até 8 eventos com fotos de até 256 KiB cada, sujeitas à memória
disponível. Após a captura, a CAM solicita ao Mega prova vinculada ao evento e a
um desafio; o Mega verifica o prazo a partir da autorização, incluindo a espera
prévia à leitura UART. A foto é descartada quando a prova não chega ou o prazo
expira; `photo_unavailable` registra ausência. As filas se perdem ao
reiniciar, e a fila cheia no Mega descarta eventos: não há garantia de foto.

**Alcance da prova:** o cenário de atraso anterior à leitura foi corrigido nos
testes com dublês e revisto. Isso depende do relógio do Mega, execução periódica,
entropia e funcionamento real do framebuffer; a UART não autentica mensagens.
Não há garantia de precisão física ou defesa contra um atacante na UART. Quatro
resets distintos podem ocupar a fila de respostas e impedir prova; carga e
buffers físicos são finitos. Ensaio real continua pendente.

Pendências digitais adicionais: proteger backups e avaliar corrida por troca de
caminho/symlink do banco, melhorar visibilidade remota das perdas e avaliar o
tratamento operacional de HTTP rejeitado de forma permanente. Hoje a CAM descarta
o item após 5 rejeições HTTP permanentes consecutivas (400, 409, 413 ou 422), em
pelo menos 30 s com Wi-Fi contínuo; a perda é contada em `rejected` (evento) ou
`photo_rejected` (foto) no heartbeat, e o painel exibe aviso. Respostas 401, 403,
404 e demais erros mantêm o item na fila. Novos bancos POSIX são criados com modo
de até `0600` sem mudar os existentes; isso não protege backups nem elimina a
corrida.

Para preparar os sketches, copiar `Config.example.h` para `Config.h` em cada
pasta. O Mega requer senha de administrador local de 10 dígitos; a CAM requer
rede Wi-Fi, URL e chave do dispositivo. O servidor deve usar a mesma senha e
chave. Os `Config.h` são ignorados pelo Git. Instalar Crypto 0.4.0, Adafruit
Fingerprint 2.1.4, Keypad 3.1.1, LiquidCrystal I2C 1.1.2 e ArduinoJson 7.4.3;
usar `arduino:avr:mega` e `esp32:esp32:esp32cam`, respectivamente. Não gravar
configurações de exemplo ou ativar a fechadura como se fossem produção.

O salt do Mega separa os registros, mas é derivado de estado previsível e não é
fonte criptográfica aleatória; senhas de 6 dígitos continuam suscetíveis a busca
offline se a EEPROM for lida. Preservar `LOCK_MODE=0` para os testes iniciais.
