# Plan — Sesiones que se reconectan solas o con un botón

> **El pedido.** A los pocos días a los vendedores se les cierra la sesión de WhatsApp Web o la de
> Claude, y hoy la única forma de arreglarlo es que el dueño vaya a la oficina y lo haga en la
> máquina. Lo que se quiere: una **página pública** con todos los vendedores, donde cada uno vea
> desde su celular si se le cayó una sesión, y un **botón** para volver a conectarla. Es gente que
> no sabe del tema: tiene que ser extremadamente fácil y corto.
>
> Fecha: 16/11/2026. Base: `main` en `aff1841`. Estado: **implementado (Fases 1–4) el 16/11, sin commitear ni desplegar**; ver §10. Decisiones
> propuestas D69–D73 (§8); se escriben en `06-DECISIONES.md` antes de tocar código, como siempre.
> Las respuestas del dueño están en §9 y ya aplicadas en el texto.
>
> **Las reglas de siempre siguen.** Nada de esto pide terminal ni reinstalar (la regla de
> PLAN-HORARIOS). Lo que anda no se toca: no cambia qué se lee, cómo se redacta ni cómo se deja un
> borrador. Todo lo nuevo es *alrededor*: saber qué sesión está viva y reabrirla.

---

## 0. Qué hay hoy, verificado en el código

### Las cuatro sesiones de cada máquina

"Se cerró la sesión" son en realidad **cuatro cosas distintas**, que se caen por motivos
distintos y se arreglan distinto. Confundirlas es el primer problema.

| # | Sesión | Dónde vive | Quién la usa | Cómo se arregla hoy | Cómo se entera el sistema hoy |
|---|---|---|---|---|---|
| S1 | **WhatsApp Web en el Chrome del vendedor** | Perfil de Chrome que `perfiles.recomendar()` elige | El pase único (`BORRADORES`, D38) y `LISTAR`, vía la extensión. **Es la ruta de producción** | Ir a la máquina, abrir Chrome en *ese* perfil, escanear el QR | **Sólo cuando falla un job**: el modelo devuelve `sesion_no_iniciada` → `SESION_CAIDA` (`jobs/borradores.py:64`). El chequeo `perfiles` mira si el IndexedDB *existe*, no si la sesión está viva (`perfiles.py:93`) |
| S2 | **Extensión Claude in Chrome** (login en claude.ai dentro de ese perfil) | Mismo perfil de Chrome | Todo lo que pasa por `--chrome` | Ir a la máquina, abrir la extensión, iniciar sesión con la cuenta compartida | Sale mezclado en `NAVEGADOR_AUSENTE` (`browser_no_disponible`), que también es "Chrome cerrado" o "deviceId equivocado" (D66). **No se distingue** |
| S3 | **Claude Code (CLI)** | `~/.claude` o `CLAUDE_CODE_OAUTH_TOKEN` en el `.env` | Cada invocación de `claude -p` | `claude` → login → `/exit`, en terminal. Con el token de D68, no vence en un año | Un 401 → `ERROR_INESPERADO` con el motivo "la sesión de Claude Code venció" (`claude_code.py:322`). **No tiene alerta propia** y no se sabe qué máquinas tienen el token de D68 |
| S4 | **WhatsApp del navegador dedicado** (D24) | `~/Library/Application Support/Centonara/Chrome` | Sólo la ruta vieja (`modo_borrador = playwright`) y `ENVIAR` | `--vincular` en terminal (`RUNBOOK-revincular-whatsapp.md`) | La vigía, cada 6 h (`vigia_sesion.py`), con alerta `sesion_dedicada_vencida` |

Lo único que el sistema ya mira bien es S4, que es justamente la que menos se usa hoy.

### Lo que existe y sirve de base

| Pieza | Qué hace | Dónde |
|---|---|---|
| Abrir el Chrome correcto | `asegurar_abierto` lanza Chrome con `--profile-directory` del perfil recomendado aunque ya esté abierto (Chrome lo pasa a la instancia viva), y en Windows restaura ventanas minimizadas | `adaptadores/navegador.py:209`, `:293` |
| Latido | Cada 30 s, con diagnóstico y `diagnostico_detalle`. Su respuesta ya trae datos del backend al agente (horarios, D64) | `bucle.py:37`, `api/agente.py:394` |
| Cola de jobs | `GET /jobs/proximo` cada 10 s — **pero contesta 423 con pausa global, descanso, máquina pausada o sin cuota** | `api/agente.py:200-225` |
| Alertas por máquina | Ya hay alertas de diagnóstico (`sesion_dedicada_vencida`, `chrome_sin_perfil`) | `core/alertas.py:248-360` |
| Lectura de LevelDB del perfil | Ya se parsea el almacenamiento de la extensión para sacar el `deviceId` (D66) | `perfiles.py:63` |
| Panel con login | Contraseña única y cookie firmada (D22). El middleware deja pasar sólo `/login` y `/healthz` | `core/sesion.py`, `frontend/middleware.ts` |

### Tres conclusiones que ordenan el plan

1. **El problema principal no es reconectar, es *enterarse*.** S1 y S2 se descubren cuando ya
   falló una corrida, y el aviso dice "SESION_CAIDA" o "NAVEGADOR_AUSENTE", que no le dice nada a
   un vendedor. Sin un estado por sesión, no hay semáforo que mostrar.
2. **El canal para "reconectar" no puede ser la cola de jobs.** La cola está cerrada justo en los
   momentos en que más hace falta (sin cuota, frenada por canario, pausa). El latido no: llega
   siempre que la máquina esté despierta.
3. **Reconectar WhatsApp necesita el teléfono del vendedor, sí o sí.** Es lo que WhatsApp exige y
   no se puede saltear. Lo que sí se puede sacar es todo lo demás: saber qué perfil, abrir Chrome,
   ir a la página, traer la ventana al frente, y confirmar que quedó.

---

## 1. Cada cuánto se caen, y qué se hace con eso

Según el dueño: **WhatsApp una vez por mes, Claude cada 15 días.** Son frecuencias normales para
una sesión vinculada y una sesión web: no hace falta investigar causas propias, hace falta que
reconectar sea trivial. No se busca bajar la frecuencia; se busca que cada caída cueste dos
minutos del vendedor y cero visitas del dueño.

Lo que sí cambia el orden: **lo de Claude cada 15 días es, muy probablemente, S3** (el `/login`
de Claude Code, que es lo que D68 describió como "vence cada tanto"). Si es así, el token de un
año repartido desde el panel (§4) la elimina entera, sin página ni botón. Por eso va primero
(Fase 1). La línea de tiempo de sesiones de la Fase 2 confirma cuál de las dos de Claude era: si
después del token sigue cayendo algo cada 15 días, es S2.

Lo único que se registra de más, porque es barato y evita falsas alarmas: en cada `SESION_CAIDA`,
qué pantalla se vio (QR, "WhatsApp está abierto en otra ventana → Usar aquí", lista). La segunda
**no es una sesión caída** —pasa cuando hay dos pestañas de WhatsApp— y no tiene que poner el
semáforo en rojo ni pedirle al vendedor que escanee nada: el agente la resuelve solo cerrando la
pestaña sobrante.

---

## 2. Lo que va a ver el vendedor

### 2.1 La página: `/conectar`

Fuera del login del panel. Pensada para el celular, una sola pantalla, letra grande, sin menús.

```
┌─────────────────────────────────┐
│  Centonara · Conexiones         │
│                                 │
│  ┌───────────────────────────┐  │
│  │ Lautaro                   │  │
│  │ WhatsApp   ● Conectado    │  │
│  │ Claude     ● Conectado    │  │
│  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │
│  │ Sofía                     │  │
│  │ WhatsApp   ● Desconectado │  │
│  │ ┌───────────────────────┐ │  │
│  │ │  Volver a conectar    │ │  │
│  │ └───────────────────────┘ │  │
│  │ Claude     ● Conectado    │  │
│  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │
│  │ Thomas                    │  │
│  │ La computadora está       │  │
│  │ dormida: mové el mouse    │  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘
```

- **Dos renglones por vendedor, no cuatro.** "WhatsApp" es S1 (y S4 si esa máquina usa la ruta
  vieja); "Claude" es S2 y S3 juntas. Al vendedor no le importa cuál de las dos de Claude es: le
  importa si tiene que hacer algo.
- **Tres estados y nada más:** verde *Conectado*, rojo *Desconectado* con botón, gris *No se
  sabe* ("la computadora está apagada / dormida", con la instrucción de qué hacer). Nunca un
  código de error.
- Se actualiza sola cada 5 segundos. Sin recargar.

### 2.2 Qué pasa al apretar "Volver a conectar WhatsApp"

1. En **la computadora** de ese vendedor, a los pocos segundos, se abre Chrome en el perfil
   correcto, en `web.whatsapp.com`, al frente de todo, con el código QR. Más una notificación del
   sistema: *"Escaneá el código con tu celular"*.
2. En **el celular**, la página cambia a las instrucciones, con un dibujo por paso:
   > 1. Mirá la pantalla de la computadora.
   > 2. En tu celular abrí WhatsApp → ⋮ (o Configuración) → **Dispositivos vinculados**.
   > 3. Tocá **Vincular un dispositivo** y apuntá al cuadrado.
   > Si WhatsApp te dice que llegaste al máximo de dispositivos, borrá uno que no uses.
3. Cuando el agente ve la lista de chats, la página pasa sola a **"¡Listo! Ya está conectado"**.
   El vendedor no aprieta nada más.
4. Si en 5 minutos no se escaneó: "No se completó. Probá de nuevo", con el mismo botón.

Es el mismo flujo que hoy hace el dueño a mano, sin el dueño.

### 2.3 Qué pasa al apretar "Volver a conectar Claude"

Depende de cuál se cayó, y el vendedor no lo tiene que saber:

- **S3 (Claude Code):** no debería llegar nunca a la página. Se resuelve con el token de D68
  repartido a todas desde el panel (§4, Fase 1). Si igual aparece, el dueño lo ve en el panel y no
  el vendedor.
- **S2 (extensión):** la cuenta compartida entra con **un código que llega por mail a una persona
  del personal** (§9.1). Ese paso no se puede automatizar ni saltear, así que el flujo lo hace
  corto y deja claro a quién pedírselo:
  1. El botón abre en la computadora Chrome en el perfil correcto, en el inicio de sesión de
     claude.ai, al frente, con una notificación que dice **el mail con el que hay que entrar**.
  2. En el mismo momento, el panel del dueño muestra una alerta urgente: *"Sofía está entrando a
     Claude: le va a llegar un código a la cuenta, pasáselo"*. **Hablar con la persona que recibe
     el código lo hace el dueño** (§9, 16/11): el sistema no le escribe a nadie más.
  3. La página del celular dice: *"En la computadora escribí el mail que aparece y tocá
     Continuar. Pedile el código a **(el nombre que se carga en el panel)** y escribilo. Después tocá el ícono de Claude en
     Chrome y apretá Iniciar sesión."* Y un botón **"Ya terminé"**, que hace que la máquina
     verifique con una sonda corta (§3.1) y pase a "¡Listo!".

  **El mail de la cuenta y el código nunca aparecen en la página pública**: el mail va sólo en la
  notificación de la máquina, y el código lo pasa una persona a otra. Un código de acceso en una
  página abierta es la cuenta enterprise entera para cualquiera que la mire.

### 2.4 Mejor que un botón: que se abra sola

Si el agente detecta que S1 se cayó, en horario de trabajo y con la máquina despierta, **abre la
ventana del QR por su cuenta** y muestra la notificación, sin esperar a que nadie apriete nada.
El vendedor, que está sentado ahí, ve la ventana y escanea. El botón de la página queda para
cuando la ventana se cerró o el vendedor no estaba. Tope: una vez cada 2 horas por máquina, nunca
en descanso (D64), nunca con un job de Claude corriendo en ese Chrome.

### 2.5 El aviso en el celular

Los vendedores están frente a la máquina cuando se les cae (§9.2), así que la notificación que más
funciona es la de la **computadora**: ahí está el vendedor y ahí se escanea. En el celular:

- **Fase 3:** la página `/conectar` se puede "agregar a pantalla de inicio" y queda como un ícono;
  el vendedor la mira cuando quiere. Sin instalar nada.
- **Fase 5 (opcional):** notificaciones push desde esa misma página (Web Push). En Android anda
  directo; en iPhone sólo si la página se agregó a la pantalla de inicio (iOS 16.4+). Es el único
  paso que pide una configuración por celular, por eso va al final y sólo si hace falta.

---

## 3. Lo que hay que construir

### 3.1 Agente

| Pieza | Qué hace |
|---|---|
| **Estado de S1 sin gastar tokens** | Leer el `Local Storage` de `web.whatsapp.com` del perfil recomendado, igual que ya se lee el de la extensión. WhatsApp Web guarda ahí el número vinculado mientras la sesión vive (`last-wid-md` y afines) y lo borra al cerrarla. **Hay que confirmarlo en una máquina real** (Fase 2): si la señal no es confiable, el plan B es una sonda corta por la extensión una vez por día antes de la corrida, que cuesta tokens |
| **Estado de S2** | Distinguir "extensión sin sesión" de "Chrome cerrado" y "deviceId equivocado". Primero buscar una señal en disco (cookies/almacenamiento de la extensión); si no hay, separar el motivo en el prompt de BORRADORES y en `NAVEGADOR_AUSENTE` |
| **Estado de S3** | Reportar en el latido si `CLAUDE_CODE_OAUTH_TOKEN` está definido (nunca el valor) y si la última invocación dio 401. Un 401 pasa de `ERROR_INESPERADO` a un código propio, `CLAUDE_SIN_SESION`, sin reintentos |
| **`sesiones` en el latido** | `{whatsapp: ok\|caida\|desconocido, claude_extension: …, claude_cli: …, numero_vinculado: "+54…"}` cada 30 s, de lo cacheado. Revisar de verdad cada 15 min (lectura de disco, es barata), y **cada 10 s durante los 5 min posteriores a una reconexión**, para que el "¡Listo!" sea inmediato |
| **Acciones por latido** | La respuesta del latido trae `acciones: [{id, tipo: "abrir_whatsapp"\|"abrir_claude"}]`. El agente las ejecuta con `asegurar_abierto` + la URL, trae la ventana al frente y muestra la notificación del sistema (`osascript display notification` en Mac, toast en Windows). Contesta con el `id` hecho en el latido siguiente. **No pasa por la cola**, así que anda con la máquina pausada o sin cuota |
| **Apertura automática** (§2.4) | Al pasar S1 de `ok` a `caida`, abrir la ventana sola con los topes de §2.4 |

### 3.2 Backend

| Pieza | Qué hace |
|---|---|
| `vendedores.sesiones` | Lo último que reportó el latido, más `desde` por sesión (cuándo cambió) |
| `sesiones_historial` | Cada cambio de estado, con TTL de 90 días. Es la línea de tiempo de la Fase 2 |
| `vendedores.acciones` | Cola chiquita de acciones pendientes por máquina, con vencimiento de 10 min (una acción vieja no se ejecuta cuando la máquina despierta al otro día) |
| `GET /api/publico/conexiones` | Sin login. Devuelve **sólo** nombre, estado de las dos líneas y si la máquina está viva/dormida. Ni números, ni chats, ni ids internos |
| `POST /api/publico/conexiones/{alias}/reconectar` | Sin login. Encola la acción. Tope: una por máquina cada 2 min. Queda en la auditoría con IP |
| `POST /api/panel/sistema/token-claude` | Con login. El dueño pega el token de `claude setup-token` y viaja a las máquinas (§4) |
| Configuración: cuenta de Claude | Dos campos nuevos en el panel: el **mail de la cuenta compartida** (viaja a la máquina para la notificación, nunca a la página pública) y **a quién pedirle el código** (un nombre, que la página muestra). El aviso es la alerta del panel: con la persona del código habla el dueño |
| Alertas | `whatsapp_desconectado` y `claude_desconectado` por máquina, nivel **aviso** mientras no haya corrida en la próxima hora y **urgente** si la hay (mismo criterio que D64). `linea_equivocada` urgente (§5) |
| Corridas | Una máquina con S1 o S2 caída **queda afuera de la corrida** como una dormida (D59), en vez de entrar y fallar. Lo que no hizo lo completa la repesca (D61) |

### 3.3 Frontend

- `app/(publico)/conectar/page.tsx`, excluida en el `middleware.ts`. Sin la barra del panel.
  Componentes nuevos y chicos; nada del panel se importa salvo los de `ui/`.
- Las instrucciones con dibujos simples (SVG propios, no capturas de WhatsApp) para Android y
  iPhone, porque el menú está en lugares distintos.
- En el panel del dueño: las sesiones en Máquinas → la máquina (con la línea de tiempo) y un
  enlace "Abrir página de conexiones" para compartirla.

---

## 4. Claude sin logins (S3, y parte de S2)

D68 ya resuelve S3 técnicamente: un token de `claude setup-token` dura un año y no vence por
inactividad. Lo que falta es que **llegue a todas sin ir a cada una**:

1. El dueño corre `claude setup-token` **una vez**, en su máquina, y pega el resultado en el panel
   (Ajustes → Sistema → Token de Claude). Se guarda en Mongo; el panel nunca lo vuelve a mostrar,
   sólo "cargado el 16/11/2026, vence aprox. el 16/11/2027".
2. El backend lo manda en la respuesta del latido a cada máquina que reporte "sin token" o un
   token distinto (comparando un hash, nunca el valor). Viaja por HTTPS y autenticado con el token
   de máquina.
3. El agente lo escribe en su `.env` (que ya está `chmod 600` / con ACL) y lo usa desde la
   próxima invocación. No hace falta reiniciar.
4. Alerta a los 11 meses: "renová el token de Claude".

Con esto S3 desaparece de la página y del día a día. **El costo es el mismo que asumió D68**: el
token queda en un lugar más (la base). Es aceptable por la misma razón que D68 lo aceptó, pero se
anota en §8.

S2 (la extensión) **no acepta un token**: usa la sesión de claude.ai del perfil. Lo que se puede
hacer es lo de §2.3 y medir en la Fase 2 cada cuánto se cae de verdad.

---

## 5. Seguridad: lo que la página pública puede y no puede hacer

La página es pública a pedido del dueño, y está bien que lo sea **porque no muestra nada ni
permite nada que valga la pena robar**:

| Qué | Por qué es seguro |
|---|---|
| Ver nombres y semáforos | No hay números, chats ni datos de clientes. Lo peor que se ve es que "Sofía está desconectada" |
| Apretar "Volver a conectar" | Sólo abre una ventana **en la computadora de la oficina**. El QR aparece en esa pantalla física, nunca en la página. Para aprovecharlo hay que estar sentado frente a la máquina |
| Apretarlo muchas veces | Tope de una cada 2 min por máquina, y cada una en la auditoría |

**La regla que no se cruza: el QR o el código de vinculación nunca se muestran en la página
pública.** Quien escanea un QR vincula *su* WhatsApp a esa máquina, y desde ahí el sistema
trabajaría sobre una línea que no es la del vendedor.

Por eso, y por R2, una guarda nueva: **después de reconectar, el agente compara el número
vinculado (`numero_vinculado`, del mismo `Local Storage`) con el número de la máquina en el
panel.** Si no coincide, la máquina no toma trabajo y salta `linea_equivocada` urgente. Hoy no
existe esta verificación, y con reconexiones hechas por los propios vendedores se vuelve
necesaria. Requiere cargar el número de cada vendedor en el panel (un campo nuevo en la máquina).

**Pública, pero sólo para conexiones** (§9.3). Sin PIN ni URL secreta. Eso fija el alcance:
la página no muestra corridas, borradores, métricas, números ni mails, y no tiene ningún botón que
no sea reconectar. Cualquier dato nuevo que alguien quiera sumarle va al panel con contraseña, no
acá. El endpoint público tiene su propio router (`api/publico.py`) y su propio modelo de respuesta,
para que un campo agregado al estado de la máquina no se filtre a la página por accidente; un test
fija la lista exacta de campos que devuelve.

---

## 6. Fases

Cada fase se puede desplegar sola y deja algo útil. Mismo criterio que el resto del proyecto:
terminan por criterio de salida, no por fecha (D19). El orden pone primero lo que más visitas a la
oficina ahorra por menos trabajo.

### Fase 1 — Claude Code sin logins (la ganancia más barata)

- Token de Claude cargado desde el panel y repartido por latido (§4).
- El latido reporta si la máquina tiene token (nunca el valor). Un 401 pasa a `CLAUDE_SIN_SESION`,
  sin reintentos, con alerta propia.

**Criterio de salida:** todas las máquinas con token, y un mes sin que nadie inicie sesión en
Claude Code. Si lo de "Claude cada 15 días" era S3 (§1), acá desaparece.

### Fase 2 — Saber (medir y mostrar, sin botones)

- Estado de S1/S2/S3 en el latido, `sesiones_historial`, y la línea de tiempo en el panel.
- Validar en una Mac y una Windows reales la señal de disco de S1 (iniciar y cerrar sesión de
  WhatsApp y ver qué cambia en `Local Storage`), y buscar la de S2. Si alguna no aparece, plan B:
  la sonda corta por la extensión una vez por día, antes de la corrida.
- La pantalla "Usar aquí" se reconoce y se resuelve sola (§1).
- Alertas `whatsapp_desconectado` / `claude_desconectado`; máquina con sesión caída queda afuera
  de la corrida.

**Criterio de salida:** durante dos semanas, cada caída de S1 y S2 aparece en el panel **antes**
de la corrida que la hubiera encontrado.

### Fase 3 — La página y el botón de WhatsApp (el pedido)

- `/conectar` pública con los semáforos y "la computadora está dormida".
- Acciones por latido, apertura de Chrome en el perfil correcto al frente, notificación del
  sistema, instrucciones con dibujos, "¡Listo!" automático.
- Apertura sola cuando S1 se cae (§2.4).
- Número del vendedor en el panel y guarda `linea_equivocada`.

**Criterio de salida:** un vendedor reconecta su WhatsApp **sin ayuda y sin explicación previa**,
desde que ve el rojo hasta el verde, en menos de 2 minutos. Se prueba con uno que no haya visto
la página antes. Es el mismo tipo de criterio que tuvo F2.

### Fase 4 — El botón de Claude (la extensión)

- El flujo de §2.3: Chrome en claude.ai con el mail en la notificación de la máquina, alerta al
  dueño, "Ya terminé" con sonda de verificación.
- Configuración del mail de la cuenta y de a quién pedirle el código.

**Criterio de salida:** un vendedor reconecta la extensión con el dueño pasándole el código a
distancia, sin que nadie vaya a la oficina, en menos de 5 minutos.

### Fase 5 — Opcional, sólo si hace falta

- **Avisos push** al celular (§2.5).

**Descartado por ahora: reconectar desde afuera de la oficina** con el código de vinculación de
WhatsApp. Los vendedores están frente a la máquina cuando se cae (§9.2), así que no hace falta, y
era lo más caro: necesitaba la extensión con modelo para tocar el Chrome del vendedor, gastaba
tokens, y mostraba un código en el celular que obligaba a un link personal por vendedor, lo que
contradice "pública sólo para conexiones". Se revisa si la situación cambia.

---

## 7. Qué no cambia

- Cómo se lee, se redacta, se deja un borrador o se envía. Las reglas R1–R5.
- La cola de jobs y sus 423: las acciones de reconexión van por otro lado a propósito.
- El panel del dueño y su contraseña (D22).
- El runbook de `--vincular` (S4) sigue valiendo; en la Fase 3 se le suma el mismo botón si esa
  máquina usa la ruta vieja.

---

## 8. Decisiones propuestas

- **D69 — Las sesiones son un dato propio, no un chequeo más.** Cuatro sesiones con estado,
  `desde` e historial, en el latido. El vendedor ve dos.
- **D70 — Reconectar va por el latido, no por la cola.** Para que funcione en pausa, sin cuota o
  con el canario frenado.
- **D71 — La página de conexiones es pública, sólo para conexiones.** Nombres, semáforos y
  botones de reconectar, nada más, con la lista de campos fijada por test. El QR y el mail de la
  cuenta de Claude sólo aparecen en la pantalla física de la máquina; el código de Claude lo pasa
  una persona a otra y nunca toca el sistema.
- **D72 — La línea vinculada se verifica.** Número vinculado ≠ número del vendedor → la máquina no
  trabaja (R2).
- **D73 — El token de Claude se carga una vez en el panel y llega solo a las máquinas.** Completa
  D68. Lo revierte lo mismo que a D68.

---

## 9. Respuestas del dueño (16/11/2026)

1. **Cómo se entra a la cuenta compartida de Claude:** con un código que llega por mail a una
   persona del personal. → La reconexión de la extensión no es 100% autoservicio: necesita a esa
   persona. El flujo la avisa y le dice al vendedor a quién pedírselo (§2.3). El código nunca
   pasa por la página.
2. **Si están frente a la máquina cuando se cae:** sí. → Alcanza con abrir el QR en la pantalla
   de la máquina; la reconexión remota queda descartada (§6, Fase 5).
3. **Pública o protegida:** pública, pero sólo para conexiones. → Sin PIN ni URL secreta, con un
   alcance cerrado por test (§5).
4. **Dispositivos vinculados por línea:** no importa; si hace falta, el vendedor borra uno para
   vincular el del sistema. → Una línea en las instrucciones (§2.2).
5. **Frecuencia:** WhatsApp una vez por mes, Claude cada 15 días. → Son caídas normales, no se
   investigan causas; Claude Code pasa a la Fase 1 porque es probablemente lo de cada 15 días (§1).

6. **Hablar con la persona que recibe el código:** lo hace el dueño. → El sistema sólo le avisa
   al dueño, con una alerta del panel (§2.3). No hay canal de aviso a terceros.

**Aprobado el 16/11: se implementan las Fases 1 a 4.** La 5 (push) queda opcional, como dice §6.

---

## 10. Cómo quedó implementado (16/11/2026)

Lo que cambió respecto del texto de arriba, y por qué:

- **No se lee el disco del perfil.** Se probó en la máquina de desarrollo: el WhatsApp Web actual
  guarda su `localStorage` con los nombres de las claves cifrados, sin `last-wid-md`. La señal
  temprana es una **revisión diaria con la sonda** (`agente/reconexion.py`): una llamada corta por
  máquina y por día, sólo con la máquina libre y fuera del descanso, salteada si un job ya
  confirmó las sesiones en las últimas 20 h. Después de abrir una ventana de reconexión la máquina
  verifica sola un par de veces (WhatsApp a los 2 y 5 min; Claude a los 4 y 9), y la página tiene
  "Ya escaneé" / "Ya terminé" para verificar en el momento.
- **D72 (línea equivocada) quedó inerte**: el backend, el panel y las alertas están, pero el
  agente no tiene de dónde leer el número vinculado (estaba en el disco). Sin número, no frena
  nada.
- **Pendiente: la pantalla "Usar aquí"** (§1). No se implementó: el agente no distingue todavía
  esa pantalla de un QR. Si aparece en la práctica, lo va a decir el detalle del `SESION_CAIDA`.
- **Pendiente: los dibujos de los pasos** (§3.3). Las instrucciones de la página son texto.
- **Sin Docker** (pedido del dueño): los tests nuevos del backend corren contra una base en
  memoria (`backend/tests/base_falsa.py`).
- **El frontend no se pudo compilar en esta máquina**: la red corta las descargas de npm. Lint,
  typecheck y vitest quedan para el CI o para una red que llegue a `registry.npmjs.org`.

Para desplegar: **primero el backend** (el agente se adapta a un backend viejo, pero el panel
nuevo necesita los endpoints nuevos), después el panel. Las máquinas se actualizan solas.

