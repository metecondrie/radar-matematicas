#!/usr/bin/env python3
"""Genera war_room.html: snapshot AUTOCONTENIDO del war room (doble click, sin
servidor ni internet). Correcciones de auditoría: el JSON embebido se escapa
(\\u003c etc.) para que ningún '</script>' proveniente de asuntos o snippets
rompa o inyecte código; los borradores se generan UNA sola vez en el backend
(ia_redactor.redactar_local) y viajan embebidos; sin claves ni datos sensibles.
"""
import os
import time

import clasificador
import ia_redactor
import oauth_setup
import util
from util import DATA

OUT = os.path.join(util.BASE, 'war_room.html')


def build():
    con = util.leer_json(os.path.join(DATA, 'contactados.json'), {})
    rad = util.leer_json(os.path.join(DATA, 'radar.json'), {'resultados': []})
    sync = util.leer_json(os.path.join(DATA, 'sync_status.json'), {})
    est_g = oauth_setup.estado()

    filas = []
    for d, c in con.get('dominios', {}).items():
        filas.append({
            'dominio': d, 'nombre': c.get('nombre', d),
            'carrera': c.get('carrera') or (c.get('asuntos') or [''])[0],
            'emails': c.get('emails', []), 'n_mails': c.get('n_mails', 0),
            'ultimo_contacto': c.get('ultimo_contacto', 0),
            'respondido': c.get('respuesta_humana', c.get('respondido', False)),
            'estado': util.estado_contacto(c),
            'asuntos': c.get('asuntos', []),
            'borrador': ia_redactor.redactar_local(
                'seguimiento', institucion=c.get('nombre', d),
                asunto=(c.get('asuntos') or [''])[0], carrera=c.get('carrera', '')),
        })
    orden = {'REINTENTAR': 0, 'EN_ESPERA': 1, 'CONTESTO': 2}
    filas.sort(key=lambda f: (orden.get(f['estado'], 3), -f['ultimo_contacto']))
    est = [f['estado'] for f in filas]

    radar_out = []
    for r in rad.get('resultados', [])[:40]:
        radar_out.append({
            'url': r.get('url'), 'titulo': r.get('titulo', ''), 'snippet': r.get('snippet', ''),
            'dominio': r.get('dominio', ''), 'tags': r.get('tags_pagina', r.get('tags', [])),
            'evidencia': r.get('evidencia', {}), 'score': r.get('score', 0),
            'estado_contacto': r.get('estado_contacto', 'NUEVO'),
            'relacionado': r.get('relacionado'),
            'borrador': ia_redactor.redactar_local('consulta', institucion=r.get('dominio', ''),
                                                   carrera=r.get('titulo', '')),
        })

    payload = {
        'generado_en': int(time.time()),
        'sync': {'corriendo': util.esta_corriendo(sync), 'mensaje': sync.get('mensaje', ''),
                 'progreso': sync.get('progreso', 0), 'total': sync.get('total', 0)},
        'token': {'cuenta': est_g.get('cuenta') or '', 'dias': est_g.get('dias_restantes'),
                  'modo': est_g.get('oauth_modo', 'pruebas')} if est_g['conectado'] else {},
        'kpis': {'instituciones': len(filas), 'contestaron': est.count('CONTESTO'),
                 'en_espera': est.count('EN_ESPERA'), 'reintentar': est.count('REINTENTAR'),
                 'radar_nuevos': sum(1 for r in radar_out if r['estado_contacto'] == 'NUEVO'),
                 'demo': bool(con.get('demo_hasta_sync'))},
        'filas': filas,
        'radar': radar_out,
        'firma': ia_redactor.ajustes().get('nombre_firma', ''),
    }
    html_txt = TEMPLATE.replace('__DATA__', util.texto_a_html_seguro_json(payload))
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(html_txt)
    try:
        os.chmod(OUT, 0o600)  # contiene datos reales del usuario
    except OSError:
        pass
    return OUT


TEMPLATE = r'''<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🎖 Radar Matemáticas — War Room</title>
<style>
:root{--bg:#0a0e13;--panel:#10161d;--panel2:#151d26;--border:#1f2a37;--txt:#dce6f0;--dim:#7d8ea1;--green:#35d07f;--amber:#f5a623;--red:#ff5c5c;--cyan:#4cc9f0;--violet:#a78bfa;--mono:ui-monospace,Menlo,Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.5 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}
a{color:var(--cyan)}
header{padding:14px 20px;border-bottom:1px solid var(--border);display:flex;flex-wrap:wrap;gap:10px;align-items:center;background:linear-gradient(180deg,#0e141b,#0a0e13)}
header h1{font-size:17px;margin:0;letter-spacing:.5px}header h1 span{color:var(--green)}
.pill{font-size:11px;padding:3px 10px;border-radius:99px;border:1px solid var(--border);color:var(--dim);white-space:nowrap}
.pill.ok{color:var(--green);border-color:#1d4630}.pill.warn{color:var(--amber);border-color:#4d3a12}.pill.bad{color:var(--red);border-color:#4d1f1f}
main{padding:18px;max-width:1150px;margin:0 auto}
.banner{padding:10px 14px;border-radius:8px;margin-bottom:14px;border:1px solid;font-size:13px}
.banner.info{background:#0c1620;border-color:#1d3a4d;color:var(--cyan)}
.banner.warn{background:#1a1408;border-color:#4d3a12;color:var(--amber)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px}
.kpi{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:14px}
.kpi .n{font:700 28px var(--mono)}.kpi .l{color:var(--dim);font-size:11.5px;text-transform:uppercase;letter-spacing:.8px;margin-top:2px}
.kpi.g .n{color:var(--green)}.kpi.a .n{color:var(--amber)}.kpi.r .n{color:var(--red)}.kpi.c .n{color:var(--cyan)}.kpi.v .n{color:var(--violet)}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--border);border-radius:10px;overflow:hidden}
th{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.7px;text-align:left;padding:10px 12px;border-bottom:1px solid var(--border);background:var(--panel2)}
td{padding:9px 12px;border-bottom:1px solid #16202b;vertical-align:top}tr:last-child td{border-bottom:none}tr:hover td{background:#131b24}
.badge{display:inline-block;font-size:11px;padding:2px 9px;border-radius:99px;border:1px solid;white-space:nowrap}
.b-contesto{color:var(--green);border-color:#1d4630;background:#0d1a12}.b-espera{color:var(--amber);border-color:#4d3a12;background:#171105}
.b-reintento{color:var(--cyan);border-color:#1d3a4d;background:#0b1520}.b-nuevo{color:var(--violet);border-color:#3b2f63;background:#130f21}
button.btn{background:var(--panel2);border:1px solid var(--border);color:var(--txt);padding:6px 11px;border-radius:7px;cursor:pointer;font-size:12.5px}
button.btn:hover{border-color:#31435a}button.btn.primary{background:#12351f;border-color:#1d4630;color:var(--green)}
.muted{color:var(--dim);font-size:12px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:13px;margin-bottom:10px}
.card .t{font-weight:600}.card .sn{color:var(--dim);font-size:12.5px;margin:5px 0}
.ev{color:var(--dim);font-size:11.5px;font-style:italic;margin-top:4px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.modalbg{position:fixed;inset:0;background:rgba(4,7,10,.78);display:none;z-index:50;align-items:flex-start;justify-content:center;padding:30px 14px;overflow-y:auto}
.modalbg.on{display:flex}.modal{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:18px;width:100%;max-width:680px}
.modal h3{margin:0 0 12px}label{display:block;color:var(--dim);font-size:11.5px;text-transform:uppercase;letter-spacing:.6px;margin:10px 0 4px}
input,textarea{background:#0c1118;border:1px solid var(--border);color:var(--txt);border-radius:7px;padding:8px 10px;font-size:13px;width:100%;font-family:inherit}
textarea{resize:vertical}
h2.sec{font-size:14px;margin:22px 0 10px}
#toast{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);background:#132030;border:1px solid #24466b;padding:10px 18px;border-radius:9px;font-size:13px;display:none;z-index:99}
</style></head><body>
<header>
<h1>🎖 RADAR <span>MATEMÁTICAS</span> — War Room</h1>
<span class="pill ok" id="pCuenta"></span>
<span class="pill" id="pToken"></span>
<span class="pill" id="pSync"></span>
<span class="pill" style="margin-left:auto">📸 foto del tablero · <span id="pGen"></span></span>
</header>
<main>
<div class="banner info">ℹ Esta es una <b>foto instantánea</b> del war room: funciona sin servidor ni internet. La versión viva (bandeja real, decisiones guardadas, IA) corre donde tengas instalado el proyecto. ✋ Nada se envía solo: los botones arman el borrador y vos lo copiás o lo abrís en tu correo.</div>
<div id="banners"></div>
<div class="kpis" id="kpis"></div>
<h2 class="sec">Campaña de contacto</h2>
<div style="overflow-x:auto"><table>
<thead><tr><th>Estado</th><th>Institución</th><th>Carrera / asunto</th><th>Último contacto</th><th>Mails</th><th>Borrador</th></tr></thead>
<tbody id="tb"></tbody></table></div>
<h2 class="sec">🛰 Radar de programas nuevos</h2>
<div id="radar"></div>
</main>
<div class="modalbg" id="mb" onclick="if(event.target===this)this.classList.remove('on')">
<div class="modal"><h3 id="mT">✉ Borrador</h3>
<label>Para</label><input id="mTo">
<label>Asunto</label><input id="mSub">
<label>Cuerpo (editable)</label><textarea id="mBody" rows="13"></textarea>
<div class="row" style="margin-top:12px">
<button class="btn primary" data-act="copy">📋 Copiar borrador</button>
<button class="btn" data-act="gmail">📧 Abrir en Gmail web</button>
<button class="btn" data-act="mailto">✉ Cliente de correo</button>
<button class="btn" style="margin-left:auto" data-act="close">Cerrar</button>
</div></div></div>
<div id="toast"></div>
<script>
const D=__DATA__;
const $=id=>document.getElementById(id);
const esc=s=>(s==null?'':String(s)).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fF=ts=>ts?new Date(ts*1000).toLocaleDateString('es-AR',{day:'2-digit',month:'2-digit',year:'numeric'}):'—';
const fH=ts=>{if(!ts)return'';const d=Math.floor((Date.now()/1000-ts)/86400);return d===0?'hoy':d===1?'ayer':'hace '+d+' d'};
function toast(m){const t=document.getElementById('toast');t.textContent=m;t.style.display='block';clearTimeout(t._h);t._h=setTimeout(()=>t.style.display='none',3000)}
document.getElementById('pCuenta').textContent='Gmail: '+(D.token.cuenta||'conectado');
const pt=document.getElementById('pToken');
if(D.token.dias!=null&&D.token.modo==='pruebas'){pt.textContent='token: '+D.token.dias+' d restantes (modo Pruebas)';pt.className='pill '+(D.token.dias<=2?'bad':D.token.dias<=4?'warn':'ok')}
const ps=document.getElementById('pSync');
if(D.sync.corriendo){ps.textContent='sync: '+D.sync.mensaje;ps.className='pill warn'}else if(D.sync.mensaje){ps.textContent='sync: '+D.sync.mensaje;ps.className='pill ok'}
document.getElementById('pGen').textContent=new Date(D.generado_en*1000).toLocaleString('es-AR');
let ban='';
if(D.kpis.demo)ban+='<div class="banner warn">⚠ Datos de ejemplo: la sincronización de tus Enviados reales todavía no terminó. Regenerá este archivo cuando termine.</div>';
if(D.token.dias!=null&&D.token.dias<=2&&D.token.modo==='pruebas')ban+='<div class="banner warn">⏰ El token de Google vence en '+D.token.dias+' días: reautorizar son 30 segundos desde Ajustes.</div>';
document.getElementById('banners').innerHTML=ban;
const k=D.kpis;
document.getElementById('kpis').innerHTML=
 '<div class="kpi c"><div class="n">'+k.instituciones+'</div><div class="l">Instituciones contactadas</div></div>'+
 '<div class="kpi g"><div class="n">'+k.contestaron+'</div><div class="l">✉ Contestaron</div></div>'+
 '<div class="kpi a"><div class="n">'+k.en_espera+'</div><div class="l">⏳ En espera</div></div>'+
 '<div class="kpi v"><div class="n">'+k.reintentar+'</div><div class="l">🔁 Reintentar (30 d)</div></div>'+
 '<div class="kpi c"><div class="n">'+k.radar_nuevos+'</div><div class="l">🛰 Nuevos en radar</div></div>';
const badge=e=>e==='CONTESTO'?'<span class="badge b-contesto">✉ CONTESTÓ</span>':e==='REINTENTAR'?'<span class="badge b-reintento">🔁 REINTENTAR</span>':'<span class="badge b-espera">⏳ EN ESPERA</span>';
document.getElementById('tb').innerHTML=D.filas.map((f,i)=>'<tr><td>'+badge(f.estado)+'</td>'+
 '<td><b>'+esc(f.nombre)+'</b><br><span class="muted">'+esc(f.dominio)+'</span></td>'+
 '<td>'+esc(f.carrera||'')+'</td><td>'+fF(f.ultimo_contacto)+' <span class="muted">('+fH(f.ultimo_contacto)+')</span></td>'+
 '<td style="font-family:var(--mono)">'+(f.n_mails||1)+'</td>'+
 '<td><button class="btn" data-act="seg" data-i="'+i+'">✉ '+(f.estado==='REINTENTAR'?'Reintentar':'Seguimiento')+'</button></td></tr>').join('');
const TAGL={virtual:['📡 virtual / a distancia','b-reintento'],gratuita:['🆓 gratuita','b-contesto'],publica:['🏛 pública','b-contesto'],estatal:['🏛 estatal','b-contesto'],privada:['💰 privada','b-espera'],con_costo:['💲 con costo','b-espera'],precio_detectado:['💲 precios en la página','b-espera'],presencial:['🏢 presencial','b-espera'],hibrida:['🔀 híbrida','b-espera'],accesible:['♿ accesibilidad','b-nuevo'],sin_clasificar:['❓ sin clasificar','b-demo']};
function tagrow(tags,ev){return (tags||[]).map(t=>{const L=TAGL[t];if(!L)return '';const e=ev&&ev[t];return '<span class="badge '+L[1]+'" title="'+esc(e||'')+'">'+L[0]+'</span>'}).join(' ')+(ev&&Object.keys(ev).length?'<div class="ev">evidencia: '+esc(Object.values(ev)[0]||'')+'</div>':'')}
document.getElementById('radar').innerHTML=(D.radar||[]).map((r,i)=>{
 const b=r.estado_contacto==='NUEVO'?'<span class="badge b-nuevo">🆕 NUEVO</span>':r.estado_contacto==='REINTENTAR'?'<span class="badge b-reintento">🔁 REINTENTAR</span>':'<span class="badge b-espera">⏳ CONTACTADO &lt;30d</span>';
 const rel=r.relacionado?'<span class="muted">· ya escribiste a otra unidad: '+esc(r.relacionado)+'</span>':'';
 return '<div class="card"><div class="row"><span class="t">'+esc(r.titulo||r.url)+'</span>'+b+'</div>'+
 '<div class="row" style="margin:6px 0 0">'+tagrow(r.tags,r.evidencia)+rel+'</div>'+
 '<div class="muted" style="margin-top:2px">'+esc(r.dominio)+' · <a href="'+esc(r.url)+'" target="_blank" rel="noopener">fuente ↗</a></div>'+
 '<div class="sn">'+esc(r.snippet||'')+'</div>'+
 '<button class="btn" data-act="cons" data-i="'+i+'">✉ Escribir consulta</button></div>';}).join('')||'<p class="muted">Sin resultados todavía.</p>';
let modalCtx=null;
function abrir(titulo,to,sub,body){modalCtx={to:to,sub:sub};document.getElementById('mT').textContent=titulo;document.getElementById('mTo').value=to||'';document.getElementById('mSub').value=sub||'';document.getElementById('mBody').value=body;document.getElementById('mb').classList.add('on')}
function copiar(){const el=document.getElementById('mBody');el.select();el.setSelectionRange(0,99999);let ok=false;try{ok=document.execCommand('copy')}catch(e){}toast(ok?'Borrador copiado ✓ — pegalo en tu correo':'Seleccioná el texto y copialo con Ctrl+C')}
function gmailWeb(){if(!$('mTo').value){toast('Falta el destinatario: pegalo en "Para"');return}const u='https://mail.google.com/mail/?view=cm&fs=1&to='+encodeURIComponent($('mTo').value)+'&su='+encodeURIComponent($('mSub').value)+'&body='+encodeURIComponent($('mBody').value);window.open(u,'_blank','noopener')}
function mailto(){if(!$('mTo').value){toast('Falta el destinatario: pegalo en "Para"');return}location.href='mailto:'+$('mTo').value+'?subject='+encodeURIComponent($('mSub').value)+'&body='+encodeURIComponent($('mBody').value)}
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-act]');if(!b)return;
 const act=b.dataset.act,i=+b.dataset.i;
 if(act==='seg'){const f=D.filas[i];abrir('✉ '+(f.estado==='REINTENTAR'?'Reintento':'Seguimiento'),(f.emails&&f.emails[0])||'','Re: '+((f.asuntos&&f.asuntos[0])||f.carrera||''),f.borrador)}
 else if(act==='cons'){const r=D.radar[i];abrir('✉ Nueva consulta','','Consulta: '+r.titulo,r.borrador)}
 else if(act==='copy')copiar();
 else if(act==='gmail')gmailWeb();
 else if(act==='mailto')mailto();
 else if(act==='close')document.getElementById('mb').classList.remove('on');
});
</script></body></html>'''


if __name__ == '__main__':
    print(build(), 'generado')
