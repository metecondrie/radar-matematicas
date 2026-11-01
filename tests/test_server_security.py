import json
import os
import re
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request

from context import datos_temp, BASE

TMP = datos_temp()


def puerto_libre():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


class TestServerSecurity(unittest.TestCase):
    proc = None
    puerto = None
    token = None

    @classmethod
    def setUpClass(cls):
        cls.puerto = puerto_libre()
        env = dict(os.environ, RADAR_DATA_DIR=TMP, PUERTO=str(cls.puerto),
                   RADAR_HOST='127.0.0.1', RADAR_ALLOWED_HOSTS='')
        cls.proc = subprocess.Popen([sys.executable, os.path.join(BASE, 'app.py')],
                                    cwd=BASE, env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            try:
                html = urllib.request.urlopen(f'http://127.0.0.1:{cls.puerto}/', timeout=2).read().decode()
                cls.token = re.search(r'name="radar-token" content="([^"]+)"', html).group(1)
                return
            except Exception:
                time.sleep(0.25)
        raise RuntimeError('el servidor de test no levantó')

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=10)

    def _req(self, path, method='GET', tok=None, ct='application/json', raw=None, host=None):
        data = raw
        r = urllib.request.Request(f'http://127.0.0.1:{self.puerto}{path}', data=data, method=method)
        if tok:
            r.add_header('X-Radar-Token', tok)
        if data is not None:
            r.add_header('Content-Type', ct)
        if host:
            r.add_header('Host', host)
        try:
            resp = urllib.request.urlopen(r, timeout=10)
            return resp.status, resp.read().decode()[:300]
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()[:300]

    def test_api_sin_token_401(self):
        self.assertEqual(self._req('/api/estado')[0], 401)

    def test_api_con_token_200(self):
        self.assertEqual(self._req('/api/estado', tok=self.token)[0], 200)

    def test_health_exento(self):
        self.assertEqual(self._req('/api/health')[0], 200)

    def test_post_sin_json_415(self):
        st, _ = self._req('/api/decision', 'POST', self.token, 'text/plain', b'{}')
        self.assertEqual(st, 415)

    def test_host_ajeno_403(self):
        st, _ = self._req('/api/estado', tok=self.token, host='atacante.example:9999')
        self.assertEqual(st, 403)

    def test_token_malo_401(self):
        st, _ = self._req('/api/estado', tok='nope')
        self.assertEqual(st, 401)

    def test_404_json(self):
        st, body = self._req('/api/nope', tok=self.token)
        self.assertEqual(st, 404)
        self.assertIn('error', json.loads(body))


if __name__ == '__main__':
    unittest.main()
