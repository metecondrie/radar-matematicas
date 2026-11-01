# Changelog

## [1.1.0] — 2026-11-01
Ronda "auditor de auditores": siete auditorías externas del repo público se
leyeron hallazgo por hallazgo; se aplicó lo correcto y se documentaron los
rechazos (`docs/RESUMEN_AUDITORIAS.md`). Reescritura completa del código base.

### Seguridad (servidor)
- Token de sesión por proceso (`X-Radar-Token` inyectado en el HTML); toda la
  API lo exige salvo `/api/health`. Sin token o token inválido → 401.
- Validación de `Host` (allowlist `RADAR_ALLOWED_HOSTS`, loopback siempre OK)
  contra DNS-rebinding → 403.
- `Content-Type: application/json` obligatorio en POST → 415; cuerpo limitado
  a 1 MB → 413; ids y tipos validados contra allowlist → 400.
- `ia_base_url` validada: solo `https://` o `http://localhost|127.0.0.1`
  (anti-SSRF/exfiltración de key); cambiar de host sin key nueva limpia la key.
- Cabeceras endurecidas (`X-Content-Type-Options`, `Referrer-Policy`,
  `Cache-Control: no-store` en API). `X-Frame-Options` se omite a propósito
  (el preview del entorno lo necesita; documentado en RESUMEN_AUDITORIAS).

### Correcciones de bugs confirmados por las auditorías
- `clasificador`: regex con `\b` y alternancias sin agrupar (falsos positivos);
  matching sin acentos ("Estadística" no tageaba); "app/plataforma virtual"
  ya no cuenta como modalidad virtual.
- `gmail_client`: el refresco de token conservaba `obtenido_en` viejo →
  vencimientos mal calculados; 5 hilos disparaban 5 refrescos → ahora 1 con
  lock y persistencia; `invalid_grant` → error de reautorización explícito;
  403 ya no reintenta.
- `util`: escrituras JSON atómicas (tmp + `os.replace`) con lock por archivo;
  `encoding='utf-8'` explícito en todo I/O; `leer_json` estricto distingue
  archivo corrupto de ausente; `estado_dominio` con UNA sola implementación,
  maneja variante `www.` y ancestros; `dominio_en` por sufijo, nunca substring.
- `generar_reporte`: JSON embebido en `<script>` escapado (`\u003c`…) → ningún
  asunto/snippet puede inyectar HTML en `war_room.html`.
- `radar`: guarda SSRF (`url_segura` resuelve DNS y rechaza privadas/loopback,
  también en redirecciones); CAPTCHA/anomaly de DuckDuckGo se reporta como
  error visible en la UI; caché 24 h; rate-limit entre consultas.
- `sync_enviados`: reanudable, `sync_cache.jsonl` con permisos 0600, ritmo
  ~8 req/s con backoff ante 429/403.

### Frontend (`static/app.js` nuevo)
- Un único listener delegado por `data-act`; sin handlers inline ni `.onclick`;
  campos de texto siempre vía `esc()` (lo verifica `tests/test_front_lint.py`).
- Polling único con flag anti-solapamiento e intervalo dinámico (3 s activo /
  30 s idle); sin `setInterval` por módulo.
- Modal de borrador con Gmail web / mailto / copiar; banda "✨ IA" vs motor
  local siempre visible; bandeja con decisión manual por correo.

### Calidad
- Suite de 67 tests (`tests/`, unittest stdlib): util, clasificador, OAuth,
  Gmail/token, radar (parseo, SSRF, dedupe), redactor (local/IA/fallback/PII),
  reporte (escape de inyección), servidor de seguridad (subproceso real:
  401/403/415/413), lint del frente, privacidad y versión.
- `scripts/check_privacidad.py`: guardia que bloquea commits con emails reales
  o secretos en archivos versionables (corre en CI y en `make check`).
- GitHub Actions (`.github/workflows/tests.yml`): Python 3.9/3.11/3.12,
  compilación, privacidad y tests en cada push.
- `Makefile` (check/test/server/reporte) y `VERSION` como fuente única
  (lo lee `app.py`).
- `seed.py` 100 % sintético y sin efectos al importar; `static_data/` con
  43 instituciones argentinas reales (solo nombres/dominios públicos).

## [1.0.0] — 2026-11-01
Primera versión pública del proyecto.

### Agregado
- OAuth 2.0 PKCE para cliente de escritorio sin librerías de Google
  (`oauth_setup.py`), scope único `gmail.readonly`.
- Cliente Gmail con refresco automático de token y lectura de cabeceras/cuerpos
  bajo demanda (`gmail_client.py`).
- Sincronización resumible de Enviados con detección de respuestas y regla de
  30 días → `data/contactados.json` (`sync_enviados.py`).
- Dashboard war-room servido por HTTP stdlib: campaña, bandeja con decisión
  manual (responder / no requiere / ignorar), radar y ajustes (`app.py`,
  `static/index.html`).
- Redactor de borradores con dos motores: LLM compatible OpenAI (Qwen/DashScope
  por defecto) y plantillas locales con caída automática (`ia_redactor.py`).
- Radar de programas vía DuckDuckGo HTML con criterios y etiquetas de distancia,
  economía y accesibilidad + score de prioridad (`radar.py`).
- Snapshot autocontenido `war_room.html` (descargar + doble click), regenerado
  automáticamente al finalizar sync y búsquedas (`generar_reporte.py`).
- Datos semilla de campaña previa y bandeja demo etiquetada (`seed.py`).
- Documentación: manual de usuario, arquitectura, auditoría, historia.

### Seguridad
- Sin envío automático de correo por diseño (mailto/copia ejecutados por el humano).
- Secretos y datos personales excluidos del repo (`.gitignore`), permisos 0600.
