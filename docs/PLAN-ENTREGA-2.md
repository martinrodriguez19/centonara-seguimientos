# Plan — Entrega 2

> Qué se arregla y qué se mejora después de la primera entrega. Dos frentes que pidió el cliente
> —todos los chats son comerciales, y el ensayo pasa a ser "dejar borradores"— más el arreglo de
> las alertas que hoy no se pueden apagar.
>
> **Estado (27/08/2026): los Sprints 1, 2 y 3 están implementados.** Decisiones registradas como
> D29, D30 y D31 en [`06-DECISIONES.md`](06-DECISIONES.md). 641 tests de backend y 212 del agente
> en verde, cobertura 100% en los cinco archivos críticos, lint y build del frontend limpios. La
> causa del fallo del 26/08 se confirmó: las Macs estaban en `AGENTE_MODO=simulado`. Queda el
> Sprint 0 (acciones desde el panel y el `.env` de cada Mac) y desplegar.

---

## 1. Qué pidió el cliente y qué pasó

**Lo que pidió:**

1. **Basta de la división comercial / personal por palabras.** Los vendedores usan chats sólo
   comerciales. Todos los chats se consideran comerciales y a todos se les redacta un mensaje.
   Las dos listas de palabras desaparecen del panel.
2. **El ensayo cambia de sentido.** Ya no es "escribe y borra": ahora es **dejar el mensaje como
   borrador en el WhatsApp del vendedor**, listo para que él lo mande con un click. Se renombra:
   "Ensayo" → **"Dejar borradores"**, "Enviar de verdad" → **"Envío"**.

**Lo que pasó en la primera prueba (26/08):** una corrida de ensayo falló con `CHAT_NO_ABRE` en
los tres primeros jobs, el canario puso el kill switch, la corrida quedó en `frenada`… y ahí
quedó, porque **no existe hoy ninguna forma de reanudar ni de reconocer una corrida frenada**. Por
eso el panel muestra desde entonces "Una corrida se frenó sola" y "El sistema está frenado" y no
hay botón que las saque.

---

## 2. Diagnóstico: por qué falló el ensayo y no el envío

El hallazgo central de la revisión de código: **el ensayo y el envío son el mismo código.** Mismo
endpoint, misma cola, mismo canario, mismos doce pasos en el agente
(`agente/agente/jobs/enviar.py:119-209`). La única diferencia son dos líneas: en ensayo no se
aprieta enviar y se limpia el campo (`enviar.py:187-190`). No hay un "camino de simulación" que
pueda romperse por separado.

Entonces, ¿por qué el ensayo dio `CHAT_NO_ABRE` y la prueba directa no? En orden de probabilidad:

1. **La máquina estaba en `AGENTE_MODO=simulado`.** En ese modo el ejecutor usa una página
   simulada **sin chats** (`agente/agente/jobs/ejecutor.py:174-177`,
   `agente/agente/adaptadores/simulada.py:69-76`): el 100% de los envíos da `CHAT_NO_ABRE`, que es
   exactamente el patrón del log. `simulado` es el valor por defecto de los instaladores
   (`instalar.sh:226`, `agente/instalador/instalar-mac.sh:248`). Si la prueba "desde la terminal"
   se hizo en otra máquina o con otro `.env`, ahí está la diferencia. **Verificarlo es el primer
   paso del Sprint 0.**
2. **Fragilidad de `buscar_contacto`** (`agente/agente/adaptadores/whatsapp_web.py:116-190`):
   esperas de 3 segundos, sólo mira 4 filas de resultados, y exige que el header coincida
   textualmente con la fila clickeada. Todo desemboca en el mismo `CHAT_NO_ABRE` genérico. Esto
   afecta igual a ensayo y envío: es ruido de timing, no de modo.

Nota: **no existe un comando de terminal que envíe** (`agente/agente/main.py:42-106`, a
propósito). Si la prueba directa fue un `curl` al endpoint, corrió el mismo código que el ensayo,
lo que refuerza la hipótesis 1.

**Dos bugs serios encontrados al revisar esto** (se arreglan en el Sprint 2):

- **`AGENTE_MODO=prueba` no protege de un envío real.** El modo del payload le gana al de la
  máquina (`ejecutor.py:210`): una Mac configurada en `prueba` aprieta enviar igual si el panel
  manda `modo: "real"`. Contradice la tabla del SOP (`docs/SOP-instalar-mac.md:262-265`).
- **Un ensayo "gasta" los borradores.** El reporte no distingue simulado
  (`enviar.py:51-58`), así que el backend marca los mensajes como `ENVIADO`, los audita como
  enviados, los cuenta en el tope diario G4 y ya no se pueden enviar de verdad después.

---

## 3. Sprint 0 — Destrabar hoy (sin código)

Todo esto se hace desde el panel o con la API que ya existe. Apaga las tres alertas.

| # | Acción | Cómo |
|---|---|---|
| S0.1 | Cancelar la corrida frenada `6a8f50e5625a8097336f04dc` | Botón "Cancelar corrida" del panel (aparece si es la última corrida con pendientes). Si no aparece: `POST /api/corridas/6a8f50e5625a8097336f04dc/cancelar` con la cookie de sesión. Apaga "Una corrida se frenó sola" |
| S0.2 | Soltar el kill switch | Botón "Reanudar" de la barra del panel. Apaga "El sistema está frenado" / "Sistema frenado" |
| S0.3 | Verificar `AGENTE_MODO` en el `.env` de **mac-lautaro** y **mac-thomas** | Si dice `simulado`, ahí está la causa de los `CHAT_NO_ABRE`. Ponerlo en `prueba` y repetir el ensayo |

Las alertas no se guardan en ningún lado (`backend/app/core/alertas.py:1-14`): se recalculan en
cada consulta. Apagar la causa apaga la alerta — el problema era que `canario_fallido` no tenía
forma de apagarse. El Sprint 3 arregla eso de raíz.

---

## 4. Sprint 1 — Todos los chats son comerciales

**Termina cuando:** una corrida completa no retiene ningún mensaje por `CHAT_NO_COMERCIAL` ni por
"conversación personal", y la pantalla de configuración no muestra listas de palabras.

| # | Tarea | Terminada cuando |
|---|---|---|
| S1.1 | Borrar la regla `CHAT_NO_COMERCIAL` del triage (`backend/app/core/triage.py:184-189`). El miembro del enum y su traducción (`frontend/lib/textos.ts:435`) se conservan, para que los mensajes históricos que ya tienen la señal guardada sigan legibles | Los tests de la señal se van (`backend/tests/test_triage.py:232-256`) y el conteo de señales se actualiza (`:290-301`) |
| S1.2 | Sacar `palabras_comerciales` de `POR_DEFECTO` (`backend/app/core/configuracion.py:74-96`) y hacer `$unset` del campo huérfano en el documento vivo. Ojo: `actualizar()` valida contra `POR_DEFECTO`, y `restablecer()` repone todo de fábrica | `GET /api/configuracion` no devuelve el campo |
| S1.3 | Quitar el campo del modelo `CambioConfiguracion` (`backend/app/api/panel.py:645`) y del type `Configuracion` (`frontend/lib/panel.ts:87-95`) — **en el mismo commit**: el test de contrato (`backend/tests/test_contrato_panel.py:61-72`) falla en ambas direcciones si van separados | Test de contrato verde |
| S1.4 | Sacar las dos tarjetas de palabras del panel (`frontend/app/config/page.tsx:170-182`) | La pantalla de configuración no tiene listas de palabras |
| S1.5 | Reescribir la cláusula `sin_contexto` del prompt de redacción (`agente/prompts/prompt-redactar.txt:53-61`): deja de apartar "conversación personal"; queda sólo para cuando no hay literalmente nada que retomar. Ajustar el "sin tema comercial visible" de `prompt-listar.txt:31-37` y `prompt-barrido.txt:52-58` | `agente/tests/test_redactar.py:116-122` actualizado |
| S1.6 | Docs: tabla de señales de `03-REGLAS.md:104-129` y `02-ARQUITECTURA.md:235-249`. Registrar la decisión en `06-DECISIONES.md` **antes** de implementar | — |

**Sugerencia — a confirmar con el cliente:** sacar del front las dos tarjetas, pero **mantener
`palabras_conflicto` funcionando en el backend** con su lista por defecto. Esa señal no clasifica
comercial/personal: aparta el seguimiento sobre un reclamo abierto ("reclamo", "abogado",
"estafa"...), que es el peor error posible del sistema (`03-REGLAS.md` §7.3). Sacar la tarjeta
quita la perilla del panel, no la protección; la lista queda editable por API si algún día hace
falta. Si el cliente quiere eliminarla del todo, es un cambio chico más — pero conviene que sea
una decisión explícita, no un efecto colateral del pedido.

Nota: existe un atajo sin despliegue — vaciar `palabras_comerciales` por `PATCH
/api/configuracion` apaga la señal hoy mismo (`triage.py:186` no la evalúa con la lista vacía).
Sirve como mitigación inmediata mientras el sprint no está desplegado, pero no reemplaza al
sprint: el prompt seguiría apartando "personales" y las tarjetas seguirían en el panel.

---

## 5. Sprint 2 — "Dejar borradores" reemplaza al ensayo

**Termina cuando:** una corrida en modo borradores deja los mensajes escritos y sin enviar en el
WhatsApp de cada vendedor, el panel los muestra como "borrador dejado" (no como enviados), y una
máquina en modo `prueba` no puede enviar de verdad aunque el payload diga `real`.

| # | Tarea | Terminada cuando |
|---|---|---|
| S2.1 | Renombrar en el panel: "Ensayo" → **"Dejar borradores"**, "Enviar de verdad" → **"Envío"** (`frontend/lib/textos.ts:207,210-230,344`, `frontend/components/enviar.tsx`, píldoras de `corrida/[id]` y `corridas`). Reescribir el texto de resultado: ya no es "nadie va a recibir nada", es "quedaron como borradores en el WhatsApp de cada vendedor" | Ningún "Ensayo" ni "de verdad" en el front (`docs/SOP-instalar-mac.md:213` incluido) |
| S2.2 | Comportamiento: en modo borradores se escribe el texto y **no se limpia el campo** (`agente/agente/jobs/enviar.py:187-190`); se cierra el chat (Escape / volver a la lista) para que WhatsApp Web persista el borrador. Los pasos 0-8 (identidad, destino permitido, campo vacío) quedan idénticos | El borrador queda visible en el chat correcto, verificado a mano en una Mac |
| S2.3 | El reporte distingue borrador de envío: `a_reporte()` incluye el flag (`enviar.py:49-58`); el backend crea el estado `BORRADOR_DEJADO` (`backend/app/core/estados.py`, transición desde `ENVIANDO`) en vez de `ENVIADO`; no cuenta en `enviados_hoy` ni consume el tope G4; evento de auditoría propio | Hoy un ensayo marca `ENVIADO` y quema los borradores; después del sprint, no |
| S2.4 | **Arreglar la precedencia de modo** (`agente/agente/jobs/ejecutor.py:205-212`): el modo efectivo es el **más restrictivo** entre `AGENTE_MODO` y el del payload. Una máquina en `prueba` nunca aprieta enviar | Un test que intenta violarlo, al estilo `test_guardrails.py` |
| S2.5 | Robustecer `buscar_contacto` (`agente/agente/adaptadores/whatsapp_web.py:116-190`): subir las esperas de 3 s, y separar códigos: "sin resultados de búsqueda" ≠ "abrí el chat pero el header no coincide". Hoy los dos son `CHAT_NO_ABRE` | Un ensayo fallido dice en el panel *qué* falló |
| S2.6 | El agente reporta su `AGENTE_MODO` al registrarse (`backend/app/api/agente.py`, evento `agente_registrado`) y el panel lo muestra por máquina | Se ve de un vistazo que una Mac quedó en `simulado` — la causa probable de esta semana |
| S2.7 | Registrar la decisión en `06-DECISIONES.md`; actualizar `03-REGLAS.md` y el SOP | — |

**Dos decisiones de diseño que conviene dejar explícitas:**

- **El circuito es "dejar borradores → el vendedor manda a mano".** No "borradores y después
  envío automático": un borrador dejado ocupa el campo de escritura, y un Envío posterior al mismo
  chat aborta con `CAMPO_NO_VACIO` (G8). Eso es correcto —falla cerrado—, pero hay que contarlo en
  el SOP para que no parezca un bug.
- **`BORRADOR_DEJADO` cuenta para el anti-duplicado G5** (recomendado): si se le dejó un borrador
  a un contacto, no generarle otro seguimiento por 7 días, lo haya mandado el vendedor o no.

El canario sigue aplicando a las corridas de borradores: si los 3 primeros fallan, frena. Con el
Sprint 3 eso deja de doler, porque frenar deja de ser un callejón sin salida.

---

## 6. Sprint 3 — Alertas que se apagan, corridas que se reanudan y cancelan

**Termina cuando:** ninguna alerta puede quedar encendida sin un botón que la resuelva, y
cualquier corrida con trabajo pendiente se puede cancelar desde el panel.

| # | Tarea | Terminada cuando |
|---|---|---|
| S3.1 | **Reanudar una corrida frenada**: transición `frenada → enviando`, endpoint `POST /api/corridas/{id}/reanudar`, y botón "Ya lo miré, continuar" en la alerta `canario_fallido` y en el detalle de la corrida. Reanudar suelta también el kill switch si lo puso el canario | La alerta se apaga sin perder los envíos pendientes. Hoy no existe ninguna transición que saque a una corrida de `frenada` (`backend/app/core/corridas.py:404-443`) |
| S3.2 | Cancelar desde el listado y el detalle de corrida. Hoy el único botón vive en `frontend/components/boton-corrida.tsx:92-112` y sólo para la última corrida con pendientes | Cualquier corrida con pendientes se cancela desde su detalle |
| S3.3 | `cancelar()` resuelve también los **mensajes**: los `ENVIANDO`/`EN_ESPERA` de la corrida pasan a `DESCARTADO` con motivo nuevo `cancelado`. Y `CANCELADO` entra al enum `Codigo` (`backend/app/core/cola.py:83-125`) — hoy es un string libre escrito directo en Mongo (`corridas.py:278-287`) | Nada queda en `ENVIANDO` para siempre; `Codigo("CANCELADO")` no revienta |
| S3.4 | Mostrar el estado real de la corrida (`frenada`, `cancelada`) en `frontend/app/corridas/page.tsx` y `corrida/[id]/page.tsx`. Hoy el campo `estado` no se muestra en ninguna pantalla | Una corrida frenada se ve frenada, no "casi terminada" |
| S3.5 | Revisar el doble cartel del freno: con el kill switch puesto, el panel muestra dos avisos de dos fuentes distintas (`kill-switch.tsx:99-105` + alerta `pausa_global` de `alertas.py:155-172`). Dejar uno | Un solo cartel de sistema frenado |

No se agrega "descartar alerta" genérico: las alertas siguen siendo derivadas del estado
(`alertas.py:1-14`), que es un buen diseño. Lo que se agrega es la acción que faltaba para
resolver la causa (`reanudar`), no una forma de esconder el síntoma.

---

## 7. Orden y dependencias

```
S0  hoy, sin código      → apaga las alertas actuales, confirma la causa del fallo
S1  todos comerciales    → chico e independiente; puede ir primero o en paralelo
S2  dejar borradores     → el cambio de producto; incluye los dos bugs de modo
S3  reanudar / cancelar  → evita que lo del 26/08 vuelva a quedar clavado
```

S1 y S2 no se pisan (triage/config vs envío/agente). S3 conviene después de S2 porque el botón
"reanudar" tiene más sentido cuando los fallos del canario ya vienen con códigos distinguibles
(S2.5).

## 8. Preguntas abiertas

1. **¿Con qué comando se probó el envío "desde la terminal"?** En el repo no hay CLI de envío. Si
   fue un `curl` al endpoint, la comparación ensayo-vs-envío corrió el mismo código y la
   diferencia estuvo en la máquina o su `.env` (S0.3 lo confirma).
2. **`palabras_conflicto`: ¿se elimina del todo o sólo del panel?** Recomendación en el Sprint 1.
3. **¿El vendedor necesita ver en el panel cuáles borradores dejó?** Con `BORRADOR_DEJADO` como
   estado propio (S2.3), el historial ya lo puede filtrar. Definir si hace falta una vista más.
