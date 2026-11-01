#!/usr/bin/env python3
"""Radar de programas: búsqueda web (DuckDuckGo HTML, sin API keys) de carreras
de matemática/estadística/ciencia de datos en Argentina.
Criterios de Alejo: distancia/virtualidad, costo (pública gratuita) y accesibilidad,
con etiquetas visibles y EVIDENCIA (fragmento del texto que originó cada etiqueta).
Correcciones de auditoría: parseo html.parser con fallback regex y detección de
CAPTCHA/markup cambiado; dedupe por URL normalizada; estado_contacto recalculado
para TODOS en cada corrida; poda 180 días/500; enriquecido contra la página real
(con guardas SSRF) para los mejores candidatos; errores visibles en el status.
"""
import html as htmlmod
import html.parser
import ipaddress
import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import clasificador
import util
from util import DATA

OUT = os.path.join(DATA, 'radar.json')
STATUS = os.path.join(DATA, 'radar_status.json')
CACHE = os.path.join(DATA, 'cache_ddg.json')
CACHE_TTL = 24 * 3600
UA = {'User-Agent': 'RadarMatematicas/1.1 (+https://github.com/metecondrie/radar-matematicas)',
      'Accept-Language': 'es-AR,es;q=0.8'}

QUERIES_DEFAULT = [
    'tecnicatura ciencia de datos a distancia universidad pública argentina gratuita',
    'licenciatura estadística virtual universidad nacional argentina',
    'profesorado de matemática a distancia argentina universidad pública',
    'carrera análisis de datos online gratuita universidad argentina inscripción',
    'universidad argentina estudiantes discapacidad ajustes razonables carreras virtuales',
    'becas universidad argentina carrera ciencia de datos matemática',
]


def set_status(**kw):
    util.set_status(STATUS, **kw)


# ---------------- parseo DuckDuckGo ----------------
class _DDGParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.items, self._a, self._snip = [], None, None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get('class', '')
        if tag == 'a' and 'result__a' in cls:
            self._a = {'href': a.get('href', ''), 'titulo': ''}
            self._buf = []
        elif tag == 'a' and 'result__snippet' in cls:
            self._snip = {'texto': ''}
            self._buf = []

    def handle_endtag(self, tag):
        if tag == 'a':
            if self._a is not None:
                self._a['titulo'] = htmlmod.unescape(
                    re.sub(r'<[^>]+>', '', ''.join(self._buf))).strip()
                self.items.append(self._a)
                self._a = None
            elif self._snip is not None:
                self._snip['texto'] = htmlmod.unescape(
                    re.sub(r'<[^>]+>', '', ''.join(self._buf))).strip()
                if self.items:
                    self.items[-1]['snippet'] = self._snip['texto']
                self._snip = None
            self._buf = []

    def handle_data(self, data):
        if self._a is not None or self._snip is not None:
            self._buf.append(data)

    def handle_entityref(self, name):
        self.handle_data(htmlmod.unescape(f'&{name};'))

    def handle_charref(self, name):
        self.handle_data(htmlmod.unescape(f'&#{name};'))


def _parseo_regex(html_txt):
    res = []
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html_txt, re.S):
        res.append({'href': m.group(1),
                    'titulo': htmlmod.unescape(re.sub(r'<[^>]+>', '', m.group(2))).strip(),
                    'snippet': ''})
    return res


def buscar(query, max_res=8):
    """Devuelve (resultados, error). error es None solo si el parseo fue sano."""
    cache = util.leer_json(CACHE, {})
    key = util.normalizar_url('https://html.duckduckgo.com/html/?q=' + urllib.parse.quote(query))
    hit = cache.get(key)
    if hit and time.time() - hit.get('ts', 0) < CACHE_TTL:
        return hit['res'], None
    url = 'https://html.duckduckgo.com/html/?' + urllib.parse.urlencode({'q': query})
    html_txt, err = None, None
    for intento in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            resp = urllib.request.urlopen(req, timeout=15)
            if resp.code in (202, 403, 429):
                err = f'bloqueado por DuckDuckGo (HTTP {resp.code})'
                time.sleep(2 ** intento)
                continue
            html_txt = resp.read(400_000).decode('utf-8', 'replace')
            break
        except urllib.error.HTTPError as e:
            if e.code in (202, 403, 429):
                err = f'bloqueado por DuckDuckGo (HTTP {e.code}, ¿CAPTCHA?)'
            else:
                err = f'HTTP {e.code}'
            time.sleep(2 ** intento)
        except Exception as e:
            err = f'fallo de red: {str(e)[:80]}'
            time.sleep(2 ** intento)
    if html_txt is None:
        return [], err
    if re.search(r'anomaly|captcha|bots use DuckDuck', html_txt, re.I):
        return [], 'bloqueado por DuckDuckGo (CAPTCHA/anomaly)'
    p = _DDGParser()
    try:
        p.feed(html_txt)
        p.close()
        res = p.items
    except Exception:
        res = []
    if not res:
        res = _parseo_regex(html_txt)
    if not res:
        return [], 'sin resultados parseables (¿cambió el HTML de DuckDuckGo?)'
    out = []
    for r in res[:max_res]:
        href = r.get('href', '')
        mu = re.search(r'uddg=([^&]+)', href)
        real = urllib.parse.unquote(mu.group(1)) if mu else href
        if not real.startswith('http') or '/y.js' in real:
            continue
        out.append({'url': real, 'titulo': r.get('titulo', ''),
                    'snippet': r.get('snippet', '')[:300], 'query': query})
    cache[key] = {'ts': int(time.time()), 'res': out}
    util.escribir_json(CACHE, cache)
    return out, None


# ---------------- SSRF guard para enriquecer ----------------
class _SeguroRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not url_segura(newurl):
            return None
        return urllib.request.HTTPRedirectHandler.redirect_request(
            self, req, fp, code, msg, headers, newurl)


def url_segura(url):
    try:
        p = urllib.parse.urlsplit(url)
        if p.scheme not in ('http', 'https') or not p.hostname:
            return False
        for info in socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == 'https' else 80)):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return False
        return True
    except Exception:
        return False


def enriquecer(r):
    """Descarga la página real (top candidatos) y reclasifica con evidencia."""
    if not url_segura(r['url']):
        return r
    try:
        opener = urllib.request.build_opener(_SeguroRedirect)
        req = urllib.request.Request(r['url'], headers=UA)
        resp = opener.open(req, timeout=15)
        ctype = resp.headers.get('Content-Type', '')
        if 'text/html' not in ctype:
            return r
        crudo = resp.read(300_000).decode('utf-8', 'replace')
        texto = util.html_a_texto(crudo)[:20000]
        tags, precios, evid = clasificador.clasificar(texto, r.get('dominio', ''))
        r['tags_pagina'] = tags
        r['evidencia'] = evid
        r['precios'] = precios
        r['origen_tag'] = 'pagina'
    except Exception:
        pass
    return r


# ---------------- corrida ----------------
def cargar_contactados():
    return util.leer_json(os.path.join(DATA, 'contactados.json'), {}).get('dominios', {})


def correr(queries=None, max_por_query=8, enriquecer_top=8):
    set_status(corriendo=True, mensaje='iniciando búsqueda…', progreso=0, errores=[])
    queries = queries or util.leer_json(os.path.join(DATA, 'ajustes.json'), {}).get(
        'radar_queries') or QUERIES_DEFAULT
    prev = util.leer_json(OUT, {}).get('resultados', [])
    vistos = {util.normalizar_url(r['url']) for r in prev}
    contactados = cargar_contactados()
    ahora = int(time.time())
    nuevos, errores = [], []
    for i, q in enumerate(queries, 1):
        set_status(corriendo=True, mensaje=f'buscando: {q[:55]}…', progreso=i,
                   total=len(queries), errores=errores)
        rs, err = buscar(q, max_por_query)
        if err:
            errores.append(f'{q[:40]}…: {err}')
        for r in rs:
            nu = util.normalizar_url(r['url'])
            if nu in vistos:
                continue
            vistos.add(nu)
            r['url_norm'] = nu
            r['dominio'] = _dom(r['url'])
            r['visto_en'] = ahora
            nuevos.append(r)
        time.sleep(2.5)
    todos = prev + nuevos
    # poda: 180 días o 500 resultados
    todos = [r for r in todos if ahora - r.get('visto_en', ahora) < 180 * 86400]
    todos.sort(key=lambda r: -r.get('visto_en', 0))
    todos = todos[:500]
    # recalcular SIEMPRE estado, tags y score (incluso lo viejo)
    for r in todos:
        r.setdefault('dominio', _dom(r['url']))
        est, match, rel = util.estado_dominio(r['dominio'], contactados)
        r['estado_contacto'] = est
        r['dominio_contactado'] = match
        r['relacionado'] = rel
        texto = (r.get('titulo', '') + ' ' + r.get('snippet', ''))
        tags, precios, evid = clasificador.clasificar(texto, r['dominio'])
        if r.get('origen_tag') != 'pagina':
            r['tags'], r['precios'], r['evidencia'] = tags, precios, evid
            r['origen_tag'] = 'snippet'
        r['score'] = clasificador.score_de(r.get('tags_pagina', r.get('tags', [])), est)
    # enriquecer con la página real a los mejores NUEVOS
    cand = [r for r in todos if r['estado_contacto'] == 'NUEVO'][:enriquecer_top]
    for j, r in enumerate(cand, 1):
        set_status(corriendo=True, mensaje=f'verificando página {j}/{len(cand)}…',
                   progreso=len(queries), total=len(queries), errores=errores)
        enriquecer(r)
        if r.get('tags_pagina'):
            r['score'] = clasificador.score_de(r['tags_pagina'], r['estado_contacto'])
        time.sleep(2)
    todos.sort(key=lambda r: (-r['score'], r['estado_contacto'] != 'NUEVO', -r.get('visto_en', 0)))
    util.escribir_json(OUT, {'actualizado_en': ahora, 'queries': queries, 'resultados': todos})
    msg = (f'Terminó con {len(errores)} errores ({len(nuevos)} nuevos, {len(todos)} totales)'
           if errores else f'OK: {len(nuevos)} nuevos ({len(todos)} totales)')
    set_status(corriendo=False, mensaje=msg, progreso=len(queries), total=len(queries),
               errores=errores, ultimo_ok=ahora)
    try:
        import generar_reporte
        generar_reporte.build()
    except Exception:
        pass
    return len(nuevos), len(todos), errores


def _dom(url):
    try:
        host = urllib.parse.urlsplit(url).netloc.lower()
        return host[4:] if host.startswith('www.') else host
    except Exception:
        return ''


def correr_async(queries=None):
    t = threading.Thread(target=lambda: correr(queries), daemon=True)
    t.start()
    return t


if __name__ == '__main__':
    n, tot, errs = correr()
    print(f'radar: {n} nuevos, {tot} totales', ('| errores: ' + '; '.join(errs)) if errs else '')
