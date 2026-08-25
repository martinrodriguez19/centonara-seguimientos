# Instalar el agente en la Mac de un vendedor

> **Se hace una sola vez por Mac, en unos 20 minutos.** Después de esto, cada
> vez que se prenda la computadora todo arranca solo: el vendedor no tiene que
> abrir nada, correr nada ni acordarse de nada.
>
> La instalación tiene tres partes:
>
> 1. **En el panel** — 5 minutos, desde cualquier computadora
> 2. **En la Mac** — un rato con el mouse en Chrome, y **un solo comando** en la Terminal
> 3. **Activar** — de vuelta en el panel, cuando se decida

**Dos cosas que este sistema todavía no hace**, para que nadie las espere:

- **No envía mensajes.** El agente lee los chats y redacta borradores; el envío
  se rechaza con un motivo explícito hasta la fase 4. Lo que sí se prueba de
  punta a punta es: botón → leer WhatsApp → borradores en el panel.
- **No hay ícono en la barra de menú** para que el vendedor pause su máquina
  (fase 5). Se pausa desde el panel.

---

## Qué hay que tener a mano antes de empezar

| | |
|---|---|
| Una cuenta de Claude | **Una por máquina**, del Enterprise del cliente. Una API key **no sirve**: desactiva la integración con Chrome |
| Chrome instalado | El que usa el vendedor todos los días |
| El teléfono del vendedor | Para escanear el QR de WhatsApp |
| La contraseña del panel | Para la parte 1 |
| Internet | Para bajar el programa |

Y confirmar con el administrador de la organización que la extensión **Claude
in Chrome** esté habilitada por política. Si está restringida, no funciona en
ninguna máquina y no se arregla desde el código.

---

# Parte 1 — En el panel

Se hace desde cualquier navegador, sin la Mac delante. Conviene tenerla lista
antes de sentarse a la máquina.

## 1.1 — Entrar

**https://frontend-produccion.onrender.com**, con la contraseña del panel.

## 1.2 — Decir a quién puede escribirle ⚠️

**Configuración → destinos permitidos.** Cargar los números de prueba, **y sólo
esos**. En la misma pantalla, **tope por corrida = 3** mientras se prueba.

En una base nueva esta lista arranca vacía, y vacía significa **a nadie**. No
es un error: es lo que hace imposible que un cliente real reciba algo por
accidente. Pero tiene una consecuencia que confunde la primera vez: si se
saltea este paso, la corrida lee los chats y **no redacta ninguno**. Parece que
no funcionó, y funcionó exactamente como debía.

## 1.3 — Dar de alta la máquina

Panel → **Dar de alta una máquina**:

- **Identificador** — minúsculas, números y guiones: `mac-rocio`, no
  `Mac de Rocío`.
- **Nombre del vendedor** — acá sí, con mayúsculas y acentos.
- **Línea de WhatsApp** — opcional.

⚠️ **El token se muestra una sola vez.** Anotá en una nota, juntos, el
**identificador** y el **token** (empieza con `sgc_`): son las dos únicas cosas
que el instalador va a preguntar en la parte 2. Si el token se pierde, en el
panel se rota y sale uno nuevo.

La máquina **nace inactiva**. Instalar no es activar.

---

# Parte 2 — En la Mac

## 2.1 — Preparar Chrome (con el mouse, 5 minutos)

En el Chrome del vendedor —el de todos los días—, en orden:

1. **Instalar la extensión Claude in Chrome** e iniciar sesión con la cuenta
   de Claude de **esta** máquina.
2. **Usar la extensión una vez**: apretar el ícono de Claude y pedirle
   cualquier cosa. Con eso la extensión queda registrada en esta máquina.
3. **Abrir `web.whatsapp.com`** y escanear el QR con el teléfono del vendedor.
4. **Dar el permiso de sitio**: ícono de Claude en la barra → **configuración →
   permisos de sitios → habilitar `web.whatsapp.com`**.

Sobre el punto 4, dos aclaraciones que ahorran una hora:

- **No es el menú de Chrome.** Si entrás por la configuración de Chrome vas a
  ver "Acceso al sitio: todos los sitios", y eso ya está bien: **no es el que
  falta**. El que hay que dar es el de adentro de la extensión.
- Es el **único paso de toda la guía que no se puede automatizar**, a
  propósito: es la extensión pidiendo que una persona autorice que un programa
  opere sobre WhatsApp. Forzarlo por archivo sería saltear un control de
  seguridad.

## 2.2 — Un solo comando en la Terminal

Abrir la **Terminal** (Cmd + barra espaciadora, escribir `Terminal`, Enter) y
pegar esto:

```bash
curl -fsSL https://github.com/martinrodriguez19/centonara-seguimientos/raw/main/instalar.sh | bash
```

Es **una sola línea**, tal cual, de `curl` a `bash`. Si se está tipeando desde
el papel y se ve partida, va todo seguido y sin espacios agregados. Un error de
tipeo se delata rápido: `curl` contesta `404` y no instala nada.

Ese comando hace **todo lo demás**: instala las herramientas, baja el
programa, averigua solo los datos de la máquina, deja configurado el arranque
automático y arranca todo. En el camino:

- **Pregunta dos cosas**: el identificador y el token — los de la nota de la
  parte 1.
- **Puede pedir, una única vez, iniciar sesión en Claude Code**: correr
  `claude` en la Terminal, entrar con la cuenta de esta máquina, salir con
  `/exit`, y volver a pegar el mismo comando de arriba.
- **Puede cerrar Chrome un momento** para volver a abrirlo bien (la sesión no
  se pierde). Si macOS pregunta si la Terminal puede controlar Chrome, es que
  **sí**.

Si algo falta, el instalador **lo dice en castellano y se corta**. La respuesta
es siempre la misma: hacer lo que dijo y **volver a pegar el mismo comando**.
Es seguro correrlo las veces que haga falta — lo que ya está hecho lo saltea, y
correrlo de nuevo es además la forma de **actualizar** el programa más
adelante.

Cuando termina dice **INSTALACIÓN COMPLETA**.

## 2.3 — La comprobación final (recomendada)

Verifica lo único que el instalador no puede: que la extensión tenga el
permiso y que la sesión de WhatsApp esté viva. Abre WhatsApp Web una vez,
**no lee ningún chat**, tarda unos minutos y cuesta alrededor de USD 0,50:

```bash
cd ~/centonara-seguimientos && uv run --directory agente python -m agente.main --sonda
```

Tiene que decir:

```
[OK ] permiso_sitio    la extensión puede entrar a web.whatsapp.com
[OK ] whatsapp_sesion  sesión iniciada, N chats a la vista
```

Si algo sale mal:

| Dice | Qué hacer |
|---|---|
| `sin_permiso` | Falta el punto 4 del paso 2.1: el permiso de la extensión |
| `sesion_no_iniciada` | WhatsApp Web pide QR: escanearlo de nuevo |
| `browser_no_disponible` | Volver a correr el instalador (paso 2.2) |

> **`selectores` va a salir en rojo, y está bien**: el envío está bloqueado a
> propósito hasta la fase 4. La lectura y la redacción funcionan igual.

---

# Parte 3 — Activar y probar

## 3.1 — Activar la máquina, que es una decisión aparte

En el panel la máquina aparece **inactiva** y así se queda hasta que alguien
la active. Antes de activarla: la conversación de consentimiento con el
vendedor, registrada (F5.7). El sistema va a mandar mensajes **desde su línea,
con su nombre** — eso tiene que estar dicho y aceptado, no supuesto.

## 3.2 — La primera corrida

1. En el panel, apretar el botón.
2. El agente lee los chats recientes. Tarda unos minutos.
3. Los borradores aparecen en la pantalla de revisión — **sólo** de los chats
   cuyo número esté en destinos permitidos.

Lo que **no** va a pasar todavía: que salga un mensaje (fase 4). Y dos
resultados que parecen fallas y no lo son:

- **Ningún borrador** — ninguno de los chats recientes es de los números
  autorizados. Es el sistema cuidando la lista, no una falla.
- **Borradores retenidos y vacíos**, con la señal `SIN_CONTEXTO` — el modelo no
  encontró con qué escribir y se negó a inventar. Se escriben a mano desde el
  panel, o se descartan.

---

# Después de instalar

- **Todo arranca solo.** Cada vez que el vendedor prende la Mac e inicia
  sesión, Chrome y el agente se levantan sin que nadie toque nada. Si el
  agente se cae, se vuelve a levantar solo.
- **Dos cosas pueden volver a pedir atención**, y las dos son sesiones que
  vencen, no fallas:
  - La de **WhatsApp Web** expira cada tanto (dura días, no meses). Cuando
    pida QR, se escanea de nuevo y listo.
  - La de **Claude Code** también caduca. El síntoma es un error que dice
    `la sesión de Claude Code venció`. Se arregla en la Terminal: correr
    `claude`, iniciar sesión, salir con `/exit`.
- **Actualizar el programa** = volver a pegar el comando del paso 2.2. No
  vuelve a preguntar nada.
- **Los logs** quedan en `~/Library/Logs/centonara/`.

Para **frenar todo** en una máquina (para un técnico):

```bash
launchctl bootout gui/$(id -u)/com.centonara.agente
launchctl bootout gui/$(id -u)/com.centonara.chrome
```

Para volver a arrancar: correr el instalador de nuevo, o reiniciar la sesión.

---

# Si algo no anda

| Síntoma | Causa y qué hacer |
|---|---|
| `Claude in Chrome requires permission` | Falta el permiso de la extensión (paso 2.1, punto 4). Lo emite el navegador, por eso no aparece en ningún log del agente |
| WhatsApp pide QR de golpe | La sesión expiró; pasa cada tanto. Escanear de nuevo |
| `la sesión de Claude Code venció` (o un `401` de OAuth) | El token caduca cada tanto. Correr `claude`, iniciar sesión con la cuenta de esa máquina, salir con `/exit` |
| `token_rechazado` en el log | El token no es el de esta máquina, o se rotó. Rotar en el panel, borrar la línea `AGENTE_TOKEN` del `.env` y correr el instalador de nuevo |
| El agente no toma trabajo | La máquina está inactiva o pausada en el panel, o el kill switch está puesto |
| `browser_no_disponible` | El Chrome registrado no es este. Correr el instalador de nuevo |
| El instalador dice que el servidor no contesta | Sin internet, o el servidor estaba dormido y tardó. Esperar un minuto y correrlo de nuevo |
| El panel muestra un error crudo | Reportarlo: los mensajes del panel se escriben para quien lo usa |

### Para técnicos

- Lo instalado son **dos LaunchAgents** (`com.centonara.agente` y
  `com.centonara.chrome`, en `~/Library/LaunchAgents/`), el proyecto en
  `~/centonara-seguimientos` con su `.env`, y las herramientas `uv` y
  `claude` en `~/.local/bin`. Son LaunchAgents y **no** LaunchDaemons a
  propósito (D16): Chrome y la extensión viven en la sesión del usuario.
- `Bootstrap failed: 5: Input/output error` al correr `launchctl bootstrap` a
  mano quiere decir **"ya está cargado"**, no que algo falló.
- El backend es `https://backend-produccion-7yqr.onrender.com` — **con
  sufijo**. `backend-produccion.onrender.com` a secas es la aplicación de otra
  persona: ese subdominio global ya estaba tomado. El instalador trae la URL
  correcta; si se toca a mano, comprobarla:

```bash
curl https://backend-produccion-7yqr.onrender.com/health
```

  Tiene que devolver `{"ok":true,"mongo":true,"entorno":"produccion"}`.

- `OPENSSL_Uplink(...): no OPENSSL_Applink` — un antivirus dejó
  `SSLKEYLOGFILE` en el entorno. El agente ya la descarta al arrancar; si
  aparece igual, es otro proceso.
- El puerto de depuración (9222) **no va a estar disponible** en Chrome 136 o
  más nuevo: Chrome lo rechaza sobre el perfil normal del usuario ("DevTools
  remote debugging requires a non-default data directory"). El instalador lo
  intenta, lo avisa y sigue: hoy no bloquea nada — lo necesita sólo el envío
  real (fase 4), y ahí se va a resolver con un directorio de datos dedicado.
