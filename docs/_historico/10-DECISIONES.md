# 10 — Decisiones

> Registro de decisiones de arquitectura y de producto. **Si algo del sistema te parece raro,
> buscalo acá antes de cambiarlo.** Probablemente hay una razón.
>
> Toda decisión nueva se agrega acá **antes** de implementarse.

---

## Formato

Cada decisión tiene: contexto, opciones evaluadas, qué se eligió y por qué, y qué la revertiría.

---

## D1 — Sólo se guarda un resumen de una línea de las conversaciones

**Contexto.** El MVP no guardaba nada. La v2 con base de datos sí puede. Los clientes del cliente
son terceros que no participaron de esta decisión.

**Opciones.** (a) Guardar la conversación completa. (b) Guardar los últimos N mensajes. (c) Sólo un
resumen de una línea.

**Decisión: (c), con TTL de 90 días.** El texto que **nosotros** enviamos se guarda indefinidamente:
es dato propio y es la defensa ante un reclamo.

**Por qué.** El resumen alcanza para redactar y para el triage. Guardar más aumenta mucho la
exposición sin mejorar el producto. Marco: Ley 25.326.

**Qué la revertiría.** Que la calidad de los borradores resulte insuficiente sin más contexto. En
ese caso se evalúa (b) con un TTL más corto, nunca (a).

---

## D2 — Ocho asientos de plan Anthropic, uno por máquina

**Contexto.** El sistema usa `claude -p` con sesión iniciada, no API key. Una API key **desactiva**
la integración con Chrome, así que no es alternativa.

**Opciones.** (a) Una cuenta compartida entre las 8 máquinas. (b) Ocho asientos individuales.

**Decisión: (b).**

**Por qué.** Una cuenta compartida entre 8 equipos tiene un problema de términos de servicio y otro
de límites de uso: las 8 máquinas compitiendo por la misma cuota se van a frenar entre ellas.
Costo mayor, pero previsible.

---

## D3 — Si la PC está apagada a la hora de envío, el mensaje se descarta

**Contexto.** El envío es a las 13:00. Un vendedor puede abrir la notebook a las 14:30.

**Opciones.** (a) Enviar tarde. (b) Acumular para el día siguiente. (c) Descartar.

**Decisión: (c).** Aparece al día siguiente en revisión posterior por si se quiere recuperar a mano.

**Por qué.** Un mensaje que sale a las 18:00 con contexto de la mañana es peor que uno que no sale.
Acumular genera una avalancha al día siguiente, que es exactamente el patrón que dispara bloqueos.

---

## D4 — Veto, no aprobación: la inacción envía

**Contexto.** El spec original exigía un checkpoint humano obligatorio. El cliente decidió que no
quiere aprobar mensaje por mensaje: hay días en que no va a poder mirar.

**Opciones.** (a) Aprobación obligatoria (la inacción **no** envía). (b) Veto con ventana (la
inacción envía). (c) Full auto sin pantalla.

**Decisión: (b), con ventana de 08:00 a 13:00, más triage.** Configurable a (c) con
`ventana_veto_minutos: 0`.

**Por qué.** El argumento original del spec —*"sin checkpoint no hay barrera entre un prompt mal
ajustado y 160 mensajes"*— apuntaba al **volumen**, y quedó resuelto por D5: el envío es código con
topes duros, no un modelo interpretando un prompt.

Lo que queda es el riesgo de **contenido**: el modelo redacta y nadie lee antes de que llegue a un
cliente real. Ningún tope numérico detecta que respondió un reclamo con una propuesta comercial.

El modelo de veto resuelve la objeción del cliente sin renunciar al freno: los días en que nadie
mira, todo sale igual, sin tocar ningún switch. Y la ventana ya existía entre 08:00 y 13:00; lo
único que se agrega es hacerla visible.

**Sobre la tasa de error.** El criterio acordado es que 1 error cada 100 mensajes es tolerable. A
160 diarios eso son ~1,6 por día, ~35 por mes, ~400 por año. Es una decisión legítima del negocio,
registrada acá en esa unidad para que no se lea como "un caso aislado".

Dos consecuencias que hacen falta igual: **el ajuste del prompt requiere detección** (de ahí la
pantalla de revisión posterior), y **los errores no se distribuyen al azar** — se concentran en el
chat con reclamo abierto, el de 60 días, el que mezcla personal y comercial. De ahí el triage.

**Qué la revertiría.** Dos semanas de datos con tasa de veto cercana a cero → se afloja a (c). Un
incidente serio con un cliente → se endurece a (a).

---

## D5 — El envío es determinístico, no conducido por el modelo

**Contexto.** El MVP hacía todo con `claude -p --chrome`. El riesgo #1 identificado es escribir en
el chat equivocado.

**Opciones.** (a) El modelo abre el chat, verifica y envía. (b) Código con selectores explícitos
(Playwright).

**Decisión: (b).** El modelo se queda en leer y redactar, donde es insustituible.

**Por qué.**
- **Precisión.** `assert header == esperado` es más confiable que un modelo interpretando una
  captura. El riesgo más caro del sistema se mitiga mejor con una aserción.
- **Costo.** El MVP midió USD 0.086 una consulta trivial y USD 0.258 abrir una pestaña. Un envío
  implica 6 a 10 interacciones con la página. A 160 diarios, el envío conducido por modelo era el
  mayor riesgo económico del proyecto.
- **Reproducibilidad.** Un fallo determinístico se depura; uno del modelo, no.

**Contrapartida aceptada.** Los selectores de WhatsApp Web cambian sin aviso. Mitigado con: un solo
archivo de selectores, falla cerrada, y smoke test diario a las 07:00.

---

## D6 — Backend en Render, agentes con polling saliente

**Contexto.** El MVP tenía a n8n empujando a `http://192.168.0.101:8787`. Requiere IP fija y regla
de firewall por máquina.

**Opciones de topología.** (a) Mantener push. (b) VPN entre todas las máquinas. (c) Los agentes
consultan por HTTPS saliente.

**Decisión de topología: (c).** Elimina firewall, IP fija y VPN. Permite trabajo remoto. Si la PC
está apagada, el job queda encolado en vez de fallar. El poll **es** el heartbeat. Y la PC del
vendedor no abre ningún puerto.

### Dónde corre el backend

**Opciones.** (a) VPS propio (Hetzner, DigitalOcean). (b) Plataforma administrada (Render,
Railway). (c) Serverless (Vercel, Cloudflare Workers).

**Decisión: (b), Render.** MongoDB Atlas para la base.

**Por qué no (a).** El VPS no es caro ni chico: un servidor de USD 5 está sobrado para 8 usuarios y
160 mensajes diarios. El problema es el **trabajo recurrente**: alguien tiene que parchear el
sistema operativo, mantener Docker, vigilar el disco y sostener los backups. Es tarea que no
aporta al producto y que con un equipo chico es lo primero que se descuida.

**Por qué no (c).** El sistema necesita conexiones abiertas 25 segundos (long-poll), un scheduler
permanente que despierte a las 13:00, y n8n corriendo como proceso. Nada de eso encaja bien en
serverless.

**El argumento que decide.** El hosting va a ser la línea de gasto más chica del proyecto: los 8
asientos de plan Anthropic cuestan bastante más, todos los meses. Discutir entre USD 5 y USD 40 de
infraestructura mientras el resto cuesta múltiplos de eso es optimizar el lugar equivocado. Se
paga la diferencia y se compra el no tener que pensar en el servidor.

**A verificar en T0.7:** que Render sostenga conexiones de 25 segundos sin cortarlas y que el
worker corra como servicio permanente.

**Qué la revertiría.** Que el costo de Render escale mal al crecer, o que aparezca una limitación
dura con las conexiones largas. En ese caso, VPS con alguien asignado a mantenerlo.

---

## D13 — Cloudflare delante de Render

**Contexto.** Cloudflare no reemplaza al backend: es una capa anterior.

**Decisión: usar Cloudflare para DNS y proxy.** Plan gratuito.

**Qué aporta.** Esconde el origen, filtra tráfico basura y ataques, y centraliza dominio y
certificados.

⚠️ **Límite que hay que tener presente.** Cloudflare corta las peticiones que superan los **100
segundos** en los planes Free, Pro y Business; sólo se puede subir en Enterprise. Nuestro long-poll
es de 25 s, así que entra cómodo. **Si alguien alguna vez lo sube a 120 s, el sistema se rompe sin
causa aparente.** Está anotado acá para que no se descubra por las malas.

---

## D7 — La cola es MongoDB, no Redis

**Opciones.** (a) Redis + ARQ/Celery. (b) MongoDB con `findOneAndUpdate` atómico.

**Decisión: (b).**

**Por qué.** 160 jobs por día no justifican otro servicio. Un `findOneAndUpdate` con `sort` da
exclusión mutua sin condiciones de carrera, y `disponible_desde` implementa el jitter sin más
infraestructura. Menos piezas que mantener, monitorear y respaldar.

**Qué la revertiría.** Superar unos miles de jobs diarios.

---

## D8 — n8n se queda, pero no es el cerebro

**Decisión.** n8n hace horarios, notificaciones e integraciones. **Cero lógica de negocio.**

**Por qué.** Su valor real es que es visible y el cliente puede tocarlo. Pero un tope que vive en
un nodo de n8n lo desconecta cualquiera con acceso al editor. Regla: *todo lo que, si falla, manda
un mensaje que no debía salir, vive en FastAPI.*

---

## D9 — El agente no es un Servicio de Windows

**Decisión.** Task Scheduler con trigger "al iniciar sesión del usuario".

**Por qué.** Chrome, la extensión y el native messaging viven en la sesión interactiva. Un servicio
como `SYSTEM` en la sesión 0 no ve ese Chrome. No es configurable: es cómo funciona el aislamiento
de sesiones. Si alguien propone NSSM, ya se evaluó.

---

## D10 — `ChannelAdapter` desde el día uno

**Decisión.** Definir la interfaz ahora aunque sólo haya una implementación real.

**Por qué.** Cuesta poco y convierte la eventual migración a WhatsApp Cloud API en cambiar una
implementación, en vez de reescribir el producto. Además, `DryRunAdapter` es la forma limpia de
implementar el modo prueba sin `if` desparramados.

---

## D11 — El código de envío no existe hasta el Sprint 4

**Decisión.** Del Sprint 0 al 3, no hay código de envío en el repositorio.

**Por qué.** Mientras se construyen las fundaciones, queremos que sea *técnicamente imposible* que
salga un mensaje. Un tope configurado se puede desconfigurar; un código que no existe, no.

---

## D12 — Nombres de dominio en español

**Decisión.** `mensajes`, `vendedores`, `guardrails`, `corridas`. Estructura técnica en inglés.

**Por qué.** Suena raro la primera vez. Es mucho peor traducir mentalmente entre lo que dice el
cliente en una reunión y lo que dice el código.

---

## D14 — MongoDB Atlas: aislamiento por credenciales, no por red

**Contexto.** `05-REGLAS-INVIOLABLES.md` §5 decía "MongoDB sin exponer a internet". Con Atlas eso
deja de ser cierto tal como está escrito, y una regla que el sistema no cumple es peor que una más
floja que sí cumple.

**La realidad.** Un clúster de Atlas tiene endpoint público con TLS. Lo que lo protege no es la
ausencia de ruta desde internet, sino la lista de IPs permitidas más las credenciales. El
aislamiento de red real (private endpoint, VPC peering) es de los tiers dedicados.

**Y un matiz que reduce el valor de la lista de IPs.** Las direcciones de salida de Render suelen
ser compartidas entre clientes de la plataforma. Si es así, permitir esas IPs habilita a nivel de
red a cualquier cliente de Render en esa región, y **la barrera efectiva son las credenciales**.
La lista de IPs pasa a ser reducción de superficie, no aislamiento. Verificar en la consola apenas
haya acceso.

**Decisión: aceptar la limitación y escribir la regla honestamente.** `05` §5 pasa a decir lo que
el sistema garantiza de verdad:

- TLS obligatorio en la conexión
- Lista de IPs permitidas (reducción de superficie, no aislamiento)
- Credenciales rotables, con procedimiento documentado
- **Un usuario de base de datos por servicio, con permisos mínimos.** El backend no necesita
  `dbAdmin`
- **Credenciales distintas para staging y producción**, sin excepción
- **El clúster de producción no comparte proyecto de Atlas con el de staging**

**Qué costaría cerrarlo del todo.** Aislamiento de red real requiere tier dedicado (M10 o superior)
y confirmar que Render soporte private endpoint fuera de planes empresariales. Tener el número a
mano: el cliente va a preguntar alguna vez.

**Por qué se escribe así y no se deja la regla linda.** Es el mismo problema que `06` §6 describe
con el `CLAUDE.md`: la contradicción entre lo escrito y lo real no es un tema de honestidad, es un
problema técnico. Una regla que nadie cumple le hace creer a alguien que está protegido.

---

## D15 — El despliegue lo dispara el CI, no Render

**Contexto.** Render despliega solo al detectar un push a la rama conectada. Con eso, un push a
`develop` con los tests rotos llega igual a staging, y el CI bloqueante de T0.6 queda decorativo
para lo único que importa.

**Decisión: auto-deploy desactivado en Render.** El despliegue lo dispara GitHub Actions mediante
deploy hook, después de que pasen lint y tests.

**Guarda de ventana horaria.** La regla de `08-CONVENCIONES` —nunca desplegar a producción después
de las 12:00 ni un viernes— se implementa **en el workflow**, no como disciplina humana. El
workflow falla fuera de ventana salvo que se pase `force: true` explícitamente.

Dos razones:

1. La disciplina falla justo cuando importa. Nadie despliega un viernes a las 18:00 estando
   tranquilo: lo hace apurado, arreglando algo, que es cuando peor se juzga.
2. **El override tiene que existir y ser fácil.** Va a haber un día en que haya que desplegar un
   arreglo a las 15:00 porque algo está roto. Una guarda sin salida de emergencia se termina
   desactivando para siempre.

Cada uso del override queda en el log. No para auditar a nadie: si aparece seguido, la ventana está
mal elegida y hay que cambiarla.

---

## Decisiones descartadas

| Idea | Por qué no |
|---|---|
| Microservicios | 8 usuarios, 160 mensajes diarios. Un monolito organizado es lo correcto |
| Kubernetes | Render alcanza y sobra |
| WebSocket en vez de long-poll | Más eficiente, más piezas. Con 8 clientes el ahorro es irrelevante |
| Que el modelo decida a quién escribirle | Regla R4. **Nunca** |
| "Autorizamos al modelo en el prompt" | Ya se probó en el MVP y **empeoró** el problema: es el patrón exacto de una inyección. El contexto va en `CLAUDE.md`, fuera del pedido |
| Multi-tenancy | Un solo cliente. Se revisa si aparece un segundo |
| Construir Coexistence ahora | Fuera de alcance. El adapter deja el camino abierto |
| App móvil | El panel es responsive. No hace falta |
| Guardrails en el prompt | Regla R1 |
