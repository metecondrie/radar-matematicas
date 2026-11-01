# Contribuir / auditar

Este repo está pensado para que cualquier persona o IA pueda auditarlo **sin
leer ninguna conversación**: todo el contexto vive en `docs/`.

## Correr todo en 60 segundos

```bash
git clone https://github.com/metecondrie/radar-matematicas
cd radar-matematicas
python3 -m unittest discover -s tests -v   # 67 tests, stdlib puro, sin pip
python3 scripts/check_privacidad.py        # guardia: nada sensible versionable
python3 -m py_compile app.py               # humo de compilación
```

O con make: `make check` (compile + privacidad + tests).

Los tests no tocan la red (urlopen se mockea) ni requieren credenciales: usan
un `RADAR_DATA_DIR` temporal. `tests/test_server_security.py` levanta el
servidor real como subproceso en un puerto libre y lo ataca (401/403/415/413).

## Reglas del código (innegociables)

1. **Stdlib puro** (Python 3.9+). No se aceptan dependencias `pip`: la
   robustez se implementa a mano (ver `util.escribir_json` atómico con lock).
2. **Nunca enviar correo.** Ningún código puede invocar `messages.send`, SMTP
   ni equivalente. La salida es `mailto:` / texto para copiar, ejecutado por
   el humano. Un grep debe seguir dando cero.
3. **Privacidad:** datos reales y secretos solo en `data/`, `client_secret.json`
   y `war_room.html` (todo gitignoreado, 0600). Tests y docs usan datos
   sintéticos (`*-ejemplo.*`, `uni-prueba.edu.ar`, `example.com`).
   `scripts/check_privacidad.py` corre en CI y debe dar verde.
4. **Frontend sin handlers inline:** un único listener delegado por `data-act`;
   todo campo de texto interpolado pasa por `esc()`. `tests/test_front_lint.py`
   lo verifica y no se debilita sin documentar el motivo.
5. **Toda ruta de red nueva pasa por las guardas:** `radar.url_segura()` para
   fetch de páginas; `ia_redactor.validar_ajustes()` para endpoints de IA.
6. **JSON siempre con `util.leer_json` / `util.escribir_json`** (utf-8,
   atómico, lock, 0600 opcional). Nunca `open()` suelto sobre `data/`.

## Dónde mirar según la duda

| Pregunta | Archivo |
|---|---|
| ¿Cómo llega un mail a la bandeja? | `docs/ARQUITECTURA.md` (flujos) + `app.py` (`bandeja_real`) |
| ¿Qué garantías de seguridad hay y cómo se prueban? | `docs/AUDITORIA.md` + `tests/test_server_security.py` |
| ¿Por qué se rechazó X de mi auditoría? | `docs/RESUMEN_AUDITORIAS.md` |
| ¿De dónde viene este diseño? | `docs/HISTORIA.md` |
| ¿Qué cambió en cada versión? | `CHANGELOG.md` (y `VERSION`, fuente única) |

## Reportar un hallazgo

Abrí un issue con: archivo + función (no número de línea), cómo reproducirlo
(comando o test mínimo) y qué esperabas. Si es de seguridad y preferís no
hacerlo público, indicá un canal privado en el issue sin incluir el dato.
