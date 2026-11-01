# Resumen de auditorías externas — veredictos y destino de cada hallazgo

**Ronda:** "auditor de auditores" (2026-11-01, v1.0.0 → v1.1.0).
**Base auditada:** commit `e11f7c1` (rama `main`, repo público).
**Insumos:** siete reportes externos independientes, generados por otras IAs a
partir del repo público:

| # | Reporte | Enfoque predominante |
|---|---|---|
| 1 | `CAMBIOS_REQUERIDOS.md` | robustez/mantenibilidad, puntaje 7.4/10 |
| 2 | `REPORTE_ARREGLOS.md` | hallazgos reproducidos ejecutando el código ([P]) y leídos ([L]); incluye tabla de tests R3 |
| 3 | `deepseek_markdown_20261101_ee7333.md` | seguridad (SSRF, headers, OAuth) |
| 4 | `plan_de_correccion_radar_matematicas.md` | plan integral, puntaje 7.8/10 |
| 5 | `Nuevo documento de texto (3).txt` | revisión estática + dinámica línea por línea |
| 6 | `PROMPT-CORRECCION-RADAR.txt` | "de 4.8/10 a 9/10", orientación producción |
| 7 | `ai_studio_code.txt` | arquitectura de sistemas, seguridad |

**Método:** cada reporte se leyó completo y cada hallazgo se contrastó contra
el código real (y cuando hizo falta, se reprodujo ejecutándolo). Nada se
aplicó en bloque. Clasificación final: **ACEPTADO** (bug verdadero, corregido),
**YA-ESTABA** (el reporte describe algo que la base auditada ya resolvía),
**RECHAZADO** (incorrecto, o choca con requisitos del proyecto; motivo abajo).

---

## 1. ACEPTADO — bugs verdaderos, corregidos en v1.1.0

### Backend
| Hallazgo (reportes) | Corrección | Verificación |
|---|---|---|
| Regex del clasificador con `\b` y alternancias sin agrupar → falsos positivos/negativos (2, 4, 5) | `clasificador.py` reescrito con palabras completas y negaciones | `tests/test_clasificador.py` |
| "Estadística/Matemática" con acento no tageaba (2) | matching normaliza acentos (`_sin_acentos`) | `test_acentos_no_rompen_tags` |
| "La app … es virtual" contaba como modalidad virtual (2) | guarda de contexto app/plataforma/sistema/trámite | tabla R3 propia en tests |
| Refresh de token conservaba `obtenido_en` viejo → countdown de 7 días mal calculado (2, 5) | `obtenido_en` se actualiza en cada refresh | `tests/test_gmail_token.py` |
| Múltiples hilos podían disparar refresh simultáneos del mismo token (2, 7) | lock + instancia compartida: 5 hilos → 1 refresh | `test_un_solo_refresh_por_5_hilos` |
| `invalid_grant` no distinguía "token revocado" de error transitorio (2, 3) | `GmailAuthError` explícito → UI pide reautorizar | `test_invalid_grant` |
| HTTP 403 reintentado inútilmente (2) | 403 no reintenta; 429/5xx con backoff | `test_403_sin_reintento` |
| Escrituras JSON no atómicas → archivo corrupto si muere el proceso (1, 4, 5, 7) | `util.escribir_json`: tmp + `os.replace` + lock por archivo | `test_atomicidad_8_hilos`, `test_json_corrupto` |
| `open()` sin `encoding='utf-8'` (4, 5) | utf-8 explícito en todo el I/O | revisión + tests |
| Filtro de dominios de ruido por substring ("x.com" descartaba "fedex.com") (2, 5) | conjuntos de dominios COMPLETOS + `dominio_en` por sufijo | `test_dominio_en_sufijo` |
| `estado_contacto` duplicado y aplicado solo a resultados nuevos del radar (2, 4) | UNA implementación en `util`, usada por sync/radar/app/reporte; ancestro/descendiente/variante `www.` | `test_estado_dominio_*` |
| `/api/estado` llamaba a `Gmail().perfil()` (red) en cada poll del frontend (2, 5) | `oauth_setup.estado()` es solo disco; verificación de red únicamente con `?verificar=1` | código + smoke |
| `sync_cache.jsonl` sin permisos 0600 (5) | `escribir_json(..., privado=True)` | inspección |
| CAPTCHA/anomaly/202/403 de DuckDuckGo silenciados como "0 resultados" (4, 5) | error explícito visible en UI (`radar_status.errores`) | `test_captcha_detectado` |
| `radar` fetch de páginas sin protección SSRF (3, 7) | `url_segura()` (DNS → descarta privadas/loopback/link-local/reservadas) + redirect handler propio | `test_radar.TestSSRF` |
| JSON embebido en `war_room.html` sin escapar → un asunto con `</script>` inyectaba HTML (3, 5, 7) | `\u003c \u003e \u0026 \u2028 \u2029` en `texto_a_html_seguro_json` | `test_generar_escapa_inyeccion` |
| seed con datos reales transcriptos del chat (1, 5) | `seed.py` 100 % sintético, sin side-effects al importar | `check_privacidad.py` |

### Servidor / API (consenso de los reportes 3, 4, 5, 6, 7)
| Hallazgo | Corrección | Verificación |
|---|---|---|
| API sin autenticación: cualquier proceso/pestaña local podía leer la bandeja | token de sesión por proceso (`X-Radar-Token`), 401 sin él | `test_server_security` |
| Sin validación de `Host` (DNS-rebinding) | allowlist `RADAR_ALLOWED_HOSTS` + loopback; 403 host ajeno | ídem |
| POST aceptaba cualquier Content-Type | 415 si no es `application/json` | ídem |
| Sin límite de tamaño de cuerpo | 413 sobre 1 MB | ídem (socket crudo) |
| `id`/`tipo`/`decision` sin validar (path traversal hacia archivos del server) | allowlists + `ID_RE`; 400 | ídem |
| `ia_base_url` libre → SSRF/exfiltración de key a cualquier host | solo `https://` o `http://localhost/127.0.0.1`; cambio de host sin key nueva limpia la key | `test_redactor.TestValidacionAjustes` |
| Sin headers de seguridad | `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Cache-Control: no-store` en API (frame-ancestors: ver Rechazados) | código |

### Frontend (1, 4, 5, 6)
| Hallazgo | Corrección |
|---|---|
| Handlers inline `onclick="…${datos}…"` → XSS si un dato traía comillas | `static/app.js` nuevo: listener delegado único por `data-act`, datos en memoria, nunca en atributos |
| Campos de texto interpolados sin escapar en varios puntos | `esc()` sistemático; lo verifica `tests/test_front_lint.py` en CI |
| Múltiples `setInterval` solapables (polls que se pisan) | polling único con flag `_busy` + intervalo dinámico 3 s/30 s |
| `fetch` sin token/errores mudos | wrapper `api()/post()` con token y toast de error |

### Bug encontrado por nuestros propios tests (no reportado por las auditorías)
- `kpis()` hacía `rad['resultados']` → **500** si `radar.json` existía vacío
  (`{}`). Corregido con `.get('resultados', [])`; cubierto por
  `test_sin_datos_no_rompe` + `test_server_security`.

---

## 2. YA-ESTABA — el reporte señala algo que la base ya resolvía

- "No hay reintentos con backoff ante 429/403 de Gmail" (6): la base ya tenía
  backoff de 30 s; se mejoró el límite de reintentos, pero no estaba ausente.
- "El redirect `localhost:8642` no puede funcionar porque el cliente registra
  `http://localhost`" (6): funciona — los clientes *installed* de Google
  aceptan loopback con puerto explícito (verificado empíricamente en vivo).
- "Los secretos podrían filtrarse al repo" (varios): `.gitignore` ya excluía
  `data/`, `client_secret.json`, `war_room.html`; se agregó además
  `scripts/check_privacidad.py` como guardia activa (mejora aceptada).
- "Falta fallback sin IA" (6): el motor local de plantillas ya existía desde
  v1.0.0; la ronda lo hizo motor por defecto (IA pasó a opt-in, ver abajo).

## 3. RECHAZADO — con motivo

| Sugerencia (reporte) | Veredicto y motivo |
|---|---|
| Agregar dependencias `filelock`, `requests` (1, 4, 6) | **Rechazado.** El principio fundacional es stdlib puro (Python 3.9+ sin pip): sobrevive reinicios de sandbox y es auditable línea por línea. La atomicidad/locks se implementaron a mano (`util.escribir_json`) y el HTTP con `urllib`; los tests prueban que funcionan bajo concurrencia real (8 hilos). |
| Cambiar `redirect_uri` a `http://localhost:8642/callback` (6) | **Rechazado: es incorrecto.** El cliente de Google del proyecto registra `http://localhost` (sin path); el flujo *installed* acepta variación de puerto, y el flujo real ya canjeó códigos con `http://localhost:8642/?code=…`. Agregar un path distinto del registrado rompe el canje. |
| Allowlist duro de dominios LLM permitidos (3) | **Rechazado.** Impondría un catálogo fijo y rompería el caso "Ollama local"/proveedores futuros. Mitigación equivalente adoptada: solo `https` o loopback, host visible en la UI, PII enmascarada antes de viajar, y la key se limpia al cambiar de host. |
| `X-Frame-Options: DENY` / CSP `frame-ancestors 'none'` (3, 5, 7) | **Rechazado en este entorno.** El dashboard se sirve en un iframe del preview de desarrollo; DENY lo rompe. El riesgo real (que un sitio de terceros consuma la API) está cubierto por token de sesión + validación de Host. Decisión documentada, no omisión. |
| mypy estricto en CI (1, 4) | **Diferido** (no rechazado de fondo): CI corre en 3 versiones de Python con stdlib puro; se prefirió invertir el presupuesto en 67 tests de comportamiento. Los tipos pueden sumarse incrementalmente. |
| Default `mencionar_accesibilidad=False` "para no revelar discapacidad" (5) | **Desviación consciente.** El requisito del usuario es consultar ajustes razonables como **pregunta institucional** ("¿con quién puedo conversar sobre procedimientos de accesibilidad?"), sin datos de salud; el texto es configurable y el flag existe. Queda en `True` por defecto por decisión del dueño del proyecto. |
| Calificación "4.8/10" del repo (6) | **No es un hallazgo, pero consta:** inconsistente con las otras seis auditorías (7.4–7.8) y con el estado real de la base; varios de sus "críticos" eran los YA-ESTABA de arriba. Sus puntos válidos (headers, límite de cuerpo) igualmente se aplicaron. |
| Contradicción interna de la tabla R3 (2) | La fila "Tecnicatura Universitaria en Estadística" exige `tags == ['nueva']` (sin tagear estadística) mientras la fila "Especialización en Estadística" exige tagear `estadistica`. Son mutuamente excluyentes bajo cualquier implementación. **Resolución:** semántica correcta (ambas son carreras de estadística → se tagean), con matching sin acentos. Documentado en `tests/test_clasificador.py`. |

---

## 4. Resultado

- Reescritura completa del código base con las correcciones aceptadas.
- 67 tests automatizados (`python3 -m unittest discover -s tests`), incluidos
  tests de seguridad contra servidor real en subproceso y lint del frente.
- CI en GitHub Actions (Python 3.9/3.11/3.12): compilación + privacidad + tests.
- `make check` reproduce localmente lo que corre en CI.

Los reportes completos recibidos no se versionan (son insumo de una ronda, y
algunos citan datos del entorno privado del usuario); este resumen es la pieza
auditable que queda en el repo.
