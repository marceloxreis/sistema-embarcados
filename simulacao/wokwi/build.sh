#!/bin/bash
# Compila o firmware MegaControlador para a simulacao Wokwi (Arduino Mega 2560).
#
# - Copia firmware/MegaControlador para uma pasta temporaria SEM Config.h.
# - Na copia, usa Config.example.h como Config.h (PIN de exemplo, so para simulacao).
# - Nunca le firmware/*/Config.h (credenciais reais).
# - Compila dentro da imagem Docker controle-acesso-avr-probe:local (avr-gcc 1.8.6 core).
# - Gera simulacao/wokwi/build/MegaControlador.ino.hex e .elf.
#
# Variaveis opcionais:
#   AVR_CORE     pasta do core arduino avr (padrao: $HOME/Library/Arduino15/packages/arduino/hardware/avr/1.8.6)
#   ARDUINO_LIBS pasta das bibliotecas (padrao: $HOME/Documents/Codex/2026-10-22/dc/work/arduino-user/libraries)
#   AVR_IMAGE    imagem Docker (padrao: controle-acesso-avr-probe:local)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
FIRMWARE_DIR="$REPO_DIR/firmware/MegaControlador"
OUT_DIR="$SCRIPT_DIR/build"

AVR_CORE="${AVR_CORE:-$HOME/Library/Arduino15/packages/arduino/hardware/avr/1.8.6}"
ARDUINO_LIBS="${ARDUINO_LIBS:-$HOME/Documents/Codex/2026-10-22/dc/work/arduino-user/libraries}"
AVR_IMAGE="${AVR_IMAGE:-controle-acesso-avr-probe:local}"

for d in "$FIRMWARE_DIR" "$AVR_CORE" "$ARDUINO_LIBS"; do
  [ -d "$d" ] || { echo "ERRO: pasta nao encontrada: $d" >&2; exit 1; }
done
command -v docker >/dev/null || { echo "ERRO: docker nao encontrado" >&2; exit 1; }

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/wokwi-build.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT

# (a) copia do sketch sem Config.h; Config.example.h vira Config.h na copia
mkdir -p "$STAGE/sketch"
rsync -a --exclude Config.h "$FIRMWARE_DIR/" "$STAGE/sketch/"
cp "$FIRMWARE_DIR/Config.example.h" "$STAGE/sketch/Config.h"

# script interno (roda dentro do container); mesma logica do build_warn.sh + avr-objcopy -O ihex
cat > "$STAGE/inner_build.sh" <<'EOF'
#!/bin/bash
# Roda DENTRO do container. /core = core arduino:avr 1.8.6 (ro), /libs = bibliotecas (ro), /work = staging (rw)
# $1 = diretorio da copia do sketch (dentro de /work); $2 = saida (dentro de /work)
set -e
SRC="$1"; OUT="$2"
rm -rf "$OUT"; mkdir -p "$OUT/obj"
CORE=/core/cores/arduino; VAR=/core/variants/mega; MCU=atmega2560
CFLAGS="-mmcu=$MCU -DF_CPU=16000000L -DARDUINO=10819 -DARDUINO_AVR_MEGA2560 -DARDUINO_ARCH_AVR -Os -g -ffunction-sections -fdata-sections -flto -fno-fat-lto-objects -I$CORE -I$VAR -Wall -Wextra"
CXXFLAGS="$CFLAGS -std=gnu++11 -fpermissive -fno-exceptions -fno-threadsafe-statics -Wno-error=narrowing"
WIRE=/core/libraries/Wire/src; EEP=/core/libraries/EEPROM/src
LIBINC="-I$WIRE -I$EEP -I/core/libraries/SoftwareSerial/src -I/libs/Keypad/src -I/libs/LiquidCrystal_I2C -I/libs/Adafruit_Fingerprint_Sensor_Library -I/libs/Crypto/src -I/libs/Crypto/src/utility -I$SRC"
cp "$SRC/MegaControlador.ino" "$OUT/MegaControlador.cpp"
objs=()
for f in "$CORE"/*.cpp; do o="$OUT/obj/core_$(basename "$f").o"; avr-g++ $CXXFLAGS -c "$f" -o "$o"; objs+=("$o"); done
for f in "$CORE"/*.c; do o="$OUT/obj/core_$(basename "$f").o"; avr-gcc $CFLAGS -std=gnu11 -c "$f" -o "$o"; objs+=("$o"); done
o="$OUT/obj/Wire.o"; avr-g++ $CXXFLAGS $LIBINC -c "$WIRE/Wire.cpp" -o "$o"; objs+=("$o")
o="$OUT/obj/twi.o"; avr-gcc $CFLAGS -std=gnu11 -c "$WIRE/utility/twi.c" -o "$o"; objs+=("$o")
for f in /libs/Keypad/src/Keypad.cpp /libs/Keypad/src/Key.cpp /libs/LiquidCrystal_I2C/LiquidCrystal_I2C.cpp /libs/Adafruit_Fingerprint_Sensor_Library/Adafruit_Fingerprint.cpp /libs/Crypto/src/SHA256.cpp /libs/Crypto/src/Hash.cpp /libs/Crypto/src/Crypto.cpp /core/libraries/SoftwareSerial/src/SoftwareSerial.cpp; do
  o="$OUT/obj/$(echo "$f" | tr '/' '_').o"; avr-g++ $CXXFLAGS $LIBINC -c "$f" -o "$o"; objs+=("$o")
done
avr-g++ $CXXFLAGS $LIBINC -c "$OUT/MegaControlador.cpp" -o "$OUT/obj/sketch.o"
avr-gcc -mmcu=$MCU -Os -flto -Wl,--gc-sections -o "$OUT/MegaControlador.elf" "$OUT/obj/sketch.o" "${objs[@]}" -lm
avr-objcopy -O ihex -R .eeprom "$OUT/MegaControlador.elf" "$OUT/MegaControlador.hex"
avr-size -A "$OUT/MegaControlador.elf" > "$OUT/size_A.txt"
avr-size "$OUT/MegaControlador.elf"
EOF
chmod +x "$STAGE/inner_build.sh"

# (b) compila no container (core e bibliotecas somente leitura)
mkdir -p "$OUT_DIR"
LOG="$OUT_DIR/build.log"
docker run --rm \
  -v "$STAGE":/work \
  -v "$AVR_CORE":/core:ro \
  -v "$ARDUINO_LIBS":/libs:ro \
  "$AVR_IMAGE" \
  bash /work/inner_build.sh /work/sketch /work/out 2>&1 | tee "$LOG"

# (c) copia HEX e ELF para a pasta da simulacao
cp "$STAGE/out/MegaControlador.hex" "$OUT_DIR/MegaControlador.ino.hex"
cp "$STAGE/out/MegaControlador.elf" "$OUT_DIR/MegaControlador.ino.elf"
echo "OK: $OUT_DIR/MegaControlador.ino.hex"
echo "OK: $OUT_DIR/MegaControlador.ino.elf"
echo "Avisos de compilacao: $(grep -c 'warning:' "$LOG" || true) (log: $LOG)"
