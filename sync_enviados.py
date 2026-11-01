#!/usr/bin/env python3
"""Sincroniza Enviados de Gmail -> data/contactados.json.
Correcciones de auditoría:
- fetch(g, ...) refresca el token en cada llamada (syncs largas > 1 h).
- La caché JSONL solo guarda exitos ('ok') o borrados ('gone'): un error
  transitorio NO se cachea y se reintenta en la próxima sync.
- Excluye la cuenta propia, noreply y dominios de correo gratuito
  (las casillas gratuitas se agrupan por casilla completa, no por 'gmail.com').
- 'respondido' = respuesta HUMANA posterior al primer contacto: filtra
  mailer-daemon/postmaster/noreply y asuntos de autorrespuesta; guarda evidencia.
- Heartbeat de estado <=30 s para que un proceso muerto no trabe el candado.
"""
import email.utils
import json
import os
import sys
import time
import urllib.error
import urllib.parse  # noqa: F401
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import util  # noqa: E402
from gmail_client import Gmail, GmailAuthError, GmailError, extraer_destinatarios  # noqa: E402
from util import clave_institucion, dominio  # noqa: E402

CACHE = os.path.join(util.DATA, 'sync_cache.jsonl')
STATUS = os.path.join(util.DATA, 'sync_status.json')
OUT = os.path.join(util.DATA, 'contactados.json')
RITMO = float(os.environ.get('RADAR_RITMO', '0.12'))
AUTORESPUESTA = ('-from:(mailer-daemon OR postmaster OR noreply OR no-reply OR donotreply) '
                 '-subject:("respuesta automática" OR autorespuesta OR "auto-reply" OR '
                 '"automatic reply" OR "fuera de la oficina" OR "out of office")')

_ultimo_tick = [0.0]


def set_status(**kw):
    util.set_status(STATUS, **kw)
    _ultimo_tick[0] = time.time()


def tick(silencioso=True):
    """Heartbeat: refresca el ts del status al menos cada 30 s."""
    if time.time() - _ultimo_tick[0] > 30:
        st = util.leer_json(STATUS, {})
        st['ts'] = int(time.time())
        util.escribir_json(STATUS, st)
        _ultimo_tick[0] = time.time()


def fetch(g, mid, headers=('To', 'Cc', 'Bcc', 'Subject', 'Date'), intento=0):
    """Devuelve ('ok', headers) | ('gone', None) | ('error', mensaje)."""
    q = '&'.join('metadataHeaders=' + h for h in headers)
    url = f'https://www.googleapis.com/gmail/v1/messages/{mid}?format=metadata&{q}'
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + g._access()})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=20))
        return 'ok', {h['name'].lower(): h['value'] for h in (r.get('payload') or {}).get('headers', [])}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return 'gone', None
        if e.code == 401 and intento < 1:
            g.forzar_refresh()
            return fetch(g, mid, headers, intento + 1)
        if e.code in (429, 403, 500, 503) and intento < 6:
            espera = 30 if e.code in (429, 403) else 2 * (intento + 1)
            set_status(corriendo=True, mensaje=f'cuota {e.code}, esperando {espera}s…')
            time.sleep(espera)
            return fetch(g, mid, headers, intento + 1)
        return 'error', f'HTTP {e.code}'
    except GmailAuthError:
        raise
    except Exception as e:
        if intento < 3:
            time.sleep(1.5 * (intento + 1))
            return fetch(g, mid, headers, intento + 1)
        return 'error', str(e)[:80]


def cargar_cache():
    ok, gone, corruptas = {}, {}, 0
    if os.path.exists(CACHE):
        for linea in open(CACHE, encoding='utf-8'):
            try:
                r = json.loads(linea)
            except Exception:
                corruptas += 1
                continue
            if r.get('gone'):
                gone[r['id']] = True
            elif isinstance(r.get('hs'), dict):
                ok[r['id']] = r['hs']
    return ok, gone, corruptas


def append_cache(rec):
    with open(CACHE, 'a', encoding='utf-8') as cf:
        cf.write(json.dumps(rec, ensure_ascii=False) + '\n')
        cf.flush()


def main():
    set_status(corriendo=True, mensaje='listando Enviados…', progreso=0)
    g = Gmail()
    cuenta = (g.tok.get('cuenta') or '').lower()
    ids = g.listar_ids(label='SENT', max_total=5000)
    truncado = len(ids) >= 5000

    ok_cache, gone_cache, corruptas = cargar_cache()
    faltan = [i for i in ids if i not in ok_cache and i not in gone_cache]
    set_status(corriendo=True, mensaje=f'{len(ids)} enviados, {len(faltan)} por leer',
               progreso=0, total=len(faltan))

    t0 = time.time()
    fallidos = 0
    for n, mid in enumerate(faltan, 1):
        estado, hs = fetch(g, mid)
        if estado == 'ok':
            append_cache({'id': mid, 'hs': hs})
            ok_cache[mid] = hs
        elif estado == 'gone':
            append_cache({'id': mid, 'gone': True})
        else:
            fallidos += 1  # NO se cachea: se reintenta la próxima vez
        if n % 50 == 0 or n == len(faltan):
            set_status(corriendo=True, mensaje=f'leyendo cabeceras {n}/{len(faltan)}',
                       progreso=n, total=len(faltan))
        tick()
        time.sleep(RITMO)

    # ---------- mapa de instituciones contactadas ----------
    contactados = {}
    for mid, hs in ok_cache.items():
        try:
            ts = email.utils.parsedate_to_datetime(hs.get('date', '')).timestamp()
        except Exception:
            ts = 0
        for e in extraer_destinatarios(hs):
            if cuenta and e == cuenta:
                continue
            if any(r in e for r in ('noreply', 'no-reply', 'mailer-daemon')):
                continue
            clave = clave_institucion(e)
            if clave in util.DOMINIOS_CORREO_LIBRE:
                continue
            c = contactados.setdefault(clave, {
                'dominio': clave, 'emails': set(), 'primer_contacto': 0,
                'ultimo_contacto': 0, 'n_mails': 0, 'asuntos': [],
                'respondido': False, 'respuesta_humana': False,
                'autorespuesta': False, 'evidencia_id': None, 'ultima_respuesta': 0})
            c['emails'].add(e)
            c['n_mails'] += 1
            if ts:
                c['primer_contacto'] = ts if not c['primer_contacto'] else min(c['primer_contacto'], ts)
                c['ultimo_contacto'] = max(c['ultimo_contacto'], ts)
            a = hs.get('subject', '(sin asunto)')
            if a and a not in c['asuntos'] and len(c['asuntos']) < 5:
                c['asuntos'].append(a)

    # conservar nombres lindos de versiones previas
    prev = util.leer_json(OUT, {}).get('dominios', {})
    for d, c in contactados.items():
        if d in prev:
            if prev[d].get('nombre'):
                c['nombre'] = prev[d]['nombre']
            if prev[d].get('carrera'):
                c.setdefault('carrera', prev[d]['carrera'])

    # ---------- ¿respondieron? (humano vs automático) ----------
    set_status(corriendo=True, mensaje='buscando respuestas recibidas…',
               progreso=len(faltan), total=len(faltan))
    claves = [d for d in contactados
              if not util.dominio_en(d, list(util.DOMINIOS_CORREO_LIBRE))]
    for i, d in enumerate(claves, 1):
        primero = contactados[d].get('primer_contacto', 0)
        after = f' after:{int(primero) - 86400}' if primero else ''
        q_humana = f'from:{d}{after} {AUTORESPUESTA}'
        try:
            r = g.listar(query=q_humana, max_total=1)
            if r:
                contactados[d]['respuesta_humana'] = True
                contactados[d]['respondido'] = True
                contactados[d]['evidencia_id'] = r[0]['id']
                contactados[d]['ultima_respuesta'] = g.fecha_interna(r[0]['id'])
            else:
                r2 = g.listar(query=f'from:{d}{after}', max_total=1)
                if r2:
                    contactados[d]['autorespuesta'] = True
        except GmailAuthError:
            raise
        except GmailError:
            pass
        if i % 20 == 0:
            set_status(corriendo=True, mensaje=f'respuestas {i}/{len(claves)}')
        tick()
        time.sleep(RITMO)

    for c in contactados.values():
        c['emails'] = sorted(c['emails'])

    util.escribir_json(OUT, {
        'sincronizado_en': int(time.time()), 'cuenta': cuenta or None,
        'total_enviados_leidos': len(ok_cache), 'fallidos': fallidos,
        'lineas_cache_corruptas': corruptas,
        'historial_truncado': truncado,
        'dominios': contactados}, privado=True)
    resp = sum(1 for c in contactados.values() if c['respuesta_humana'])
    msg = f'OK: {len(contactados)} dominios, {resp} respondieron'
    if fallidos:
        msg += f' | {fallidos} mensajes sin leer (se reintentará)'
    if truncado:
        msg += ' | historial truncado en 5000'
    set_status(corriendo=False, mensaje=msg, progreso=len(faltan), total=len(faltan),
               ultimo_ok=int(time.time()))
    try:
        import generar_reporte
        generar_reporte.build()
    except Exception as e:
        util.set_status(os.path.join(util.DATA, 'sync_status.json'),
                        **{**util.leer_json(STATUS, {}), 'reporte_error': str(e)[:120]})
    print('LISTO', msg)


if __name__ == '__main__':
    try:
        main()
    except GmailAuthError as e:
        set_status(corriendo=False, mensaje=f'ERROR AUTH: {e}')
        print('ERROR AUTH:', e)
        sys.exit(1)
    except GmailError as e:
        set_status(corriendo=False, mensaje=f'ERROR: {e}')
        print('ERROR:', e)
        sys.exit(1)
