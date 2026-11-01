import unittest

from context import datos_temp

datos_temp()
import clasificador as c  # noqa: E402

TABLA = [
    ('Carrera gratuita, sin arancel ni cuota', 'unx.edu.ar', {'gratuita'}, {'con_costo'}),
    ('Arancel mensual $45.000', 'uade.edu.ar', {'privada', 'con_costo', 'precio_detectado'}, {'publica'}),
    ('análisis de funciones reales', 'x.org', set(), {'publica'}),
    ('la distancia entre puntos de un espacio métrico', 'x.org', set(), {'virtual'}),
    ('Tecnicatura 100% a distancia, exámenes presenciales en sedes regionales', 'x.org', {'virtual', 'presencial'}, set()),
    ('Modalidad no presencial', 'x.org', {'virtual'}, {'presencial'}),
    ('Campus virtual para consultas. Cursada presencial.', 'x.org', {'presencial'}, {'virtual'}),
]


class TestClasificador(unittest.TestCase):
    def test_tabla_del_reporte(self):
        for texto, dom, debe, nodebe in TABLA:
            tags = set(c.clasificar(texto, dom)[0])
            self.assertFalse(debe - tags, f'{texto}: faltan {debe - tags}')
            self.assertFalse(nodebe & tags, f'{texto}: sobran {nodebe & tags}')

    def test_instituciones(self):
        self.assertEqual(c.tipo_institucion('uade.edu.ar'), 'privada')
        self.assertEqual(c.tipo_institucion('fcf.unam.edu.ar'), 'publica')
        self.assertEqual(c.tipo_institucion('dominio-inventado.edu.ar'), 'desconocida')
        self.assertEqual(c.tipo_institucion('edu.gob.ar'), 'estatal')

    def test_score_prioriza_virtual_publica_gratuita(self):
        alta = c.score_de(['virtual', 'gratuita', 'publica', 'accesible'], 'NUEVO')
        baja = c.score_de(['privada', 'con_costo', 'presencial'], 'NUEVO')
        self.assertGreater(alta, baja)

    def test_sin_declare_salud_en_tags(self):
        tags, _, _ = c.clasificar('ajustes razonables para estudiantes con discapacidad', 'x.org')
        self.assertIn('accesible', tags)


if __name__ == '__main__':
    unittest.main()
