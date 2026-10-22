import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class BuzzerTests(unittest.TestCase):
    def test_buzzer_follows_door_timeouts_and_stops_on_close(self):
        source = Path(__file__).with_suffix('.cpp')
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'test-buzzer'
            command = [os.environ.get('CXX', 'c++'), '-std=c++11']
            sdk = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
            if sys.platform == 'darwin' and sdk.exists():
                command += ['-isysroot', str(sdk)]
            result = subprocess.run(command + [str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
