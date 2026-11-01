#!/usr/bin/env python3
"""Radar Matemáticas — servidor del dashboard (stdlib puro, sin dependencias).
Binding seguro por defecto (127.0.0.1; RADAR_HOST=0.0.0.0 solo bajo proxy/sandbox
confiable, junto con RADAR_ALLOWED_HOSTS). Toda la API exige un token de sesión
que se inyecta en la página; POST exige application/json y cuerpo <= 1 MB.
NUNCA envía correos: solo lee Gmail y arma borradores/mailto para el humano.
"""
import concurrent.futures
import json
import logging
import logging.handlers
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import util  # noqa: E402
from util import DATA  # noqa: E402

os.makedirs(DATA, exist_ok=True)
LOG_F = os.path.join(DATA, 'app.log')
_log = logging.getLogger('radar')
_log.setLevel(logging.INFO)
_fh = logging.handlers.RotatingFileHandler(LOG_F, maxBytes=1_000_000, backupCount=2,
                                           encoding='utf-8')
_fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
_log.addHandler(_fh)

import clasificador  # noqa: E402
import ia_redactor  # noqa: E402
import oauth_setup  # noqa: E402
import radar  # noqa: E402
from gmail_client import Gmail, GmailAuthError, GmailError  # noqa: E402

PUERTO = int(os.environ.get('PUERTO', '8643'))
HOST = os.environ.get('RADAR_HOST', '127.0.0.1')
ALLOWED_HOSTS = os.environ.get('RADAR_ALLOWED_HOSTS', '')
HOSTS_OK = ({'localhost', '127.0.0.1', '[::1]'} |
            {h.strip().lower() for h in ALLOWED_HOSTS.split(',') if h.strip()})
WILDCARD = '*' in ALLOWED_HOSTS
SESSION_TOKEN = secrets.token_urlsafe(32)
MAX_BODY = 1_000_000


def _leer_version():
    """Fuente única de verdad: el archivo VERSION del repo."""
    try:
        with open(os.path.join(BASE, 'VERSION'), encoding='utf-8') as f:
            return f.read().strip() or '0.0.0'
    except OSError:
        return '0.0.0'


VERSION = _leer_version()

DECISIONES_F = os.path.join(DATA, 'decisiones.json')
CACHE_BANDEJA = os.path.join(DATA, 'bandeja_cache.json')
EMAIL_RE = util.EMAIL_RE
DECISIONES_OK = {'pendiente', 'responder', 'no_responder', 'ignorado'}
RELEVANTES_SUFIJOS = ('.edu.ar', '.gob.ar', '.edu', '.ac.ar', '.ac.cr', '.ac.mx')


def leer_json(path, default):
    return util.leer_json(path, default)


def decisiones():
    with util.lock_de(DECISIONES_F):
        return util.leer_json(DECISIONES_F, {}, estricto=True)


def guardar_decision(mid, dec, nota=''):
    if dec not in DECISIONES_OK:
        raise ValueError('decisión inválida')
    with util.lock_de(DECISIONES_F):
        d = util.leer_json(DECISIONES_F, {}, estricto=True)
        d[mid] = {'decision': dec, 'fecha': int(time.time()), 'nota': nota[:500]}
        util.escribir_json(DECISIONES_F, d, privado=True)


def kpis():
    con = leer_json(os.path.join(DATA, 'contactados.json'), {})
    doms = con.get('dominios', {})
    rad = leer_json(os.path.join(DATA, 'radar.json'), {'resultados': []})
    est = [util.estado_contacto(c) for c in doms.values()]
    nuevos = [r for r in rad.get('resultados', []) if r.get('estado_contacto') == 'NUEVO']
    bases = {util.dominio_base(d) for d in doms}
    return {
        'instituciones': len(doms), 'universidades': len(bases),
        'contestaron': est.count('CONTESTO'), 'en_espera': est.count('EN_ESPERA'),
        'reintentar': est.count('REINTENTAR'), 'radar_nuevos': len(nuevos),
        'radar_total': len(rad.get('resultados', [])),
        'dominios_demo': bool(con.get('demo_hasta_sync')),
        'cuenta': con.get('cuenta'), 'sincronizado_en': con.get('sincronizado_en'),
    }


# ---------------- bandeja ----------------
def es_relevante(dom, contactados):
    if util.dominio_en(dom, list(util.DOMINIOS_RUIDO)):
        return False
    if dom.endswith(RELEVANTES_SUFIJOS):
        return True
    est, _, _ = util.estado_dominio(dom, contactados)
    return est != 'NUEVO' or bool(util.estado_dominio(dom, contactados)[2])


def bandeja_real(g, force=False):
    cache = util.leer_json(CACHE_BANDEJA, {})
    if not force and cache.get('ts') and time.time() - cache['ts'] < 600:
        return cache['mensajes'], cache.get('cuenta')
    cuenta = (g.tok.get('cuenta') or '').lower()
    dom_propio = util.dominio(cuenta) if cuenta else ''
    msgs = g.listar(query='in:inbox newer_than:90d', max_total=60)
    con = leer_json(os.path.join(DATA, 'contactados.json'), {}).get('dominios', {})

    def meta(m):
        try:
            md = g.metadata(m['id'], headers=('From', 'Subject', 'Date'))
        except GmailError:
            return None
        hs = md['headers']
        frm = hs.get('from', '')
        em = EMAIL_RE.findall(frm)
        if not em:
            return None
        em = em[0].lower()
        d = util.dominio(em)
        if d == dom_propio or util.dominio_en(d, list(util.DOMINIOS_RUIDO)):
            return None
        return {'id': m['id'], 'from': em, 'from_nombre': frm.split('<')[0].strip().strip('"') or d,
                'subject': hs.get('subject', '(sin asunto)'), 'date': hs.get('date', ''),
                'dominio': d, 'snippet': md.get('snippet', '')[:200], 'demo': False,
                'relevante': es_relevante(d, con),
                'presencial': bool({'presencial', 'hibrida'} & set(clasificador.clasificar(
                    (hs.get('subject', '') + ' ' + md.get('snippet', '')))[0]))}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(meta, msgs))
    out = [r for r in res if r][:40]
    util.escribir_json(CACHE_BANDEJA, {'ts': int(time.time()), 'mensajes': out,
                                       'cuenta': cuenta}, privado=True)
    return out, cuenta


def bandeja_demo():
    return [dict(m) for m in leer_json(os.path.join(DATA, 'bandeja_demo.json'),
                                       {'mensajes': []})['mensajes']]


def bandeja(force=False, todo=False):
    dec = decisiones()
    aviso = None
    est = oauth_setup.estado()
    if est['conectado']:
        try:
            g = Gmail()
            msgs, cuenta = bandeja_real(g, force)
            modo = 'real'
        except GmailAuthError as e:
            msgs, cuenta, modo, aviso = bandeja_demo(), None, 'demo', str(e)
        except GmailError as e:
            msgs, cuenta, modo, aviso = bandeja_demo(), None, 'demo', str(e)
    else:
        msgs, cuenta, modo = bandeja_demo(), None, 'demo'
    if not todo:
        msgs = [m for m in msgs if m.get('relevante', True)]
    for m in msgs:
        if 'id' in m:
            m['decision'] = dec.get(m['id'], {}).get('decision', 'pendiente')
    return {'mensajes': msgs, 'modo': modo, 'cuenta': cuenta, 'aviso': aviso}


def mensaje_completo(mid):
    dec = decisiones().get(mid, {}).get('decision', 'pendiente')
    if mid.startswith('demo-'):
        for m in bandeja_demo():
            if m['id'] == mid:
                copia = dict(m)
                copia['decision'] = dec
                return copia
        raise ValueError('mensaje demo no encontrado')
    g = Gmail()
    full = g.cuerpo_texto(mid)
    hs = full['headers']
    frm = hs.get('from', '')
    tags = clasificador.clasificar(full['texto'] or full['snippet'])[0]
    return {'id': mid, 'from': (EMAIL_RE.findall(frm) or ['?'])[0],
            'from_nombre': frm.split('<')[0].strip().strip('"'),
            'subject': hs.get('subject', ''), 'date': hs.get('date', ''),
            'dominio': util.dominio((EMAIL_RE.findall(frm) or ['x@y'])[0]),
            'texto': full['texto'], 'snippet': full['snippet'],
            'decision': dec, 'demo': False,
            'presencial': 'presencial' in tags or 'hibrida' in tags}


# ---------------- handler ----------------
class Handler(BaseHTTPRequestHandler):
    server_version = 'RadarMat/1.1'
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        _log.info('%s %s', self.address_string(), fmt % args)

    # ---------- guardias ----------
    def _guard(self, es_post):
        host = (self.headers.get('Host') or '').lower().split(':')[0]
        if not WILDCARD and host not in HOSTS_OK:
            return 403, 'Host no permitido'
        origin = self.headers.get('Origin')
        if origin and not WILDCARD:
            ok_or = {f'http://{h}' for h in HOSTS_OK} | {f'https://{h}' for h in HOSTS_OK}
            if origin.lower().rstrip('/') not in ok_or:
                return 403, 'Origin no permitido'
        ruta = self.path.split('?')[0]
        if ruta.startswith('/api/') and ruta != '/api/health':
            recibido = self.headers.get('X-Radar-Token', '')
            if not secrets.compare_digest(recibido, SESSION_TOKEN):
                return 401, 'token de sesión inválido'
            if es_post:
                ct = (self.headers.get('Content-Type') or '').split(';')[0].strip().lower()
                if ct != 'application/json':
                    return 415, 'se requiere Content-Type: application/json'
        return None

    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        elif isinstance(body, str):
            body = body.encode('utf-8')
        try:
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def do_OPTIONS(self):
        try:
            self.send_response(204)
            self.send_header('Allow', 'GET, POST, OPTIONS')
            self.send_header('Content-Length', '0')
            self.end_headers()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def _error(self, code, msg, codigo='error'):
        cid = secrets.token_hex(4)
        _log.error('req %s -> %s %s', cid, code, msg)
        self._send(code, {'error': msg, 'codigo': codigo, 'id': cid})

    def _body(self):
        try:
            n = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            raise ValueError('Content-Length inválido')
        if n > MAX_BODY:
            raise OverflowError('cuerpo demasiado grande')
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode('utf-8'))
        except Exception:
            raise ValueError('JSON inválido')

    # ---------- GET ----------
    def do_GET(self):
        g = self._guard(False)
        if g:
            return self._error(g[0], g[1], 'guard')
        try:
            ruta = self.path.split('?')[0]
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if ruta == '/':
                html_txt = open(os.path.join(BASE, 'static', 'index.html'), encoding='utf-8').read()
                return self._send(200, html_txt.replace('__RADAR_TOKEN__', SESSION_TOKEN),
                                  'text/html; charset=utf-8')
            if ruta in ('/static/app.css', '/static/app.js'):
                p = os.path.join(BASE, 'static', os.path.basename(ruta))
                data = open(p, 'rb').read()
                ctype = 'text/css; charset=utf-8' if ruta.endswith('.css') else 'application/javascript; charset=utf-8'
                return self._send(200, data, ctype)
            if ruta == '/api/health':
                return self._send(200, {'status': 'ok', 'version': VERSION})
            if ruta == '/api/estado':
                est = oauth_setup.estado()
                if qs.get('verificar') == ['1'] and est['conectado']:
                    try:
                        est['cuenta'] = Gmail().perfil().get('emailAddress')
                    except GmailError as e:
                        est['verificacion_error'] = str(e)[:150]
                return self._send(200, {
                    'gmail': est, 'kpis': kpis(), 'version': VERSION,
                    'sync': leer_json(os.path.join(DATA, 'sync_status.json'), {}),
                    'radar_status': leer_json(radar.STATUS, {})})
            if ruta == '/api/campana':
                con = leer_json(os.path.join(DATA, 'contactados.json'), {})
                filas = []
                for d, c in con.get('dominios', {}).items():
                    filas.append({
                        'dominio': d, 'nombre': c.get('nombre', d),
                        'carrera': c.get('carrera') or (c.get('asuntos') or [''])[0],
                        'emails': c.get('emails', []), 'n_mails': c.get('n_mails', 0),
                        'ultimo_contacto': c.get('ultimo_contacto', 0),
                        'respuesta_humana': c.get('respuesta_humana', c.get('respondido', False)),
                        'autorespuesta': c.get('autorespuesta', False),
                        'estado': util.estado_contacto(c)})
                orden = {'REINTENTAR': 0, 'EN_ESPERA': 1, 'CONTESTO': 2}
                filas.sort(key=lambda f: (orden.get(f['estado'], 3), -f['ultimo_contacto']))
                return self._send(200, {'filas': filas,
                                        'demo_hasta_sync': con.get('demo_hasta_sync', False),
                                        'sincronizado_en': con.get('sincronizado_en')})
            if ruta == '/api/bandeja':
                return self._send(200, bandeja(force=qs.get('force') == ['1'],
                                               todo=qs.get('todo') == ['1']))
            if ruta == '/api/mensaje':
                return self._send(200, mensaje_completo((qs.get('id') or [''])[0]))
            if ruta == '/api/radar':
                r = leer_json(os.path.join(DATA, 'radar.json'), {'resultados': [], 'actualizado_en': 0})
                dec = decisiones()
                con = leer_json(os.path.join(DATA, 'contactados.json'), {}).get('dominios', {})
                out = []
                for x in r.get('resultados', []):
                    key = 'radar:' + _hash_url(x.get('url', ''))
                    if dec.get(key, {}).get('decision') == 'ignorado':
                        continue
                    est, match, rel = util.estado_dominio(x.get('dominio', ''), con)
                    x = dict(x)
                    x['estado_contacto'], x['dominio_contactado'], x['relacionado'] = est, match, rel
                    x['score'] = clasificador.score_de(x.get('tags_pagina', x.get('tags', [])), est)
                    out.append(x)
                out.sort(key=lambda x: (-x['score'], x['estado_contacto'] != 'NUEVO', -x.get('visto_en', 0)))
                st = leer_json(radar.STATUS, {})
                return self._send(200, {'resultados': out[:60], 'status': st,
                                        'actualizado_en': r.get('actualizado_en', 0),
                                        'queries': leer_json(os.path.join(DATA, 'ajustes.json'), {}).get(
                                            'radar_queries') or radar.QUERIES_DEFAULT,
                                        'errores': st.get('errores', [])})
            if ruta == '/api/ajustes':
                a = ia_redactor.ajustes()
                out = dict(a)
                out['ia_api_key'] = ''
                out['ia_api_key_set'] = bool(a.get('ia_api_key'))
                out['ia_host'] = urllib.parse.urlparse(a.get('ia_base_url') or '').hostname or ''
                return self._send(200, out)
            return self._error(404, 'ruta desconocida', 'ruta')
        except ValueError as e:
            return self._error(400, str(e), 'entrada')
        except OverflowError:
            return self._error(413, 'cuerpo demasiado grande', 'body')
        except (GmailAuthError, GmailError) as e:
            return self._error(400, f'Gmail: {e}', 'gmail')
        except util.JsonCorrupto as e:
            return self._error(500, 'archivo de datos corrupto (se apartó para revisión)', 'datos')
        except Exception as e:
            _log.error('traceback: %s', traceback.format_exc())
            return self._error(500, 'error interno', 'interno')

    # ---------- POST ----------
    def do_POST(self):
        g = self._guard(True)
        if g:
            return self._error(g[0], g[1], 'guard')
        try:
            ruta = self.path.split('?')[0]
            b = self._body()

            if ruta == '/api/decision':
                mid = b.get('id')
                if not isinstance(mid, str) or not mid or len(mid) > 128:
                    raise ValueError('id inválido')
                guardar_decision(mid, b.get('decision', ''), str(b.get('nota', '')))
                return self._send(200, {'ok': True})

            if ruta == '/api/campana/mark':
                dom = (b.get('dominio') or '').lower()
                val = bool(b.get('respuesta_humana'))
                p = os.path.join(DATA, 'contactados.json')
                with util.lock_de(p):
                    con = util.leer_json(p, {}, estricto=True)
                    c = con.get('dominios', {}).get(dom)
                    if not c:
                        raise ValueError('dominio desconocido')
                    c['respuesta_humana'] = val
                    c['respondido'] = val
                    c['marca_manual'] = int(time.time())
                    util.escribir_json(p, con, privado=True)
                return self._send(200, {'ok': True})

            if ruta == '/api/redactar':
                tipo = b.get('tipo', 'respuesta')
                modo = b.get('modo', 'ia')
                if tipo not in ('respuesta', 'consulta', 'seguimiento'):
                    raise ValueError('tipo inválido')
                if modo not in ('ia', 'local'):
                    raise ValueError('modo inválido')
                ctx = {'institucion': str(b.get('institucion', ''))[:200],
                       'asunto': str(b.get('asunto', ''))[:300],
                       'carrera': str(b.get('carrera', ''))[:200],
                       'texto_original': str(b.get('texto_original', ''))[:4000]}
                if b.get('msg_id'):
                    m = mensaje_completo(str(b['msg_id'])[:64])
                    ctx['institucion'] = ctx['institucion'] or m.get('from_nombre', '')
                    ctx['asunto'] = ctx['asunto'] or m.get('subject', '')
                    ctx['texto_original'] = ctx['texto_original'] or (m.get('texto') or m.get('snippet', ''))
                borrador, motor, aviso = ia_redactor.redactar(tipo=tipo, modo=modo, **ctx)
                return self._send(200, {'borrador': borrador, 'motor': motor, 'aviso': aviso})

            if ruta == '/api/radar/buscar':
                st = leer_json(radar.STATUS, {})
                if util.esta_corriendo(st):
                    return self._send(200, {'ok': False, 'aviso': 'ya hay una búsqueda corriendo'})
                qs = b.get('queries')
                if qs is not None and not isinstance(qs, list):
                    raise ValueError('queries debe ser una lista')
                radar.correr_async(qs)
                return self._send(200, {'ok': True})

            if ruta == '/api/radar/descartar':
                url = str(b.get('url', ''))[:500]
                if not url:
                    raise ValueError('falta url')
                guardar_decision('radar:' + _hash_url(url),
                                 'ignorado' if b.get('descartar', True) else 'pendiente')
                return self._send(200, {'ok': True})

            if ruta == '/api/gmail/client':
                if b.get('json'):
                    oauth_setup.guardar_client_json(str(b['json'])[:20000])
                else:
                    oauth_setup.guardar_client(str(b.get('client_id', '')), str(b.get('client_secret', '')))
                return self._send(200, {'ok': True})

            if ruta == '/api/gmail/auth-url':
                if not oauth_setup.client_presente():
                    return self._error(400, 'Primero cargá las credenciales de Google Cloud '
                                            '(client_id y client_secret, o el JSON completo).', 'credenciales')
                return self._send(200, {'url': oauth_setup.generar_auth_url()})

            if ruta == '/api/gmail/exchange':
                r = oauth_setup.intercambiar(str(b.get('url_o_codigo', ''))[:4000])
                threading.Thread(target=_sync_thread, daemon=True).start()
                return self._send(200, r)

            if ruta == '/api/gmail/sync':
                st = leer_json(os.path.join(DATA, 'sync_status.json'), {})
                if util.esta_corriendo(st):
                    return self._send(200, {'ok': False, 'aviso': 'la sincronización ya está corriendo'})
                threading.Thread(target=_sync_thread, daemon=True).start()
                return self._send(200, {'ok': True})

            if ruta == '/api/ajustes':
                errs = ia_redactor.validar_ajustes(b)
                if errs:
                    return self._error(400, '; '.join(errs), 'ajustes')
                a = ia_redactor.guardar_ajustes(b)
                return self._send(200, {'ok': True,
                                        'ia_host': urllib.parse.urlparse(a.get('ia_base_url') or '').hostname or ''})

            if ruta == '/api/ia/probar':
                a = ia_redactor.ajustes()
                if not a.get('ia_api_key'):
                    return self._error(400, 'No hay API key cargada.', 'ia')
                t0 = time.time()
                borrador, motor, aviso = ia_redactor.redactar(
                    tipo='consulta', institucion='Universidad de Ejemplo',
                    carrera='Licenciatura de Ejemplo', modo='ia')
                return self._send(200, {'motor': motor, 'aviso': aviso,
                                        'segundos': round(time.time() - t0, 1),
                                        'muestra': borrador[:400]})
            return self._error(404, 'ruta desconocida', 'ruta')
        except ValueError as e:
            return self._error(400, str(e), 'entrada')
        except OverflowError:
            return self._error(413, 'cuerpo demasiado grande', 'body')
        except (GmailAuthError, GmailError) as e:
            return self._error(400, f'Gmail: {e}', 'gmail')
        except util.JsonCorrupto:
            return self._error(500, 'archivo de datos corrupto (se apartó para revisión)', 'datos')
        except Exception as e:
            _log.error('traceback: %s', traceback.format_exc())
            return self._error(500, 'error interno', 'interno')


def _hash_url(url):
    import hashlib
    return hashlib.sha1(util.normalizar_url(url).encode()).hexdigest()[:16]


def _sync_thread():
    flags = 0
    if os.name == 'nt':
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        subprocess.run([sys.executable, os.path.join(BASE, 'sync_enviados.py')],
                       cwd=BASE, timeout=7200, creationflags=flags)
    except Exception as e:
        util.set_status(os.path.join(DATA, 'sync_status.json'), corriendo=False,
                        mensaje=f'ERROR: {e}')


def main():
    import seed
    seed.seed_all()
    if HOST != '127.0.0.1' and not WILDCARD and not ALLOWED_HOSTS:
        print('ERROR: con RADAR_HOST distinto de 127.0.0.1 debés definir '
              'RADAR_ALLOWED_HOSTS (o "*" bajo un proxy confiable).', flush=True)
        sys.exit(1)
    srv = ThreadingHTTPServer((HOST, PUERTO), Handler)
    print(f'Radar Matemáticas v{VERSION} escuchando en http://{HOST}:{PUERTO}', flush=True)
    srv.serve_forever()


if __name__ == '__main__':
    main()
