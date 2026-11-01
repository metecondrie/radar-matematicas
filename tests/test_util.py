import json
import os
import threading
import unittest

from context import datos_temp

datos_temp()
import util  # noqa: E402


class TestAtomico(unittest.TestCase):
    def test_ocho_hilos_escriben_sin_corromper(self):
        p = os.path.join(util.DATA, 'decisiones.json')
        errs = []

        def w(i):
            try:
                for j in range(15):
                    with util.lock_de(p):
                        d = util.leer_json(p, {}, estricto=True)
                        d[f'k{i}_{j}'] = j
                        util.escribir_json(p, d, privado=True)
            except Exception as e:
                errs.append(e)
        ts = [threading.Thread(target=w, args=(i,)) for i in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(errs, [])
        d = json.load(open(p, encoding='utf-8'))
        self.assertEqual(len(d), 120)

    def test_json_corrupto_no_pisa(self):
        p = os.path.join(util.DATA, 'roto.json')
        open(p, 'w', encoding='utf-8').write('{"a": 1,')
        self.assertEqual(util.leer_json(p, {'def': 1}), {'def': 1})
        self.assertTrue(any(f.startswith('roto.json.corrupto-') for f in os.listdir(util.DATA)))
        with self.assertRaises(util.JsonCorrupto):
            open(p, 'w', encoding='utf-8').write('no json')
            util.leer_json(p, {}, estricto=True)


class TestDominios(unittest.TestCase):
    def test_dominio_en_sufijo_no_substring(self):
        self.assertFalse(util.dominio_en('fedex.com', ['x.com']))
        self.assertFalse(util.dominio_en('unix.com', ['x.com']))
        self.assertFalse(util.dominio_en('unisantander.edu.es', ['santander.com.ar']))
        self.assertTrue(util.dominio_en('mail.x.com', ['x.com']))
        self.assertTrue(util.dominio_en('x.com', ['x.com']))

    def test_clave_institucion(self):
        self.assertEqual(util.clave_institucion('secre@instituto.edu.ar'), 'instituto.edu.ar')
        self.assertEqual(util.clave_institucion('secretaria.ejemplo.noexiste@gmail.com'), 'secretaria.ejemplo.noexiste@gmail.com')

    def test_estado_contacto_bordes_30_dias(self):
        ahora = 1_000_000_000
        self.assertEqual(util.estado_contacto({'ultimo_contacto': ahora - 29 * 86400}, ahora), 'EN_ESPERA')
        self.assertEqual(util.estado_contacto({'ultimo_contacto': ahora - 31 * 86400}, ahora), 'REINTENTAR')
        self.assertEqual(util.estado_contacto({'respuesta_humana': True, 'ultimo_contacto': 1}, ahora), 'CONTESTO')
        self.assertEqual(util.estado_contacto({'respondido': True}, ahora), 'CONTESTO')  # legado

    def test_estado_dominio_ancestro_y_base(self):
        con = {'fcen.uba.ar': {'ultimo_contacto': 9999999999}}
        self.assertEqual(util.estado_dominio('fcen.uba.ar', con)[0], 'EN_ESPERA')
        self.assertEqual(util.estado_dominio('uba.ar', con)[0], 'EN_ESPERA')
        # otra facultad del mismo dominio base: NUEVO pero relacionado
        est, match, rel = util.estado_dominio('dcen.uba.ar', con)
        self.assertEqual(est, 'NUEVO')
        self.assertEqual(rel, 'fcen.uba.ar')
        est, match, rel = util.estado_dominio('ing.uba.ar', con)
        self.assertEqual(est, 'NUEVO')
        self.assertEqual(rel, 'fcen.uba.ar')
        self.assertEqual(util.estado_dominio('unsam.edu.ar', con)[0], 'NUEVO')

    def test_estado_dominio_variante_www(self):
        # www.uba.ar y uba.ar son el mismo host: sus subdominios heredan estado
        con = {'www.uba.ar': {'ultimo_contacto': 9999999999}}
        self.assertEqual(util.estado_dominio('dcen.uba.ar', con)[0], 'EN_ESPERA')
        self.assertEqual(util.estado_dominio('uba.ar', con)[0], 'EN_ESPERA')
        # y un contacto a fcen.uba.ar matchea la clave www.fcen.uba.ar
        con2 = {'www.fcen.uba.ar': {'ultimo_contacto': 9999999999}}
        self.assertEqual(util.estado_dominio('fcen.uba.ar', con2)[0], 'EN_ESPERA')


class TestVarios(unittest.TestCase):
    def test_normalizar_url(self):
        a = util.normalizar_url('https://WWW.Example.AR/carrera/?utm_source=x&id=1#frag')
        self.assertEqual(a, 'https://example.ar/carrera?id=1')
        self.assertEqual(util.normalizar_url('https://a.ar/'), 'https://a.ar/')

    def test_enmascarar_pii(self):
        t = util.enmascarar_pii('Escribí a informes@universidad-ejemplo.edu.ar o al 0351 433-4000')
        self.assertNotIn('informes@universidad-ejemplo.edu.ar', t)
        self.assertNotIn('433-4000', t)
        self.assertIn('[email]', t)

    def test_html_a_texto(self):
        t = util.html_a_texto('<p>Hola &nbsp; <script>malo()</script><b>mundo</b></p>')
        self.assertIn('Hola', t)
        self.assertIn('mundo', t)
        self.assertNotIn('malo()', t)

    def test_json_seguro_script(self):
        s = util.texto_a_html_seguro_json({'a': '</script><script>alert(1)</script>'})
        self.assertNotIn('</script>', s)
        self.assertIn('\\u003c', s)


if __name__ == '__main__':
    unittest.main()
