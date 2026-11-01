/* Radar Matemáticas — frontend del war room. Sin frameworks.
   Todo handler inline con datos está prohibido: un único listener delegado
   por data-act; los datos se leen de arrays en memoria, nunca del HTML. */
'use strict';
const TOKEN = (document.querySelector('meta[name="radar-token"]') || {}).content || '';
let ESTADO = {}, CAMP = {filas: []}, BAN = {mensajes: [], modo: 'demo'}, SEL = null,
    RADAR = {}, AJ = {}, modalCtx = null, banTodo = false;

const $ = id => document.getElementById(id);
const esc = s => (s == null ? '' : String(s)).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const fFecha = ts => ts ? new Date(ts * 1000).toLocaleDateString('es-AR', {day: '2-digit', month: '2-digit', year: 'numeric'}) : '—';
const fHace = ts => { if (!ts) return ''; const d = Math.floor((Date.now() / 1000 - ts) / 86400); return d === 0 ? 'hoy' : d === 1 ? 'ayer' : `hace ${d} d`; };
function toast(m) { const t = $('toast'); t.textContent = m; t.style.display = 'block'; clearTimeout(t._h); t._h = setTimeout(() => t.style.display = 'none', 4200); }
async function api(path, opts) {
  const o = Object.assign({headers: {'X-Radar-Token': TOKEN}}, opts || {});
  if (o.body) o.headers['Content-Type'] = 'application/json';
  const r = await fetch(path, o);
  const j = await r.json().catch(() => ({error: 'respuesta inválida'}));
  if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status));
  return j;
}
const post = (path, body) => api(path, {method: 'POST', body: JSON.stringify(body || {})});
function copiarTexto(txt) {
  const ta = document.createElement('textarea');
  ta.value = txt; document.body.appendChild(ta); ta.select();
  let ok = false; try { ok = document.execCommand('copy'); } catch (e) {}
  ta.remove(); toast(ok ? 'Copiado ✓' : 'No se pudo copiar: seleccioná y Ctrl+C');
}
function abrirGmailWeb(to, sub, body) {
  const u = 'https://mail.google.com/mail/?view=cm&fs=1&to=' + encodeURIComponent(to) +
            '&su=' + encodeURIComponent(sub) + '&body=' + encodeURIComponent(body);
  window.open(u, '_blank', 'noopener');
  toast('Se abre Gmail en una pestaña — el envío lo hacés vos ✋');
}
function abrirMailto(to, sub, body) {
  if (body.length > 1800) { copiarTexto(body); toast('Cuerpo largo: copiado al portapapeles; pegalo en tu cliente de correo'); }
  location.href = 'mailto:' + to + '?subject=' + encodeURIComponent(sub) + '&body=' + encodeURIComponent(body);
}

/* ---------- tabs ---------- */
document.querySelectorAll('nav button').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('nav button').forEach(x => x.classList.remove('on'));
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('on'));
  b.classList.add('on'); $('tab-' + b.dataset.tab).classList.add('on');
  if (b.dataset.tab === 'bandeja') loadBandeja();
  if (b.dataset.tab === 'radar') loadRadar();
  if (b.dataset.tab === 'ajustes') loadAjustes();
}));

/* ---------- estado + polling único ---------- */
let _pollT = null, _busy = false;
function hayTarea() {
  const s = ESTADO.sync || {}, r = ESTADO.radar_status || {};
  return (s.corriendo && Date.now() / 1000 - (s.ts || 0) < 180) ||
         (r.corriendo && Date.now() / 1000 - (r.ts || 0) < 180);
}
async function pollEstado() {
  if (_busy) return; _busy = true;
  try { ESTADO = await api('/api/estado'); renderEstado(); } catch (e) { /* silencioso */ }
  finally {
    _busy = false;
    clearTimeout(_pollT);
    _pollT = setTimeout(pollEstado, hayTarea() ? 3000 : 30000);
  }
}
function renderEstado() {
  const g = ESTADO.gmail || {};
  const pg = $('pillGmail');
  if (g.conectado) { pg.textContent = 'Gmail: ' + (g.cuenta || 'conectado'); pg.className = 'pill ok'; }
  else { pg.textContent = 'Gmail: NO conectado'; pg.className = 'pill bad'; }
  const pt = $('pillToken');
  if (g.conectado && g.oauth_modo === 'pruebas' && g.dias_restantes != null) {
    pt.textContent = `token: ${g.dias_restantes} d restantes (modo Pruebas)`;
    pt.className = 'pill ' + (g.dias_restantes <= 2 ? 'bad' : g.dias_restantes <= 4 ? 'warn' : 'ok');
  } else if (g.conectado) { pt.textContent = 'token: modo Producción'; pt.className = 'pill ok'; }
  else { pt.textContent = 'token: —'; pt.className = 'pill'; }
  const s = ESTADO.sync || {};
  const ps = $('pillSync');
  const viva = s.corriendo && Date.now() / 1000 - (s.ts || 0) < 180;
  if (viva) { ps.innerHTML = 'sync: <span class="spin"></span> ' + esc(s.mensaje || ''); ps.className = 'pill warn'; }
  else if (s.mensaje) { ps.textContent = 'sync: ' + s.mensaje; ps.className = 'pill ' + (String(s.mensaje).startsWith('ERROR') ? 'bad' : 'ok'); }
  else { ps.textContent = 'sync: nunca'; ps.className = 'pill'; }
  renderWar();
}

/* ---------- war room ---------- */
function renderWar() {
  const k = ESTADO.kpis || {}, g = ESTADO.gmail || {};
  let ban = '';
  if (!g.conectado) ban += '<div class="banner bad">⚠ <b>Gmail no conectado.</b> Se muestran datos de ejemplo. Andá a <b>⚙ Ajustes</b> para conectar tu cuenta (2 minutos).</div>';
  else if (g.necesita_reauth) ban += `<div class="banner bad">⏰ El token de Google vence en <b>${g.dias_restantes} días</b>. <button class="btn sm" data-act="reauth">🔑 Reautorizar ahora</button> (30 segundos: link → permitir → pegar la URL)</div>`;
  if (k.dominios_demo) ban += `<div class="banner info">ℹ Datos de ejemplo (${k.instituciones} instituciones). Al conectar Gmail y sincronizar, esto se reemplaza por tus Enviados reales.</div>`;
  $('warBanners').innerHTML = ban;
  $('kpis').innerHTML = `
    <div class="kpi c"><div class="n">${k.instituciones ?? '—'}</div><div class="l">Instituciones (${k.universidades ?? '—'} universidades)</div></div>
    <div class="kpi g"><div class="n">${k.contestaron ?? '—'}</div><div class="l">✉ Contestaron</div></div>
    <div class="kpi a"><div class="n">${k.en_espera ?? '—'}</div><div class="l">⏳ En espera</div></div>
    <div class="kpi v"><div class="n">${k.reintentar ?? '—'}</div><div class="l">🔁 Reintentar (30 d)</div></div>
    <div class="kpi c"><div class="n">${k.radar_nuevos ?? '—'}</div><div class="l">🛰 Nuevos en radar</div></div>`;
  $('campMeta').textContent = k.sincronizado_en ? ('· actualizado ' + fHace(k.sincronizado_en)) : '';
}
async function loadCampana() {
  try { CAMP = await api('/api/campana'); } catch (e) { return; }
  const tb = $('campBody');
  tb.innerHTML = (CAMP.filas || []).map((f, i) => {
    const b = f.estado === 'CONTESTO' ? '<span class="badge b-contesto">✉ CONTESTÓ</span>'
            : f.estado === 'REINTENTAR' ? '<span class="badge b-reintento">🔁 REINTENTAR</span>'
            : '<span class="badge b-espera">⏳ EN ESPERA</span>';
    const auto = f.autorespuesta && !f.respuesta_humana ? '<span class="badge b-demo" title="solo respuestas automáticas">🤖 auto</span>' : '';
    return `<tr>
      <td>${b} ${auto}</td>
      <td><b>${esc(f.nombre || f.dominio)}</b><br><span class="muted">${esc(f.dominio)}</span></td>
      <td>${esc(f.carrera || '') || '<span class="muted">—</span>'}</td>
      <td>${fFecha(f.ultimo_contacto)} <span class="muted">(${fHace(f.ultimo_contacto)})</span></td>
      <td style="font-family:var(--mono)">${f.n_mails || 1}</td>
      <td><button class="btn sm" data-act="seg" data-i="${i}">✉ ${f.estado === 'REINTENTAR' ? 'Reintentar' : 'Seguimiento'}</button>
          <button class="btn sm" data-act="mark" data-i="${i}" title="marcar/desmarcar respuesta humana">✎</button></td>
    </tr>`;
  }).join('') || '<tr><td colspan="6" class="muted">Sin datos todavía.</td></tr>';
}

/* ---------- bandeja ---------- */
async function loadBandeja(force) {
  const el = $('banList'); el.innerHTML = '<div style="padding:14px" class="muted"><span class="spin"></span> cargando…</div>';
  try { BAN = await api('/api/bandeja' + (force ? '?force=1' : '') + (banTodo ? '&todo=1' : '')); }
  catch (e) { el.innerHTML = '<div class="banner bad">' + esc(e.message) + '</div>'; return; }
  $('banModo').textContent = BAN.modo === 'real' ? ('REAL · ' + (BAN.cuenta || '')) : 'DEMO (conectá Gmail en Ajustes)';
  $('banModo').className = 'badge ' + (BAN.modo === 'real' ? 'b-contesto' : 'b-demo');
  $('banBanners').innerHTML =
    (BAN.aviso ? `<div class="banner bad">⚠ ${esc(BAN.aviso)}</div>` : '') +
    (BAN.modo === 'real' ? '' : '<div class="banner warn">🧪 Bandeja <b>DEMO</b> con respuestas de ejemplo para probar el flujo (decidir → redactar → enviar vos). Conectá Gmail en ⚙ Ajustes para ver tus correos reales.</div>');
  const labels = {
    pendiente: '<span class="badge b-demo">pendiente</span>',
    responder: '<span class="badge b-contesto">✉ a responder</span>',
    no_responder: '<span class="badge b-espera">✓ no requiere</span>',
    ignorado: '<span class="badge b-reintento">🗑 ignorado</span>'};
  el.innerHTML = (BAN.mensajes || []).map(m => `
    <div class="msg ${SEL === m.id ? 'sel' : ''}" data-act="msg" data-id="${esc(m.id)}">
      <div class="f"><span>${esc(m.from_nombre || m.from)}</span><span class="d">${esc((m.date || '').slice(0, 22))}</span></div>
      <div class="s">${esc(m.subject || '(sin asunto)')}</div>
      <div class="row" style="margin-top:4px">${labels[m.decision] || ''}${m.demo ? '<span class="badge b-demo">DEMO</span>' : ''}${m.presencial ? '<span class="badge b-espera" title="menciona instancias presenciales">🏢 presencial</span>' : ''}</div>
    </div>`).join('') || '<div style="padding:14px" class="muted">Sin correos relevantes en los últimos 90 días. Activá "ver todo" para mirar el resto.</div>';
}
async function abrirMensaje(id) {
  SEL = id;
  let m;
  try { m = await api('/api/mensaje?id=' + encodeURIComponent(id)); }
  catch (e) { $('banDetail').innerHTML = '<div class="banner bad">' + esc(e.message) + '</div>'; return; }
  document.querySelectorAll('.msg').forEach(x => x.classList.toggle('sel', x.dataset.id === id));
  $('banDetail').innerHTML = `
    <div class="row" style="justify-content:space-between">
      <div><b>${esc(m.subject || '')}</b>
        <div class="muted">De: ${esc(m.from_nombre || '')} &lt;${esc(m.from || '')}&gt; · ${esc(m.date || '')} ${m.demo ? '· <span class="badge b-demo">DEMO</span>' : ''}</div></div>
    </div>
    ${m.presencial ? '<div class="banner warn" style="margin-top:10px">🏢 Esta respuesta menciona instancias presenciales o híbridas: revisá si te sirven antes de contestar.</div>' : ''}
    <hr>
    <pre class="cuerpo">${esc(m.texto || m.snippet || '(sin cuerpo)')}</pre>
    <div class="row" style="margin-top:12px">
      <button class="btn primary" data-act="resp-panel">✉ Responder…</button>
      <button class="btn" data-act="dec" data-dec="no_responder" data-id="${esc(id)}">✅ No requiere respuesta</button>
      <button class="btn danger" data-act="dec" data-dec="ignorado" data-id="${esc(id)}">🗑 Ignorar</button>
      <span class="muted" style="margin-left:auto">Decisión: <b>${esc(m.decision || 'pendiente')}</b></span>
    </div>
    <div id="panelRespuesta"></div>`;
}
function abrirPanelRespuesta() {
  $('panelRespuesta').innerHTML = `
    <hr>
    <h3>✉ Tu respuesta <span class="muted">(la revisás, la editás y la mandás vos — nada sale solo)</span></h3>
    <div class="row">
      <button class="btn ai" data-act="gen" data-modo="ia">✨ Redactar con IA</button>
      <button class="btn" data-act="gen" data-modo="local">📝 Redactor local</button>
      <span class="muted" id="respAviso"></span>
    </div>
    <textarea id="respBody" rows="10" style="margin-top:10px" placeholder="El borrador aparece acá — podés editarlo libremente"></textarea>
    <div class="row" style="margin-top:10px">
      <button class="btn primary" data-act="resp-gmail">📧 Abrir en Gmail web</button>
      <button class="btn" data-act="resp-mailto">✉ Cliente de correo</button>
      <button class="btn" data-act="resp-copy">📋 Copiar</button>
      <button class="btn" data-act="dec" data-dec="responder" data-id="${esc(SEL)}">↩ Marcar "a responder"</button>
    </div>`;
}
async function genRespuesta(modo) {
  $('respAviso').innerHTML = '<span class="spin"></span> redactando…';
  try {
    const r = await post('/api/redactar', {modo, tipo: 'respuesta', msg_id: SEL});
    $('respBody').value = r.borrador;
    $('respAviso').textContent = (r.motor === 'ia' ? '✨ IA (' + esc(AJ.ia_modelo || '') + ' → ' + esc(AJ.ia_host || '') + ')' : '📝 motor local') + (r.aviso ? ' — ' + r.aviso : '');
    await post('/api/decision', {id: SEL, decision: 'responder'});
  } catch (e) { $('respAviso').textContent = 'Error: ' + e.message; }
}

/* ---------- radar ---------- */
const TAGL = {
  virtual: ['📡 virtual / a distancia', 'b-reintento'], gratuita: ['🆓 gratuita', 'b-contesto'],
  publica: ['🏛 pública', 'b-contesto'], estatal: ['🏛 estatal', 'b-contesto'],
  privada: ['💰 privada', 'b-espera'], con_costo: ['💲 con costo', 'b-espera'],
  precio_detectado: ['💲 precios en la página', 'b-espera'], presencial: ['🏢 presencial', 'b-espera'],
  hibrida: ['🔀 híbrida', 'b-espera'], accesible: ['♿ accesibilidad', 'b-nuevo'],
  sin_clasificar: ['❓ sin clasificar', 'b-demo']};
function tagrow(tags, ev) {
  return (tags || []).map(t => {
    const L = TAGL[t]; if (!L) return '';
    const e = ev && ev[t];
    return `<span class="badge ${L[1]}" ${e ? `title="${esc(e)}"` : ''}>${L[0]}</span>`;
  }).join(' ') + (ev && Object.keys(ev).length ? `<div class="ev">evidencia: ${esc(Object.values(ev)[0] || '')}</div>` : '');
}
async function loadRadar() {
  try { RADAR = await api('/api/radar'); } catch (e) { return; }
  const st = RADAR.status || {};
  const viva = st.corriendo && Date.now() / 1000 - (st.ts || 0) < 180;
  $('radarStatus').innerHTML = viva ? '<span class="spin"></span> ' + esc(st.mensaje || 'buscando…') : (st.mensaje ? esc(st.mensaje) : 'sin búsquedas todavía');
  $('radarMeta').textContent = RADAR.actualizado_en ? ('actualizado ' + fHace(RADAR.actualizado_en)) : '';
  $('radarErrores').innerHTML = (RADAR.errores || []).length ?
    '<div class="banner warn">⚠ Errores de la última búsqueda:<br>' + RADAR.errores.map(e => '· ' + esc(e)).join('<br>') + '</div>' : '';
  const badge = e => e === 'NUEVO' ? '<span class="badge b-nuevo">🆕 NUEVO</span>' : e === 'REINTENTAR' ? '<span class="badge b-reintento">🔁 REINTENTAR</span>' : '<span class="badge b-espera">⏳ CONTACTADO &lt;30d</span>';
  $('radarList').innerHTML = (RADAR.resultados || []).map((r, i) => `
    <div class="card">
      <div class="row"><span class="t">${esc(r.titulo || r.url)}</span>${badge(r.estado_contacto)}</div>
      <div class="row" style="margin:6px 0 0">${tagrow(r.tags_pagina || r.tags, r.evidencia)}${r.relacionado ? `<span class="muted">· ya escribiste a otra unidad: ${esc(r.relacionado)}</span>` : ''}</div>
      <div class="muted" style="margin-top:2px">${esc(r.dominio)} · <a href="${esc(r.url)}" target="_blank" rel="noopener">abrir fuente ↗</a> · ${r.origen_tag === 'pagina' ? 'verificado contra la página' : 'según snippet'}</div>
      <div class="sn">${esc(r.snippet || '')}</div>
      <div class="row">
        <button class="btn sm primary" data-act="cons" data-i="${i}">✉ Escribir consulta</button>
        <button class="btn sm danger" data-act="radar-descartar" data-i="${i}">🗑 Descartar</button>
      </div>
    </div>`).join('') || '<p class="muted">Todavía no hay resultados. Tocá "Buscar programas ahora" (corre en el servidor, ~1 min).</p>';
}

/* ---------- modal borrador ---------- */
function abrirModal(ctx) {
  modalCtx = ctx;
  $('mdTitulo').textContent = ctx.tipo === 'consulta' ? '✉ Nueva consulta' : '✉ Seguimiento / reintento';
  $('mdTo').value = ctx.to || '';
  $('mdSubject').value = ctx.subject || '';
  $('mdBody').value = '';
  $('mdAviso').innerHTML = '<span class="spin"></span> redactando con motor local…';
  $('modalBg').classList.add('on');
  modalRedactar('local');
}
async function modalRedactar(modo) {
  $('mdAviso').innerHTML = '<span class="spin"></span> redactando…';
  try {
    const r = await post('/api/redactar', {modo, tipo: modalCtx.tipo || 'consulta',
      institucion: modalCtx.institucion, asunto: modalCtx.asunto, carrera: modalCtx.carrera});
    $('mdBody').value = r.borrador;
    $('mdAviso').textContent = (r.motor === 'ia' ? '✨ redactado con IA (' + (AJ.ia_host || '') + ')' : '📝 motor local') + (r.aviso ? ' — ' + r.aviso : '');
  } catch (e) { $('mdAviso').textContent = 'Error: ' + e.message; }
}

/* ---------- ajustes ---------- */
async function loadAjustes() {
  try {
    AJ = await api('/api/ajustes');
    $('iaBase').value = AJ.ia_base_url || ''; $('iaModelo').value = AJ.ia_modelo || '';
    $('iaKey').value = ''; $('iaKey').placeholder = AJ.ia_api_key_set ? '•••••••• (ya cargada — escribí una nueva para reemplazar)' : 'sk-… (opcional)';
    $('iaEstado').textContent = AJ.ia_base_url ? ('activa → ' + (AJ.ia_host || '')) : 'desactivada (motor local)';
    $('iaEstado').className = 'badge ' + (AJ.ia_base_url ? 'b-nuevo' : 'b-demo');
    $('iaHost').textContent = AJ.ia_base_url ? ('El contenido de los mensajes elegidos viajaría a: ' + (AJ.ia_host || '')) : 'Sin proveedor: todo se redacta en tu equipo.';
    $('pfFirma').value = AJ.nombre_firma || ''; $('pfPila').value = AJ.nombre_pila || '';
    $('pfContexto').value = AJ.contexto_personal || '';
    $('pfAcces').checked = !!AJ.mencionar_accesibilidad;
    $('pfAccesTxt').value = AJ.texto_accesibilidad || '';
    $('pfOAuth').value = AJ.oauth_modo || 'pruebas';
    $('radQueries').value = (AJ.radar_queries || []).join('\n');
    renderGmailCfg();
  } catch (e) { toast('Error cargando ajustes: ' + e.message); }
}
function renderGmailCfg() {
  const g = ESTADO.gmail || {};
  $('ajGmailState').textContent = g.conectado ? ('CONECTADO · ' + (g.cuenta || '')) : (g.client_presente ? 'CLIENT OK · falta autorizar' : 'NO conectado');
  $('ajGmailState').className = 'badge ' + (g.conectado ? 'b-contesto' : g.client_presente ? 'b-espera' : 'b-demo');
  let h = '';
  if (!g.client_presente) {
    h += `<p>Dos formas de cargar las credenciales de Google Cloud:</p>
    <ol class="ol">
      <li>Pegá acá el contenido completo de tu archivo <code>client_secret.json</code>, o</li>
      <li>pegá solo las dos líneas <code>client_id</code> y <code>client_secret</code>.</li>
    </ol>
    <label>client_secret.json completo (opcional)</label>
    <textarea id="csJson" rows="4" placeholder='{"installed": {"client_id": …}}'></textarea>
    <label>client_id</label><input id="csId" placeholder="1234567890-….apps.googleusercontent.com">
    <label>client_secret</label><input id="csSecret" type="password" placeholder="GOCSPX-…">
    <div class="row" style="margin-top:10px"><button class="btn primary" data-act="cs-guardar">💾 Guardar credenciales</button></div>`;
  } else {
    h += `<ol class="ol">
      <li>Generá el link de autorización y abrilo en tu navegador (logueate con tu cuenta de Gmail).</li>
      <li>Aceptá la pantalla "Google no ha verificado esta app" → <b>Configuración avanzada → Ir a Radar Matemáticas (no seguro)</b> → Permitir.</li>
      <li>El navegador va a ir a <code>localhost:8642</code> y <b>no va a cargar: es normal</b>. Copiá TODA la URL de la barra de direcciones y pegala acá (el código vence en ~10 min).</li>
    </ol>
    <div class="row"><button class="btn primary" data-act="auth-url">🔗 1. Generar link de autorización</button></div>
    <div id="authUrlBox" style="margin-top:10px"></div>
    <label>2. Pegá la URL de localhost:8642 (o el código)</label>
    <div class="row"><input id="exUrl" placeholder="http://localhost:8642/?code=4/0A…"><button class="btn ai" data-act="exchange" style="white-space:nowrap">🔑 3. Canjear</button></div>`;
  }
  h += `<hr><div class="row">
    <button class="btn" data-act="sync" ${g.conectado ? '' : 'disabled style="opacity:.4"'}>🔄 Sincronizar mis Enviados ahora</button>
    <span class="muted" id="syncMsg"></span></div>
    <p class="muted" style="margin-top:8px">La sincronización lee cabeceras de tus Enviados y arma el filtro "ya les escribiste" (regla de 30 días). ${g.oauth_modo === 'pruebas' ? 'Con la app de Google en modo Pruebas, el token se corta cada 7 días: el tablero avisa y reautorizar lleva 30 segundos.' : 'Modo Producción activo: sin vencimiento semanal.'}</p>`;
  $('ajGmailBody').innerHTML = h;
}
let LAST_AUTH_URL = '';
async function genAuthUrl() {
  try {
    const r = await post('/api/gmail/auth-url', {});
    LAST_AUTH_URL = r.url || '';
    $('authUrlBox').innerHTML = `<div class="banner info">Abrí este link en tu navegador:<br>
      <code style="display:block;margin-top:6px;word-break:break-all">${esc(LAST_AUTH_URL)}</code>
      <button class="btn sm" style="margin-top:8px" data-act="copy-auth">📋 Copiar link</button></div>`;
  } catch (e) { toast('Error: ' + e.message); }
}
async function guardarAjustes() {
  const b = {
    ia_base_url: $('iaBase').value.trim(), ia_modelo: $('iaModelo').value.trim(),
    nombre_firma: $('pfFirma').value, nombre_pila: $('pfPila').value,
    contexto_personal: $('pfContexto').value,
    mencionar_accesibilidad: $('pfAcces').checked,
    texto_accesibilidad: $('pfAccesTxt').value,
    oauth_modo: $('pfOAuth').value,
    radar_queries: $('radQueries').value.split('\n').map(s => s.trim()).filter(Boolean),
  };
  const k = $('iaKey').value.trim(); if (k) b.ia_api_key = k;
  try {
    const r = await post('/api/ajustes', b);
    toast('Ajustes guardados ✓' + (r.ia_host ? ' · IA → ' + r.ia_host : ''));
    loadAjustes();
  } catch (e) { toast('Error: ' + e.message); }
}

/* ---------- listener delegado único ---------- */
document.addEventListener('click', async e => {
  const b = e.target.closest('[data-act]'); if (!b) return;
  const act = b.dataset.act, i = +b.dataset.i, id = b.dataset.id;
  try {
    if (act === 'msg') abrirMensaje(id);
    else if (act === 'ban-refresh') loadBandeja(true);
    else if (act === 'resp-panel') abrirPanelRespuesta();
    else if (act === 'gen') genRespuesta(b.dataset.modo);
    else if (act === 'dec') { await post('/api/decision', {id, decision: b.dataset.dec}); toast('Decisión guardada: ' + b.dataset.dec); loadBandeja(); }
    else if (act === 'resp-gmail') { const m = BAN.mensajes.find(x => x.id === SEL) || {}; abrirGmailWeb(m.from || '', (m.subject || '').startsWith('Re:') ? m.subject : 'Re: ' + (m.subject || ''), $('respBody').value); }
    else if (act === 'resp-mailto') { const m = BAN.mensajes.find(x => x.id === SEL) || {}; abrirMailto(m.from || '', (m.subject || '').startsWith('Re:') ? m.subject : 'Re: ' + (m.subject || ''), $('respBody').value); }
    else if (act === 'resp-copy') copiarTexto($('respBody').value);
    else if (act === 'seg') { const f = CAMP.filas[i]; abrirModal({tipo: 'seguimiento', institucion: f.nombre || f.dominio, asunto: (CAMP.filas[i].carrera || ''), carrera: f.carrera || '', to: (f.emails || [])[0] || '', subject: 'Re: ' + (f.carrera || 'mi consulta anterior')}); }
    else if (act === 'mark') { const f = CAMP.filas[i]; const nv = !f.respuesta_humana; if (confirm('¿Marcar ' + f.dominio + ' como ' + (nv ? 'CON respuesta humana' : 'SIN respuesta humana') + '?')) { await post('/api/campana/mark', {dominio: f.dominio, respuesta_humana: nv}); loadCampana(); } }
    else if (act === 'cons') { const r = RADAR.resultados[i]; abrirModal({tipo: 'consulta', institucion: r.dominio, carrera: r.titulo, to: '', subject: 'Consulta: ' + (r.titulo || '')}); }
    else if (act === 'radar-descartar') { const r = RADAR.resultados[i]; await post('/api/radar/descartar', {url: r.url, descartar: true}); toast('Descartado'); loadRadar(); }
    else if (act === 'radar-buscar') { const r = await post('/api/radar/buscar', {}); toast(r.aviso || 'Búsqueda lanzada 🛰'); loadRadar(); }
    else if (act === 'reauth') { document.querySelector('nav button[data-tab=ajustes]').click(); genAuthUrl(); }
    else if (act === 'cs-guardar') { const j = ($('csJson') || {}).value; if (j && j.trim()) await post('/api/gmail/client', {json: j}); else await post('/api/gmail/client', {client_id: $('csId').value, client_secret: $('csSecret').value}); toast('Credenciales guardadas ✓'); pollEstado(); setTimeout(loadAjustes, 400); }
    else if (act === 'auth-url') genAuthUrl();
    else if (act === 'copy-auth') copiarTexto(LAST_AUTH_URL);
    else if (act === 'exchange') { const r = await post('/api/gmail/exchange', {url_o_codigo: $('exUrl').value}); toast('✅ Conectado: ' + (r.cuenta || 'cuenta verificada') + ' — sincronizando Enviados…'); pollEstado(); loadAjustes(); loadCampana(); }
    else if (act === 'sync') { const r = await post('/api/gmail/sync', {}); toast(r.aviso || 'Sincronización lanzada — mirá el estado arriba'); pollEstado(); }
    else if (act === 'ajustes-guardar') guardarAjustes();
    else if (act === 'ia-probar') { $('iaTest').innerHTML = '<span class="spin"></span> probando…'; const r = await post('/api/ia/probar', {}); $('iaTest').innerHTML = r.motor === 'ia' ? `✅ IA respondió en ${r.segundos}s` : `⚠ ${esc(r.aviso || '')}`; }
    else if (act === 'md-ia') modalRedactar('ia');
    else if (act === 'md-local') modalRedactar('local');
    else if (act === 'md-gmail') { if (!$('mdTo').value.trim()) { toast('Falta el destinatario: pegalo en "Para" 📮'); return; } abrirGmailWeb($('mdTo').value, $('mdSubject').value, $('mdBody').value); }
    else if (act === 'md-mailto') { if (!$('mdTo').value.trim()) { toast('Falta el destinatario: pegalo en "Para" 📮'); return; } abrirMailto($('mdTo').value, $('mdSubject').value, $('mdBody').value); }
    else if (act === 'md-copy') copiarTexto($('mdBody').value);
    else if (act === 'md-close') $('modalBg').classList.remove('on');
  } catch (err) { toast('Error: ' + err.message); }
});
$('modalBg').addEventListener('click', e => { if (e.target === $('modalBg')) $('modalBg').classList.remove('on'); });
$('banTodo').addEventListener('change', e => { banTodo = e.target.checked; loadBandeja(); });
$('iaPreset').addEventListener('change', e => {
  const v = e.target.value; if (!v) return;
  const [base, modelo] = v.split('|');
  $('iaBase').value = base; $('iaModelo').value = modelo;
});

/* ---------- init ---------- */
pollEstado(); loadCampana(); loadAjustes();
