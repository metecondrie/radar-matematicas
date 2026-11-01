# Arquitectura

## Principios de diseño
1. **Stdlib puro** (Python 3.9+): cero dependencias → sobrevive reinicios de
   sandbox, auditable línea por línea, instalable en cualquier lado.
2. **Nunca enviar correo**: no existe código que invoque `messages.send` ni SMTP.
   La salida hacia el mundo es siempre `mailto:` o texto copiado por el usuario.
3. **Lectura mínima**: solo cabeceras (`format=metadata`) para el mapeo de campaña;
   cuerpos completos solo bajo demanda explícita del usuario en la bandeja.
4. **Estado en archivos JSON** en `data/` (permisos 0600 para lo sensible):
   simple de inspeccionar, sin base de datos.
5. **Resumibilidad y cuota**: caché JSONL de sincronización + ritmo de ~8 req/s +
   backoff exponencial ante 429/403 (cuota por minuto de Gmail).

## Módulos

```
app.py            ThreadingHTTPServer + router manual. Sirve static/index.html y
                  la API JSON protegida por token de sesión (ver Seguridad).
                  Lanza sync/radar en hilos (subproceso para sync). Único pool
                  de hilos del proyecto: 4 workers para metadata de bandeja.
gmail_client.py   Clase Gmail: refresh automático de access_token (refresh_token
                  guardado), perfil, listado con paginación, metadata por id,
                  cuerpo texto (walk de partes MIME, base64url).
oauth_setup.py    PKCE S256 + state. guardar_client() reconstruye client_secret.json
                  desde client_id+secret (plan C). intercambiar() valida state y
                  canjea código; escribe gmail_token.json (0600).
sync_enviados.py  Enviados → contactados.json. Caché sync_cache.jsonl (reanuda).
                  Detección de respuestas: 1 query barata por dominio (from:dominio,
                  maxResults=1). Al terminar regenera war_room.html.
radar.py          DuckDuckGo HTML (sin API key): parseo regex de result__a/snippet.
                  Etiquetado por criterios: virtual / pública / privada / accesible,
                  score de prioridad, dedupe por URL, regla 30 días vs contactados.
ia_redactor.py    redactar(tipo, contexto, modo): 'ia' → POST /chat/completions
                  (cualquier API compatible OpenAI: Qwen/DashScope, OpenAI,
                  Groq, OpenRouter, Ollama local). OPT-IN: desactivada hasta que
                  el usuario carga base_url+key en Ajustes (validadas: solo
                  https o http://localhost). 'local' → plantillas propias
                  (consulta/respuesta/seguimiento), siempre disponibles.
                  Caída automática ia→local con aviso visible. PII enmascarada
                  antes de viajar al proveedor.
generar_reporte.py  Snapshot war_room.html: datos embebidos como const JSON +
                  CSS/JS inline (funciona sin red: preview sandboxed, doble click).
seed.py           Datos semilla (campaña previa transcripta) + bandeja DEMO marcada.
```

## API HTTP (puerto 8643)

| Método | Ruta | Efecto |
|---|---|---|
| GET | `/` | dashboard (HTML lleva inyectado el token de sesión) |
| GET | `/api/health` | único endpoint exento de token (liveness) |
| GET | `/api/estado` | Gmail/token/sync/radar + KPIs |
| GET | `/api/campana` | filas de campaña con estado (CONTESTO/EN_ESPERA/REINTENTAR) |
| GET | `/api/bandeja?force=1` | recibidos no-ruido (caché 10 min) o DEMO |
| GET | `/api/mensaje?id=` | cuerpo completo bajo demanda (id validado contra allowlist) |
| POST | `/api/decision` | guarda decisión por mensaje {pendiente,responder,no_responder,ignorado} |
| POST | `/api/campana/mark` | marca/desmarca respuesta humana en un dominio |
| POST | `/api/redactar` | borrador {modo: ia|local, tipo, msg_id o contexto} |
| GET/POST | `/api/radar`, `/api/radar/buscar` | resultados / lanza búsqueda en hilo |
| POST | `/api/radar/descartar` | oculta un resultado del radar |
| GET/POST | `/api/ajustes` | firma, contexto, config IA (la key nunca se devuelve) |
| POST | `/api/gmail/client` | guarda credenciales (valida sufijo .apps.googleusercontent.com) |
| POST | `/api/gmail/auth-url` | genera link PKCE + oauth_state.json |
| POST | `/api/gmail/exchange` | canjea código → token; dispara sync |
| POST | `/api/gmail/sync` | lanza sync_enviados.py en subproceso |
| POST | `/api/ia/probar` | smoke test del endpoint LLM |

## Esquemas de datos (ver `docs/ejemplos/` con datos sintéticos)

- `contactados.json`: `{sincronizado_en, cuenta, total_enviados_leidos, dominios: {dominio: {dominio, nombre?, carrera?, emails[], primer_contacto, ultimo_contacto, n_mails, asuntos[], respondido}}}`
- `radar.json`: `{actualizado_en, queries[], resultados[]: {url, titulo, snippet, query, dominio, tags[], score, estado_contacto, dominio_contactado, visto_en}}`
- `decisiones.json`: `{message_id: {decision, fecha, nota}}`
- `ajustes.json`: `{nombre_firma, contexto_personal, ia_base_url, ia_api_key, ia_modelo}`
- `gmail_token.json`: respuesta de token Google + `obtenido_en` + `autorizado_en` (para el conteo de 7 días del modo Pruebas).

## Flujo OAuth (cliente instalado, sin librerías)
1. `oauth_setup.generar_auth_url()`: verifier/challenge S256, state aleatorio,
   `redirect_uri=http://localhost:8642`, scope `gmail.readonly`, `prompt=consent`.
2. El usuario pega la URL del redirect (página que no carga): se extrae `code`,
   se valida `state`, se canjea con `code_verifier` + client_secret.
3. `refresh_token` persistido; `gmail_client` refresca access 120 s antes de expirar.
   Nota: el cliente de Google Cloud registra `http://localhost`; los clientes
   *installed* aceptan redirect loopback con puerto explícito (por eso 8642 funciona).

## Seguridad del servidor (v1.1.0)

- **Token de sesión**: cada proceso genera `secrets.token_urlsafe(32)`; se
  inyecta en el HTML (`<meta name="radar-token">`) y el frontend lo envía en
  cada request (`X-Radar-Token`). Todo `/api/*` lo exige salvo `/api/health`.
- **Host allowlist**: `RADAR_ALLOWED_HOSTS` (coma-separado, `*` habilita todo
  para entornos preview). Loopback siempre permitido. Host ajeno → 403.
- **Entrada hostil**: POST sin `Content-Type: application/json` → 415; cuerpo
  > 1 MB → 413; `id`/`tipo`/`decision` fuera de allowlist → 400; ids de Gmail
  validados con `ID_RE` (hex 8-32) antes de tocar la red.
- **SSRF**: `radar.url_segura()` resuelve DNS y rechaza IPs
  privadas/loopback/link-local/reservadas, también en redirecciones
  (handler propio). `ia_base_url` solo acepta `https://` o `http://localhost`.
- **XSS**: frontend sin handlers inline (listener delegado único por
  `data-act`), campos de texto siempre vía `esc()`; el JSON embebido en
  `war_room.html` se escapa (`\u003c`) — nada puede cerrar el `<script>`.
  Lo verifica `tests/test_front_lint.py` en CI.
- **Decisión documentada**: no se envía `X-Frame-Options: DENY` porque el
  preview del entorno de desarrollo sirve el dashboard en un iframe; la
  protección real (token + host) cubre el riesgo de clickjacking de la API.
  Ver `docs/RESUMEN_AUDITORIAS.md`.

## Tests y calidad

- `python3 -m unittest discover -s tests` (67 tests, stdlib puro): util,
  clasificador, OAuth, Gmail/refresh, radar (parseo/DDG-bloqueado/SSRF),
  redactor (local/IA/fallback/PII/validaciones), reporte (escape de
  inyección), servidor de seguridad levantado como subproceso real
  (401/403/415/413), lint del frente, privacidad, versión.
- `python3 scripts/check_privacidad.py`: bloquea emails reales/secretos en
  archivos versionables. `make check` corre compile + privacidad + tests.
- GitHub Actions (`.github/workflows/tests.yml`): Python 3.9 / 3.11 / 3.12.

## Fallos conocidos / decisiones defensivas
- `messages.batch` devolvía error incluso con 1 id en este proyecto → se usa
  `messages.get` por id, **secuencial y con ritmo acotado (~8 req/s)**; el
  único pool de hilos (4 workers) está en `app.py` para metadata de bandeja.
- Cuota por minuto Gmail: backoff 30 s ante 429/403, reintento hasta 6 veces.
- DuckDuckGo puede cambiar el HTML o rate-limitar: el parseo es defensivo y el
  fallo se reporta en `radar_status.json` sin romper el resto.
- El modo Pruebas de Google Cloud corta refresh tokens a los 7 días: el dashboard
  muestra countdown (`autorizado_en + 7d`) y avisa con ≤2 días.
