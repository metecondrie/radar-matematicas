#!/usr/bin/env python3
"""OAuth 2.0 PKCE para cliente de escritorio, sin librerías de Google.
Correcciones de auditoría: el chequeo de error= va PRIMERO; state obligatorio
cuando se pega una URL; TTL de 30 min para el state; state de un solo uso
(se consume tras el canje); la cuenta queda cacheada en gmail_token.json para
que /api/estado no haga llamadas de red.
"""
import base64
import hashlib
import json
import os
import re
import secrets
import time
import urllib.error  # noqa: F401
import urllib.parse
import urllib.request

import util
from util import DATA

CS_F = os.path.join(util.BASE, 'client_secret.json')
STATE_F = os.path.join(DATA, 'oauth_state.json')
TOK_F = os.path.join(DATA, 'gmail_token.json')
AJUSTES_F = os.path.join(DATA, 'ajustes.json')

REDIRECT = 'http://localhost:8642'
SCOPE = 'https://www.googleapis.com/auth/gmail.readonly'
TOKEN_URI = 'https://oauth2.googleapis.com/token'
STATE_TTL = 1800  # 30 minutos


def guardar_client(client_id, client_secret):
    client_id = (client_id or '').strip()
    client_secret = (client_secret or '').strip()
    if not client_id.endswith('.apps.googleusercontent.com'):
        raise ValueError('el client_id debe terminar en .apps.googleusercontent.com')
    if not client_secret:
        raise ValueError('falta el client_secret')
    cs = {'installed': {
        'client_id': client_id,
        'client_secret': client_secret,
        'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
        'token_uri': TOKEN_URI,
        'redirect_uris': [REDIRECT, 'http://localhost'],
    }}
    util.escribir_json(CS_F, cs, privado=True)
    return True


def guardar_client_json(texto_json):
    """Acepta el client_secret.json completo (subida de archivo o pegado)."""
    cs = json.loads(texto_json)
    inst = cs.get('installed') or cs.get('web')
    if not inst or not inst.get('client_id'):
        raise ValueError('el JSON no parece un client_secret de Google')
    return guardar_client(inst['client_id'], inst.get('client_secret', ''))


def client_presente():
    return os.path.exists(CS_F)


def generar_auth_url():
    cs = util.leer_json(CS_F, {}, estricto=True)['installed']
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b'=').decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    state = secrets.token_urlsafe(32)
    params = {
        'client_id': cs['client_id'],
        'redirect_uri': REDIRECT,
        'response_type': 'code',
        'scope': SCOPE,
        'access_type': 'offline',
        'prompt': 'consent',
        'state': state,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    }
    url = 'https://accounts.google.com/o/oauth2/auth?' + urllib.parse.urlencode(params)
    util.escribir_json(STATE_F, {
        'code_verifier': verifier, 'state': state, 'redirect_uri': REDIRECT,
        'scope': SCOPE, 'token_uri': cs.get('token_uri', TOKEN_URI),
        'created_at': int(time.time())}, privado=True)
    return url


def extraer_codigo(s):
    s = s.strip().strip('"').strip("'")
    m = re.search(r'[?&]code=([^&#\s]+)', s)
    if m:
        return urllib.parse.unquote(m.group(1))
    m = re.fullmatch(r'(4/0[A-Za-z0-9_\-]+|1//[A-Za-z0-9_\-]+)', s)
    if m:
        return s
    raise ValueError('No encontré ningún código ahí. Pegá la URL completa de la barra de direcciones (http://localhost:8642/?code=...)')


def intercambiar(url_o_codigo):
    if not os.path.exists(STATE_F):
        raise ValueError('Primero generá el link de autorización (paso 1).')
    st = util.leer_json(STATE_F, {}, estricto=True)
    cs = util.leer_json(CS_F, {}, estricto=True)['installed']
    edad = int(time.time()) - st.get('created_at', 0)
    if edad > STATE_TTL:
        raise ValueError('El link de autorización venció (pasaron más de 30 min). Generá uno nuevo.')
    pegado = url_o_codigo.strip()
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(pegado).query) if pegado.startswith('http') or '=' in pegado else {}
    # 1) error de Google primero (mensaje útil, no "no encontré código")
    if qs.get('error'):
        raise ValueError('Google devolvió un error: '
                         f'{qs["error"][0]} (¿denegaste el permiso?). Generá el link de nuevo y aceptá.')
    # 2) state: obligatorio si viene URL; código suelto = aviso explícito
    sin_state = False
    if pegado.startswith('http'):
        recibido = qs.get('state', [None])[0]
        if not recibido or recibido != st['state']:
            raise ValueError('El parámetro state falta o no coincide. Volvé a generar el link de autorización.')
    else:
        sin_state = True
    codigo = extraer_codigo(pegado)
    data = urllib.parse.urlencode({
        'code': codigo,
        'client_id': cs['client_id'],
        'client_secret': cs['client_secret'],
        'redirect_uri': st['redirect_uri'],
        'grant_type': 'authorization_code',
        'code_verifier': st['code_verifier'],
    }).encode()
    req = urllib.request.Request(st['token_uri'], data=data,
                                 headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        resp = json.load(urllib.request.urlopen(req, timeout=25))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Google rechazó el código (HTTP {e.code}): {e.read().decode(errors="replace")[:300]}')
    if 'refresh_token' not in resp:
        raise RuntimeError('Google no dio refresh_token. Revocá el permiso en '
                           'https://myaccount.google.com/permissions y volvé a autorizar.')
    ahora = int(time.time())
    resp['obtenido_en'] = ahora
    resp['autorizado_en'] = ahora
    cuenta = None
    try:
        rq = urllib.request.Request('https://www.googleapis.com/gmail/v1/users/me/profile',
                                    headers={'Authorization': 'Bearer ' + resp['access_token']})
        cuenta = json.load(urllib.request.urlopen(rq, timeout=20)).get('emailAddress')
    except Exception:
        pass
    if cuenta:
        resp['cuenta'] = cuenta
    util.escribir_json(TOK_F, resp, privado=True)
    try:
        os.remove(STATE_F)  # state de un solo uso
    except OSError:
        pass
    return {'ok': True, 'cuenta': cuenta, 'scope': resp.get('scope'),
            'aviso_edad': edad > 570, 'sin_state': sin_state}


def oauth_modo():
    return util.leer_json(AJUSTES_F, {}).get('oauth_modo', 'pruebas')


def estado():
    """Solo disco: sin llamadas de red (el frontend pollea seguido)."""
    out = {'client_presente': client_presente(), 'token_presente': os.path.exists(TOK_F),
           'conectado': False, 'cuenta': None, 'vence_testing': None,
           'oauth_modo': oauth_modo(), 'necesita_reauth': False}
    if out['token_presente']:
        try:
            tok = util.leer_json(TOK_F, {}, estricto=True)
            out['conectado'] = True
            out['scope'] = tok.get('scope')
            out['cuenta'] = tok.get('cuenta')
            aut = tok.get('autorizado_en') or tok.get('obtenido_en', 0)
            out['autorizado_en'] = aut
            if oauth_modo() == 'pruebas':
                out['vence_testing'] = aut + 7 * 86400
                dias = max(0, round((out['vence_testing'] - time.time()) / 86400, 1))
                out['dias_restantes'] = dias
                out['necesita_reauth'] = dias <= 2
        except util.JsonCorrupto:
            out['conectado'] = False
            out['motivo'] = 'token corrupto: reautorizá'
    return out


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        print(intercambiar(sys.argv[1]))
    else:
        print(generar_auth_url())
