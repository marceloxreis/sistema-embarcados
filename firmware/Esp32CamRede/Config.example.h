#pragma once
constexpr char WIFI_SSID[] = "SEU_WIFI";
constexpr char WIFI_PASSWORD[] = "SUA_SENHA_WIFI";
// LAN: IP do computador com o servidor. Nuvem: https://<dominio> (sem porta; Caddy na 443, ver docs/DEPLOY.md).
// Em https:// a CAM confere o certificado com as raízes de ServerCA.h (Let's Encrypt).
constexpr char SERVER_URL[] = "http://192.168.1.100:8080";
// constexpr char SERVER_URL[] = "https://controle-acesso.duckdns.org";
constexpr char DEVICE_KEY[] = "DEFINA_UMA_CHAVE_COM_PELO_MENOS_16_CARACTERES";
constexpr char DEVICE_ID[] = "porta01";
// OTA (atualização pelo Wi-Fi): descomente e defina uma senha própria (8+ caracteres). Sem esta linha, a OTA fica desligada.
// #define OTA_PASSWORD "DEFINA_UMA_SENHA_OTA"
