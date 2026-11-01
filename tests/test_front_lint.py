"""Lint del frente: garantiza que el dashboard no reintroduzca los bugs que
la auditoría marcó como críticos (handlers inline, inyección por campos de
texto sin escapar, fetch sin token).

Nota de criterio: prohibir innerHTML por completo sería sobrerrestricción —
el render por plantillas con `esc()` sistemático es el patrón del proyecto.
La regla exigible es: TODO campo de texto dinámico interpolado en una
plantilla pasa por esc(). Los números y literales no presentan riesgo."""
import re
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / 'static'

# campos de texto que, si se interpolan crudos, son vector de XSS
CAMPOS_TEXTO = ('nombre', 'titulo', 'subject', 'from', 'snippet', 'dominio',
                'asunto', 'carrera', 'url', 'mensaje', 'aviso', 'cuenta',
                'texto', 'email', 'to', 'body', 'firma', 'host', 'query')


class TestFrontLint(unittest.TestCase):
    def setUp(self):
        self.html = (STATIC / 'index.html').read_text(encoding='utf-8')
        self.js = (STATIC / 'app.js').read_text(encoding='utf-8')

    def test_sin_handlers_inline_html(self):
        self.assertNotRegex(self.html, re.compile(r'\son(click|change|input|submit|load|error)\s*=', re.I))

    def test_sin_handlers_por_propiedad_js(self):
        self.assertNotRegex(self.js, re.compile(r'\.on(click|change|input|submit|load|error)\s*='))

    def test_sin_document_write_ni_eval(self):
        for patron in ('document.write', 'eval(', 'outerHTML', 'javascript:'):
            self.assertNotIn(patron, self.js)

    def test_interpolaciones_de_texto_escapadas(self):
        # toda interpolación ${...} que toque un campo de texto debe usar esc()
        for chunk in re.findall(r'\$\{([^{}]*)\}', self.js):
            toca_texto = re.search(r'\.(%s)\b' % '|'.join(CAMPOS_TEXTO), chunk)
            if toca_texto and not chunk.strip().startswith('esc(') \
                    and 'esc(' not in chunk:
                self.fail(f'campo de texto sin escapar: ${{{chunk}}}')

    def test_token_presente_en_html(self):
        self.assertIn('name="radar-token"', self.html)

    def test_fetch_envia_token(self):
        self.assertIn("'X-Radar-Token'", self.js)
        # fetch solo dentro del wrapper api()
        self.assertLessEqual(self.js.count('fetch('), 2)

    def test_sin_iframe_de_otros_origenes(self):
        self.assertNotIn('<iframe', self.html)

    def test_meta_seguridad(self):
        self.assertIn('referrer" content="no-referrer', self.html)


if __name__ == '__main__':
    unittest.main()
