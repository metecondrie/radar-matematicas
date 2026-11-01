import io
import json
import os
import time
import unittest
import urllib.error

from context import datos_temp

datos_temp()
import gmail_client  # noqa: E402
import util  # noqa: E402


def http_error(code, cuerpo):
    return urllib.error.HTTPError('http://x', code, 'err', {}, io.BytesIO(cuerpo.encode()))


class TestPostForm(unittest.TestCase):
    def test_invalid_grant_es_auth_error(self):
        orig = urllib.request.urlopen if hasattr(urllib, 'request') else None
        import urllib.request as ur

        def fake(req, timeout=None):
            raise http_error(400, '{"error":"invalid_grant"}')
        old = ur.urlopen
        ur.urlopen = fake
        try:
            with self.assertRaises(gmail_client.GmailAuthError):
                gmail_client._post_form('http://x', {})
        finally:
            ur.urlopen = old

    def test_403_permisos_no_reintenta(self):
        import urllib.request as ur
        llamadas = []

        def fake(req, timeout=None):
            llamadas.append(1)
            raise http_error(403, '{"error":{"errors":[{"reason":"accessNotConfigured"}]}}')
        old = ur.urlopen
        ur.urlopen = fake
        try:
            with self.assertRaises(gmail_client.GmailError):
                gmail_client._get_json('http://x', 'tok')
            self.assertEqual(len(llamadas), 1)  # no reintentable
        finally:
            ur.urlopen = old


class TestRefreshUnico(unittest.TestCase):
    def test_cinco_instancias_un_refresh(self):
        cs = {'installed': {'client_id': 'c', 'client_secret': 's', 'token_uri': 'http://token'}}
        util.escribir_json(gmail_client.CS_F, cs, privado=True)
        util.escribir_json(gmail_client.TOK_F, {
            'access_token': 'viejo', 'refresh_token': 'r', 'expires_in': 3600,
            'obtenido_en': int(time.time()) - 3 * 3600, 'cuenta': 'x@x.ar'}, privado=True)
        llamadas = []

        def fake_post(url, data, intento=0):
            llamadas.append(1)
            return {'access_token': 'nuevo', 'expires_in': 3600}
        old = gmail_client._post_form
        gmail_client._post_form = fake_post
        try:
            for _ in range(5):
                g = gmail_client.Gmail()
                g._access()
            self.assertEqual(len(llamadas), 1)
            disco = util.leer_json(gmail_client.TOK_F, {})
            self.assertGreater(disco['obtenido_en'], int(time.time()) - 60)
            self.assertEqual(disco['cuenta'], 'x@x.ar')
        finally:
            gmail_client._post_form = old


class TestFetchSync(unittest.TestCase):
    def test_fetch_estados(self):
        import sync_enviados as se
        import urllib.request as ur

        class G:
            def _access(self):
                return 'tok'

            def forzar_refresh(self):
                self.refrescado = True
        respuestas = [http_error(404, 'x')]

        def fake(req, timeout=None):
            e = respuestas.pop(0)
            if e:
                raise e
            return io.BytesIO(json.dumps({'payload': {'headers': [
                {'name': 'To', 'value': 'a@b.edu.ar'}]}}).encode())
        old = ur.urlopen
        ur.urlopen = fake
        try:
            est, hs = se.fetch(G(), '1234567890abcdef')
            self.assertEqual(est, 'gone')
            respuestas.append(None)
            est, hs = se.fetch(G(), '1234567890abcdef')
            self.assertEqual(est, 'ok')
            self.assertEqual(hs['to'], 'a@b.edu.ar')
        finally:
            ur.urlopen = old


if __name__ == '__main__':
    unittest.main()
