# Sistema de Seguimiento Comercial — puesta en marcha

> **Qué hace este sistema.** Lee los chats de WhatsApp de cada vendedor, busca
> los clientes que quedaron sin respuesta, redacta un mensaje de seguimiento
> para cada uno, y lo deja como borrador en el chat para que el vendedor lo
> mande. Sólo si en el panel se prende el **envío automático**, los manda solo,
> de lunes a viernes dentro del horario de envío.
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

Y tres cosas que conviene confirmar antes:

- Que la extensión **Claude in Chrome** esté permitida por la organización. Si
  está bloqueada por política, no funciona en ninguna máquina y no hay forma de
  arreglarlo desde el sistema.
- Que la Mac tenga **macOS 13 o más nuevo** (`sw_vers -productVersion` en la
  Terminal). Con menos, el instalador se detiene y dice que hay que seguir el
  apartado "Mac con macOS anterior a 13" del panel (Ajustes → Instalar y reparar).
- Contar con **pegar el instalador dos veces**: la primera se detiene pidiendo
  iniciar sesión en Claude Code. No es una falla.

**La misma guía, con botón para copiar cada comando, está en el panel:** Ajustes
→ Instalar y reparar. Y con las diferencias de una PC con Windows, en
[`SOP-instalar-windows.md`](SOP-instalar-windows.md).

---

# Parte 1 — En el panel

Se hace desde cualquier computadora, sin la Mac delante.

**El panel:** https://frontend-produccion.onrender.com

## 1.1 — Contarle al sistema sobre la empresa

**Ajustes → Mensajes → Indicaciones para redactar.**

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

**Ajustes → Seguridad → Destinos permitidos.**

Esta lista es el freno de mano del sistema: **sólo se le escribe a los números
que estén ahí**. Arranca vacía, y vacía significa **a nadie**.

Para las pruebas, cargar dos o tres números propios y nada más. Cuando el
sistema ya demostró que escribe bien, se abre a todos los contactos escribiendo
la palabra `ABRIR` — es un acto deliberado y queda registrado.

> **La confusión más común:** con la lista en números de prueba, una corrida lee
> los chats y **no genera casi nada**. No está roto: está haciendo lo que se le
> pidió.

## 1.3 — Elegir qué chats se siguen

**Ajustes → Qué chats y cuántos.** Dos formas:

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

**Ajustes → Envío y horarios → Horario de envío.** Por defecto es de 9 a 19, de
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
curl -fsSL --http1.1 https://github.com/martinrodriguez19/centonara-seguimientos/raw/main/instalar.sh | bash
```

Es **una sola línea**, tal cual, de `curl` a `bash`. El `--http1.1` no es opcional: en macOS
10.15 el `curl` que viene con el sistema contesta **503** a GitHub sin él, y el error engaña —
parece de GitHub o de la red, y es del `curl`.

Ese comando instala todo lo que hace falta (no hay que tener nada preparado),
baja el programa, averigua solo los datos de la máquina, deja configurado el
arranque automático y lo enciende. En el camino:

- **Pregunta el identificador y el token** — los de la nota de la parte 1.
- **Pide iniciar sesión en Claude Code**, una única vez, y se detiene: correr
  `claude` en la Terminal, entrar con la cuenta de esta máquina, salir escribiendo
  `/exit`, y volver a pegar el mismo comando de arriba.
- **Al final ofrece vincular el navegador de envío** (paso 2.3). Conviene decir
  que sí ahí mismo, con el teléfono a mano.
- **Termina esperando la señal de vida del agente** y dice **QUEDÓ AL DÍA** con
  el commit, y después **INSTALACIÓN COMPLETA**. Si dice **NO QUEDÓ AL DÍA**,
  dice qué falta: hacer eso y volver a pegar el mismo comando. Recién con
  "completa" se sigue con la Parte 3.

Si algo falta, el instalador **lo dice en castellano y se detiene**. La
respuesta es siempre la misma: hacer lo que dice y **volver a pegar el mismo
comando**. Es seguro correrlo las veces que haga falta.

**Actualizar no requiere volver a correrlo.** El instalador deja un tercer
servicio, el actualizador, que corre al iniciar sesión y cada hora y pone el
agente en la versión que fija el panel (Ajustes → Sistema → *Versión del agente*).
El detalle de cada máquina (Máquinas → la máquina) muestra qué versión corre y si está al día.

Si la Mac tenía el proyecto clonado con `git` (la guía original decía eso), el
instalador aparta ese `.git` a `~/.centonara/git-viejo-<fecha>` y sigue solo.
No hay que hacer nada a mano.

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

## 2.4 — Comprobar que quedó bien

El instalador ya lo hace al final. Para volver a mirarlo después, o cuando el
panel dice "sin conexión" con la Mac prendida:

```bash
launchctl list | grep centonara
```

Los tres servicios (chrome, agente, actualizador) con su número de proceso. Un
guion en vez de número es que no está corriendo. Y lo que decide de verdad, la
señal de vida que el agente escribe cada 30 segundos:

```bash
cat ~/.centonara/estado/vivo.json
```

Si `cuando` es de hace más de dos minutos, el agente no está corriendo aunque
el servicio figure. Para levantarlo: `launchctl kickstart -k gui/$(id -u)/com.centonara.agente`.

## 2.5 — Reinstalar desde cero

Cuando una Mac falla y sigue fallando después de volver a correr el instalador,
conviene dejar de arreglarla encima: el instalador conserva el `.env`, el
entorno y lo que sea que esté roto. Reinstalar desde cero son dos comandos.

**Conviene cuando:** la máquina figura sin conexión y el agente no arranca
aunque se lo reinicie; el instalador dice NO QUEDÓ AL DÍA dos veces seguidas por
lo mismo; o se cambió de vendedor o de cuenta en esa computadora.

**1. Desinstalar.** Pide escribir `SI` antes de tocar nada e imprime el
identificador de la máquina:

```bash
curl -fsSL --http1.1 https://github.com/martinrodriguez19/centonara-seguimientos/raw/main/desinstalar.sh | bash
```

Para y borra los tres servicios, mata el agente (también los que hayan quedado
de versiones anteriores) y el navegador de envío, y borra el proyecto, el estado
y los logs. **Conserva** la sesión de WhatsApp del navegador de envío (no hay
que volver a escanear ese QR), el login de Claude Code, y el Chrome del
vendedor, que no se toca nunca. Para borrar también la sesión del navegador de
envío —cuando la Mac cambia de vendedor o de línea— se agrega `-s -- --todo` al
final del comando. En una Mac con macOS anterior a 13 no toca Node ni Claude
Code: al reinstalar no hay que repetir ese rodeo.

**2. Instalar de nuevo:** el comando de 2.2, tal cual. Va a pedir el
identificador y el token; si el token no está anotado, en el panel: Máquinas →
la máquina → ⋯ → **Rotar token**, y usar el nuevo. Tiene que terminar en
**QUEDÓ AL DÍA** e **INSTALACIÓN COMPLETA**.

**3. En el panel** no hay que dar de alta nada: la máquina sigue existiendo y
vuelve sola a "conectada". Si estaba a mitad de una corrida, cancelarla desde el
inicio **antes** de desinstalar. Si estaba pausada o desactivada, sigue
estándolo.

---

# Parte 3 — Encender el sistema

## 3.1 — La conversación con el vendedor, y registrarla

El sistema manda mensajes **desde la línea del vendedor, con su nombre**. Eso
tiene que estar hablado y aceptado, no supuesto.

Cuando la conversación ya pasó: en el panel, en Máquinas → la máquina → menú ⋯, botón
**Registrar consentimiento**. Queda con fecha en el historial, y sin eso el
sistema no le encola ningún envío.

## 3.2 — Activar la máquina

En la misma tarjeta, **Activar**. Recién ahí empieza a tomar trabajo.

## 3.3 — La primera corrida: los borradores quedan en los chats

En el panel, **Generar seguimientos**. Lo que va a pasar, **sin apretar nada
más** (D36):

1. El sistema lee los chats (unos minutos; se ve trabajar a Chrome solo).
2. Para los contactos que están agendados con nombre, abre el chat y busca el
   número real — sin eso no se le puede escribir a nadie con seguridad.
3. Redacta un mensaje por cada chat que valga la pena.
4. Y a cada mensaje que pasa las reglas lo escribe **como borrador dentro de su
   chat**: abre la conversación, verifica que el número sea el correcto, deja el
   texto escrito y **no aprieta enviar**. Van de a uno, con pausas al azar.

Al día siguiente el vendedor entra a WhatsApp y los borradores están ahí
arriba, listos para mandar con un click. **El sistema nunca envía solo.**

En **Revisar borradores** del panel se ve cómo quedó todo: los que ya están en
los chats, los que el sistema descartó y por qué, y los que necesitan una
decisión. Las señales que aparecen en un borrador ya dejado —"habla de un
reclamo", "menciona un precio"— son **información para el vendedor antes de
mandarlo**, no un freno.

Dos resultados que **parecen fallas y no lo son**:

- **Pocos borradores o ninguno**: casi todos los chats son de números que no
  están en destinos permitidos (paso 1.2), o el sistema ya les escribió hace
  poco.
- **Borradores apartados con un motivo**: el redactor no encontró de qué
  hablar —una conversación que fue sólo "ok, gracias"— y se negó a inventar.
  Se pueden escribir a mano ahí mismo, o descartar.

> Si el sistema está frenado con el botón rojo cuando termina la generación,
> los borradores **esperan** en vez de descartarse. Al soltar el freno, el
> botón **Revisar ahora** del panel los retoma.

## 3.4 — El envío de verdad (opcional, y es otro botón)

Dejar borradores es el circuito normal: el vendedor manda a mano. El **Envío**
es lo otro, y sigue siendo una decisión explícita de una persona: pide escribir
la cantidad exacta de mensajes que van a salir.

- Los manda **de a uno, con pausas al azar**, sólo a los números permitidos, y
  dentro del horario configurado.
- Si los tres primeros de una máquina fallan, esa máquina se frena sola y las
  demás siguen (D35). El panel lo avisa con el botón para continuar al lado.

⚠️ Un chat que ya tiene un borrador dejado **no acepta un envío después**: el
sistema lo detecta ocupado y aborta, a propósito, para no pisar lo que el
vendedor tenía escrito.

---

# El día a día, una vez andando

- **El vendedor** prende la Mac y todo arranca solo; si el agente se cae, se
  vuelve a levantar solo. Su trabajo con el sistema es uno: a la mañana, mirar
  los borradores que aparecieron en sus chats y mandar los que le sirven.
- **El responsable** entra al panel, aprieta *Generar seguimientos* —
  normalmente el día anterior — y después revisa cómo quedó.
- **Tres cosas vencen cada tanto** y hay que rehacerlas. No son fallas:

| Qué vence | Cómo se ve | Cómo se arregla |
|---|---|---|
| La sesión de WhatsApp del vendedor | Chrome pide el QR | Escanearlo de nuevo |
| La sesión del navegador de envío | El panel avisa *"venció la sesión del motor"* — lo revisa solo, antes de que falle una corrida | Correr el comando del paso 2.3 (`RUNBOOK-revincular-whatsapp.md`) |
| La sesión de Claude Code | La corrida falla con *"la sesión de Claude Code venció"* u *"OAuth session expired"* | En la Terminal: `claude`, iniciar sesión (o `/login`), `/exit`. Después, cancelar la corrida frenada en el panel y volver a disparar |

---

# Si algo no anda

| Lo que se ve | Qué es |
|---|---|
| El instalador dice "macOS 13 o más" y se detiene | La Mac tiene un sistema más viejo. Seguir "Mac con macOS anterior a 13" en el panel (Ajustes → Instalar y reparar) y volver a pegar el instalador |
| El instalador se detiene en [2/8] pidiendo iniciar sesión | Claude Code no tiene sesión en esta Mac. Es lo normal en una máquina nueva: `claude` → iniciar sesión → `/exit` → el mismo comando de nuevo |
| Termina en **NO QUEDÓ AL DÍA**: el agente no dio señal de vida | Los servicios quedaron, pero el agente se cae al arrancar. `tail -n 50 ~/Library/Logs/centonara/agente.err` dice por qué; si no se entiende, 2.5 |
| `Claude in Chrome requires permission` | Falta el permiso de la extensión (paso 2.1, punto 4). Lo dice el navegador, por eso no aparece en ningún log |
| La máquina figura "sin conexión" | La Mac está apagada, sin internet, o el agente se detuvo. 2.4 dice cómo mirarlo; volver a correr el comando del paso 2.2 lo revive; si sigue, 2.5 |
| Una corrida queda "en curso" para siempre | Una máquina de la corrida está apagada y su trabajo espera. Botón **Cancelar corrida** en el panel, **antes** de la hora de la programada: si a esa hora hay una en curso, la de ese día se saltea |
| La corrida falla por tiempo | La tanda era muy grande. Bajar "Chats a leer por máquina" a 10 y volver a disparar |
| El vendedor cerró Chrome | No hay que hacer nada: el sistema lo abre solo cuando necesita leer |
| El panel muestra un error raro | Reportarlo. Los mensajes del panel están escritos para quien lo usa, no para quien lo programó |

---

# Apéndice para quien mantiene el sistema

**Qué quedó instalado en la Mac:** el proyecto en `~/centonara-seguimientos`,
tres servicios de arranque automático (`com.centonara.agente`,
`com.centonara.chrome` y `com.centonara.actualizador`, en
`~/Library/LaunchAgents/`), una copia del actualizador en `~/.centonara/bin/`, la
señal de vida en `~/.centonara/estado/vivo.json`, la sesión del navegador de
envío en `~/Library/Application Support/Centonara/Chrome`, y las herramientas
`uv` y `claude` en `~/.local/bin`. Los logs, en `~/Library/Logs/centonara/`; el
del actualizador es `actualizador.log`. Todo eso —salvo la sesión del navegador
de envío, `uv` y `claude`— es lo que borra `desinstalar.sh` (2.5).

**El agente no tiene modo (D32).** Instalado, está siempre operativo: si un
mensaje queda como borrador o se envía lo decide el botón que se apretó en el
panel, no un archivo de la Mac. La variable `AGENTE_MODO` que aparecía acá en
versiones anteriores ya no existe — si quedó en un `.env` viejo, se ignora.

Para desarrollo existe el flag `--simulado` (corre contra una página en
memoria, sin navegador); en ese estado la tarjeta de la máquina en el panel
muestra "simulado" en amarillo, y todos los envíos y borradores "fallan" con
*no se pudo abrir el chat*. Ninguna máquina llega ahí por configuración: hay
que pedirlo en la línea de comandos, cada vez.

**Cuando WhatsApp cambie por dentro** y los mensajes dejen de salir, esto dice
exactamente qué se rompió, abriendo el chat de un número de prueba y sin enviar
nada:

```bash
cd ~/centonara-seguimientos && uv run --directory agente python -m agente.main --verificar-selectores --chat +549XXXXXXXXXX
```

**Para entregar el sistema a otra empresa** (o para limpiar las pruebas):
Ajustes → Sistema → **Empezar de cero**. Borra corridas, borradores, mensajes y los
números que el sistema había averiguado, y deja la lista de destinos vacía otra
vez. No borra el historial de auditoría — ese registro es inmutable a propósito,
ni siquiera el sistema puede borrarlo — ni toca los chats de WhatsApp de nadie.

**Actualizar el programa:** no hay que hacer nada. El actualizador
(`com.centonara.actualizador`) corre al iniciar sesión y cada hora, pregunta al
panel qué versión toca, y si es otra la baja, la instala y espera a que el
agente vuelva con ella; si no vuelve, restaura la anterior. Para no esperar la
hora:

```bash
bash ~/centonara-seguimientos/agente/instalador/actualizar.sh
```

**Volver a una versión anterior:** desde el panel, Ajustes → Sistema → *Versión
del agente* → pegar el commit. Todas las máquinas van a ése en menos de una hora,
sin tocar ninguna. Vaciar el campo las devuelve a lo último publicado.

**Una PC con Windows:** ver [`SOP-instalar-windows.md`](SOP-instalar-windows.md).
