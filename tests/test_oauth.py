import os
import time
import unittest

from context import datos_temp

datos_temp()
import oauth_setup  # noqa: E402
import util  # noqa: E402


class TestExtraerCodigo(unittest.TestCase):
    def test_url_redirect(self):
        url = ('http://localhost:8642/?state=abc&code=4%2F0AVGzR1_ejemplo123'
               '&scope=https://www.googleapis.com/auth/gmail.readonly')
        self.assertEqual(oauth_setup.extraer_codigo(url), '4/0AVGzR1_ejemplo123')

    def test_codigo_suelto(self):
        self.assertEqual(oauth_setup.extraer_codigo('4/0AVGzR1_ejemplo123'), '4/0AVGzR1_ejemplo123')

    def test_basura(self):
        with self.assertRaises(ValueError):
            oauth_setup.extraer_codigo('cualquier cosa')


class TestIntercambiar(unittest.TestCase):
    def setUp(self):
        oauth_setup.guardar_client('1234567890-test.apps.googleusercontent.com', 'GOCSPX-test')
        oauth_setup.generar_auth_url()  # crea state fresco

    def test_error_de_google_primero(self):
        with self.assertRaises(ValueError) as cm:
            oauth_setup.intercambiar('http://localhost:8642/?error=access_denied&state=x')
        self.assertIn('denegaste', str(cm.exception))

    def test_state_distinto_rechazado(self):
        st = util.leer_json(oauth_setup.STATE_F, {})
        with self.assertRaises(ValueError):
            oauth_setup.intercambiar(f'http://localhost:8642/?state=OTRO&code=4/0A{st["state"][:4]}x')

    def test_url_sin_state_rechazada(self):
        with self.assertRaises(ValueError):
            oauth_setup.intercambiar('http://localhost:8642/?code=4/0Aejemplo123')

    def test_state_vencido(self):
        st = util.leer_json(oauth_setup.STATE_F, {})
        st['created_at'] = int(time.time()) - 4000
        util.escribir_json(oauth_setup.STATE_F, st, privado=True)
        with self.assertRaises(ValueError) as cm:
            oauth_setup.intercambiar('http://localhost:8642/?code=4/0Aejemplo123')
        self.assertIn('venció', str(cm.exception))

    def test_sin_state_file(self):
        os.remove(oauth_setup.STATE_F)
        with self.assertRaises(ValueError):
            oauth_setup.intercambiar('4/0Aejemplo123')


class TestEstadoSinRed(unittest.TestCase):
    def test_estado_no_llama_red(self):
        # sin token: conectado False y sin excepciones de red
        if os.path.exists(oauth_setup.TOK_F):
            os.remove(oauth_setup.TOK_F)
        e = oauth_setup.estado()
        self.assertFalse(e['conectado'])
        self.assertIn('oauth_modo', e)


if __name__ == '__main__':
    unittest.main()
