#!/usr/bin/env python3
"""Datos semilla de arranque (100% sintéticos) + bandeja DEMO.
Sin efectos al importar: seed_all() se llama desde app.main() o a mano.
Fechas relativas a hoy para que el demo muestre siempre los tres estados.
Todo lo semillado se REEMPLAZA con datos reales al sincronizar Gmail.
"""
import json
import os
import time

import ia_redactor
import util
from util import DATA

DIA = 86400


def seed_contactados():
    p = os.path.join(DATA, 'contactados.json')
    if os.path.exists(p):
        return False
    ahora = int(time.time())
    filas = [
        ('universidad-ejemplo.edu.ar', 'Universidad Nacional de Ejemplo',
         'Tecnicatura en Ciencia de Datos (a distancia)', ahora - 2 * DIA, True),
        ('instituto-demo.edu.ar', 'Instituto Demo',
         'Profesorado en Matemática', ahora - 1 * DIA, False),
        ('academia-privada-ejemplo.ar', 'Academia Privada Ejemplo',
         'Curso de Datos (arancelado)', ahora - 45 * DIA, False),
        ('cienciasexactas-ejemplo.edu.ar', 'Exactas Ejemplo',
         'Lic. en Estadística', ahora - 4 * DIA, True),
        ('campusvirtual-ejemplo.edu.ar', 'Campus Virtual Ejemplo',
         'Analista de Datos (virtual)', ahora - 5 * DIA, False),
    ]
    doms = {}
    for d, nombre, carrera, ult, resp in filas:
        doms[d] = {'dominio': d, 'nombre': nombre, 'carrera': carrera, 'emails': [],
                   'primer_contacto': ult - 3 * DIA, 'ultimo_contacto': ult,
                   'n_mails': 2 if resp else 1, 'asuntos': [f'Consulta: {carrera}'],
                   'respondido': resp, 'respuesta_humana': resp,
                   'autorespuesta': False, 'evidencia_id': None,
                   'ultima_respuesta': ult + 3600 if resp else 0}
    util.escribir_json(p, {
        'sincronizado_en': ahora, 'cuenta': '(sin conectar)', 'origen': 'seed_sintetico',
        'demo_hasta_sync': True, 'total_enviados_leidos': 0, 'dominios': doms}, privado=True)
    return True


def seed_bandeja_demo():
    p = os.path.join(DATA, 'bandeja_demo.json')
    if os.path.exists(p):
        return False
    ahora = time.strftime('%Y-%m-%d %H:%M')
    msgs = [
        {'id': 'demo-1', 'demo': True, 'from': 'informes@universidad-ejemplo.edu.ar',
         'from_nombre': 'Informes UNdeEjemplo (DEMO)',
         'subject': 'RE: Consulta Tecnicatura en Ciencia de Datos',
         'date': ahora, 'dominio': 'universidad-ejemplo.edu.ar',
         'snippet': 'Gracias por comunicarte. La tecnicatura es 100% a distancia…',
         'texto': ('Estimado:\n\nGracias por comunicarte con la Universidad Nacional de Ejemplo.\n\n'
                   'Te confirmo que la Tecnicatura en Ciencia de Datos es 100% a distancia, '
                   'con clases sincrónicas opcionales y exámenes en sedes regionales.\n\n'
                   'La inscripción abre en febrero. Para ajustes razonables, escribinos a '
                   'inclusion@universidad-ejemplo.edu.ar y te derivan al programa de '
                   'accesibilidad.\n\nSaludos cordiales,\nEquipo de Informes\n\n'
                   '[MENSAJE DEMO: ejemplo de cómo se verá tu bandeja al conectar Gmail]')},
        {'id': 'demo-2', 'demo': True, 'from': 'alumnos@cienciasexactas-ejemplo.edu.ar',
         'from_nombre': 'Exactas Ejemplo (DEMO)',
         'subject': 'RE: Lic. en Estadística — requisitos',
         'date': ahora, 'dominio': 'cienciasexactas-ejemplo.edu.ar',
         'snippet': 'La licenciatura se cursa en modalidad híbrida…',
         'texto': ('Hola:\n\nLa Licenciatura en Estadística tiene modalidad híbrida: la mayoría '
                   'de las materias son virtuales, pero hay dos instancias presenciales por '
                   'cuatrimestre en la sede central.\n\nRequisitos: secundario completo y curso '
                   'de nivelación en matemática (virtual).\n\nSaludos,\n'
                   'Secretaría de Asuntos Estudiantiles\n\n[MENSAJE DEMO]')},
        {'id': 'demo-3', 'demo': True, 'from': 'no-reply@academia-privada-ejemplo.ar',
         'from_nombre': 'Academia Privada Ejemplo (DEMO)',
         'subject': 'Re: Consulta por cursos de datos — respuesta automática',
         'date': ahora, 'dominio': 'academia-privada-ejemplo.ar',
         'snippet': 'Su consulta fue recibida con el número de trámite 4471…',
         'texto': ('Su consulta fue recibida y registrada con el número de trámite 4471-B. '
                   'Un asesor le responderá dentro de las 72 horas hábiles. Le adelantamos que '
                   'nuestros cursos son arancelados.\n\n[MENSAJE DEMO]')},
    ]
    util.escribir_json(p, {'mensajes': msgs})
    return True


def seed_ajustes():
    if not os.path.exists(os.path.join(DATA, 'ajustes.json')):
        ia_redactor.guardar_ajustes({})
    return True


def seed_all():
    c = seed_contactados()
    b = seed_bandeja_demo()
    seed_ajustes()
    return {'contactados_seeded': c, 'bandeja_demo_seeded': b}


if __name__ == '__main__':
    print(seed_all())
