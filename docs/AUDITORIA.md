# Auditoría de seguridad y privacidad

Documento pensado para revisión humana o por otra IA, sin necesidad de leer la
conversación de origen. Ante cualquier duda de comportamiento, el código es la
fuente de verdad; este doc enumera garantías verificables y limitaciones honestas.

## Modelo de amenazas (resumen)

| Actor / riesgo | Mitigación |
|---|---|
| Envío accidental o malicioso de correo en nombre del usuario | **Inexistente por diseño**: scope `gmail.readonly`; no hay llamada a `send`/SMTP en todo el repo (verificable con `grep -RniE "messages/send|smtplib" .`). La salida es `mailto:`/portapapeles, ejecutada por el humano. |
| Fuga de secretos por el repo | `.gitignore` excluye `client_secret.json`, `data/`, `uploads/`, `war_room.html`. Nunca se commitean tokens ni datos reales. |
| Fuga de secretos en disco del servidor | `client_secret.json`, `gmail_token.json`, `oauth_state.json`, `ajustes.json`, `contactados.json`, `decisiones.json` con `chmod 0600`. |
| API key de IA expuesta por la API | `/api/ajustes` devuelve `ia_api_key` enmascarada (`••••`) + flag `ia_api_key_set`; la clave solo viaja del servidor al endpoint LLM configurado por el usuario. |
| CSRF / control no autenticado del servidor | Doble capa desde v1.1.0: **token de sesión** por proceso (`X-Radar-Token`, inyectado en el HTML, exigido por toda la API salvo `/api/health`) + **validación de `Host`** contra allowlist (loopback siempre OK, `RADAR_ALLOWED_HOSTS` para previews). Sin token o con Host ajeno → 401/403. Además: POST exige `Content-Type: application/json` (415) y cuerpo ≤ 1 MB (413). |
| Confusión de pestañas en OAuth (ataque de state mixto) | `state` aleatorio validado en el canje; PKCE S256 evita interceptación del code. |
| Código de autorización pegado por otro canal | El canje valida `state` y expiración (~10 min, con aviso). |
| SSRF vía radar / vía configuración de IA | `radar.url_segura()` resuelve DNS y rechaza IPs privadas/loopback/link-local/reservadas (también en redirecciones, con handler propio). `ia_base_url` solo acepta `https://` o `http://localhost/127.0.0.1`; cambiar de host sin key nueva **limpia la key** (no viaja a un servidor distinto por error). |
| XSS por datos de correos/páginas en el dashboard y en `war_room.html` | Frontend con listener delegado único (sin handlers inline), campos de texto vía `esc()`; JSON embebido del snapshot escapado (`\u003c` → imposible cerrar el `<script>`). Lo verifica `tests/test_front_lint.py` y `tests/test_reporte.py`. |
| Datos personales en artefactos compartibles | `war_room.html` contiene datos reales del usuario (es SU archivo personal, gitignoreado). El repo publica solo esquemas con datos sintéticos en `docs/ejemplos/`. |
| Contenido de correos saliendo del sandbox | Solo si el usuario configura una API key de IA: entonces el contexto del mensaje elegido viaja al endpoint LLM que él configuró. Sin key, todo es local. Está documentado en la UI y aquí. |

## Garantías verificables (comandos)

```bash
grep -RniE "messages/send|smtplib|imaplib.*append" .        # → sin resultados: no envía
grep -Rn "gmail.readonly" .                                  # → scope único de lectura
grep -Rn "chmod" *.py util.py | grep 0o600                   # → permisos de secretos
git log --oneline -- data client_secret.json                 # → sin commits de secretos
python3 -m unittest discover -s tests                        # → 67 tests verdes
python3 scripts/check_privacidad.py                          # → nada sensible versionable
```

Nota: `X-Frame-Options: DENY` se omite a propósito (el preview del entorno de
desarrollo sirve el dashboard en iframe); el riesgo equivalente está cubierto
por token de sesión + validación de Host. Ver `docs/RESUMEN_AUDITORIAS.md`.

## Limitaciones honestas
1. **Token de 7 días**: Google Cloud en modo *Pruebas* revoca refresh tokens a los
   7 días. No es un defecto del código; el sistema lo detecta (401) y lo muestra
   como countdown. Reautorización manual asistida (~30 s).
2. **Scraping de DuckDuckGo**: sin API oficial; el parseo puede romperse si cambia
   el HTML. Fallos acotados y reportados (`data/radar_status.json`).
3. **Cuotas Gmail**: sincronización ritmada (~8 req/s) con backoff; cuentas con
   historiales enormes tardan más pero reanudan (caché JSONL).
4. **Servidor sin TLS**: auth propia sí tiene (token de sesión + Host allowlist),
   pero el tráfico es HTTP plano; pensado para localhost o el proxy del entorno
   de desarrollo. No exponer directamente a internet sin reverse proxy con TLS.
5. **Clasificación del radar heurística** (regex sobre título/snippet/dominio):
   las etiquetas 📡/🆓/💰/♿ son orientación, no verdad certificada; por eso los
   borradores siempre preguntan modalidad, costos y accesibilidad a la institución.

## Decisiones de privacidad adicionales
- La sincronización guarda solo cabeceras (To/Cc/Subject/Date) en caché local.
- Los cuerpos completos se descargan únicamente al abrir un mensaje en la bandeja.
- Dominios de ruido (redes sociales, bancos, newsletters) se filtran de la bandeja.
- El contexto personal y la firma que usa la IA son editables y viven solo locales.
