# 🎖 Radar Matemáticas

Bot personal de campaña de contacto a universidades argentinas + war-room visual.
Hecho a medida para Alejo: busca carreras de matemática / estadística / ciencia de
datos (priorizando **virtuales, públicas gratuitas y accesibles**), recuerda a qué
instituciones ya les escribió (regla de 30 días), lee las respuestas recibidas y
redacta borradores de correo — con IA o con un motor local de plantillas.

> **Regla de oro del sistema: NUNCA envía correos automáticamente.**
> Solo lee Gmail (`gmail.readonly`), propone borradores y abre `mailto:`.
> El envío lo hace siempre el humano, desde su propio cliente de correo.

## Qué hace

| Módulo | Función |
|---|---|
| `app.py` | Servidor HTTP (stdlib puro) del dashboard + API JSON, puerto 8643 |
| `static/index.html` | Dashboard war-room: campaña, bandeja con decisión manual, radar, ajustes |
| `gmail_client.py` | Cliente Gmail solo-lectura con refresco automático de token OAuth |
| `oauth_setup.py` | Flujo OAuth 2.0 PKCE para cliente de escritorio (sin librerías de Google) |
| `sync_enviados.py` | Enviados → `data/contactados.json`; detecta qué dominios respondieron |
| `radar.py` | Búsqueda web (DuckDuckGo HTML) con criterios de distancia/economía/accesibilidad |
| `ia_redactor.py` | Borradores: LLM compatible OpenAI (Qwen por defecto) + motor local de respaldo |
| `generar_reporte.py` | Genera `war_room.html`: snapshot autocontenido (descargar + doble click) |
| `seed.py` | Datos semilla de arranque (campaña previa) y bandeja demo |

## Arranque rápido

```bash
python3 app.py          # sin dependencias externas: Python 3.9+ stdlib
# → dashboard en http://localhost:8643
```

Conexión de Gmail (2 min): pegar `client_id`/`client_secret` en
*Ajustes → Conexión Gmail* (o adjuntar el `client_secret.json`), generar el link de
autorización, aceptar en el navegador y pegar de vuelta la URL de `localhost:8642`.
Detalle paso a paso en [`docs/MANUAL_USUARIO.md`](docs/MANUAL_USUARIO.md).

## Modo "descargar y doble click"

`war_room.html` es una **foto autocontenida del tablero** (datos embebidos, sin
servidor ni internet). Se regenera sola al terminar cada sincronización o búsqueda
del radar. Descargala del workspace y abrila con doble click en cualquier PC.

## Seguridad y privacidad (resumen)

- Scope OAuth único: `https://www.googleapis.com/auth/gmail.readonly`.
- API protegida con **token de sesión** (`X-Radar-Token`, generado en cada
  arranque e inyectado en el HTML) + validación de `Host` + límite de cuerpo
  (1 MB) + `Content-Type` obligatorio en POST.
- Anti-SSRF en las dos salidas a la red: el radar valida IPs resueltas por DNS
  (incluidas redirecciones) y la `ia_base_url` solo acepta `https://` o
  `http://localhost`.
- Este repo **no contiene ni contendrá secretos ni datos personales**:
  `data/`, `client_secret.json` y `war_room.html` están gitignoreados, y
  `scripts/check_privacidad.py` bloquea en CI cualquier email real o secreto
  que intente entrar. En `docs/ejemplos/` hay datos sintéticos para inspeccionar
  los esquemas.
- Tokens y ajustes con permisos `0600`; la IA es **opt-in** (motor local por
  defecto); la API key vive solo en `data/ajustes.json` local, se enmascara la
  PII antes de viajar y la key se limpia si cambiás de proveedor.
- Sin envíos automáticos: no existe ninguna ruta de código que llame a `send`.
- Auditoría interna: [`docs/AUDITORIA.md`](docs/AUDITORIA.md) · veredictos de
  siete auditorías externas: [`docs/RESUMEN_AUDITORIAS.md`](docs/RESUMEN_AUDITORIAS.md).

## Tests y calidad

```bash
make check    # compilación + guardia de privacidad + 67 tests (o sin make:)
python3 -m unittest discover -s tests
python3 scripts/check_privacidad.py
```

CI en GitHub Actions (`.github/workflows/tests.yml`) con Python 3.9/3.11/3.12:
compilación, privacidad y toda la suite — incluidos tests de seguridad contra
servidor real en subproceso (401/403/415/413) y lint del frente (sin handlers
inline, campos de texto siempre escapados).

## Documentación

- [`docs/MANUAL_USUARIO.md`](docs/MANUAL_USUARIO.md) — guía en criollo para Alejo
- [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md) — módulos, flujos, API, seguridad, esquemas de datos
- [`docs/AUDITORIA.md`](docs/AUDITORIA.md) — modelo de amenazas y garantías, para IAs auditoras
- [`docs/RESUMEN_AUDITORIAS.md`](docs/RESUMEN_AUDITORIAS.md) — siete auditorías externas: qué se aceptó, qué se rechazó y por qué
- [`docs/HISTORIA.md`](docs/HISTORIA.md) — cronología de decisiones (contexto sin leer el chat)
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — cómo correr tests y reglas del código
- [`CHANGELOG.md`](CHANGELOG.md)

## Licencia

MIT — ver [`LICENSE`](LICENSE). © 2026 Alejo Omentari Ongaro.
