# Historia y cronología de decisiones

Contexto completo del proyecto para quien llegue después (humano o IA) sin leer la
conversación original. El usuario es Alejo (Argentina); su cuenta de correo no se publica por privacidad.

## El problema real
Alejo escribe mails a universidades argentinas consultando por carreras de
matemática, estadística y ciencia de datos (tecnicaturas, profesorados,
licenciaturas), con tres criterios personales: **modalidad a distancia/virtual**,
**costo (prefiere públicas gratuitas)** y **accesibilidad / ajustes razonables por
discapacidad**. Necesitaba: (a) no volver a escribirle a quien ya contactó hace
menos de 30 días, (b) ver de un vistazo quién contestó, (c) decidir él mismo qué
responder (nunca envío automático: "puede ser catastrófico"), (d) borradores
asistidos por IA opcionales, (e) un tablero tipo war-room.

## Cronología
1. **Chat previo (exportado)**: se definió la campaña, la regla de 30 días, el
   filtro por Enviados y el plan OAuth de escritorio (redirect `localhost:8642`).
   El export trajo la conversación, no el código.
2. **Reconstrucción en workspace nuevo**: se rehízo el bot desde cero. El OAuth se
   completó por chat: el usuario pegó la URL del redirect con el `code`; canje con
   PKCE exitoso; cuenta verificada (privada).
3. **Lección de persistencia**: en un reinicio de sandbox se perdieron archivos
   porque vivían fuera del workspace persistido. Regla adoptada: todo el proyecto
   vive en el workspace; secretos con 0600; lo importante se regenera
   (`war_room.html`) o se reanuda (caché JSONL).
4. **Gmail API — descubrimientos técnicos**: `messages.batch` fallaba incluso con
   un solo id → se migró a `messages.get` por id, secuencial y con ritmo acotado
   (el único pool de hilos del proyecto, 4 workers, vive en el dashboard para la
   metadata de bandeja); cuotas por minuto (429/403) → ritmo ~8 req/s + backoff
   30 s; sincronización de 1.305 Enviados reanurable.
5. **Requisitos de UI del usuario**: war-room HTML, bandeja con decisión manual
   (responder/no/ignorar), botón "aplicar inteligencia artificial" editable y
   siempre con fallback local, y que el envío sea humano (mailto/copia).
6. **Radar con criterios**: primera versión buscaba solo distancia/accesibilidad;
   tras pregunta del usuario se agregaron economía (pública/gratuita/becas) y
   etiquetas visibles + score de prioridad (virtuales públicas primero, privadas
   al fondo).
7. **Modo doble click**: `war_room.html` autocontenido (datos embebidos) como
   artefacto descargable; se regenera al cerrar cada sync/búsqueda.
8. **Apertura del proyecto**: repo Git documentado (este) para auditoría externa;
   datos reales y secretos quedan fuera por `.gitignore`; esquemas con ejemplos
   sintéticos en `docs/ejemplos/`.
9. **Ronda "auditor de auditores" (v1.1.0)**: el usuario hizo público el repo y
   lo sometió a siete auditorías externas de IA. Se leyó cada reporte completo y
   se evaluó hallazgo por hallazgo contra el código real — no como lista de
   tareas: hubo consensos acertados (bugs verdaderos confirmados y corregidos),
   sugerencias rechazadas con motivo (p. ej. dependencias externas que violan el
   principio stdlib-puro, un cambio de `redirect_uri` que es técnicamente
   incorrecto para clientes *installed*) y una tabla de tests de un auditor que
   era internamente contradictoria. Veredicto por veredicto en
   `docs/RESUMEN_AUDITORIAS.md`. Resultado: reescritura completa del código base,
   capa de seguridad en el servidor (token de sesión, host allowlist, 415/413,
   anti-SSRF), 67 tests automatizados, guardia de privacidad y CI en GitHub
   Actions.

## Preferencias de comunicación del usuario
Español rioplatense, explicaciones simples ("con peras y manzanas"), pasos
numerados cortos, avisos honestos de limitaciones. No asumir conocimientos
técnicos: los archivos .py/.json lo confunden; mostrarle siempre el artefacto
visual (war_room.html / preview).

## Estado actual del sistema
- Conectado y sincronizado (1.305 Enviados leídos, 139 dominios históricos;
  68 con respuesta humana detectada; campaña reciente de 35 días ≈ 22
  instituciones: 11 contestaron, 11 en espera).
- Radar con 55 resultados etiquetados (score: virtuales públicas accesibles primero).
- Dashboard vivo en el workspace + snapshot descargable `war_room.html`.
- Suite de 67 tests verde + CI (Python 3.9/3.11/3.12) + guardia de privacidad.
- Pendientes opcionales: API key de IA (sin ella, motor local), reautorización
  semanal del token (modo Pruebas de Google).
