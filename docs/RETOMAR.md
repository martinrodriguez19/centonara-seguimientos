# Retomar el proyecto

> **Si estás llegando a este repositorio por primera vez, o volviendo después de
> un tiempo, empezá acá.** Este documento dice en qué estado está todo, qué
> sigue, y —sobre todo— qué decisiones ya se tomaron y no hace falta volver a
> discutir.
>
> Última actualización: 27 de agosto de 2026.
>
> **Nota:** después de la primera entrega se implementó la Entrega 2 (D29 a
> D31): todos los chats se consideran comerciales, "Dejar borradores" reemplaza
> al ensayo, y las corridas frenadas se pueden reanudar y cancelar. El detalle,
> con el diagnóstico del incidente del 26/08, está en
> [`PLAN-ENTREGA-2.md`](PLAN-ENTREGA-2.md). Los números de abajo de la sección 2
> quedaron de la entrega anterior; hoy son 641 tests de backend y 212 del
> agente, verdes.

---

## 1. Qué es esto

El dueño de una empresa de materiales de construcción aprieta un botón. En la
Mac de cada vendedor, Claude abre WhatsApp Web, lee los chats recientes, arma un
mensaje de seguimiento para cada contacto, y —después de que el dueño los
revisa— los envía desde la línea del propio vendedor.

Las máquinas quedan prendidas al mediodía. El trabajo pasa durante el almuerzo.

Dos cosas que definen todo el diseño:

- **Los mensajes salen de la línea personal del vendedor.** Un mensaje al chat
  equivocado no es un bug de software: es un cliente real recibiendo algo que no
  tenía que recibir, desde el número de alguien que confía en el sistema.
- **La cantidad de máquinas es variable.** Se dan de alta y de baja desde el
  panel. Nada en el código puede asumir un número fijo.

Contexto completo en [`01-PROYECTO.md`](01-PROYECTO.md).

---

## 2. Dónde estamos, verificado

No de memoria — esto es lo que da correr el repositorio hoy:

| | |
|---|---|
| Tests backend | **553**, verdes |
| Tests agente | **94**, verdes |
| Cobertura | **100%** en los cinco archivos críticos: `contactos`, `estados`, `cola`, `guardrails`, `triage` |
| Ruff | limpio en backend y agente |
| Frontend | **compila** — `lint` y `typecheck` en verde en CI |
| CI | siete jobs, todos pasando |
| Producción | tiene desplegada la versión vieja. El deploy es manual (`workflow_dispatch`): mergear no despliega |

### Lo que está terminado

**F1 — Núcleo, completa.** Normalización a E.164 con las 294 características
argentinas, máquina de estados, cola atómica sobre MongoDB con escalonamiento y
canarios, alta y baja de máquinas con token, los cuatro endpoints del agente,
bucle con reintentos, nueve chequeos de diagnóstico, kill switch, y auditoría
inmutable por rol de MongoDB.

**F2 — Panel, escrito.** Login, estado, alta y baja de máquinas, el botón, kill
switch, revisión de borradores, configuración, historial, alertas y métricas.
Compila. **No se ejecutó nunca contra el backend levantado.**

**F4 — El motor de envío, escrito y probado.** La secuencia de doce pasos, la
verificación de identidad, el modo prueba, y los casos adversos —grupo en vez de
persona, chat archivado, número ilegible, dos contactos con el mismo nombre—
contra una página falsa. Se puede probar entero sin navegador porque
`agente/adaptadores/pagina.py` define un protocolo de ocho operaciones.

### Lo que NO está hecho

- **Nadie vio el sistema andar.** Que compile y que los tests pasen no es lo
  mismo que verlo funcionar. Backend y panel nunca se levantaron juntos.
- **F3 — Generación.** Los jobs `LISTAR` y `REDACTAR` no están implementados.
  Los prompts sí están, migrados del MVP sin cambios, en `agente/prompts/`.
- **F4 — El navegador.** El motor existe; falta enchufarle Playwright y los
  selectores reales de WhatsApp Web.
- **F5 — macOS.** Nada. Ninguna Mac tocó este código todavía.

---

## 3. Qué sigue

**El próximo paso concreto: levantar backend y panel juntos y usarlo.**

```bash
docker compose -f infra/docker-compose.dev.yml up -d
```

```bash
uv run --directory backend fastapi dev app/main.py
```

Y desde `frontend/`, `pnpm install` y `pnpm dev`. La secuencia completa está en
el [README](../README.md).

Es la primera vez que el sistema se ve a sí mismo. Esperá encontrar cosas: el
panel se escribió contra los tipos del cliente de API, no contra respuestas
reales. Ese es el trabajo de F2, y su criterio de salida es que alguien de
afuera del equipo entre, entienda qué está viendo, dé de alta una máquina y
dispare una corrida sin ayuda.

Después, F3. Necesita Chrome con la extensión Claude in Chrome y una sesión de
WhatsApp Web — **y se puede hacer en Windows**, el MVP se validó ahí. No hace
falta esperar las Macs.

El detalle de todo lo que falta, con el motivo por el que está bloqueado, está
en [`PENDIENTE-CON-MAQUINA.md`](PENDIENTE-CON-MAQUINA.md).

### Tres cosas que no se resuelven escribiendo código

Conviene pedirlas ya, porque dependen de otra persona:

1. **Una línea de WhatsApp de prueba**, que no sea de nadie del equipo. Se le van
   a mandar mensajes de verdad y puede terminar bloqueada.
2. **Confirmar con el administrador del Claude Enterprise que la extensión
   Claude in Chrome esté habilitada por política.** Si está restringida, el
   sistema no funciona en ninguna máquina y no se arregla desde el código. Es lo
   único que puede frenar el proyecto entero.
3. **Tres contactos propios** que acepten recibir mensajes de prueba.

---

## 4. Decisiones ya tomadas — no volver a discutirlas

Un agente que llega nuevo va a querer proponer varias de estas. Ya se
discutieron y hay motivo. Están todas con su número en
[`06-DECISIONES.md`](06-DECISIONES.md).

| Lo que se va a querer proponer | Por qué no |
|---|---|
| "Falta un entorno de staging" | **No hay usuarios que proteger** (D17). Se prueba en producción a propósito. Un segundo entorno costaba cinco servicios y no protegía a nadie |
| "Habría que poner fechas de entrega" | **Sin plazos** (D19). Las fases terminan por criterio de salida, no por calendario |
| "Faltan guardrails" | Eran veinte y quedaron **ocho** (D20). Los que se sacaron eran el mismo control escrito dos veces |
| "Volvamos a n8n para los horarios" | Hacía tres crons y costaba dos servicios (D18). Ahora es APScheduler adentro de FastAPI |
| "El login debería tener magic links u OAuth" | **Una contraseña** (D22). Entran una o dos personas |
| "Hay que hashear con Argon2" | **SHA-256** para tokens de máquina (D23). No son contraseñas de humanos |
| "Retengamos los chats viejos" | Se sacó esa señal del triage: contradecía el criterio con el que el MVP se validó en la realidad |
| "Esto es para Windows" | **macOS** (D16). El parque real es Mac. LaunchAgent, nunca LaunchDaemon |

Y una que importa más que las otras: **esto no es una empresa de información
confidencial, vende materiales.** La seguridad que se sostiene es la de
corrección —verificar identidad, topes, fallar cerrado, auditoría inmutable,
consentimiento del vendedor—. La paranoia de infraestructura se relajó a
propósito.

---

## 5. Las cinco reglas

Estas sí no se cruzan. Completas en [`03-REGLAS.md`](03-REGLAS.md), que es corto
y conviene leer entero.

- **R1** — Verificar la identidad del contacto antes de escribir, y abortar si
  no coincide.
- **R2** — El sistema falla cerrado. Si no puede decidir, no hace.
- **R3** — El modelo redacta; el código decide y envía.
- **R4** — Sólo se escribe a números de `destinos_permitidos`. Lista vacía
  significa **a nadie**, no "a todos".
- **R5** — Todo lo que sale queda registrado, y el registro es inmutable a nivel
  de base de datos, no por convención.

---

## 6. Cosas que ya costaron tiempo

Para no volver a pagarlas. Todas tienen test de regresión.

- **`configuracion.actualizar()` lee antes de escribir.** El upsert directo
  creaba un documento sólo con el campo tocado y se llevaba puestas las palabras
  de conflicto, apagando el triage **en silencio**.
- **`inicializar()` al arrancar es deliberadamente no fatal.** Si Mongo está
  caído, el proceso tiene que llegar a levantar para que `/health` devuelva 503 y
  Render saque la instancia. Si aborta, Render entra en ciclo de reinicio.
- **`hmac.compare_digest` sobre `str` con acentos lanza `TypeError`.** Una
  contraseña con tilde devolvía 500 en vez de 401. Se compara en bytes.
- **`ASGITransport` no dispara el lifespan.** Un test de arranque escrito así no
  prueba nada.
- **El TTL de MongoDB borra documentos, no campos.** Para vencer sólo los
  resúmenes hay un `$unset` programado.
- **Los roles de MongoDB sólo conceden, nunca deniegan**, y no tienen efecto sin
  `--auth`. Por eso el Mongo local corre autenticado y los privilegios se
  enumeran uno por uno.
- **La espera entre envíos vive en `disponible_desde`, nunca en un `sleep`.** Un
  agente que se reinicia no pierde el turno.
- **`OperationFailure` no tiene `.code_name`.** Se compara `.code == 13`.

---

## 7. Cómo se trabaja acá

- **Un solo entorno: producción.** No hay `develop`. Todo va a `main`.
- **Nombres de dominio en español** (`mensajes`, `vendedores`, `corridas`,
  `guardrails`), estructura técnica en inglés.
- **El desarrollo es en PowerShell.** Ahí `&&` es un error de sintaxis: los
  comandos se escriben con `uv run --directory <carpeta>`, no encadenando `cd`.
- **Un check que sólo verificaste que pasa, no sabés si sirve.** Los guardas del
  CI se prueban en las dos direcciones.
- Convenciones completas en [`07-CONVENCIONES.md`](07-CONVENCIONES.md).

---

## 8. El índice

Todo lo demás cuelga de [`00-INDICE.md`](00-INDICE.md). Son nueve documentos y
están en orden de lectura.
