# Manual de usuario (en criollo)

## Las dos formas de usar el sistema

### 1) La foto del tablero: descargar + doble click 🖱️
1. En el workspace de Qwen, panel derecho → `bot-matematicas` → **`war_room.html`**.
2. Tocá el ícono de descarga (⬇) del archivo.
3. En tu PC: doble click. Se abre en el navegador, sin instalar nada, sin internet.

Ahí ves: números de la campaña, tabla de universidades con cartelitos
(✉ CONTESTÓ / ⏳ EN ESPERA / 🔁 REINTENTAR), el radar de programas nuevos con sus
etiquetas (📡 virtual · 🆓 pública gratuita · 💰 privada ·  accesibilidad), y botones
**✉** que arman un borrador para copiar a tu Gmail.

Ese archivo se **regenera solo** cada vez que termina una sincronización o una
búsqueda del radar: si querés la foto aggiornada, volvelo a descargar.

### 2) La versión viva (dashboard completo)
Corre en el workspace de Qwen (servidor interno, puerto 8643). Tiene todo lo de la
foto **más**:

- **📥 Bandeja real**: tus correos recibidos de instituciones. Por cada uno vos
  decidís: **✉ Responder / ✅ No requiere respuesta / 🗑 Ignorar**.
- **✨ Redactar con IA** o **📝 Redactor local**: el borrador aparece editable;
  después **📧 Abrir en mi Gmail** te lo deja listo y **el envío lo hacés vos**.
- **🛰 Radar**: botón "Buscar programas ahora".
- **⚙ Ajustes**: conexión de Gmail, clave de IA, tu firma y tu contexto personal.

> ✋ **Nada se envía solo. Nunca.** Es la regla de oro del sistema.

## Conectar Gmail (una sola vez, ~2 minutos)
1. ⚙ Ajustes → *Conexión Gmail*: pegá el `client_id` y el `client_secret` que están
   dentro de tu archivo `client_secret.json` (abrilo con el Bloc de notas), o
   adjuntá el archivo en el chat.
2. Botón **🔗 Generar link de autorización** → abrilo → elegí tu cuenta → pantalla
   fea "Google no ha verificado esta app" → **Configuración avanzada → Ir a Radar
   Matemáticas (no seguro)** → **Permitir**.
3. El navegador va a `localhost:8642` y **no carga: es normal**. Copiá toda la URL
   de la barra de direcciones y pegala en el campo **Canjear**. Listo: arranca sola
   la sincronización de tus Enviados (~10 min la primera vez).

## El ritual de los 7 días ⏰
Con la app de Google en modo *Pruebas*, Google corta el token cada 7 días.
El tablero muestra el contador y se pone rojo cuando quedan ≤2 días.
Reautorizar = repetir los pasos 2 y 3 (30 segundos). Si algún día hartan, el plan B
es una contraseña de aplicación IMAP (no vence), a cambio de un permiso más amplio:
consultalo antes de cambiar.

## IA para los borradores (opcional)
Sin clave, el botón ✨ usa el **redactor local** (plantillas formales prolijas con tu
firma) y te avisa. Con una clave de Qwen/DashScope (o cualquier API compatible con
OpenAI) cargada en ⚙ Ajustes → *Inteligencia artificial*, los borradores los escribe
la IA. Botón **🧪 Probar IA** para verificar.

## Correrlo en tu propia PC (para valientes)
Necesitás Python 3.9+. Descargá el repo de GitHub, entrá a la carpeta y:
```
python3 app.py
```
Abrí http://localhost:8643 en tu navegador. Los datos viven en `data/` (se crean
solos). Ojo: si lo corrés en tu PC, el workspace de Qwen y tu PC son dos copias
independientes (no se sincronizan entre sí).
