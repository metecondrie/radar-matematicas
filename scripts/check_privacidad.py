#!/usr/bin/env python3
"""Guardia de privacidad del repositorio.

Recorre los archivos versionables (respeta .gitignore: nunca entra a data/,
uploads/, war_room.html ni client_secret.json) y falla si encuentra:
  - emails que no sean claramente sintéticos (dominios example/ejemplo/demo/
    prueba o fixtures explícitos de tests),
  - secretos con forma real: tokens de Google (ya29.…, GOCSPX-…), PATs de
    GitHub (github_pat_…), claves de OpenAI (sk-…), de Google (AIza…),
    Bearer tokens largos, o valores de client_secret que no sean de prueba,
  - la cuenta de correo real del usuario, en cualquier forma.

Uso:  python3 scripts/check_privacidad.py     (exit 0 = limpio, 1 = hallazgos)
Lo corre GitHub Actions en cada push y `make check` en local.
"""
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Directorios/archivos que NUNCA se recorren (datos reales del usuario).
SALTEAR_DIRS = {'.git', 'data', 'uploads', '__pycache__', '.venv', 'node_modules',
                '.mypy_cache', '.pytest_cache'}
SALTEAR_ARCH = {'war_room.html', 'client_secret.json'}
EXT_OK = {'.py', '.md', '.html', '.js', '.css', '.json', '.yml', '.yaml', '.txt',
          '.cfg', '.toml', '.in', ''}

EMAIL_RE = re.compile(r'[A-Za-z0-9_.+-]+@[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+')

# Un email es aceptable si el dominio o la casilla son claramente de ejemplo.
DOMINIOS_SINTETICOS = ('example.com', 'example.org', 'example.net', 'example.ar')
MARCAS_SINTETICAS = ('ejemplo', 'demo', 'prueba', 'noexiste', 'placeholder',
                     'sample', 'test', 'fixture')
EMAILS_PERMITIDOS = {  # fixtures literales de los tests / docs
    'a@b.edu.ar', 'x@x.ar', 'secre@instituto.edu.ar',
    'infos@uni-prueba.edu.ar', 'juan.perez@uni.edu.ar',
}

SECRETOS = [
    (re.compile(r'ya29\.[A-Za-z0-9_-]{20,}'), 'token de acceso Google (ya29.…)'),
    (re.compile(r'GOCSPX-(?!\.\.\.|…|test)[A-Za-z0-9_-]{8,}'), 'client secret de Google (GOCSPX-…)'),
    (re.compile(r'github_pat_[A-Za-z0-9_]{20,}'), 'fine-grained PAT de GitHub'),
    (re.compile(r'ghp_[A-Za-z0-9]{30,}'), 'classic PAT de GitHub'),
    (re.compile(r'sk-[A-Za-z0-9_-]{20,}'), 'API key estilo OpenAI (sk-…)'),
    (re.compile(r'AIza[0-9A-Za-z_-]{30,}'), 'API key de Google (AIza…)'),
    (re.compile(r'Bearer\s+[A-Za-z0-9._~-]{25,}'), 'Bearer token literal'),
    (re.compile(r'"client_secret"\s*:\s*"(?!GOCSPX-test)[^"]{8,}"'), 'client_secret con valor real'),
]

# La cuenta real del usuario jamás puede aparecer (ni ofuscada a medias).
# (Los patrones se arman por concatenación para que ESTE archivo no se
# auto-denuncie al ser escaneado.)
_APELLIDO = 'on' + 'garo'
PROHIBIDOS = [re.compile(r'alejo\s*' + _APELLIDO, re.I),
              re.compile('alejo' + _APELLIDO, re.I)]


def email_sintetico(email: str) -> bool:
    low = email.lower()
    if low in EMAILS_PERMITIDOS:
        return True
    local, _, dom = low.partition('@')
    if dom in DOMINIOS_SINTETICOS:
        return True
    return any(m in local or m in dom for m in MARCAS_SINTETICAS)


def revisar(path: str):
    """Devuelve lista de (nro_linea, motivo, fragmento)."""
    hallazgos = []
    try:
        with open(path, encoding='utf-8') as f:
            lineas = f.read().splitlines()
    except (UnicodeDecodeError, OSError):
        return hallazgos
    for i, ln in enumerate(lineas, 1):
        for m in EMAIL_RE.finditer(ln):
            if not email_sintetico(m.group(0)):
                hallazgos.append((i, 'email no sintético', m.group(0)))
        for rx, motivo in SECRETOS:
            m = rx.search(ln)
            if m:
                hallazgos.append((i, motivo, m.group(0)[:24] + '…'))
        for rx in PROHIBIDOS:
            m = rx.search(ln)
            if m:
                hallazgos.append((i, 'dato personal del usuario', m.group(0)))
    return hallazgos


def main() -> int:
    total = 0
    archivos = 0
    for root, dirs, files in os.walk(BASE):
        dirs[:] = sorted(d for d in dirs if d not in SALTEAR_DIRS)
        for fn in sorted(files):
            if fn in SALTEAR_ARCH or os.path.splitext(fn)[1].lower() not in EXT_OK:
                continue
            path = os.path.join(root, fn)
            archivos += 1
            rel = os.path.relpath(path, BASE)
            for nro, motivo, frag in revisar(path):
                total += 1
                print(f'PRIVACIDAD {rel}:{nro}: {motivo} → {frag}')
    if total:
        print(f'\n✖ {total} hallazgo(s) de privacidad en {archivos} archivos revisados.')
        print('  Estos archivos se versionan: sanealos antes de commitear.')
        return 1
    print(f'✓ Privacidad OK: {archivos} archivos versionables sin emails reales ni secretos.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
