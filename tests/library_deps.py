"""Resolve bibliotecas dos testes host, com modo estrito opcional."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT.parents[1] / 'work/arduino-user/libraries'


def require_library(test, name, version, required_files):
    base = Path(os.environ.get('CONTROLE_TEST_LIBS', str(DEFAULT)))
    library = base / name
    try:
        properties = dict(line.split('=', 1) for line in
                          (library / 'library.properties').read_text().splitlines()
                          if '=' in line)
        if properties.get('version') != version:
            raise ValueError(f'versão encontrada: {properties.get("version", "ausente")}')
        for required_file in required_files:
            if not (library / required_file).is_file():
                raise ValueError(f'arquivo ausente: {required_file}')
    except (OSError, ValueError) as exc:
        message = (f'{name} {version} indisponível em {library}: {exc}. '
                   'Veja o preparo de testes no README.md.')
        if os.environ.get('CONTROLE_TEST_STRICT') == '1':
            test.fail(message)
        test.skipTest(message)
    return library
