# Sistema de Seguimiento Comercial — puesta en marcha

> **Qué hace este sistema.** Lee los chats de WhatsApp de cada vendedor, busca
> los clientes que quedaron sin respuesta, redacta un mensaje de seguimiento
> para cada uno, y los manda **después de que una persona los revise y apriete
> enviar**. Nada sale solo.
>
> **Cuánto lleva ponerlo a andar:** unos 20 minutos en el panel y otros 20 en
> cada Mac. Se hace una sola vez por computadora.
>
> **No hace falta saber de computación, ni instalar Python, ni nada técnico.**
> Todo lo que la Mac necesita lo trae un solo comando que se copia y se pega.

---

## Lo que hay que tener a mano

| | |
|---|---|
| La Mac del vendedor | Con **Google Chrome** instalado |
| Una cuenta de Claude | **Una por máquina.** Del Enterprise de la empresa. Una API key *no sirve* |
| El teléfono del vendedor | Para escanear dos códigos QR |
| La contraseña del panel | La que se usa para entrar a la pantalla de control |
| Un rato con el vendedor | Para explicarle qué hace el sistema y que lo acepte |

Y una cosa que conviene confirmar antes: que la extensión **Claude in Chrome**
esté permitida por la organización. Si está bloqueada por política, no funciona
en ninguna máquina y no hay forma de arreglarlo desde el sistema.

---

# Parte 1 — En el panel

Se hace desde cualquier computadora, sin la Mac delante.

**El panel:** https://frontend-produccion.onrender.com

## 1.1 — Contarle al sistema sobre la empresa

**Configuración → Sobre la empresa.**

Acá va todo lo que el redactor necesita saber para escribir mensajes que sirvan:
qué vende la empresa, qué productos y servicios ofrece, promociones vigentes,
cómo le habla a sus clientes, con qué conviene recuperar a alguien que se
enfrió.

Cuanto más concreto, mejores salen los mensajes. Es la diferencia entre *"¿cómo
andás? ¿seguimos en contacto?"* y un mensaje que retoma lo que esa persona
había pedido y le ofrece algo real.

Se puede cambiar cuando se quiera: cada mensaje que se redacta usa la versión
del momento.

## 1.2 — Decir a quién se le puede escribir ⚠️

**Configuración → Destinos permitidos.**

Esta lista es el freno de mano del sistema: **sólo se le escribe a los números
que estén ahí**. Arranca vacía, y vacía significa **a nadie**.

Para las pruebas, cargar dos o tres números propios y nada más. Cuando el
sistema ya demostró que escribe bien, se abre a todos los contactos escribiendo
la palabra `ABRIR` — es un acto deliberado y queda registrado.

> **La confusión más común:** con la lista en números de prueba, una corrida lee
> los chats y **no genera casi nada**. No está roto: está haciendo lo que se le
> pidió.

## 1.3 — Elegir qué chats se siguen

**Configuración → Qué chats se siguen.** Dos formas:

- **Los más recientes** — mira los chats de arriba de la lista, dentro de la
  ventana de silencio que se configure (por ejemplo, entre 5 y 90 días sin
  hablar). Sirve para el día a día.
- **Barrido del historial** — va al fondo del WhatsApp y avanza **del chat más
  viejo hacia hoy**, de a tandas. Es el modo para recuperar clientes viejos que
  quedaron sin recontactar. Cada corrida sigue donde terminó la anterior, y
  nunca le escribe dos veces a la misma persona.

En "Topes" se elige cuántos chats se leen por corrida. **Para el barrido,
empezar con 10**: tandas chicas que terminan rinden más que tandas grandes que
se cortan por la mitad.

## 1.4 — El horario en que pueden salir mensajes

**Configuración → Cuándo y a qué ritmo sale.** Por defecto es de 9 a 19, de
lunes a viernes, hora de Argentina. Se cambia, o se saca del medio con el botón
**Sin restricción (24/7)**.

## 1.5 — Dar de alta la máquina

**Panel → Dar de alta una máquina:**

- **Identificador** — minúsculas, números y guiones: `mac-rocio`, no `Mac de Rocío`.
- **Nombre del vendedor** — acá sí, con mayúsculas y acentos.

⚠️ **El token se muestra una sola vez.** Anotá en una nota, juntos, el
**identificador** y el **token** (empieza con `sgc_`): son las dos únicas cosas
que la Mac va a preguntar. Si se pierde, se rota desde el panel y sale otro.

La máquina nace **inactiva**. Instalar no es activar.

---

# Parte 2 — En la Mac del vendedor

## 2.1 — Preparar Chrome (con el mouse)

En el Chrome que el vendedor usa todos los días, en este orden:

1. **Instalar la extensión Claude in Chrome** e iniciar sesión con la cuenta de
   Claude de **esta** máquina.
2. **Usarla una vez**: apretar el ícono de Claude y pedirle cualquier cosa. Con
   eso queda registrada en la computadora.
3. **Abrir `web.whatsapp.com`** y escanear el QR con el teléfono del vendedor.
4. **Dar el permiso de sitio**: ícono de Claude → **configuración → permisos de
   sitios → habilitar `web.whatsapp.com`**.

Sobre el punto 4, dos cosas que ahorran una hora:

- **No es el menú de Chrome.** Si entrás por la configuración de Chrome vas a
  ver "Acceso al sitio: todos los sitios", y eso ya está bien: **no es ese**. El
  que falta es el de adentro de la extensión.
- Es el **único paso de toda la instalación que no se puede automatizar**, a
  propósito: es la extensión pidiendo que una persona autorice que un programa
  opere sobre WhatsApp.

## 2.2 — Un comando, y listo

Abrir la **Terminal** (Cmd + barra espaciadora, escribir `Terminal`, Enter) y
pegar esto:

```bash
curl -fsSL https://github.com/martinrodriguez19/centonara-seguimientos/raw/main/instalar.sh | bash
```

Es **una sola línea**, tal cual, de `curl` a `bash`.

Ese comando instala todo lo que hace falta (no hay que tener nada preparado),
baja el programa, averigua solo los datos de la máquina, deja configurado el
arranque automático y lo enciende. En el camino:

- **Pregunta el identificador y el token** — los de la nota de la parte 1.
- **Puede pedir iniciar sesión en Claude Code**, una única vez: correr `claude`
  en la Terminal, entrar con la cuenta de esta máquina, salir escribiendo
  `/exit`, y volver a pegar el mismo comando de arriba.
- **Al final ofrece vincular el navegador de envío** (paso 2.3). Conviene decir
  que sí ahí mismo, con el teléfono a mano.

Si algo falta, el instalador **lo dice en castellano y se detiene**. La
respuesta es siempre la misma: hacer lo que dice y **volver a pegar el mismo
comando**. Es seguro correrlo las veces que haga falta — y correrlo de nuevo es
además la forma de **actualizar** el programa más adelante.

Cuando termina dice **INSTALACIÓN COMPLETA**.

## 2.3 — Vincular el navegador que escribe los mensajes

Para escribir, el sistema usa **un navegador aparte** del que el vendedor usa
todos los días, con su propia sesión de WhatsApp. Eso hace que el sistema nunca
le toque las pestañas ni la sesión al vendedor.

Se vincula escaneando un QR, igual que WhatsApp Web en una computadora nueva:
**WhatsApp del teléfono → Configuración → Dispositivos vinculados → Vincular un
dispositivo.**

El instalador lo ofrece solo al final. Si en su momento se dijo que no, o si
esa sesión vence más adelante, se hace con:

```bash
cd ~/centonara-seguimientos && uv run --directory agente python -m agente.main --vincular
```

---

# Parte 3 — Encender el sistema

## 3.1 — La conversación con el vendedor, y registrarla

El sistema manda mensajes **desde la línea del vendedor, con su nombre**. Eso
tiene que estar hablado y aceptado, no supuesto.

Cuando la conversación ya pasó: en el panel, en la tarjeta de la máquina, botón
**Registrar consentimiento**. Queda con fecha en el historial, y sin eso el
sistema no le encola ningún envío.

## 3.2 — Activar la máquina

En la misma tarjeta, **Activar**. Recién ahí empieza a tomar trabajo.

## 3.3 — La primera corrida, sin enviar nada

En el panel, **Generar seguimientos**. Lo que va a pasar:

1. El sistema lee los chats (unos minutos; se ve trabajar a Chrome solo).
2. Para los contactos que están agendados con nombre, abre el chat y busca el
   número real — sin eso no se le puede escribir a nadie con seguridad.
3. Redacta un mensaje por cada chat que valga la pena, y los deja en
   **Revisar borradores**.

Ahí se leen uno por uno. Se pueden editar, aprobar o descartar.

Dos resultados que **parecen fallas y no lo son**:

- **Pocos borradores o ninguno**: casi todos los chats son de números que no
  están en destinos permitidos (paso 1.2), o el sistema ya les escribió hace
  poco.
- **Borradores apartados con un motivo**: el redactor no encontró de qué
  hablar —una conversación que fue sólo "ok, gracias"— y se negó a inventar.
  Se pueden escribir a mano ahí mismo, o descartar.

## 3.4 — Dejar borradores, o enviar

Cuando los borradores se ven bien, hay dos botones (D30):

- **Dejar borradores**: el sistema abre cada chat, verifica el contacto,
  escribe el mensaje y **no lo envía** — queda como borrador en el WhatsApp del
  vendedor, que lo manda con un click cuando quiera. Ojo: mientras ese borrador
  esté sin mandar, el sistema no vuelve a escribir en ese chat (lo detecta
  ocupado y aborta, a propósito).
- **Envío**: los manda **de a uno, con pausas al azar**, sólo a los números
  permitidos, y frenando todo si los tres primeros fallan.

---

# El día a día, una vez andando

- **El vendedor no hace nada.** Prende la Mac y todo arranca solo. Si el agente
  se cae, se vuelve a levantar solo.
- **El responsable** entra al panel, aprieta *Generar seguimientos*, revisa los
  borradores y manda los que le gustan.
- **Tres cosas vencen cada tanto** y hay que rehacerlas. No son fallas:

| Qué vence | Cómo se ve | Cómo se arregla |
|---|---|---|
| La sesión de WhatsApp del vendedor | Chrome pide el QR | Escanearlo de nuevo |
| La sesión del navegador de envío | Un envío falla diciendo que no hay sesión | Correr el comando del paso 2.3 |
| La sesión de Claude Code | Un error que dice *"la sesión de Claude Code venció"* | En la Terminal: `claude`, iniciar sesión, `/exit` |

---

# Si algo no anda

| Lo que se ve | Qué es |
|---|---|
| `Claude in Chrome requires permission` | Falta el permiso de la extensión (paso 2.1, punto 4). Lo dice el navegador, por eso no aparece en ningún log |
| La máquina figura "sin conexión" | La Mac está apagada, sin internet, o el agente se detuvo. Volver a correr el comando del paso 2.2 lo revive |
| Una corrida queda "en curso" para siempre | Botón **Cancelar corrida** en el panel. Lo pendiente se descarta y lo ya generado queda en revisión |
| La corrida falla por tiempo | La tanda era muy grande. Bajar "Chats a leer por máquina" a 10 y volver a disparar |
| El vendedor cerró Chrome | No hay que hacer nada: el sistema lo abre solo cuando necesita leer |
| El panel muestra un error raro | Reportarlo. Los mensajes del panel están escritos para quien lo usa, no para quien lo programó |

---

# Apéndice para quien mantiene el sistema

**Qué quedó instalado en la Mac:** el proyecto en `~/centonara-seguimientos`,
dos servicios de arranque automático (`com.centonara.agente` y
`com.centonara.chrome`, en `~/Library/LaunchAgents/`), y las herramientas `uv` y
`claude` en `~/.local/bin`. Los logs, en `~/Library/Logs/centonara/`.

**Los tres modos del agente**, en el archivo `~/centonara-seguimientos/.env`,
línea `AGENTE_MODO`:

| Modo | Qué hace |
|---|---|
| `simulado` | No toca ningún navegador. Para verificar que la máquina está viva. ⚠️ Todos los envíos y borradores "fallan" con *no se pudo abrir el chat*: si eso pasa en todos, la máquina quedó en este modo |
| `prueba` | Abre el chat, verifica la identidad, escribe el mensaje **y lo deja como borrador, sin enviarlo** (D30) |
| `real` | Lo mismo, y puede apretar enviar |

**La máquina pone el techo.** Una Mac en `prueba` nunca aprieta enviar, aunque
desde el panel se pida un envío real: a lo sumo deja el borrador. El modo de
cada máquina se ve en su tarjeta del panel.

Después de cambiarlo:

```bash
launchctl kickstart -k gui/$(id -u)/com.centonara.agente
```

**Cuando WhatsApp cambie por dentro** y los mensajes dejen de salir, esto dice
exactamente qué se rompió, abriendo el chat de un número de prueba y sin enviar
nada:

```bash
cd ~/centonara-seguimientos && uv run --directory agente python -m agente.main --verificar-selectores --chat +549XXXXXXXXXX
```

**Para entregar el sistema a otra empresa** (o para limpiar las pruebas):
Configuración → **Empezar de cero**. Borra corridas, borradores, mensajes y los
números que el sistema había averiguado, y deja la lista de destinos vacía otra
vez. No borra el historial de auditoría — ese registro es inmutable a propósito,
ni siquiera el sistema puede borrarlo — ni toca los chats de WhatsApp de nadie.

**Actualizar el programa:** volver a correr el comando del paso 2.2. No vuelve a
preguntar nada.
