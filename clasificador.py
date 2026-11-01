#!/usr/bin/env python3
"""Clasificador de modalidad / costo / accesibilidad para resultados del radar.
Funciones puras y testeables. Regla clave: las negaciones mandan
("sin arancel" NO es con_costo; "no presencial" ES virtual), y las siglas de
universidades NO se buscan por regex (las resuelve static_data/instituciones_ar.json).
"""
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
INST_F = os.path.join(BASE, 'static_data', 'instituciones_ar.json')

RE_GRATIS = re.compile(
    r'\b(?:gratuit[oa]s?|'
    r'sin\s+(?:costo|cargo|arancel(?:es)?|cuotas?)'
    r'(?:\s*(?:ni|o|y|,)\s*(?:costo|cargo|arancel(?:es)?|cuotas?))*|'
    r'arancel\s+cero|no\s+arancelad[oa])\b', re.I)
RE_PAGO = re.compile(
    r'\b(?:arancel(?:es)?|cuotas?|mensualidad(?:es)?|matr[ií]cula|'
    r'costo\s+(?:mensual|de\s+la\s+carrera))\b', re.I)
RE_PRECIO = re.compile(r'\$\s?\d{1,3}(?:\.\d{3})*(?:,\d+)?')
RE_VIRTUAL = re.compile(
    r'\b(?:100\s?%\s*(?:virtual|a\s+distancia|online)|'
    r'(?:totalmente|completamente)\s+(?:virtual|a\s+distancia|online)|'
    r'modalidad\s+(?:virtual|a\s+distancia|online)|'
    r'educaci[oó]n\s+a\s+distancia|'
    r'(?:carrera|tecnicatura|licenciatura|profesorado|curso|cursada|estudiar)s?\s+'
    r'(?:virtual|a\s+distancia|online|no\s+presenciales?)|'
    r'no\s+presencial)\b', re.I)
RE_PRESENCIAL = re.compile(
    r'\b(?:presencial(?:es|idad)?|h[ií]brid[oa]|'
    r'ex[aá]menes?\s+presenciales?|instancias?\s+presenciales?|'
    r'sedes?\s+(?:regionales?|presenciales?|f[ií]sicas?))\b', re.I)
RE_ACCES = re.compile(
    r'\b(?:ajustes\s+razonables|discapacidad|accesib\w*|inclusi[oó]n)\b', re.I)

_cache_inst = None


def instituciones():
    global _cache_inst
    if _cache_inst is None:
        try:
            with open(INST_F, encoding='utf-8') as f:
                _cache_inst = json.load(f)
        except Exception:
            _cache_inst = []
    return _cache_inst


def tipo_institucion(dom):
    """publica | privada | estatal | desconocida, por sufijo más largo."""
    dom = dom.lower()
    if dom.endswith('.gob.ar'):
        return 'estatal'
    mejor = ('desconocida', 0)
    for it in instituciones():
        d = it['dominio'].lower()
        if (dom == d or dom.endswith('.' + d)) and len(d) > mejor[1]:
            mejor = (it['tipo'], len(d))
    return mejor[0]


def _evidencia(texto, m, radio=80):
    a = max(0, m.start() - radio)
    b = min(len(texto), m.end() + radio)
    return ('…' if a else '') + texto[a:b].strip() + ('…' if b < len(texto) else '')


def clasificar(texto, dom=''):
    """Devuelve (tags, precios, evidencias).
    Orden: quita matches de GRATIS antes de buscar PAGO; quita VIRTUAL antes
    de buscar PRESENCIAL (así 'no presencial' no cuenta como presencial)."""
    t = texto or ''
    tags, precios, evid = [], [], {}

    m = RE_GRATIS.search(t)
    if m:
        tags.append('gratuita')
        evid['gratuita'] = _evidencia(t, m)
        t = RE_GRATIS.sub(' ', t)
    m = RE_PAGO.search(t)
    if m:
        tags.append('con_costo')
        evid['con_costo'] = _evidencia(t, m)
    precios = RE_PRECIO.findall(texto or '')[:5]
    if precios:
        tags.append('precio_detectado')

    m = RE_VIRTUAL.search(t)
    if m:
        tags.append('virtual')
        evid['virtual'] = _evidencia(t, m)
        t = RE_VIRTUAL.sub(' ', t)
    m = RE_PRESENCIAL.search(t)
    if m:
        tags.append('presencial')
        evid['presencial'] = _evidencia(t, m)
        if 'virtual' in tags:
            tags.append('hibrida')

    m = RE_ACCES.search(texto or '')
    if m:
        tags.append('accesible')
        evid['accesible'] = _evidencia(texto or '', m)

    tipo = tipo_institucion(dom) if dom else 'desconocida'
    if tipo == 'publica':
        tags.append('publica')
    elif tipo == 'privada':
        tags.append('privada')
    elif tipo == 'estatal':
        tags.append('estatal')
    else:
        tags.append('sin_clasificar')
    return tags, precios, evid


def score_de(tags, estado_contacto='NUEVO'):
    s = 0
    t = set(tags)
    if 'virtual' in t:
        s += 2
    if 'gratuita' in t:
        s += 2
    if 'publica' in t:
        s += 2
    if 'estatal' in t:
        s += 1
    if 'accesible' in t:
        s += 1
    if estado_contacto == 'NUEVO':
        s += 1
    if 'hibrida' in t:
        s -= 1
    if 'con_costo' in t:
        s -= 1
    if 'presencial' in t and 'hibrida' not in t:
        s -= 2
    if 'privada' in t:
        s -= 2
    return s
