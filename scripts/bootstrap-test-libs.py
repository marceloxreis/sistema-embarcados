#!/usr/bin/env python3
"""Baixa revisões fixas das bibliotecas usadas pelos testes host."""
import argparse
from pathlib import Path
import subprocess
import tempfile

LIBRARIES = (
    ('ArduinoJson', 'https://github.com/bblanchon/ArduinoJson.git', 'v7.4.3',
     '77771d3c07668e01d8f52acb03910c1110bb373f'),
    ('Adafruit_Fingerprint_Sensor_Library',
     'https://github.com/adafruit/Adafruit-Fingerprint-Sensor-Library.git', '2.1.4',
     'b5de3ff6b430922d702db76e0c9ce29200c06d34'),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path, help='diretório novo para as bibliotecas')
    args = parser.parse_args()
    destination = args.destination.absolute()
    if destination.exists():
        parser.error(f'destino já existe: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.test-libs-', dir=destination.parent) as tmp:
        staged = Path(tmp) / 'libraries'
        staged.mkdir()
        for name, url, tag, revision in LIBRARIES:
            target = staged / name
            subprocess.run(['git', 'clone', '--quiet', '--depth', '1', '--branch', tag,
                            url, str(target)], check=True)
            actual = subprocess.check_output(['git', '-C', str(target), 'rev-parse', 'HEAD'], text=True).strip()
            if actual != revision:
                raise SystemExit(f'{name}: revisão inesperada {actual}; esperada {revision}')
        staged.rename(destination)
    print(f'Bibliotecas preparadas em {destination}')


if __name__ == '__main__':
    main()
