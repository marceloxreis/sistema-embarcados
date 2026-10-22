#pragma once
#include <Arduino.h>

// Copie para Config.h (ignorado pelo Git) e configure antes de gravar.
// ADMIN_PIN abaixo é somente um exemplo: substitua pelos seus 10 dígitos.
// O servidor deve ter IP reservado no roteador.
constexpr char WIFI_SSID[] = "SEU_WIFI";
constexpr char WIFI_PASSWORD[] = "SUA_SENHA_WIFI";
constexpr char SERVER_URL[] = "http://192.168.1.100:8080";
constexpr char DEVICE_KEY[] = "DEFINA_UMA_CHAVE_COM_PELO_MENOS_16_CARACTERES";
constexpr char DEVICE_ID[] = "porta01";
constexpr char ADMIN_PIN[] = "0000000000";

// 0: simulação sem saída elétrica (padrão); 1: pulso; 2: energizada até abrir.
// Só mudar depois de confirmar o regime permitido e o mecanismo da fechadura.
constexpr uint8_t LOCK_MODE = 0;
constexpr uint32_t LOCK_PULSE_MS = 200; // parâmetro de ensaio, NÃO especificação da trava
constexpr uint8_t LOCK_ON = HIGH;      // ajustar se o driver for ativo em LOW
constexpr uint8_t LOCK_PIN = 23;
constexpr uint8_t BUZZER_PIN = 2; // ativo HIGH, via NPN; pull-down externo, sem pull-up

constexpr uint8_t LCD_ADDRESS = 0x27;
constexpr uint8_t I2C_SDA = 21, I2C_SCL = 22;
constexpr uint8_t FINGER_RX = 16, FINGER_TX = 17;
constexpr uint8_t BUTTON_1 = 34, BUTTON_2 = 35; // pull-ups externos de 10k para 3V3
constexpr uint8_t LED_R = 4, LED_G = 18, LED_B = 19;
constexpr bool RGB_COMMON_ANODE = false;

// Keypad lê as linhas e aciona as colunas. GPIOs 36 e 39 são somente entrada:
// pull-ups externos de 10k nas linhas 3 e 4.
const byte ROW_PINS[4] = {27, 32, 36, 39};
const byte COL_PINS[4] = {13, 14, 25, 26};
constexpr uint8_t MAX_USERS = 100;
constexpr uint16_t EVENT_QUEUE_SIZE = 128;
constexpr uint32_t ENTRY_MS = 60000, OPEN_MS = 300000;
constexpr uint32_t UI_TIMEOUT_MS = 60000;
