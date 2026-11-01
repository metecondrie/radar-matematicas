import unittest

from context import datos_temp

datos_temp()
import radar  # noqa: E402
import util  # noqa: E402

HTML_OK = '''<html><body>
<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Funi.edu.ar%2Fdatos&amp;rut=1">Tecnicatura en Datos &amp; IA</a>
<a class="result__snippet" href="#">Carrera <b>gratuita</b>, 100% a distancia.</a>
<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fotra.ar%2Fmat">Profesorado de Matem&aacute;tica</a>
<a class="result__snippet">Modalidad virtual con ajustes razonables.</a>
</body></html>'''
HTML_CAPTCHA = '<html><body>anomaly: please verify you are not a bot. captcha</body></html>'


class FakeResp:
    code = 200

    def __init__(self, txt):
        self._txt = txt
        self.headers = {'Content-Type': 'text/html'}

    def read(self, n=None):
        return self._txt.encode()


class TestParseo(unittest.TestCase):
    def _buscar(self, html_txt):
        import urllib.request as ur
        old = ur.urlopen
        ur.urlopen = lambda req, timeout=None: FakeResp(html_txt)
        try:
            return radar.buscar('query de prueba', max_res=5)
        finally:
            ur.urlopen = old

    def test_parseo_html_parser(self):
        res, err = self._buscar(HTML_OK)
        self.assertIsNone(err)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0]['url'], 'https://uni.edu.ar/datos')
        self.assertIn('&', res[0]['titulo'])  # entidades des-escapadas
        self.assertIn('gratuita', res[0]['snippet'])

    def test_captcha_detectado(self):
        res, err = self._buscar(HTML_CAPTCHA)
        self.assertEqual(res, [])
        self.assertIn('CAPTCHA', err)

    def test_html_cambiado(self):
        res, err = self._buscar('<html><body><p>sin resultados</p></body></html>')
        self.assertEqual(res, [])
        self.assertIn('parseables', err)


class TestDedupe(unittest.TestCase):
    def test_url_normalizada_deduplica(self):
        a = util.normalizar_url('https://www.uni.edu.ar/datos?utm_source=x')
        b = util.normalizar_url('https://uni.edu.ar/datos#frag')
        self.assertEqual(a, b)


class TestSSRF(unittest.TestCase):
    def test_url_segura_rechaza(self):
        for u in ('http://127.0.0.1:8643/api/estado', 'http://169.254.169.254/',
                  'http://[::1]/', 'file:///etc/passwd', 'ftp://x.ar/', 'https://'):
            self.assertFalse(radar.url_segura(u), u)


class TestEstadoRecalculado(unittest.TestCase):
    def test_correr_recalcula_previos(self):
        # simula: resultado viejo NUEVO + dominio ahora contactado
        ahora = int(__import__('time').time())
        contacto = {'uni.edu.ar': {'ultimo_contacto': ahora - 2 * 86400, 'respondido': False}}
        est, match, rel = util.estado_dominio('uni.edu.ar', contacto)
        self.assertEqual(est, 'EN_ESPERA')
        contacto['uni.edu.ar']['ultimo_contacto'] = ahora - 40 * 86400
        self.assertEqual(util.estado_dominio('uni.edu.ar', contacto)[0], 'REINTENTAR')


if __name__ == '__main__':
    unittest.main()
