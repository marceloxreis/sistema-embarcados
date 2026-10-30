import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class PortableComponentTests(unittest.TestCase):
    def test_firmware_copies_match_shared_protocol(self):
        root = Path(__file__).resolve().parents[1] / 'firmware'
        for name in ('SerialFrame.h', 'MessageProtocol.h'):
            original = (root / 'shared' / name).read_bytes()
            for sketch in ('MegaControlador', 'Esp32CamRede'):
                self.assertEqual((root / sketch / name).read_bytes(), original)

    def test_components(self):
        sdk = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
        for name in ('user_store', 'serial_frame', 'boot_counter', 'message_protocol', 'dy50_filter', 'door'):
            with self.subTest(component=name), tempfile.TemporaryDirectory() as directory:
                binary = Path(directory) / name
                command = [os.environ.get('CXX', 'c++'), '-std=c++11', '-Wall', '-Wextra', '-Werror']
                if sys.platform == 'darwin' and sdk.exists():
                    command += ['-isysroot', str(sdk)]
                source = Path(__file__).with_name('test_' + name + '.cpp')
                subprocess.run(command + [str(source), '-o', str(binary)], check=True, capture_output=True, text=True)
                subprocess.run([str(binary)], check=True, capture_output=True, text=True)
