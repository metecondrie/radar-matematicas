import json
import unittest

from context import datos_temp

datos_temp()
import ia_redactor  # noqa: E402
import util  # noqa: E402


class FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self, n=None):
        return self._b


def mock_urlopen(payload=None, exc=None):
    """Parchea urllib.request.urlopen; devuelve función de restauración."""
    import urllib.request as ur

    def fake(req, timeout=None):
        if exc:
            raise exc
        return FakeResp(payload)
    old = ur.urlopen
    ur.urlopen = fake
    return lambda: setattr(ur, 'urlopen', old)


class TestLocal(unittest.TestCase):
    def setUp(self):
        ia_redactor.guardar_ajustes({'nombre_firma': 'Alejo Prueba',
                                     'nombre_pila': 'Alejo'})

    def test_redactar_local_consulta(self):
        cuerpo = ia_redactor.redactar_local('consulta', institucion='Universidad de Prueba',
                                            carrera='Tecnicatura en Datos')
        self.assertIn('Tecnicatura en Datos', cuerpo)
        self.assertIn('Alejo Prueba', cuerpo)
        self.assertTrue(cuerpo.startswith('Estimados:'))

    def test_local_sin_firma_usa_placeholder(self):
        ia_redactor.guardar_ajustes({'nombre_firma': '', 'nombre_pila': ''})
        cuerpo = ia_redactor.redactar_local('consulta', institucion='X')
        self.assertIn('[tu nombre y apellido]', cuerpo)

    def test_accesibilidad_configurable(self):
        ia_redactor.guardar_ajustes({'mencionar_accesibilidad': False})
        cuerpo = ia_redactor.redactar_local('consulta', institucion='X')
        self.assertNotIn('accesibilidad', cuerpo.lower())
        ia_redactor.guardar_ajustes({'mencionar_accesibilidad': True})
        cuerpo = ia_redactor.redactar_local('consulta', institucion='X')
        self.assertIn('accesibilidad', cuerpo.lower())

    def test_tipo_desconocido(self):
        with self.assertRaises(ValueError):
            ia_redactor.redactar_local('hackeo', institucion='X')

    def test_redactar_modo_local(self):
        cuerpo, motor, aviso = ia_redactor.redactar('seguimiento', institucion='X', modo='local')
        self.assertEqual(motor, 'local')
        self.assertIsNone(aviso)
        self.assertTrue(cuerpo)


class TestIA(unittest.TestCase):
    def setUp(self):
        ia_redactor.guardar_ajustes({'nombre_firma': 'Alejo Prueba',
                                     'ia_base_url': '', 'ia_api_key': '', 'ia_modelo': ''})

    def test_ia_no_configurada_cae_a_local(self):
        cuerpo, motor, aviso = ia_redactor.redactar('consulta', institucion='X', modo='ia')
        self.assertEqual(motor, 'local')
        self.assertIn('falló', aviso)

    def test_ia_ok(self):
        ia_redactor.guardar_ajustes({'ia_base_url': 'http://127.0.0.1:9/v1',
                                     'ia_api_key': 'k-test', 'ia_modelo': 'm'})
        payload = {'choices': [{'message': {'content': '  Estimados: cuerpo IA.  '}}]}
        restore = mock_urlopen(payload)
        try:
            cuerpo, motor, aviso = ia_redactor.redactar('consulta', institucion='X', modo='ia')
        finally:
            restore()
        self.assertEqual(motor, 'ia')
        self.assertEqual(cuerpo, 'Estimados: cuerpo IA.')
        self.assertIsNone(aviso)

    def test_ia_error_http_cae_a_local(self):
        import urllib.error
        ia_redactor.guardar_ajustes({'ia_base_url': 'http://127.0.0.1:9/v1',
                                     'ia_api_key': 'k-test', 'ia_modelo': 'm'})
        err = urllib.error.HTTPError('http://127.0.0.1:9/v1', 500, 'boom', {}, None)
        restore = mock_urlopen(exc=err)
        try:
            cuerpo, motor, aviso = ia_redactor.redactar('consulta', institucion='X', modo='ia')
        finally:
            restore()
        self.assertEqual(motor, 'local')
        self.assertIn('HTTP 500', aviso)

    def test_pii_enmascarada_antes_de_viajar(self):
        # lo que se envía al proveedor no puede llevar emails crudos
        capturado = {}
        import urllib.request as ur

        def fake(req, timeout=None):
            capturado['body'] = req.data.decode()
            return FakeResp({'choices': [{'message': {'content': 'ok'}}]})
        ia_redactor.guardar_ajustes({'ia_base_url': 'http://127.0.0.1:9/v1',
                                     'ia_api_key': 'k-test', 'ia_modelo': 'm'})
        old = ur.urlopen
        ur.urlopen = fake
        try:
            ia_redactor.redactar_ia('respuesta', institucion='X',
                                    texto_original='Escribí a juan.perez@uni.edu.ar o al 011 4444 5555')
        finally:
            ur.urlopen = old
        self.assertNotIn('juan.perez@uni.edu.ar', capturado['body'])
        self.assertIn('[email]', capturado['body'])


class TestValidacionAjustes(unittest.TestCase):
    def test_rechaza_base_url_peligrosa(self):
        for u in ('file:///etc/passwd', 'http://169.254.169.254/v1',
                  'http://example.com/v1', 'ftp://x/v1'):
            errs = ia_redactor.validar_ajustes({'ia_base_url': u})
            self.assertTrue(errs, u)

    def test_acepta_loopback_y_https(self):
        for u in ('http://localhost:11434/v1', 'http://127.0.0.1:11434/v1',
                  'https://dashscope.aliyuncs.com/compatible-mode/v1'):
            self.assertEqual(ia_redactor.validar_ajustes({'ia_base_url': u}), [], u)

    def test_modelo_invalido(self):
        self.assertTrue(ia_redactor.validar_ajustes({'ia_modelo': 'mal modelo!'}))
        self.assertEqual(ia_redactor.validar_ajustes({'ia_modelo': 'qwen-plus'}), [])

    def test_cambio_de_host_limpia_key(self):
        ia_redactor.guardar_ajustes({'ia_base_url': 'http://127.0.0.1:9/v1',
                                     'ia_api_key': 'k-vieja', 'ia_modelo': 'm'})
        ia_redactor.guardar_ajustes({'ia_base_url': 'https://otro.example/v1'})
        self.assertEqual(ia_redactor.ajustes()['ia_api_key'], '')
        # limpiar
        ia_redactor.guardar_ajustes({'ia_base_url': '', 'ia_api_key': '', 'ia_modelo': ''})


if __name__ == '__main__':
    unittest.main()
