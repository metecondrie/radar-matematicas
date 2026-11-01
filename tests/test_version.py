import unittest
from pathlib import Path

from context import datos_temp, BASE

datos_temp()


class TestVersion(unittest.TestCase):
    def test_archivo_version_consistente(self):
        contenido = (Path(BASE) / 'VERSION').read_text(encoding='utf-8').strip()
        self.assertRegex(contenido, r'^\d+\.\d+\.\d+$')
        import app
        self.assertEqual(app.VERSION, contenido)

    def test_changelog_menciona_version(self):
        changelog = (Path(BASE) / 'CHANGELOG.md').read_text(encoding='utf-8')
        contenido = (Path(BASE) / 'VERSION').read_text(encoding='utf-8').strip()
        self.assertIn(contenido, changelog)


if __name__ == '__main__':
    unittest.main()
