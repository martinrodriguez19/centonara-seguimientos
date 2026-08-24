# Lo que falta, y necesita una máquina

> Todo lo que se podía construir sin tocar un navegador está hecho y probado.
> Esto es lo que queda, ordenado por lo que hay que conseguir antes.
>
> Cada punto dice **por qué** no se pudo hacer sin la máquina. Si alguno se
> puede destrabar de otra forma, mejor: la lista no es un ritual.

---

> **21 de agosto de 2026.** Las tres cosas de esta sección están confirmadas, y la
> máquina de desarrollo (Windows) quedó configurada: el diagnóstico da
> `diagnostico_ok`, los nueve chequeos. Los tres números de prueba están en
> `destinos_permitidos` de la base **local**, normalizados a E.164, con el tope
> por corrida en 3. La lista de producción sigue vacía, que significa "a nadie".
>
> El permiso de sitio ya está concedido y **verificado corriendo**, con
> `--sonda`: la extensión entra a `web.whatsapp.com` y la sesión está
> iniciada. Los cuatro ítems de "configurar esta máquina" están cerrados.

## Antes de nada: tres cosas que no dependen del equipo técnico

Ninguna se resuelve escribiendo código, y las tres tienen plazo de otra persona.
Conviene pedirlas ya, aunque el resto no arranque hoy.

- [x] **Una línea de WhatsApp de prueba.** Que no sea de nadie del equipo ni de
      un vendedor. Se le van a mandar mensajes de verdad y puede terminar
      bloqueada.
- [x] **Confirmar con el administrador del Claude Enterprise** que la extensión
      **Claude in Chrome esté habilitada por política de la organización.**
      ⚠️ Si está restringida, el sistema no funciona en ninguna máquina y no es
      algo que se arregle desde el código. Es una llamada, no una tarea técnica,
      y es lo único que puede frenar el proyecto entero.
- [x] **Tres contactos propios** que acepten recibir mensajes de prueba, para el
      final de la fase 4.

---

## A — ~~Se destraba con el acceso a npm~~ · **resuelto por el CI**

*Estaba bloqueado por: la red a `registry.npmjs.org` cortada desde la máquina
donde se escribió (falla el TLS, probablemente inspección corporativa).*

**Ya no hay nada que hacer acá.** En el primer push a `main`, el job `frontend`
corrió `pnpm install --frozen-lockfile`, `pnpm lint` y `pnpm typecheck` sobre
los 27 archivos, y pasó en verde.

Es decir: el panel entero —login, el botón, la revisión de borradores, la
configuración, el historial, las alertas y las métricas— **compila**. Era el
riesgo abierto más grande que quedaba: casi tres mil líneas de TypeScript
escritas sin que ningún compilador las mirara nunca. Ya no lo es.

De paso quedaron confirmados los íconos de `lucide-react`. Un import que no
existe es un error de tipos, así que si `typecheck` pasó, los catorce están.

Lo único que sigue sin verificarse es cómo se **ve** y cómo se **comporta** en
un navegador de verdad. Que tipe no quiere decir que funcione: eso se prueba en
la fase 2, con el backend levantado al lado.


---

## B — Necesita Chrome con la extensión y una sesión de WhatsApp

*Bloqueado por: no hay Claude Code con `--chrome`, ni extensión, ni sesión de
WhatsApp Web en esta máquina.*

**Se puede hacer en Windows.** El MVP se validó ahí; no hace falta esperar la Mac.

### Configurar esta máquina (media hora)

El agente ya sabe decir qué falta. Corré:

```bash
cd agente
uv run python -m agente.main --diagnostico
```

Hoy marca tres cosas en rojo, y son exactamente las que hay que resolver:

- [x] **`claude_bin`** — poner la ruta COMPLETA al ejecutable en `CLAUDE_BIN`.
      No `claude` a secas: el PATH del proceso que lanza el agente no es el de
      tu terminal (problema #2 del MVP).
- [x] **`permiso_mcp`** — `~/.claude/settings.json` con
      `{"permissions":{"allow":["mcp__claude-in-chrome"]}}`. Sin esto, en modo
      headless se auto-deniega todo y el error es un 502 mudo (problema #3).
- [x] **`device_id`** — fijar `AGENTE_DEVICE_ID` con el deviceId del Chrome de
      esta máquina. Con más de un Chrome conectado a la cuenta, headless no sabe
      a cuál ir (problema #5).

Y uno que el diagnóstico **no puede verificar** y es el que se olvida:

- [x] **Permiso de sitio de la extensión** para `web.whatsapp.com`. Es una capa
      **distinta** del permiso MCP: aunque `settings.json` esté bien, sin esto
      falla con "requires permission" (problema #4). Se concede a mano en el
      navegador, una vez por máquina.

### F3.0 — El puente del backend · **no estaba en esta lista**

Esta sección listaba F3 como dos ejecutores. Son tres piezas: **el backend no
conectaba una con la otra.** `reportar_resultado()` sólo trataba el caso
`ENVIAR`, y `Tipo.REDACTAR` no lo encolaba ningún código, así que un resultado
de `LISTAR` se guardaba y ahí moría.

- [x] `app/core/generacion.py`: `LISTAR` → N `REDACTAR`, y `REDACTAR` → un
      borrador. La validación que ya existía hace el resto.
- [x] El teléfono viaja en `contexto` y no en `payload`: `REDACTAR` no envía
      nada y `PayloadRedactar` no lo acepta, pero el borrador y el triage lo
      necesitan. `JobEntregado` sólo manda `payload`, así que el número no sale
      del backend.
- [x] No se redacta para números fuera de `destinos_permitidos`. Es R4, y es
      plata: con la lista en los tres de prueba, es la diferencia entre pagar
      tres redacciones y pagar veinte.
- [x] Idempotencia: un `LISTAR` reportado dos veces no encola todo de nuevo.

### F3.1 — El job `LISTAR`

- [x] Implementar el ejecutor con la invocación validada del MVP (`--chrome`,
      prompt por stdin, `encoding="utf-8"`, `cwd` en la carpeta del agente).
- [ ] **Correrlo contra WhatsApp Web y ver qué se rompe.** Es la primera vez que
      el sistema nuevo toca la página, y el MVP se validó contra versiones
      anteriores de Claude Code, de la extensión y de WhatsApp. Si algo dejó de
      funcionar, se ve acá.

El prompt ya está escrito y migrado sin cambios funcionales, en
`agente/prompts/prompt-listar.txt`.

### F3.2 — El job `REDACTAR`

- [x] Implementarlo. **No abre el navegador**: es una llamada de texto plano.
      Criterio verificable: redactar 20 borradores no abre ninguna pestaña.
- [ ] Verificar que el costo baje como esperamos. Sacar el paso más frecuente
      del circuito del navegador es donde está el ahorro del proyecto.

El prompt está en `agente/prompts/prompt-redactar.txt`.

### F3.8 — Medir

- [ ] Correr una generación completa y anotar el costo real. Ya se registra
      solo por job y por corrida; falta el número.
- [ ] Comparar los borradores contra los del MVP. La forma que propuse:
      mezclarlos y que alguien del cliente los puntúe sin saber cuál es cuál. Si
      son peores, algo se rompió en la migración y es barato de arreglar ahora.

---

## C — Necesita Playwright y una línea de WhatsApp descartable

*Bloqueado por: hay que escribir en chats reales para saber si los selectores
funcionan.*

**El motor de envío ya está escrito y probado** (`agente/jobs/enviar.py`, 42
tests): la secuencia completa, la verificación de identidad, el modo prueba, y
los casos adversos —grupo, chat archivado, número ilegible, dos contactos con el
mismo nombre— contra una página falsa.

Lo que falta es enchufarle un navegador de verdad.

### F4.2 — Cómo se conecta al Chrome

- [ ] Probar las dos opciones y elegir **con evidencia**:
      **(A)** CDP sobre el Chrome del vendedor · **(B)** perfil dedicado de
      Playwright.
- [ ] Criterio: cuál sobrevive a que el vendedor cierre el navegador, reinicie
      la máquina y trabaje media jornada.
- [ ] Medir explícitamente: si cierra Chrome, ¿se pierde la sesión? Si está
      escribiendo en el mismo chat, ¿qué pasa? Con la opción B, **es un segundo
      dispositivo vinculado a esa línea** — ocupa uno de los cuatro lugares que
      WhatsApp permite y es una sesión más que se puede caer sin que nadie la vea.

### F4.3 — Los selectores

- [ ] Escribir `agente/adaptadores/whatsapp_web.py`: la implementación real del
      protocolo `Pagina`, que ya está definido con las ocho operaciones que hacen
      falta.
- [ ] Todos los selectores en **un solo archivo**, con la fecha de última
      verificación. Ninguno fuera de ahí.
- [ ] La función que verifica que siguen respondiendo, para correr antes de cada
      corrida.

### F4.12 y F4.13 — Probar que aborta

- [ ] **50 verificaciones de identidad** contra la línea de prueba, en modo
      prueba. Criterio: 0 falsos positivos, 0 mensajes escritos por error.
- [ ] ⚠️ **La prueba de identidad incorrecta, ANTES del primer envío real.**
      Encolar un mensaje con un `contacto_id` que no corresponde al chat, y
      verificar **en el DOM** que el campo de escritura quedó vacío. Que el log
      diga "aborté" no alcanza.

      Si se hace al revés, el primer envío real es también la primera vez que
      confiamos en algo que no probamos.

### F4.14 — Los tres mensajes reales

Antes de ejecutar, las cinco cosas:

- [ ] Los 3 contactos aceptaron recibirlos
- [ ] La prueba de identidad incorrecta pasó
- [ ] `destinos_permitidos` tiene **exactamente** esos 3 números y ninguno más
- [ ] El tope de 3 está activo
- [ ] El kill switch probado, y sabés usarlo

- [ ] Enviar de a uno, parando entre cada uno. Si algo se ve raro en el primero,
      frenar. No hay ninguna razón para apurar esto.

### 🚪 Y ahí se para y se decide

- [ ] Presentarle al cliente los tres mensajes tal como los recibió el
      destinatario, el costo medido por mensaje, y el riesgo de bloqueo de líneas
      sin suavizarlo. **La presentación tiene que permitirle decir que no.**

---

## D — Necesita Macs

*Bloqueado por: no hay ninguna Mac disponible.*

Todo esto es **plomería**: cómo arranca el programa, qué permisos pide el
sistema, cómo se instala. Nada cambia lo que el producto hace, y por eso está al
final.

- [ ] **F5.1** — Correr el agente en una Mac y documentar qué pide macOS y no
      pide Windows: permisos de Automatización, acceso al disco, si Gatekeeper
      molesta. **Es la lista que nadie tiene**, porque el MVP nunca corrió en Mac.
      Después, agregar el chequeo `permisos_macos` al diagnóstico.
- [x] **F5.2** — El LaunchAgent en `~/Library/LaunchAgents/`. Lo escribe
      `agente/instalador/instalar-mac.sh`. **Falta probarlo en una Mac.** Tiene que ser un
      LaunchAgent y **no** un LaunchDaemon: Chrome y la extensión viven en la
      sesión interactiva del usuario y un daemon no los ve.
- [ ] **F5.3** — ~~Escribir el instalador~~ hecho: `instalar-mac.sh`, con el
      SOP en `docs/SOP-instalar-mac.md`. Falta **probarlo en al menos dos Macs
      distintas**, que es lo que el criterio pedía.
- [ ] **F5.4** — El ícono de la barra de menú con "pausar por hoy". Criterio: un
      vendedor pausa su máquina sin ayuda.
- [ ] **F5.6** — Los tres SOPs, y ⚠️ **retirar de circulación el SOP viejo**, que
      dice textual *"No envía ningún mensaje. Nunca."* — Drive, mails, impresos,
      grupos. Es el paso que se olvida.
- [ ] **F5.7** — Una conversación de consentimiento por vendedor, registrada. El
      backend no encola envíos sin eso.
- [ ] **F5.8** — Alta escalonada: una máquina, después dos, después el resto.
      **Instalar no es activar.**

---

## Producción nunca estuvo enchufada

Se sondeó el 21 de agosto de 2026, yendo a buscar los deploy hooks. Lo que hay
no es "la versión vieja andando": es un esqueleto sin conectar.

**Lo que se comprobó desde afuera, sin entrar al dashboard:**

- `frontend-produccion.onrender.com/healthz` responde `{"ok":true,"servicio":
  "frontend"}`, que es exactamente lo que sirve este repositorio. Ese servicio
  **es nuestro** y está vivo.
- Pero `/api/estado` devuelve un 404 de Next: la ruta proxy del panel
  (`app/api/[...ruta]`) no está desplegada. O sea que corre una versión
  **anterior a `9ed1c3a`**, la del panel. Es el esqueleto del sprint 0.
- Su propia sonda lo dice todo:

  ```
  GET /api/estado-backend
  {"alcanzable":false,"url":"http://localhost:8000/health","motivo":"fetch failed: ECONNREFUSED"}
  ```

  **`BACKEND_URL` nunca se configuró** y quedó en el valor por defecto del
  código. El panel de producción no le habla a ningún backend.

- ⚠️ `backend-produccion.onrender.com` **no es nuestro**. Devuelve
  `{"message":"Cannot GET /health","error":"Not Found","statusCode":404}`, que es
  el formato de Express/NestJS; FastAPI devuelve `{"detail":"Not Found"}`. Los
  subdominios de Render son globales: el nombre estaba tomado y a nuestro
  servicio le tocó otro con sufijo. **La URL que parece la nuestra es la
  aplicación de un tercero.**

  Lo bueno de que `BACKEND_URL` estuviera sin configurar: el panel nunca le mandó
  nada a ese servidor. Si alguien lo hubiera "arreglado" poniéndole esa URL a
  ojo, la contraseña del panel habría viajado a una aplicación ajena.

**Lo que hay que hacer en el dashboard, todo junto en una sola visita:**

- [x] ~~Anotar la **URL real** de `backend-produccion`~~ →
      **`https://backend-produccion-7yqr.onrender.com`**. Existe, está vivo y
      responde `{"ok":true,"mongo":true,"entorno":"produccion"}`: `MONGO_URL`
      está configurado y Atlas contesta.

      Pero corre **el esqueleto**: `/openapi.json` expone **una sola ruta**,
      `/health`. No están ni la API del panel ni la del agente. Es la versión de
      `38d27e1`, del sprint 0. Lo mismo que el frontend.
- [ ] Configurar `BACKEND_URL` en `frontend-produccion` con esa URL real.
- [ ] Confirmar que el backend tenga `MONGO_URL`, `PANEL_PASSWORD` y
      `SESION_SECRET`. Los tres son `sync: false`, así que no están en el
      blueprint y nadie sabe desde acá si están puestos.
- [ ] Copiar los deploy hooks de cada servicio, para el secreto de abajo.

⚠️ **Y antes de disparar la primera corrida en producción**: `destinos_permitidos`
tiene que estar en los números de prueba. En una base nueva arranca vacía —que
significa a nadie— así que el riesgo real es al revés: nadie va a poder mandar
nada hasta que alguien la abra a propósito. Eso está bien y es la regla R4.

---

## El backup nunca corrió bien

`backup-produccion` dice *"No successful runs yet"* y sale con estado 1.

`infra/scripts/backup.sh` tiene **cinco puntos de aborto, cada uno con su
mensaje**, así que la primera línea del log lo identifica sin adivinar:

| Mensaje | Causa |
|---|---|
| `FALTA la variable X` | Una `sync: false` sin configurar |
| `ABORTA: no pude conectarme a la base` | `MONGO_URL` mal, o Atlas bloqueando la IP |
| `ABORTA: la base tiene N documentos` | La base está vacía |
| `ABORTA: el dump pesa N bytes` | Dump truncado |
| `ABORTA: subió N y el local pesa M` | Subida a R2 incompleta |

⚠️ **Si dice "0 documentos", no es un bug.** El backend de producción es el
esqueleto y nadie escribió nunca nada en esa base. El script se niega a subir un
backup vacío a propósito, y su propio comentario explica por qué: *"Un backup
vacío que se sube sin chistar es peor que un backup que falla: te deja creyendo
que estás cubierto."* En ese caso el backup empieza a andar solo cuando la base
tenga datos.

### Resuelto: es la base vacía, y no hay nada que arreglar

El log dice:

```
ABORTA: la base tiene 0 documentos, menos que el mínimo de 1.
```

Llegar hasta ahí descarta lo demás: **las siete variables están configuradas**
—el chequeo es lo primero que corre— y **la conexión a Atlas funciona**, porque
pasó el aborto anterior. Simplemente no hay nada que respaldar.

⚠️ **Desplegar no lo arregla.** `ciclo_de_vida` llama a `inicializar()`, que crea
colecciones e índices y **ningún documento**; la configuración por defecto se
escribe con un `$setOnInsert` que sólo dispara cuando alguien la pide. La
secuencia real es:

1. Deploy → 6 colecciones vacías → `0 documentos`, el backup sigue fallando
2. Alguien entra al panel → `configuracion.obtener()` escribe el documento
3. 1 documento ≥ el mínimo → **el backup pasa solo**

⚠️⚠️ **NO bajar `MINIMO_DOCS` a 0.** Cuando el cron falle unos días seguidos va a
dar la tentación. Eso convierte el guard en un backup vacío que se sube todos los
días y deja creyendo que hay cobertura — exactamente contra lo que el script fue
escrito.

- [ ] Cuando alguien entre al panel por primera vez, **verificar en Atlas que el
      documento de `configuracion` haya aparecido en una base llamada
      `seguimiento`**. Es lo único que cierra la duda que deja el propio mensaje
      del script: *"Puede ser la base equivocada en MONGO_URL"*. Desde afuera no
      se puede distinguir, porque Mongo crea la base en la primera escritura y un
      nombre equivocado se ve igual que una base legítimamente vacía.

---

## El deploy no funciona todavía

- [ ] **Cargar el secreto `RENDER_DEPLOY_HOOKS_PRODUCCION`.** Sin esto,
      `Deploy a produccion` falla en el primer paso y **producción se queda con
      la versión vieja para siempre**, aunque `main` esté verde. Se descubrió al
      intentar el primer despliegue: el environment `produccion` existe en GitHub
      pero está vacío, y no hay ningún secreto a nivel repositorio.

      Es un **array JSON** con los deploy hooks de Render, uno por servicio del
      blueprint — `backend-produccion`, `frontend-produccion` y
      `backup-produccion`. Cada hook se copia del dashboard de Render, en
      Settings → Deploy Hook del servicio.

      ```bash
      gh secret set RENDER_DEPLOY_HOOKS_PRODUCCION --env produccion --body '["https://api.render.com/deploy/srv-...?key=...","https://api.render.com/deploy/srv-...?key=..."]'
      ```

      ⚠️ Cada hook es una credencial: quien lo tenga puede disparar un despliegue.
      No van al repositorio ni a un chat.

- [ ] **Borrar los environments viejos de GitHub.** Quedaron cuatro de la época
      de staging: `develop - backend-produccion`, `develop - backend-staging`,
      `develop - frontend-produccion`, `develop - frontend-staging`. Son de la
      misma limpieza que los servicios de Render de acá abajo.

---

## Dos cosas de infraestructura, de cinco minutos

- [ ] **Borrar los servicios viejos de Render.** Quedaron cinco de más:
      `backend-staging`, `frontend-staging`, `n8n-produccion`, `n8n-staging`,
      `backup-staging`. Ya están fuera del blueprint; borrarlos es en el
      dashboard.
- [ ] **Antes de borrar los n8n, abrí las dos URLs.** Si alguna pide crear
      cuenta, esa instancia estuvo abierta a quien diera con ella. Es la única
      exposición real que encontré en toda la auditoría, y se verifica en dos
      minutos.
- [ ] Aplicar el rol de MongoDB en Atlas siguiendo `RUNBOOK-auditoria.md`, y
      correr los cuatro comandos de verificación. Sin eso, la regla R5 —el
      registro es inmutable— no se está cumpliendo aunque el código esté bien.

---

## Lo que NO hace falta hacer

Para que nadie lo busque:

- El motor de envío, la verificación de identidad y el modo prueba **están
  escritos y probados**. Falta el navegador, no la lógica.
- Los ocho guardrails, el triage, la cola, la máquina de estados y la auditoría
  inmutable **están terminados**, con 100% de cobertura en los cinco archivos
  críticos.
- El panel completo **está escrito**: login, estado, alta y baja de máquinas, el
  botón, el kill switch, revisión de borradores, configuración, historial,
  alertas y métricas, y **compila** — el CI lo verificó. Falta verlo andar.
- Los escenarios de caos **están probados**: apagar una Mac a mitad de corrida,
  ocho agentes sobre la misma cola, apretar enviar dos veces, reiniciar el
  backend con trabajo pendiente.
