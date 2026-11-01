#!/usr/bin/env python3
"""Utilidades compartidas: E/S atómica UTF-8, locks, estados de contacto,
dominios, normalización de URLs, HTML→texto y enmascarado de PII.
Stdlib puro, Python 3.9+, Windows y Linux.
"""
import html
import html.parser
import json
import os
import re
import threading
import time
import urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get('RADAR_DATA_DIR') or os.path.join(BASE, 'data')

_locks = {}
_locks_guard = threading.Lock()

# Dominios de correo gratuito: no son instituciones (una secretaría puede usarlos,
# por eso se agrupan por casilla completa y no por dominio).
DOMINIOS_CORREO_LIBRE = {
    'gmail.com', 'googlemail.com', 'hotmail.com', 'hotmail.com.ar', 'outlook.com',
    'outlook.com.ar', 'live.com', 'live.com.ar', 'msn.com', 'yahoo.com',
    'yahoo.com.ar', 'icloud.com', 'me.com', 'proton.me', 'protonmail.com',
    'aol.com', 'gmx.com',
}

# Ruido de bandeja: dominios COMPLETOS (nunca substring: 'x.com' no debe
# descartar 'fedex.com' ni 'santander' a 'unisantander.edu.es').
DOMINIOS_RUIDO = {
    'gmail.com', 'google.com', 'googleusercontent.com', 'youtube.com',
    'calendar.google.com', 'accounts.google.com', 'facebookmail.com',
    'facebook.com', 'instagram.com', 'twitter.com', 'x.com', 'linkedin.com',
    'whatsapp.com', 'telegram.org', 'mercadolibre.com.ar', 'mercadolibre.com',
    'mercadopago.com.ar', 'mercadopago.com', 'santander.com.ar', 'santanderrio.com.ar',
    'galicia.com.ar', 'nacion.com.ar', 'bbva.com.ar',
}

EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
TEL_RE = re.compile(r'(?:\+?\d{1,3}[\s-]?)?(?:\(\d{2,4}\)[\s-]?)?\d{3,4}[\s-]?\d{4}')
ID_RE = re.compile(r'[0-9a-f]{8,32}')


class JsonCorrupto(Exception):
    pass


def lock_de(path):
    with _locks_guard:
        return _locks.setdefault(os.path.abspath(path), threading.RLock())


def leer_json(path, default=None, estricto=False):
    """No existe -> default. Corrupto -> se aparta como .corrupto-<ts> y
    (estricto) levanta JsonCorrupto o (no estricto) devuelve default."""
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (ValueError, OSError):
        try:
            os.replace(path, f'{path}.corrupto-{int(time.time())}')
        except OSError:
            pass
        if estricto:
            raise JsonCorrupto(path)
        return default


def escribir_json(path, obj, privado=False, indent=1):
    """Atómico: tmp con modo final + fsync + os.replace (sin ventana 0644)."""
    carpeta = os.path.dirname(os.path.abspath(path))
    os.makedirs(carpeta, exist_ok=True)
    tmp = os.path.join(carpeta, f'.tmp_{os.getpid()}_{threading.get_ident()}')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600 if privado else 0o644)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(obj, f, indent=indent, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def set_status(path, **kw):
    kw.setdefault('ts', int(time.time()))
    with lock_de(path):
        escribir_json(path, kw)


def esta_corriendo(status, max_silencio=180):
    """Un status queda 'corriendo' huérfano si el proceso muere: se considera
    vivo solo si hubo heartbeat reciente."""
    return bool(status.get('corriendo')) and (time.time() - status.get('ts', 0)) < max_silencio


# ---------------- dominios ----------------
def dominio(email):
    return email.split('@')[-1].lower().strip('>.')


def dominio_en(d, lista):
    """Igualdad o subdominio (sufijo '.'+x). Nunca substring suelto."""
    d = d.lower()
    for x in lista:
        x = x.lower()
        if d == x or d.endswith('.' + x):
            return True
    return False


def clave_institucion(email_addr):
    """Dominio para instituciones; casilla completa para correo gratuito
    (evita mezclar todas las secretarías @gmail.com bajo una sola clave)."""
    d = dominio(email_addr)
    return email_addr.lower() if d in DOMINIOS_CORREO_LIBRE else d


def dominio_base(d):
    partes = d.split('.')
    return '.'.join(partes[-2:]) if len(partes) >= 2 else d


# ---------------- estado de campaña (UNA sola implementación) ----------------
def estado_contacto(c, ahora=None):
    """c: dict de dominio con respondido/respuesta_humana/ultimo_contacto."""
    ahora = ahora if ahora is not None else time.time()
    if c.get('respuesta_humana', c.get('respondido', False)):
        return 'CONTESTO'
    ult = c.get('ultimo_contacto', 0)
    if ult and (ahora - ult) >= 30 * 86400:
        return 'REINTENTAR'
    return 'EN_ESPERA'


def estado_dominio(dom, contactados, ahora=None):
    """(estado, match, relacionado).
    Igual/ancestro/descendiente de un contactado -> su estado.
    Si solo comparte dominio base (otra unidad de la misma universidad) ->
    NUEVO con relacionado=<dominio contactado>."""
    ahora = ahora if ahora is not None else time.time()
    dom = dom.lower()
    for d, c in contactados.items():
        d = d.lower()
        if d.startswith('www.'):
            d = d[4:]  # www.uba.ar y uba.ar son el mismo host
        if d == dom or dom.endswith('.' + d) or d.endswith('.' + dom):
            return estado_contacto(c, ahora), d, None
    base = dominio_base(dom)
    for d, c in contactados.items():
        if dominio_base(d.lower()) == base:
            return 'NUEVO', None, d
    return 'NUEVO', None, None


# ---------------- urls ----------------
def normalizar_url(url):
    p = urllib.parse.urlsplit(url)
    host = p.netloc.lower()
    if host.startswith('www.'):
        host = host[4:]
    q = urllib.parse.parse_qs(p.query)
    q = {k: v for k, v in q.items()
         if k.lower() not in ('utm_source', 'utm_medium', 'utm_campaign',
                              'utm_term', 'utm_content', 'fbclid', 'gclid')}
    qs = urllib.parse.urlencode(q, doseq=True)
    path = p.path.rstrip('/') or '/'
    return urllib.parse.urlunsplit((p.scheme.lower(), host, path, qs, ''))


# ---------------- html -> texto ----------------
class _TextoHTML(html.parser.HTMLParser):
    IGNORA = {'script', 'style', 'head', 'title', 'meta', 'link'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._saltar = 0
        self._partes = []

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORA:
            self._saltar += 1
        elif tag in ('p', 'br', 'div', 'tr', 'li', 'h1', 'h2', 'h3', 'h4'):
            self._partes.append('\n')

    def handle_endtag(self, tag):
        if tag in self.IGNORA and self._saltar:
            self._saltar -= 1

    def handle_data(self, data):
        if not self._saltar:
            self._partes.append(data)

    def texto(self):
        t = ''.join(self._partes)
        t = re.sub(r'[ \t\r\f\v]+', ' ', t)
        t = re.sub(r'\s*\n\s*', '\n', t)
        return t.strip()


def html_a_texto(crudo):
    p = _TextoHTML()
    try:
        p.feed(crudo)
        p.close()
    except Exception:
        return re.sub(r'<[^>]+>', ' ', crudo)
    return p.texto()


def texto_a_html_seguro_json(obj):
    """Serializa para embeber dentro de <script>: escapa <, >, & y separadores
    de línea (OWASP). Impide romper el bloque con '</script>'."""
    return (json.dumps(obj, ensure_ascii=False)
            .replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
            .replace('\u2028', '\\u2028').replace('\u2029', '\\u2029'))


# ---------------- privacidad ----------------
def enmascarar_pii(texto):
    """Reemplaza emails y teléfonos por marcas antes de enviar contenido a un LLM."""
    t = EMAIL_RE.sub('[email]', texto or '')
    t = TEL_RE.sub('[tel]', t)
    return t
