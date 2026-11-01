#!/usr/bin/env python3
"""Redactor de borradores.
Motores:
  - 'local': plantillas propias sin conexión (siempre disponibles).
  - 'ia': cualquier endpoint compatible con OpenAI (/chat/completions).
    DESACTIVADO por defecto: el usuario elige proveedor y carga su key en Ajustes.
Privacidad: sin key/config, nada sale de la máquina. Con IA activa, el contenido
del mensaje elegido viaja al proveedor configurado (se muestra el host en la UI)
previo enmascarado de emails/teléfonos.
Las plantillas NO declaran datos de salud del usuario: la accesibilidad se
plantea como pregunta institucional configurable.
"""
import json
import os
import re
import urllib.parse
import urllib.error
import urllib.request

import util

AJUSTES_F = os.path.join(util.DATA, 'ajustes.json')

AJUSTES_DEFAULT = {
    'nombre_firma': '',
    'nombre_pila': '',
    'contexto_personal': '',
    'ia_base_url': '',
    'ia_api_key': '',
    'ia_modelo': '',
    'oauth_modo': 'pruebas',
    'mencionar_accesibilidad': True,
    'texto_accesibilidad': ('¿Con quién puedo conversar sobre los procedimientos de '
                            'accesibilidad y ajustes razonables de la institución?'),
    'radar_queries': [],
}

RE_MODEL = re.compile(r'^[\w.:/-]{1,80}$')


def ajustes():
    a = dict(AJUSTES_DEFAULT)
    a.update(util.leer_json(AJUSTES_F, {}))
    return a


def validar_ajustes(nuevos):
    errs = []
    if 'ia_base_url' in nuevos and nuevos['ia_base_url']:
        u = nuevos['ia_base_url'].rstrip('/')
        p = urllib.parse.urlparse(u)
        ok = p.scheme == 'https' or (p.scheme == 'http' and p.hostname in ('localhost', '127.0.0.1'))
        if not ok:
            errs.append('ia_base_url debe ser https:// (o http://localhost para modelos locales)')
    if 'ia_modelo' in nuevos and nuevos['ia_modelo'] and not RE_MODEL.fullmatch(nuevos['ia_modelo']):
        errs.append('ia_modelo con caracteres inválidos')
    if 'nombre_firma' in nuevos and len(nuevos['nombre_firma'] or '') > 120:
        errs.append('nombre_firma demasiado largo (máx 120)')
    if 'contexto_personal' in nuevos and len(nuevos['contexto_personal'] or '') > 1500:
        errs.append('contexto_personal demasiado largo (máx 1500)')
    if 'oauth_modo' in nuevos and nuevos['oauth_modo'] not in ('pruebas', 'produccion'):
        errs.append('oauth_modo debe ser pruebas o produccion')
    return errs


def guardar_ajustes(nuevos):
    a = ajustes()
    base_anterior = (a.get('ia_base_url') or '').rstrip('/')
    base_nueva = (nuevos.get('ia_base_url', base_anterior) or '').rstrip('/')
    # Si cambia el host de IA sin proveer key nueva, se limpia la key anterior
    # (evita que la clave viaje a un servidor distinto por error o ataque).
    if base_nueva != base_anterior and not nuevos.get('ia_api_key'):
        a['ia_api_key'] = ''
    for k, v in nuevos.items():
        if k in AJUSTES_DEFAULT or k in a:
            a[k] = v
    util.escribir_json(AJUSTES_F, a, privado=True)
    return a


# ---------------- motor local ----------------
def redactar_local(tipo, institucion='', asunto='', texto_original='', carrera=''):
    a = ajustes()
    firma = a.get('nombre_firma') or '[tu nombre y apellido]'
    pila = a.get('nombre_pila') or (firma.split()[0] if a.get('nombre_firma') else '[tu nombre]')
    acces = ''
    if a.get('mencionar_accesibilidad'):
        acces = f"3. {a.get('texto_accesibilidad')}\n"
    remota = ('¿Los exámenes, la inscripción y los trámites (legajo, títulos) pueden '
              'realizarse íntegramente en forma remota, sin asistir a una sede?')
    inst = (institucion or '').strip()
    saludo = 'Estimados:'
    if tipo == 'respuesta':
        cuerpo = (
            f'{saludo}\n\nMuchas gracias por su respuesta y por la información.\n\n'
            'Me quedan algunas consultas para poder avanzar:\n'
            '1. ¿Cuáles son los requisitos de inscripción y las fechas vigentes?\n'
            '2. ¿La modalidad es totalmente a distancia o requiere instancias presenciales? '
            + remota + '\n'
            + acces + '\n'
            'Quedo atento a sus comentarios.\n\nSaludos cordiales,\n' + firma)
    elif tipo == 'consulta':
        cuerpo = (
            f'{saludo}\n\nMi nombre es {pila} y les escribo desde Argentina. Estoy interesado en '
            + (f'la carrera de {carrera}' if carrera else
               'sus carreras de matemática, estadística y ciencia de datos') + '.\n\n'
            'Quisiera consultar:\n'
            '1. ¿La carrera se cursa a distancia o tiene instancias presenciales obligatorias? '
            + remota + '\n'
            '2. ¿Cuáles son los requisitos y las fechas de inscripción?\n'
            + acces + '\n'
            'Desde ya muchas gracias por su tiempo.\n\nSaludos cordiales,\n' + firma)
    elif tipo == 'seguimiento':
        cuerpo = (
            f'{saludo}\n\nLes escribo nuevamente en seguimiento de mi consulta anterior'
            + (f' ({asunto})' if asunto else '') + '.\n\n'
            'Sigo muy interesado en la propuesta académica y les agradecería si pudieran '
            'orientarme sobre requisitos de inscripción, modalidad de cursada (y si los '
            'exámenes y trámites pueden hacerse en forma remota)'
            + (' y los procedimientos de accesibilidad' if a.get('mencionar_accesibilidad') else '')
            + '.\n\nQuedo a disposición por cualquier dato adicional que necesiten.\n\n'
            'Saludos cordiales,\n' + firma)
    else:
        raise ValueError(f'tipo de borrador desconocido: {tipo}')
    return cuerpo


# ---------------- motor IA ----------------
def redactar_ia(tipo, institucion='', asunto='', texto_original='', carrera=''):
    a = ajustes()
    if not a.get('ia_api_key') or not a.get('ia_base_url'):
        raise RuntimeError('IA no configurada: elegí un proveedor y cargá tu API key en Ajustes.')
    if tipo not in ('respuesta', 'consulta', 'seguimiento'):
        raise ValueError(f'tipo de borrador desconocido: {tipo}')
    instruccion = {
        'respuesta': 'Redactá una RESPUESTA al correo recibido: agradecé, sé concreto y cordial, y retomá las preguntas pendientes que tengan sentido según lo que ya respondieron.',
        'consulta': 'Redactá un PRIMER correo de consulta a la institución: carrera, modalidad a distancia, inscripción y accesibilidad.',
        'seguimiento': 'Redactá un correo de SEGUIMIENTO breve y amable, recordando la consulta anterior sin sonar insistente.',
    }[tipo]
    contexto = a.get('contexto_personal') or ''
    sysp = ('Sos el asistente de redacción de correos de una persona que consulta a '
            'instituciones educativas. Escribís en español rioplatense, registro formal '
            '(trato de usted). Tono cordial, claro, sin florituras. 120-220 palabras. '
            'No inventes datos concretos (fechas, nombres, teléfonos). '
            + (f'Contexto del usuario: {contexto} ' if contexto else '')
            + f'Firmá siempre: {a.get("nombre_firma") or "[tu nombre y apellido]"}. '
            + 'Devolvé SOLO el cuerpo del correo, sin asunto ni comentarios.')
    userp = (f'{instruccion}\n\n'
             f'Institución: {institucion or "(sin dato)"}\n'
             f'Carrera: {carrera or "(sin dato)"}\n'
             f'Asunto del hilo: {asunto or "(sin dato)"}\n'
             f'--- Correo recibido / contexto (PII enmascarada) ---\n'
             f'{util.enmascarar_pii(texto_original or "(sin texto)")[:2500]}\n--- fin ---')
    payload = json.dumps({
        'model': a.get('ia_modelo') or 'qwen-plus',
        'messages': [{'role': 'system', 'content': sysp},
                     {'role': 'user', 'content': userp}],
        'temperature': 0.6,
    }).encode()
    req = urllib.request.Request(
        a['ia_base_url'].rstrip('/') + '/chat/completions', data=payload,
        headers={'Content-Type': 'application/json',
                 'Authorization': 'Bearer ' + a['ia_api_key']})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'la API de IA respondió HTTP {e.code}')
    except Exception as e:
        raise RuntimeError(f'no se pudo contactar al proveedor de IA: {str(e)[:120]}')
    try:
        return r['choices'][0]['message']['content'].strip()
    except (KeyError, IndexError):
        raise RuntimeError('la API de IA devolvió una respuesta inesperada')


def redactar(tipo='respuesta', institucion='', asunto='', texto_original='', carrera='', modo='ia'):
    """Devuelve (borrador, motor_usado, aviso). Si la IA falla, cae al local."""
    if tipo not in ('respuesta', 'consulta', 'seguimiento'):
        raise ValueError(f'tipo de borrador desconocido: {tipo}')
    if modo == 'ia':
        try:
            return redactar_ia(tipo, institucion, asunto, texto_original, carrera), 'ia', None
        except Exception as e:
            aviso = f'La IA falló ({str(e)[:200]}). Usé el motor local.'
            return redactar_local(tipo, institucion, asunto, texto_original, carrera), 'local', aviso
    return redactar_local(tipo, institucion, asunto, texto_original, carrera), 'local', None


if __name__ == '__main__':
    print(redactar_local('consulta', institucion='Universidad de Ejemplo',
                         carrera='Licenciatura en Ciencias de la Computación'))
