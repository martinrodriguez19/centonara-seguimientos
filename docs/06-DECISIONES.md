# 06 — Decisiones

> Si algo del sistema te parece raro, buscalo acá antes de cambiarlo. Probablemente hay una razón.
>
> Toda decisión nueva se agrega **antes** de implementarse. Cada una tiene: contexto, opciones,
> qué se eligió y qué la revertiría.

---

## Vigentes

### D1 — Sólo se guarda un resumen de una línea de las conversaciones

**Contexto.** El MVP no guardaba nada. Con base de datos sí se puede. Los clientes del cliente son
terceros que no participaron de esta decisión.

**Opciones.** (a) La conversación completa. (b) Los últimos N mensajes. (c) Un resumen de una línea.

**Decisión: (c), y el resumen se borra a los 90 días.** El texto que **nosotros** enviamos se
guarda indefinidamente: es dato propio y es la defensa ante un reclamo.

**Cómo se implementa, porque el camino obvio está mal.** No con un índice TTL: un TTL de Mongo
borra el documento entero, así que se llevaría puesto el mensaje enviado junto con el resumen. Es
una tarea diaria que hace `$unset` del campo (`core/esquema.purgar_resumenes`).

**Por qué.** El resumen alcanza para redactar y para el triage. Guardar más aumenta mucho la
exposición sin mejorar el producto.

**Qué la revertiría.** Que la calidad de los borradores resulte insuficiente sin más contexto. Ahí
se evalúa (b) con TTL corto, nunca (a).

---

### D2 — Una cuenta de Claude por máquina, sobre el Enterprise del cliente

**Contexto.** El sistema usa `claude -p` con sesión iniciada, no API key. Una API key **desactiva**
la integración con Chrome, así que no es alternativa.

**Decisión: cada Mac inicia sesión con su propia cuenta, dentro del Claude Enterprise que el
cliente ya tiene.** No se compran suscripciones individuales.

**Por qué no una cuenta compartida entre las máquinas.** Dos problemas: los términos de servicio, y
los límites de uso — varias máquinas compitiendo por la misma cuota se frenan entre ellas justo
cuando corren todas juntas, que es siempre, porque las dispara un botón.

**Lo que hay que verificar antes de la fase 2**, porque no lo sabemos y cambia el plan si sale mal:

1. Que el administrador del Enterprise pueda asignar un asiento a cada vendedor. Probablemente no
   sean miembros de la organización hoy.
2. **Que la extensión Claude in Chrome esté habilitada por la política de la organización.** Un
   administrador de Enterprise puede restringir funciones, y si ésta está apagada el sistema no
   funciona en ninguna máquina. Es una llamada al administrador, no una tarea técnica.
3. Que el límite de uso por asiento aguante una corrida diaria de 20 chats con el navegador
   abierto. Es lo que mide F3.8.

**Qué cambia respecto de la versión anterior.** Antes esto era una compra que bloqueaba la fase 2 y
era la línea de gasto más grande del proyecto. Con Enterprise deja de ser una compra y pasa a ser
una tarea de administración — más barato y más rápido, pero con una dependencia nueva: la política
de la organización.

---

### D3 — Un borrador vence a las 24 h

**Contexto.** Entre que se genera y que se envía puede pasar tiempo, y una Mac puede estar apagada.

**Decisión: a las 24 h el borrador se descarta.** Aparece en el historial por si se quiere
recuperar a mano.

**Por qué.** Un mensaje que sale con contexto de anteayer es peor que uno que no sale. Acumular
genera una avalancha al día siguiente, que es exactamente el patrón que dispara bloqueos.

---

### D4 — Revisión antes de enviar, no aprobación mensaje por mensaje

**Contexto.** El dueño no quiere aprobar de a uno. Hay días en que no va a poder mirar.

**Decisión: la corrida genera, el dueño revisa si quiere, y aprieta enviar.** El envío es un
segundo acto explícito, no un temporizador.

**Por qué.** El plan anterior tenía una ventana de veto donde la inacción enviaba sola. Eso
requería que el dueño entendiera que no hacer nada equivale a aprobar — la confusión más probable
de toda la interfaz. Con el envío detrás de un segundo botón, la inacción no manda nada, y el
dueño no tiene que aprobar de a uno: aprueba la tanda.

Lo que esto no resuelve es el riesgo de contenido: el modelo redacta y puede que nadie lea. De ahí
el triage, que aparta los casos donde un error cuesta caro.

**Qué la revertiría.** Que el dueño pida que salga solo. Se implementa con un temporizador
configurable, pero apagado por defecto.

---

### D5 — El envío es determinístico, no conducido por el modelo

**Contexto.** El MVP hacía todo con `claude -p --chrome`. El riesgo número uno es escribir en el
chat equivocado.

**Opciones.** (a) El modelo abre el chat, verifica y envía. (b) Código con selectores (Playwright).

**Decisión: (b).** El modelo se queda en leer y redactar, donde es insustituible.

**Por qué.**
- **Precisión.** `assert header == esperado` es más confiable que un modelo interpretando una
  captura. El riesgo más caro se mitiga mejor con una aserción que con una instrucción.
- **Costo.** El MVP midió USD 0,086 una consulta trivial y USD 0,258 abrir una pestaña. Un envío
  son 6 a 10 interacciones con la página. El envío conducido por modelo era el mayor riesgo
  económico del proyecto.
- **Reproducibilidad.** Un fallo determinístico se depura; uno del modelo, no.

**Contrapartida aceptada.** Los selectores cambian sin aviso. Mitigado con: un solo archivo, falla
cerrada, y chequeo antes de cada corrida.

---

### D6 — Backend en Render, agentes que consultan

**Contexto.** El MVP tenía n8n empujando a una IP fija de la LAN. Requiere IP fija y regla de
firewall por máquina.

**Decisión de topología: los agentes consultan por HTTPS saliente.** Elimina firewall, IP fija y
VPN. Permite trabajo remoto. Si la Mac está apagada, el job espera. La consulta es el latido. La
Mac no abre ningún puerto.

**Decisión de hosting: Render**, con MongoDB Atlas. Un VPS de USD 5 estaría sobrado, pero alguien
tiene que parchear el sistema operativo, mantener Docker y vigilar el disco — trabajo que no
aporta al producto y que con un equipo chico es lo primero que se descuida.

El argumento que decide: el hosting es la línea de gasto más chica del proyecto, y con el Claude
Enterprise ya pagado por el cliente (D2), es directamente la única. Discutir entre USD 5 y USD 20
de infraestructura mientras se gasta tiempo de equipo en mantenerla es optimizar el lugar
equivocado.

---

### D7 — La cola es MongoDB, no Redis

**Decisión.** `findOneAndUpdate` con `sort` da exclusión mutua sin condiciones de carrera, y
`disponible_desde` implementa el jitter sin más infraestructura. Menos piezas que mantener.

**Qué la revertiría.** Superar unos miles de jobs diarios.

---

### D9 — El agente es un LaunchAgent, no un LaunchDaemon

**Decisión.** `~/Library/LaunchAgents/`, con trigger al iniciar sesión.

**Por qué.** Chrome, la extensión y el native messaging viven en la sesión interactiva del usuario.
Un LaunchDaemon corre fuera de esa sesión y no ve ese Chrome. No es configurable: es cómo funciona
el aislamiento de sesiones. (Reemplaza a la decisión equivalente sobre Task Scheduler de Windows.)

---

### D12 — Nombres de dominio en español

**Decisión.** `mensajes`, `vendedores`, `corridas`, `guardrails`. Estructura técnica en inglés.

**Por qué.** Suena raro la primera vez. Es mucho peor traducir mentalmente entre lo que dice el
cliente en una reunión y lo que dice el código.

---

### D13 — Cloudflare adelante de Render

**Decisión: DNS y proxy, plan gratuito.** Ya está configurado y no cuesta nada mantenerlo.

⚠️ **Límite a tener presente.** Cloudflare corta las peticiones de más de **100 segundos** en los
planes Free, Pro y Business. Nuestra consulta del agente es instantánea, así que no toca ese
límite — pero está anotado para que nadie lo descubra por las malas si algún día se agrega un
endpoint largo.

---

### D16 — El parque es macOS *(nueva)*

**Contexto.** Toda la documentación anterior asumía Windows 11: Task Scheduler, `%PROGRAMDATA%`,
PyInstaller, Inno Setup, "Windows nativo, no WSL". El parque real es Mac.

**Decisión: se reescribe todo lo del agente para macOS.** LaunchAgent, `/opt/centonara`, permisos
de Automatización, sin empaquetado firmado por ahora.

**Consecuencias.** Dos de los siete problemas del MVP desaparecen (el corte de `cmd.exe` en el
salto de línea, y `cp1252` rompiendo acentos). Aparece una lista nueva —Gatekeeper, permisos de
privacidad— que **todavía no conoce nadie**, porque el MVP nunca corrió en Mac.

Por eso todo lo de macOS quedó junto y al final (fase 5). Es plomería —cómo arranca el programa,
qué permisos pide el sistema, cómo se instala— y no cambia lo que el producto hace. Las fases 1 a
4 se construyen desde Windows, donde el MVP ya está validado, y el código que sale de ahí sirve
igual en la Mac: Python es Python, y Playwright contra una página web es el mismo Playwright.

---

### D17 — Un solo entorno: producción *(nueva)*

**Contexto.** El plan anterior tenía staging y producción completos: ocho servicios en Render,
dos proyectos de Atlas, dos crons de backup, dos instancias de n8n, y un despliegue disparado por
CI para que un push con los tests rotos no llegara a staging.

**Decisión: se elimina staging. Se prueba en producción.**

**Por qué.** No hay usuarios del panel todavía y no hay mensajes reales saliendo: el riesgo de
probar en producción es aproximadamente cero, y el costo de mantener el espejo ya se pagó — cinco
de los primeros dieciséis commits del proyecto se fueron en infraestructura duplicada.

Lo que protege en su lugar es `destinos_permitidos` (R4): mientras la lista tenga sólo números de
prueba, ninguna corrida en producción puede alcanzar a un cliente real.

**Qué la revertiría.** El día que haya vendedores activos mandando mensajes reales todos los días,
volver a tener un lugar donde ensayar cambios pasa a valer lo que cuesta.

---

### D18 — Se elimina n8n *(nueva)*

**Contexto.** n8n hacía tres cosas: un cron de disparo, un aviso de retenidos y unas alertas. A
cambio costaba dos servicios, dos discos, dos claves de cifrado, un runbook, tres commits de
depuración (puerto, heap, autenticación) y un problema de seguridad real — desde la versión 1.0
n8n no tiene autenticación básica y la cuenta de dueño se la queda quien llegue primero a la URL.

**Decisión: se elimina.** Los horarios los maneja APScheduler dentro del proceso de FastAPI. El
disparo lo hace el botón.

**Por qué se había puesto.** Porque es visible y el cliente puede tocarlo. Pero la regla del
proyecto era que n8n no puede tener lógica de negocio — con lo cual lo que el cliente podía tocar
ahí no cambiaba nada. Se pagaba el costo de la pieza sin cobrar su beneficio.

**Qué la revertiría.** Que el cliente pida integraciones con herramientas suyas (un CRM, una
planilla). Ahí n8n vuelve a tener sentido, y vuelve como integrador, no como cerebro.

---

### D19 — Sin plazos, sin ventana de despliegue *(nueva)*

**Contexto.** El plan anterior comprometía 14 semanas (18 "realistas"), sprints con duración fija,
y una regla de no desplegar a producción después de las 12:00 ni un viernes, implementada como
guarda en el CI.

**Decisión: las fases terminan por criterio verificable, no por fecha. Se despliega cuando está
listo.**

**Por qué.** El sistema no corre solo: si un despliegue rompe algo, no sale ningún mensaje hasta
que alguien apriete el botón. La ventana horaria protegía contra una corrida automática de las
13:00 que ya no existe.

Y sobre los plazos: la parte más incierta del proyecto depende de WhatsApp Web y de una
integración con el navegador, ninguna de las dos bajo nuestro control. Un plazo ahí no informa,
sólo obliga a apurar.

---

### D20 — Ocho guardrails, no veinte *(nueva)*

**Contexto.** El plan anterior especificaba 20 guardrails, casi todos implementados dos veces
—backend y agente— con el argumento de que "el agente no confía en el backend", y 100% de
cobertura exigida sobre los 20.

**Decisión: ocho.** Los que cubren un modo de falla que cuesta caro. El resto se agrega el día que
aparezca el caso.

**Por qué.** Los dos lados los escribe el mismo equipo. La duplicación no agregaba una barrera
independiente: agregaba dos lugares donde el mismo `if` puede quedar desincronizado, que es una
forma nueva de fallar. La duplicación que **sí** se conserva —topes, ventana, pausa, destinos—
tiene otro motivo, mejor: un job puede quedar encolado y ejecutarse minutos después, y en el medio
el tope o la pausa pueden haber cambiado. Esa segunda verificación es contra el paso del tiempo.

---

### D21 — La lista de destinos permitidos reemplaza a "el código de envío no existe" *(nueva)*

**Contexto.** La regla anterior prohibía que el código de envío existiera en el repositorio hasta
el sprint 4, con un job de CI que lo verificaba. La intención era buena: que fuera técnicamente
imposible que saliera un mensaje. El efecto colateral era que **prohibía explorar la parte más
incierta del sistema durante seis semanas**.

**Decisión: el código de envío puede existir desde el primer día, y lo que garantiza que no llegue
a un cliente real es `configuracion.destinos_permitidos`.**

**Por qué es mejor.** La regla vieja dejaba de aplicar el día que el código se escribía, y a partir
de ahí no quedaba ninguna garantía estructural. La lista sigue siendo útil después: es lo que
acota el piloto, y es lo que se usa el día que haya que restringir el sistema de nuevo.

---

### D22 — Login con contraseña única *(nueva)*

**Contexto.** El plan anterior usaba Auth.js con magic links por correo, lo que requiere una cuenta
de correo saliente, un proveedor SMTP y una dependencia externa más.

**Decisión: una contraseña en variable de entorno y una cookie de sesión firmada.**

**Por qué.** Entran una o dos personas. El magic link resuelve el problema de administrar muchos
usuarios, que no tenemos.

**Qué la revertiría.** Que entren los vendedores al panel, y no sólo el dueño.

---

### D23 — El token de máquina se hashea con SHA-256, no con Argon2id *(nueva)*

**Contexto.** El plan anterior pedía Argon2id para los tokens de las máquinas, copiando lo que se
hace con contraseñas.

**Decisión: SHA-256.**

**Por qué.** Argon2 y bcrypt existen para secretos que elige un humano: tienen poca entropía y se
pueden adivinar probando, así que conviene que cada intento sea lento. Este token son 32 bytes de
`secrets.token_urlsafe` — nadie lo va a encontrar por fuerza bruta, y un KDF lento sólo agregaría
una dependencia y latencia a una consulta que corre cada diez segundos por máquina.

SHA-256 además es determinístico, lo que permite **buscar la máquina por el hash con un índice**.
Con Argon2 (salt por registro) habría que recorrer todas las máquinas comparando una por una.

**Lo que sí se conserva, que es lo que importaba:** el token en claro no se guarda en ningún lado.
Se muestra una vez al dar de alta la máquina y después no se puede recuperar.

**Qué la revertiría.** Que alguna vez el token lo elija una persona en vez de generarse. Ahí vuelve
a ser un secreto de baja entropía y Argon2 vuelve a ser lo correcto.

---

### D24 — El envío usa un navegador dedicado, no el Chrome del vendedor *(revisa F4.2)*

**Contexto.** F4.2 había elegido CDP sobre el Chrome del vendedor, apoyada en una medición del
24/8/2026 en Chrome 151: pasar `--user-data-dir` explícito —aunque apuntara al directorio de
siempre— bastaba para que el puerto de depuración abriera. **Chrome 152 cerró esa puerta**, y se
verificó en la primera Mac real ese mismo día: con la ruta explícita del directorio por defecto,
Chrome rechaza el puerto con `DevTools remote debugging requires a non-default data directory`.
No es un bug nuestro ni una configuración: es Google blindando las cookies del perfil real contra
CDP, y va a seguir en esa dirección.

**Opciones.** (a) CDP sobre el perfil del vendedor — muerta en Chrome 152. (b) Un directorio de
datos dedicado lanzado por LaunchAgent con el puerto, y CDP contra ese. (c) Un contexto
persistente de Playwright sobre un directorio dedicado, que el agente abre sólo cuando envía.
(d) Enviar por la extensión, como `LISTAR` — descartada: el envío tiene que ser determinístico y
barato, y un modelo apretando "enviar" no es ninguna de las dos cosas.

**Decisión: (c).** `ENVIAR` corre sobre `launch_persistent_context` con el Chrome real del
sistema y una carpeta propia (`~/Library/Application Support/Centonara/Chrome`). La sesión de
WhatsApp de esa carpeta se vincula una vez, al instalar (`--vincular`), y usa uno de los cuatro
dispositivos que WhatsApp permite. `LISTAR` no cambia: sigue por la extensión, en el Chrome del
vendedor.

**Por qué (c) y no (b).** Hacen lo mismo, pero (b) arrastra todo lo que esta semana demostró ser
frágil: el LaunchAgent con flags, el puerto que hay que verificar, el "Chrome tiene que estar
cerrado del todo", y la carrera con la instancia del Dock. (c) no tiene puerto, no tiene launchctl
para el navegador del motor, y no pelea con la instancia del vendedor porque es otro proceso con
otra carpeta. Menos piezas móviles en la máquina de un vendedor gana.

**Costo asumido.** Una segunda sesión de WhatsApp que también expira y hay que re-vincular
(escaneando el QR en la ventana que abre `--vincular`). Y una ventana de Chrome visible durante
los envíos — que además es deseable: lo que el sistema hace en la máquina del vendedor se ve.

**Qué la revertiría.** Que WhatsApp trate distinto a la sesión del dispositivo vinculado extra
(bloqueos, verificaciones), o que el cliente no acepte el dispositivo adicional. Ahí se evalúa (d)
con guardas determinísticas alrededor, nunca (a), que ya no existe.

---

### D25 — Los chats sin teléfono se resuelven, no se descartan; y la lectura apunta a los fríos

**Contexto.** Especificación del dueño (25/8/2026), y dos realidades que la primera Mac confirmó:
los contactos reales están agendados por **nombre** —el número no está a la vista en la lista, y
en WhatsApp Business está más escondido—, y el caso de uso del sistema son los **clientes fríos**
del historial, no los chats de arriba de la lista.

**Decisión, en dos partes.**

1. **Job `RESOLVER`**: los chats que `LISTAR` trae con `contacto_telefono: null` ya no se
   descartan. Van en lote a un job determinístico que corre en el navegador dedicado —los mismos
   selectores verificados del motor, sin modelo y sin costo por token—, abre cada chat por nombre
   y lee el número real del panel de contacto. Recién con el número se decide R4 y se redacta.
   Lo que no se puede leer con certeza vuelve `null` con motivo: deducir un número sigue prohibido.
   En identidad no se ahorra: es regla del dueño, no optimización pendiente.
2. **Ventana de antigüedad** (`antiguedad_min_dias` / `antiguedad_max_dias`, en la configuración
   del panel): el `LISTAR` recorre la lista hacia atrás buscando chats cuyo silencio caiga en la
   ventana, y el backend la revalida al encolar. Fuera de la ventana no se redacta ni se resuelve.

**Qué la revertiría.** Que abrir N chats por corrida en el navegador dedicado resulte demasiado
lento o demasiado visible en la máquina del vendedor. Ahí se evalúa resolver en tandas más chicas
o cachear números ya resueltos en `contactos`.

---

### D26 — La ventana horaria de envío la maneja el dueño desde el panel

**Contexto.** G6 (ventana 09:00–19:00, lunes a viernes) estaba fija en la configuración sin forma
de editarla, y frenó el primer envío de prueba a las 19:14. El dueño fue explícito: "va a estar
manejado por alguien responsable, no necesita ventanas".

**Decisión: la ventana pasa a ser editable desde Configuración** (horario y días, con `24:00`
como fin-de-día inclusive y un atajo "sin restricción 24/7"). El mecanismo no se borra: sigue
existiendo, con su valor por defecto conservador para instalaciones nuevas, y cada cambio queda
en la auditoría como el resto de la configuración. El sistema no decide por el dueño; deja
registro de lo que el dueño decidió.

**Qué la revertiría.** Un bloqueo de línea o reporte de spam atribuible a horarios no humanos.
Ahí la conversación es sobre el valor configurado, no sobre el mecanismo — que para eso quedó.

---

### D27 — Contexto de empresa en cada redacción, y barrido del historial con cursor

**Contexto.** Dos pedidos del dueño para cerrar el producto (25/8/2026). Uno: su cliente tiene
toda la información de la empresa —productos, promociones, tono— y quiere que el redactor escriba
con eso, no a ciegas. Dos: el caso de negocio real es recuperar a los clientes viejos: recorrer el
historial de WhatsApp del más antiguo hacia hoy, de a tandas diarias, sin recontactar a nadie.

**Decisión, en tres partes.**

1. **`contexto_empresa`**: un texto libre del dueño en Configuración (tope 6000 caracteres) que
   viaja en el payload de cada `REDACTAR`. No viola la regla "el prompt no viaja por la red": lo
   que viaja es una **variable acotada** —como ya lo eran los resúmenes— que el prompt fijo de la
   máquina interpola entre marcas explícitas y enmarca como dato de referencia, no instrucciones.
   Reusar el sistema para otro rubro es cambiar ese texto, sin deploy.
2. **Barrido del historial** (`modo_lectura: "barrido"`): la posición en la lista de WhatsApp no
   sirve de cursor —se reordena con cada mensaje—, así que el cursor es **la antigüedad**: cada
   máquina guarda en su documento hasta qué antigüedad llegó (`barrido.hasta_dias`) y los nombres
   de la última tanda para desempatar la frontera. La primera corrida va al fondo; cada una pide
   "los N más viejos con antigüedad ≤ cursor, salteando los ya vistos". Una tanda corta = llegó al
   presente, y queda marcado. La ventana de antigüedad del modo "recientes" no aplica: el barrido
   es su propia estrategia.
3. **No repetir ni pagar de más**: el anti-duplicado corre **antes** de redactar (un mensaje no
   descartado en los últimos `dias_anti_duplicado` bloquea la redacción — antes se pagaba y el
   triage lo tiraba después), y los números que el `RESOLVER` averigua quedan en la colección
   `telefonos` (máquina + nombre → número), así el barrido no reabre chats ya resueltos.

**Qué la revertiría.** Que la antigüedad que reporta el modelo sea demasiado imprecisa como cursor
(tandas que se pisan o se saltean chats). Ahí se evalúa un cursor híbrido con más nombres
recordados, o pedir al modelo la fecha del último mensaje en vez de días.

---

## Descartadas

| Idea | Por qué no |
|---|---|
| Microservicios, Kubernetes | Es una herramienta para un equipo comercial chico |
| WebSocket o long-poll de 25 s | Un `GET` cada 10 s alcanza, y no depende de que Render y Cloudflare sostengan conexiones largas |
| Que el modelo decida a quién escribirle | Regla R3. **Nunca** |
| "Autorizamos al modelo en el prompt" | Ya se probó en el MVP y **empeoró** el problema: es el patrón exacto de una inyección. El contexto va en `CLAUDE.md`, fuera del pedido |
| Retener los chats de más de 60 días | Contradecía el criterio validado del MVP. La antigüedad no es por sí sola una señal de riesgo |
| `ChannelAdapter` para la API oficial de WhatsApp | Una interfaz para una implementación que está fuera de alcance sin fecha. Se define el día que haga falta |
| PyInstaller con autoactualización firmada | En macOS, Gatekeeper vuelve a poner el binario en cuarentena en cada reemplazo. Con pocas máquinas, `git pull` es más corto |
| Multi-cliente | Un solo cliente. Se revisa si aparece un segundo |
| App móvil | El panel es responsive |
