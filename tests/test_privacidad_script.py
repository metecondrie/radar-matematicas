import subprocess
import sys
import unittest
from pathlib import Path

from context import BASE


class TestCheckPrivacidad(unittest.TestCase):
    def test_repo_limpio(self):
        r = subprocess.run([sys.executable, str(Path(BASE) / 'scripts' / 'check_privacidad.py')],
                           capture_output=True, text=True, encoding='utf-8', timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('Privacidad OK', r.stdout)


if __name__ == '__main__':
    unittest.main()
