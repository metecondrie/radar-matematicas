#!/usr/bin/env python3
"""Cliente Gmail (solo lectura) con refresco automático de token.
Sin librerías externas: solo urllib + el token OAuth guardado en data/gmail_token.json.
Correcciones de auditoría: obtenido_en se actualiza al refrescar (1 refresco por
vencimiento, no por request); invalid_grant => GmailAuthError; 403 clasificado por
reason (cuota reintentable vs permisos no); reintentos con backoff+jitter y
Retry-After; cuerpos con charset real y HTML→texto vía html.parser.
"""
import base64
import json
import os
import random
import re
import threading
import time
import urllib.error  # noqa: F401  (explícito: se usa urllib.error.HTTPError)
import urllib.parse
import urllib.request

import util
from util import DATA, ID_RE, html_a_texto

TOK_F = os.path.join(DATA, 'gmail_token.json')
CS_F = os.path.join(util.BASE, 'client_secret.json')
API = 'https://www.googleapis.com/gmail/v1/users/me'
EMAIL_RE = util.EMAIL_RE


class GmailError(Exception):
    pass


class GmailAuthError(GmailError):
    """El permiso de Google venció o fue revocado (modo Pruebas: 7 días)."""


class GmailCuotaError(GmailError):
    """Cuota por minuto alcanzada: reintentable."""


def _reintentable(code, cuerpo=''):
    if code in (429, 500, 502, 503):
        return True
    if code == 403:
        reason = ''
        try:
            reason = json.loads(cuerpo).get('error', {}).get('errors', [{}])[0].get('reason', '')
        except Exception:
            pass
        return reason in ('rateLimitExceeded', 'userRateLimitExceeded', 'quotaExceeded', '')
    return False


def _post_form(url, data, intento=0):
    req = urllib.request.Request(
        url, data=urllib.parse.urlencode(data).encode(),
        headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        return json.load(urllib.request.urlopen(req, timeout=25))
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode(errors='replace')[:400]
        if 'invalid_grant' in cuerpo:
            raise GmailAuthError('El permiso de Google venció o fue revocado. Reautorizá en Ajustes.')
        if e.code in (429, 500, 502, 503) and intento < 5:
            time.sleep(min(30, 2 ** intento) + random.random())
            return _post_form(url, data, intento + 1)
        raise GmailError(f'HTTP {e.code}: {cuerpo[:300]}')


def _get_json(url, token, intento=0):
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token})
    try:
        return json.load(urllib.request.urlopen(req, timeout=25))
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode(errors='replace')[:400]
        if e.code == 401:
            raise GmailAuthError('401: token rechazado. Reautorizá en Ajustes.')
        if _reintentable(e.code, cuerpo) and intento < 5:
            espera = min(60, 2 ** intento) + random.random()
            time.sleep(espera)
            return _get_json(url, token, intento + 1)
        raise GmailError(f'HTTP {e.code}: {cuerpo[:200]}')


def token_presente():
    return os.path.exists(TOK_F) and os.path.exists(CS_F)


class Gmail:
    def __init__(self):
        if not token_presente():
            raise GmailError('Gmail no conectado: faltan credenciales o token.')
        self.tok = util.leer_json(TOK_F, {}, estricto=True)
        self.cs = util.leer_json(CS_F, {}, estricto=True)['installed']
        self._lock = threading.RLock()
        self._expira = self.tok.get('obtenido_en', 0) + self.tok.get('expires_in', 3600) - 120

    def forzar_refresh(self):
        with self._lock:
            self._expira = 0

    def _access(self):
        with self._lock:
            if time.time() >= self._expira:
                disco = util.leer_json(TOK_F, None, estricto=True)
                if disco and time.time() < disco.get('obtenido_en', 0) + disco.get('expires_in', 3600) - 120:
                    self.tok = disco  # otro proceso/hilo ya refrescó
                else:
                    if not self.tok.get('refresh_token'):
                        raise GmailAuthError('sin refresh_token: hay que reautorizar')
                    nuevo = _post_form(self.cs['token_uri'], {
                        'refresh_token': self.tok['refresh_token'],
                        'client_id': self.cs['client_id'],
                        'client_secret': self.cs['client_secret'],
                        'grant_type': 'refresh_token'})
                    ahora = int(time.time())
                    nuevo['refresh_token'] = self.tok['refresh_token']
                    nuevo['obtenido_en'] = ahora  # el bug era conservar el viejo
                    nuevo['autorizado_en'] = self.tok.get('autorizado_en') or self.tok.get('obtenido_en', ahora)
                    for k in ('cuenta', 'scope'):
                        if self.tok.get(k):
                            nuevo[k] = self.tok[k]
                    util.escribir_json(TOK_F, nuevo, privado=True)
                    self.tok = nuevo
                self._expira = self.tok.get('obtenido_en', 0) + self.tok.get('expires_in', 3600) - 120
            return self.tok['access_token']

    # ---------- lectura ----------
    def perfil(self):
        return _get_json('https://www.googleapis.com/gmail/v1/users/me/profile', self._access())

    def listar(self, query='', label=None, max_total=5000, fields='messages/id,nextPageToken'):
        out, page = [], None
        while True:
            q = {'maxResults': '250', 'fields': fields}
            if query:
                q['q'] = query
            if label:
                q['labelIds'] = label
            url = API + '/messages?' + urllib.parse.urlencode(q)
            if page:
                url += '&pageToken=' + urllib.parse.quote(page)
            r = _get_json(url, self._access())
            out += r.get('messages', [])
            page = r.get('nextPageToken')
            if not page or len(out) >= max_total:
                return out[:max_total]

    def listar_ids(self, query='', label=None, max_total=5000):
        return [m['id'] for m in self.listar(query, label, max_total)]

    @staticmethod
    def _validar_id(mid):
        if not ID_RE.fullmatch(mid or ''):
            raise ValueError('id de mensaje inválido')
        return urllib.parse.quote(mid, safe='')

    def metadata(self, mid, headers=('To', 'Cc', 'Bcc', 'From', 'Subject', 'Date')):
        mid = self._validar_id(mid)
        q = '&'.join('metadataHeaders=' + h for h in headers)
        r = _get_json(f'{API}/messages/{mid}?format=metadata&{q}', self._access())
        hs = {h['name'].lower(): h['value'] for h in (r.get('payload') or {}).get('headers', [])}
        return {'id': r['id'], 'headers': hs, 'snippet': r.get('snippet', '')}

    def fecha_interna(self, mid):
        mid = self._validar_id(mid)
        r = _get_json(f'{API}/messages/{mid}?format=minimal&fields=id,internalDate', self._access())
        try:
            return int(r.get('internalDate', 0)) // 1000
        except Exception:
            return 0

    def cuerpo_texto(self, mid):
        """Cuerpo en texto plano respetando charset de cada parte; HTML→texto
        con html.parser; ignora adjuntos (partes con filename)."""
        mid = self._validar_id(mid)
        r = _get_json(f'{API}/messages/{mid}?format=full', self._access())
        hs = {h['name'].lower(): h['value'] for h in (r.get('payload') or {}).get('headers', [])}
        partes = []

        def charset_de(p):
            ct = ''
            for h in p.get('headers', []) or []:
                if h['name'].lower() == 'content-type':
                    ct = h['value']
            m = re.search(r'charset="?([\w-]+)"?', ct, re.I)
            return m.group(1) if m else 'utf-8'

        def walk(p):
            if (p.get('body') or {}).get('data') and not (p.get('filename') or ''):
                partes.append((p.get('mimeType', ''), charset_de(p), p['body']['data']))
            for sp in p.get('parts', []) or []:
                walk(sp)
        walk(r.get('payload') or {})
        texto = ''
        for mime, charset, data in partes:
            try:
                crudo = base64.urlsafe_b64decode(data + '==').decode(charset, errors='replace')
            except (LookupError, Exception):
                try:
                    crudo = base64.urlsafe_b64decode(data + '==').decode('utf-8', errors='replace')
                except Exception:
                    continue
            if mime == 'text/plain':
                texto = crudo
                break
            if mime == 'text/html' and not texto:
                texto = html_a_texto(crudo)
        return {'headers': hs, 'snippet': r.get('snippet', ''), 'texto': texto.strip()[:6000]}


def extraer_destinatarios(hs, campos=('to', 'cc', 'bcc')):
    texto = ' '.join(hs.get(k, '') for k in campos)
    return {e.lower() for e in EMAIL_RE.findall(texto)}
