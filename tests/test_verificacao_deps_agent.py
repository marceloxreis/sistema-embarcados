"""Verifica comportamento das dependências host em instalações parciais."""
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TESTS = Path(__file__).resolve().parent
NAME = 'Adafruit_Fingerprint_Sensor_Library'
FILES = ('Adafruit_Fingerprint.cpp', 'Adafruit_Fingerprint.h')


class VerificacaoDepsTests(unittest.TestCase):
    def run_integration(self, root, strict):
        env = os.environ.copy()
        env['CONTROLE_TEST_LIBS'] = str(root)
        env['CONTROLE_TEST_STRICT'] = '1' if strict else '0'
        return subprocess.run(
            [sys.executable, '-m', 'unittest', 'discover', '-s', str(TESTS),
             '-p', 'test_dy50_library_integration.py', '-v'],
            env=env, capture_output=True, text=True)

    def test_partial_adafruit_is_skipped_or_failed_before_compilation(self):
        for missing in FILES:
            for strict in (False, True):
                with self.subTest(missing=missing, strict=strict), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    lib = root / NAME
                    lib.mkdir()
                    (lib / 'library.properties').write_text('version=2.1.4\n')
                    for filename in FILES:
                        if filename != missing:
                            (lib / filename).write_text('')
                    result = self.run_integration(root, strict)
                    self.assertEqual(result.returncode, 1 if strict else 0, result.stderr)
                    self.assertIn('arquivo ausente: ' + missing, result.stderr)
                    self.assertIn('FAILED (failures=1)' if strict else 'OK (skipped=1)', result.stderr)

    def test_missing_transitive_arduinojson_header_fails_compilation(self):
        for strict in (False, True):
            with self.subTest(strict=strict), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                lib = root / 'ArduinoJson'
                (lib / 'src').mkdir(parents=True)
                (lib / 'library.properties').write_text('version=7.4.3\n')
                (lib / 'src/ArduinoJson.h').write_text('#include "ArduinoJson.hpp"\n')
                env = os.environ.copy()
                env['CONTROLE_TEST_LIBS'] = str(root)
                env['CONTROLE_TEST_STRICT'] = '1' if strict else '0'
                result = subprocess.run(
                    [sys.executable, '-m', 'unittest', 'discover', '-s', str(TESTS),
                     '-p', 'test_camera_network.py', '-v'],
                    env=env, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0, result.stderr)
                self.assertIn('ArduinoJson.hpp', result.stderr)
                # Cada teste da CAM que compila com ArduinoJson falha; a contagem cresce com os cenários.
                failures=re.search(r'FAILED \(failures=(\d+)\)', result.stderr)
                self.assertIsNotNone(failures, result.stderr)
                self.assertGreaterEqual(int(failures.group(1)), 2)
                self.assertNotIn('skipped=', result.stderr)

    def test_dependency_checks_complete_and_missing_inputs(self):
        from unittest.mock import patch
        from library_deps import require_library

        for name, version, files in (
            (NAME, '2.1.4', FILES),
            ('ArduinoJson', '7.4.3', ('src/ArduinoJson.h',)),
        ):
            for case in ('complete', 'missing_properties', 'wrong_version', 'missing_file'):
                for strict in (False, True):
                    with self.subTest(name=name, case=case, strict=strict), tempfile.TemporaryDirectory() as temp:
                        root = Path(temp)
                        lib = root / name
                        lib.mkdir()
                        if case != 'missing_properties':
                            (lib / 'library.properties').write_text(
                                'version=' + ('0.0.0' if case == 'wrong_version' else version) + '\n')
                        for filename in files:
                            path = lib / filename
                            path.parent.mkdir(parents=True, exist_ok=True)
                            if case != 'missing_file' or filename != files[-1]:
                                path.write_text('')
                        env = {'CONTROLE_TEST_LIBS': str(root),
                               'CONTROLE_TEST_STRICT': '1' if strict else '0'}
                        with patch.dict(os.environ, env):
                            if case == 'complete':
                                self.assertEqual(require_library(self, name, version, files), lib)
                            else:
                                exception = AssertionError if strict else unittest.SkipTest
                                with self.assertRaises(exception):
                                    require_library(self, name, version, files)
