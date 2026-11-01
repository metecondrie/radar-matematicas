import json
import os
import re
import time
import unittest
from pathlib import Path

from context import datos_temp

TMP = Path(datos_temp())
MALIGNO = '</script><script>alert(1)</script>'


class TestReporte(unittest.TestCase):
    def setUp(self):
        import util
        self.util = util
        ahora = int(time.time())
        util.escribir_json(os.path.join(TMP, 'contactados.json'), {'dominios': {
            'uni-prueba.edu.ar': {
                'nombre': f'Uni de Prueba {MALIGNO}', 'carrera': 'Tecnicatura en Datos',
                'emails': ['infos@uni-prueba.edu.ar'], 'n_mails': 2,
                'ultimo_contacto': ahora - 3 * 86400, 'respuesta_humana': False,
                'asuntos': [f'Consulta {MALIGNO}']}}})
        util.escribir_json(os.path.join(TMP, 'radar.json'), {'resultados': [
            {'url': 'https://uni-prueba.edu.ar/x', 'titulo': f'Tecnicatura {MALIGNO}',
             'snippet': 'virtual gratuita', 'dominio': 'uni-prueba.edu.ar',
             'tags': ['nueva', 'virtual'], 'score': 6, 'estado_contacto': 'NUEVO'}],
            'errores': [], 'actualizado': ahora})
        util.escribir_json(os.path.join(TMP, 'sync_status.json'), {})

    def _generar(self, nombre):
        import generar_reporte
        out = os.path.join(str(TMP), nombre)
        original = generar_reporte.OUT
        generar_reporte.OUT = out
        try:
            devolver = generar_reporte.build()
        finally:
            generar_reporte.OUT = original
        return devolver, Path(out).read_text(encoding='utf-8')

    def test_generar_escapa_inyeccion(self):
        _, html = self._generar('war_room_test.html')
        # el payload maligno NO puede aparecer como HTML ejecutable
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('uni-prueba.edu.ar', html)
        # los datos embebidos siguen siendo JSON válido y conservan el texto
        m = re.search(r'const D=(\{.*?\});\n', html, re.S)
        self.assertIsNotNone(m, 'no encontré el bloque const D=…')
        data = json.loads(m.group(1))  # \u003c etc. se desescapan solos
        nombres = ' '.join(f['nombre'] for f in data['filas'])
        self.assertIn('<script>alert(1)</script>', nombres)  # dato intacto, solo escapado en HTML
        self.assertEqual(data['kpis']['instituciones'], 1)
        self.assertEqual(len(data['radar']), 1)

    def test_sin_datos_no_rompe(self):
        self.util.escribir_json(os.path.join(TMP, 'contactados.json'), {})
        self.util.escribir_json(os.path.join(TMP, 'radar.json'), {})
        out, html = self._generar('war_room_vacio.html')
        self.assertTrue(Path(out).exists())
        self.assertIn('const D=', html)


if __name__ == '__main__':
    unittest.main()
