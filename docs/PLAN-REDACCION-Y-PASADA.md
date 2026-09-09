# Plan — Redacción y pasada del pase único

> Siete pedidos sobre **cómo escribe** el pase único, dos sobre **cómo recorre**, y uno sobre
> **cuánto deja** (20 borradores por máquina y por día).
>
> Fecha: 09/09/2026. Estado: **implementado entero** el mismo día — las cinco fases, decisiones
> D40 a D44 registradas. Ver §10 para lo que cambió respecto de lo planeado.
> El apéndice §9 tiene todos los valores nuevos juntos, para no tener que releer el plan al codear.
> Base: `main` en `5affaec`, con D38 (pase único) y D39 (volumen por día y por máquina) ya en verde.
>
> **La regla que ordena el plan, igual que en [PLAN-VOLUMEN-PASE-UNICO](PLAN-VOLUMEN-PASE-UNICO.md):**
> nada de lo que se suma puede empeorar lo que hoy funciona. El circuito viejo
> (`modo_borrador = "playwright"`) no se toca en ninguna fase.
>
> **Y una regla nueva, propia de este plan:** *el volumen va último, pero va*. Los 20 borradores
> por máquina y por día están adentro del plan, con los números puestos (§6) y con los timeouts del
> agente subidos para que entren. Lo único que se les pide es el orden: seis de los siete pedidos de
> redacción son "escribió algo que no debía escribir", y subir de 6-7 a 20 **antes** de arreglar la
> redacción es multiplicar por tres exactamente lo que molestó.

---

## 0. Las dos definiciones que fijamos antes de escribir

| Pregunta | Respuesta que rige este plan |
|---|---|
| "De atrás para adelante y máximo 3 semanas de cercanía" | **Del más viejo hacia hoy, frenando a 21 días.** El recorrido arranca en el extremo viejo de la ventana y camina hacia el presente; ningún chat cuyo último mensaje tenga **menos de 21 días** recibe borrador. En config: `antiguedad_min_dias = 21` y orden invertido. |
| "No recontactar problemáticos" / "si dice ya compré" | **Se memoriza.** No alcanza con que el modelo lo decida cada vez: el contacto queda vetado en la base y viaja en la lista de "no escribir" de todas las corridas siguientes. Se deja de pagar la lectura de ese chat y no depende de que el modelo acierte dos veces seguidas. |

---

## 1. Cada pedido, traducido a causa concreta

Lo importante de esta tabla es la columna del medio: **cuatro de los siete pedidos no son "el modelo
escribe mal", son "el prompt no se lo pide" o "el sistema no se lo puede decir".**

| # | Pedido | Por qué pasa hoy | Dónde se arregla |
|---|---|---|---|
| P1 | No recontactar problemáticos ni disconformes | El prompt **no menciona el conflicto en ningún lado**. `palabras_conflicto` existe pero sólo la lee `triage.evaluar`, que corre en el circuito viejo — en el pase único nadie la mira | Prompt + veto memorizado + señal |
| P2 | Evitar exceso de signos | El prompt dice *"sin signos de exclamacion de mas"*: no es una regla, es una opinión. Nada verifica | Prompt (regla contable) + señal `EXCESO_DE_SIGNOS` |
| P3 | Si ya compró, no preguntar por la misma venta | El prompt sólo conoce dos finales: dejar borrador de seguimiento, o saltear por `sin_tema`. **La venta cerrada no tiene rama** | Prompt: tercera rama, mensaje de post-venta |
| P4 | "No analiza nada, manda mensajes de chats que encuentra a mano" | Dos fallas distintas: nada obliga a leer más que el último mensaje, y nada verifica que el borrador se apoye en algo real. Además el recorrido `recientes` empieza arriba de la lista cada vez — literalmente, lo que está a mano | Prompt (`tema` + `cita` obligatorios) + Fase 3 (recorrido) |
| P5 | Sigue escribiendo muy formal | El prompt pide *"tono cordial y directo"* y nada más. Sin ejemplos y sin lista de frases prohibidas, el modelo cae al registro neutro de manual | Prompt (voz + 6 ejemplos + `frases_prohibidas`) + señal `TONO_FORMAL` |
| P6 | Repitió chats ya agarrados | Tres agujeros reales, ver §5 | Fase 4 |
| P7 | Si aparece "ya compré", no escribirle | Mismo hueco que P3 | Prompt + veto memorizado |
| P8 | De atrás para adelante, hasta 3 semanas | `recientes` va de arriba hacia abajo; `barrido` va del fondo hacia hoy pero **ignora la ventana de antigüedad**. "Los más viejos, pero no los de este mes" hoy no se puede pedir | Fase 3 |
| P9 | No repetir números de una corrida | Todas las listas anti-repetición son **por nombre**. El número nunca se compara | Fase 4 |
| P10 | **20 borradores** | `tope_diario_borradores` ya está en 20. Lo que no da es el resto de la aritmética —tandas de 6, cinco tandas, 20 minutos cada una— y va a dar menos todavía con las reglas nuevas | Fase 5: tandas de 8, timeout de 35 min, techo de visitas |

### La nota que gobierna toda la Fase 1

> *"No quiero que seamos excesivos en el personalizado, ya que muchos chats quizás no se llegan a
> ver mensajes o conversaciones viejas. Pero sí quiero una ligera personalización."*

Esto no es un matiz de tono: **es la instrucción que evita que P4 se arregle rompiendo P1.** Un
modelo al que se le exige personalizar y no tiene contexto, lo inventa. Por eso la Fase 1 define
**dos niveles de personalización** y autoriza explícitamente el nivel bajo — un mensaje corto y
humano sin tema concreto es una respuesta *correcta*, no una falla. Sin ese permiso escrito, el
modelo rellena el hueco con una conversación que no existió.

---

## 2. Fase 1 — Redacción *(el 70% del valor, y es casi todo texto)*

Toca `agente/prompts/prompt-borradores.txt`, más campos nuevos en el reporte
(`agente/agente/jobs/borradores.py`) y un módulo de señales nuevo en el backend.

### F1.1 — Reescribir `COMO REDACTAR`

El bloque actual (líneas ~120-145 del prompt) tiene cuatro viñetas de tono y ningún ejemplo.
Propuesta de reemplazo:

```
COMO REDACTAR

Escribis como escribe un vendedor argentino en WhatsApp: de vos, corto, sin
formalidad de oficina. Es un mensaje entre dos personas que ya se hablaron, no
una comunicacion de una empresa.

Reglas contables (estas no son de estilo, se cuentan):
  - UNA sola linea, hasta 3 oraciones, nunca mas de {{LARGO_MAXIMO}} caracteres.
  - CERO signos de exclamacion. Ni uno.
  - Como maximo UN signo de pregunta en todo el mensaje.
  - Sin puntos suspensivos, sin emojis, sin palabras en mayuscula sostenida.

Frases que NO se usan nunca, ni parecidas:
{{FRASES_PROHIBIDAS}}

DOS NIVELES DE PERSONALIZACION. Elegis segun lo que REALMENTE viste en el chat:

  Nivel A - hay un tema comercial concreto (un producto, una cotizacion, un
  pedido, una obra). Retomalo en UNA clausula corta y hace una pregunta. No
  reconstruyas la conversacion entera ni menciones fechas viejas.

  Nivel B - el chat es flaco: pocos mensajes, o no se entiende de que se
  hablaba. Escribi corto y humano SIN inventar un tema. El nivel B es una
  respuesta CORRECTA, no una falla: preferilo mil veces antes que suponer.

  ⚠️ Nunca supongas para llegar al nivel A. Si dudas entre A y B, es B.

EJEMPLOS

  Bien (nivel A):
    "Hola Marcelo, te escribo por las chapas que estabas viendo. Seguis con
     eso o ya lo resolviste?"
    "Hola, quedamos en que te pasaba la cotizacion del porton. La necesitas
     todavia?"
  Bien (nivel B):
    "Hola Ana, como va? Te escribo para ver si podemos retomar lo que
     estabamos hablando."
  Bien (post-venta, ver abajo):
    "Hola, vi que al final lo compraste. Te falto algo o quedo todo bien?"

  Mal, y por que:
    "Estimado, sigue en pie esa necesidad?"        -> formal, de manual
    "Hola!! Como andas?? Te queria consultar..."   -> signos de mas
    "Hola Juan, retomando nuestra charla del 14 de marzo sobre los 200m2 de
     chapa que necesitabas para la obra de Pilar"  -> personalizado de mas,
                                                      y la mitad es inventada
```

### F1.2 — La tercera rama: la venta que ya se cerró *(P3 y P7)*

En el paso 5 del prompt, entre "leer el chat" y "redactar", entra una decisión que hoy no existe:

```
   a-bis. Decidi QUE clase de chat es, antes de escribir nada:

     VENTA ABIERTA  -> hay un tema comercial sin cerrar. Es el caso normal:
                       segui al paso b.
     VENTA CERRADA  -> en el chat se ve que la compra ya se hizo (con nosotros
                       o en otro lado): "ya compre", "ya lo consegui", "lo
                       compre en otro lado", "ya me lo mandaron", o el pedido
                       se despacho. NO le preguntes por esa venta, ni si sigue
                       interesado, ni si quiere avanzar. Dos opciones:
                         - si el chat es claro, dejas un mensaje de POST-VENTA:
                           preguntas si le falto algo o si quedo todo bien. Ni
                           una palabra de volver a comprar.
                         - si no esta claro, no dejas nada.
                       En los dos casos anotas motivo "ya_compro".
     DISCONFORME    -> en el chat hay un reclamo, un enojo, una queja, una
                       cancelacion, un "no me interesa", un "no me escriban
                       mas", o cualquiera de estas palabras del dueño:
{{PALABRAS_VETO}}
                       NO dejas borrador. Ninguno. Anotas motivo "disconforme"
                       y seguis. Un seguimiento comercial arriba de un reclamo
                       abierto es el peor error que puede cometer el sistema.
```

⚠️ **Que el post-venta se pueda apagar de un click.** `mensaje_post_compra: true` en config (default
`true`, que es lo que pediste). En `false`, VENTA CERRADA nunca deja nada. Es la perilla que quiero
tener el día que un post-venta salga raro, sin esperar un deploy.

### F1.3 — Que se pueda saber si leyó *(P4)*

Dos campos nuevos, obligatorios cuando `borrador_dejado: true`:

| Campo | Qué es | Para qué |
|---|---|---|
| `tema` | 3-6 palabras: *"cotización de portón"*, *"chapas para obra"*, `null` si es nivel B | Que el panel muestre de qué habla cada borrador sin leer el texto |
| `cita` | Un fragmento **literal** del chat, hasta 80 caracteres, que es lo que el borrador retoma. Vacío en nivel B | Es el detector de mentiras más barato que existe: es difícil producir una cita literal sin haber leído |

Verificación en `borradores._revisar_chat`: nivel A (`tema` no vacío) sin `cita` ⇒ se degrada a
nivel B y se anota. En el backend, `cita` vacía en un borrador que afirma tema concreto ⇒ señal
`SIN_ANCLAJE` en la fila del panel.

⚠️ **`cita` es texto literal de un tercero.** Va guardado junto a `resumen_ultimo` y **entra al
mismo `purgar_resumenes`** de `esquema.py:214` (D1, 90 días). Si se guarda y no se purga, el plan
rompe la política de retención en silencio.

### F1.4 — Señales de redacción, en un módulo aparte

Módulo nuevo `backend/app/core/redaccion.py`: funciones **puras** que miran el texto ya escrito y
devuelven señales, sin bloquear nada.

| Señal | Cómo se detecta |
|---|---|
| `EXCESO_DE_SIGNOS` | Cuenta `!`/`¡`, `?` de más, `...`, emojis, mayúscula sostenida |
| `TONO_FORMAL` | `triage.contiene_alguna(texto, config["frases_prohibidas"])` — la misma función, sin acentos y por subcadena |
| `SIN_ANCLAJE` | Afirma tema y no trae cita |
| `CHAT_DISCONFORME` | `contiene_alguna(resumen, config["palabras_conflicto"])` sobre un chat que **sí** recibió borrador — o sea: el modelo no lo detectó y hay que ir a borrarlo a mano |

**Por qué módulo nuevo y no `guardrails.py`:** el CI exige 100% de cobertura en `guardrails` y sus
señales tienen semántica de bloqueo en el circuito viejo. Estas son informativas y sólo del pase
único. Meterlas ahí es cambiar el significado de un archivo que hoy funciona, por comodidad.

Se enganchan en `pase_unico._registrar_dejado`, sumándose a la lista `senales` que ya existe
(`pase_unico.py:~470`). Cero cambios de flujo.

### F1.5 — Dos listas nuevas de configuración

`frases_prohibidas` y `palabras_veto_chat`, con el mismo patrón que `palabras_conflicto`: viven en
`configuracion.POR_DEFECTO`, se editan por API, viajan al prompt. **El criterio queda del lado del
dueño y sin deploy**, que es lo que hace que este plan no vuelva dentro de un mes.

```python
"frases_prohibidas": [
    "sigue en pie", "quedo a disposicion", "estimado", "estimada",
    "no dude", "aguardo su respuesta", "cordial saludo",
    "me comunico con usted", "por este medio", "atentamente",
],
"palabras_veto_chat": [
    "no me interesa", "no me escriban", "no me escribas", "dejen de escribir",
    "sacame de la lista", "denme de baja", "estafa", "denuncia", "abogado",
],
"mensaje_post_compra": True,
```

> **Ajuste al implementar:** `palabras_veto_chat` quedó como la lista de *disconformidad* (lo que
> hace saltear el chat), y la familia "ya compré / compré en otro lado" quedó escrita en la rama
> VENTA CERRADA del prompt, no en la lista. Mezclarlas hacía que "ya compré" fuera disconforme.
> Y es una lista **distinta** de `palabras_conflicto` a propósito: aquélla ("factura", "problema")
> es para que una persona *mire* —enciende `CHAT_DISCONFORME` después—, ésta es para *no escribir*.
> Usar la de triage en el prompt habría salteado medio WhatsApp de un corralón.

---

## 3. Fase 2 — Los vetos se memorizan

Colección nueva `vetados`, índice único `(maquina, clave)`:

```
{ maquina, clave: "num:+549..." | "nombre:Juan Perez", motivo: "disconforme" | "ya_compro",
  cita, corrida_id, creado_en, vence_en }
```

- **Se llena sola** desde `procesar_reporte`: cada chat con motivo `disconforme` o `ya_compro`
  deja su fila. Cero trabajo manual.
- **Se lee en `_no_escribir`** (`pase_unico.py:~250`), **primero de todo**. Esto importa: la lista
  se trunca en `MAX_NO_ESCRIBIR = 120`, así que el orden decide quién se cae. Los vetados van
  arriba de los recientes, siempre.
- **Vencimiento:** `disconforme` a 365 días, `ya_compro` a 180. Un veto perpetuo es una lista negra
  que nadie decidió armar; un cliente que reclamó en marzo puede volver a interesar el año que
  viene. Los dos números van a config.
- **Clave por número cuando se puede, por nombre cuando no** — la misma escalera que
  `pase_unico._identificar`. Nunca se deduce un número.

> **Lo que NO hace esta fase:** una pantalla para editar la lista a mano. Se puede sacar a alguien
> con un `DELETE` por API. Si en un mes la lista resulta ruidosa, la pantalla se hace ahí, con
> datos reales — no antes.

---

## 4. Fase 3 — De atrás para adelante, frenando a 21 días

### El problema estructural

Hoy la dirección y la ventana **están pegadas**, y en el peor sentido:

| Modo | Dirección | ¿Respeta `antiguedad_min/max`? | ¿Cursor entre corridas? |
|---|---|---|---|
| `recientes` | de arriba hacia abajo | sí | **no** |
| `barrido` | del fondo hacia hoy | **no** (se va a 3650 días) | sí, por máquina |

Lo que pediste —*los más viejos primero, pero nada de menos de 21 días*— no es ninguno de los dos.

### F3.1 — Un eje nuevo, `orden_recorrido`

`orden_recorrido: "mas_nuevos_primero" | "mas_viejos_primero"`, default `mas_nuevos_primero` (o
sea: **la migración no cambia nada** hasta que alguien toque el switch). Sólo afecta al bloque
`RECORRIDO_RECIENTES` de `borradores.py:88`, que pasa a tener dos variantes.

La variante nueva le pide al modelo: scrollear hasta pasar `{{ANTIGUEDAD_MAX}}` días, y desde ahí
recorrer **hacia arriba** (hacia hoy), frenando en cuanto los chats bajen de `{{ANTIGUEDAD_MIN}}`
días. Y desambiguar `fin_de_ventana` igual que hoy: llegar a `{{N_CHATS}}` es siempre `false`.

### F3.2 — `antiguedad_min_dias = 21`

Un cambio de configuración, no de código: el campo ya existe, ya viaja al prompt
(`pase_unico.py:~165`) y ya está en el panel. **Lo que hace falta es que el panel diga qué
significa**, porque hoy dice "desde cuántos días de silencio" y nadie lo lee como "no toques a los
de este mes".

### F3.3 — Cursor de ventana por máquina *(y esto arregla la mitad de P6)*

En `recientes` no hay cursor: **cada corrida arranca en el mismo lugar de la lista.** Lo único que
evita repetir es `no_escribir`, que sólo conoce a los que recibieron mensaje — un chat que se
visitó y se salteó (campo ocupado, sin tema, ahora también disconforme) **no deja rastro de
ninguna clase, y la corrida siguiente lo vuelve a abrir y lo vuelve a pagar.**

Cursor nuevo `ventana.hasta_dias` en `vendedores`, hermano del de barrido y con la misma mecánica
(`vendedores.registrar_barrido` ya es casi esta función). Avanza con cada tanda que vuelve.

⚠️ **Separado del cursor de barrido, no compartido.** Son dos recorridos con extremos distintos;
compartir el campo hace que cambiar de modo salte tramos enteros del historial.

---

## 5. Fase 4 — No repetir: ni chats, ni números

P6 y P9 tienen **tres causas independientes**. Las tres hay que tocarlas o el problema vuelve.

### Causa 1 — `ya_vistos` se trunca, y se trunca al revés

`pase_unico.py:~180`: `_sin_repetidos(vistos)[-MAX_NOMBRES:]` — se queda con los **últimos 60**.
Yendo de arriba hacia abajo, los que el modelo se vuelve a cruzar apenas empieza la tanda siguiente
son los **primeros** que visitó, y son justo los que se caen.

Con 6-7 borradores nunca se llegó a 60 y por eso no se vio. Con 20 por día y contando los
salteados, se llega.

**Arreglo:** subir a 120 (igual que `no_escribir`, ya medido contra el tamaño del prompt) y quedarse
con la cola **sólo cuando el recorrido va del más viejo hacia hoy** (Fase 3), donde el riesgo sí
está en la frontera. Con el cursor de F3.3 el riesgo baja solo, porque el recorrido deja de
reempezar.

### Causa 2 — Nadie compara números *(P9, literal)*

Todas las listas son por nombre. Dos chats con nombres distintos ("Juan", "Juan Ferretería") y el
mismo teléfono son, hoy, dos personas para el sistema. Tres piezas:

1. **`no_escribir_numeros`** en el payload: los números que esta corrida ya usó, más los de la
   ventana anti-duplicado. Regla nueva en el prompt, **después** de abrir el chat (que es cuando el
   número se ve): *si el número visible está en la lista, no escribas, motivo `numero_repetido`.*
2. **Red abajo, en `_registrar_dejado`:** antes de `crear_borrador`, si ya hay un `BORRADOR_DEJADO`
   con ese `contacto_id` en esta corrida, no se registra el segundo y se cuenta aparte. No
   des-escribe nada —el borrador ya está en WhatsApp— pero convierte "creemos que repite" en un
   número del panel.
3. `telefonos` (que ya existe, con índice `(maquina, nombre)` único) es la memoria que permite
   mandar el número de un contacto **antes** de abrir su chat.

### Causa 3 — Lo visitado y salteado se olvida entre corridas

Lo cubre el cursor de F3.3, más una memoria corta de visitados por máquina (nombre + número +
fecha + resultado, ~30 días) que alimenta `ya_vistos` de la corrida siguiente.

---

## 6. Fase 5 — Los 20 borradores, y el tiempo para que entren

**Esto está adentro del plan, con los números puestos.** No queda pendiente de nada: la única
condición es de orden —va después de las reglas de redacción, no antes— y el motivo está en §0.

`tope_diario_borradores` **ya está en 20**. Lo que no cierra es el resto:

```
Hoy:  chats_por_tanda = 6   ×   max_tandas_por_maquina = 5   =  30 posibles
      pero tope_por_corrida = 25, y cada tanda que deja menos de 6 igual quema una tanda
```

Y con las reglas nuevas **van a dejar menos**: los disconformes, los "ya compré", los `sin_tema` con
la vara más alta y los `numero_repetido` son cuatro motivos nuevos de saltear. Un rendimiento
razonable a esperar es **4-5 borradores por tanda de 8, no 8.**

### F5.1 — Los timeouts suben, porque las tandas ahora hacen más

Hoy una tanda tiene 20 minutos (`agente/agente/jobs/claude_code.py:59`) y el comentario que está al
lado dice *"si no alcanzaran, la respuesta es achicar la tanda"*. **Ese comentario se escribió antes
de este plan y hay que cambiarlo con el código.** La Fase 1 le agrega trabajo real a cada chat —leer
más mensajes, clasificar la conversación en tres ramas, extraer una cita literal— y la única forma
de que entren 8 borradores es darle tiempo.

| Constante | Dónde | Hoy | Propuesto |
|---|---|---|---|
| `TIMEOUT_BORRADORES` | `agente/agente/jobs/claude_code.py:59` | 20 min | **35 min** |
| `TIMEOUT_LISTAR` | `claude_code.py:53` | 25 min | 25 min (no se toca) |
| `SEGUNDOS_PARA_DAR_POR_COLGADO` | `backend/app/core/cola.py:56` | 60 min | 60 min (no se toca) |

⚠️ **El techo y el orden del deploy.** `SEGUNDOS_PARA_DAR_POR_COLGADO` tiene que ser **mayor** que
el timeout más largo del agente: si fuera menor, el backend devolvería a la cola un job que el
agente todavía está haciendo, y ese trabajo se pagaría dos veces. Con 35 min quedan 25 de margen y
no hace falta tocarlo. **Si alguna vez se sube arriba de ~45 min, primero se sube el techo del
backend y recién después el del agente** — al revés hay una ventana en la que los jobs se duplican.
Es el mismo orden de deploy que ya está anotado en la auditoría del 28/08 (backend primero, agentes
después).

⚠️ **Y el reintento se hace más caro.** `cola.INTENTOS_POR_CODIGO = {"TIMEOUT": 2}`: un timeout más
su reintento pasan de 40 a **70 minutos** de máquina para llegar a la misma conclusión. Con el techo
de visitas de F5.2 el timeout deja de ser el freno normal y pasa a ser lo que siempre debió ser —la
red de abajo— así que el costo esperado no cambia; el del caso malo, sí.

### F5.2 — El techo que hoy falta: visitas por tanda

⚠️ **Este es el riesgo que las reglas de la Fase 1 crean, y hay que taparlo en el mismo release.**
El prompt dice *"frená cuando hayas dejado {{N_CHATS}} borradores"* — **cuenta borradores dejados,
no chats abiertos.** Una tanda con reglas estrictas puede abrir 30 chats buscando sus 8 y morir en
el timeout. Una tanda que muere en el timeout **no reporta**, y una tanda que no reporta no avanza
el cursor: se pierde todo lo leído y la próxima relee lo mismo.

`max_visitas_por_tanda = 20`, en el prompt como **segundo motivo de freno**, con su propio valor de
`fin_de_ventana: false` y motivo `tope_de_visitas` en el reporte. Sin esto, subir el timeout sólo
hace que las tandas se cuelguen más caro.

### F5.3 — Los números

| Campo | Hoy | Propuesto | Por qué |
|---|---|---|---|
| `tope_diario_borradores` | 20 | **20** | Es el número pedido y ya estaba puesto |
| `chats_por_tanda` | 6 | **8** | Con 35 min entran. El tope duro del panel (12) no se toca |
| `max_visitas_por_tanda` | — | **20** | F5.2 |
| `max_tandas_por_maquina` | 5 | **6** | A 4-5 por tanda, 20 salen en 4-5 tandas; la sexta es el margen |
| `tope_por_corrida` | 25 | **30** | Que no recorte los 20 cuando una tanda rinde bien |

```
Peor caso de tiempo:  6 tandas × 35 min = 3 h 30 por máquina, en serie
Caso esperado:        4-5 tandas × ~25 min = 1 h 40 a 2 h, y los 20 borradores salen ahí
```

**El costo, dicho de frente:** entre 4 y 6 invocaciones de modelo con navegador por vendedor por
día, cada una más larga que hoy. Sigue abierto el pendiente de cuota de la auditoría del 28/08 (un
`LISTAR` de barrido costó US$1,35 y fundió la cuota del día de una cuenta). **No frena esta fase,
pero el primer día a 20 hay que mirar el gasto de esa jornada antes del segundo** — y para eso está
la corrida canaria de §7.3.

### F5.4 — El panel dice la aritmética

La tarjeta "Volumen" que ya existe (`frontend/app/config/page.tsx:503`) suma el desglose de motivos
de salteo de la última corrida:

> *Se visitaron 42 chats y quedaron 19 borradores. Los 23 restantes: 9 con el campo ocupado, 6 sin
> tema, 4 con la venta ya cerrada, 3 disconformes, 1 número repetido.*

Sin este desglose no hay forma de distinguir "el prompt se puso estricto y está bien" de "el
recorrido se rompió". Es lo que va a decidir si los 20 se sostienen o si hay que aflojar una regla.

## 7. Mejoras que no pediste y que yo pondría

1. **Un recorrido de prueba que no escribe.** El mismo prompt sin los pasos c y d: reporta qué
   chats tomaría y qué diría, sin dejar nada. Estaba descartado en el plan anterior por no
   pagarse; **con este plan se paga solo.** La Fase 1 reescribe la voz del sistema, y hoy la única
   forma de ver si quedó bien es gastar 20 borradores reales en la línea de un vendedor. Lo pondría
   como Fase 0.
2. **Golden set de redacción, sin modelo.** 10 borradores fijos (buenos y malos) en un test que
   corre `redaccion.py` contra ellos: cero exclamaciones, frases prohibidas, placeholders, largo.
   No prueba que el modelo escriba bien; prueba que **los chequeos siguen atrapando lo que ya
   atrapaban** cuando alguien vuelva a tocar el prompt en tres meses. Barato y es la única
   regresión posible sobre texto.
3. **Una corrida canaria de una sola tanda** después del deploy de la Fase 1: `chats_por_tanda = 3`
   en una máquina, se leen los 3 borradores a mano, y recién ahí se sube. La infraestructura de
   canario por máquina ya existe (D35).
4. **Tasa de descarte por vendedor en el panel.** `tasa_de_edicion` ya existe (`mensajes.py:339`).
   Falta la de descarte, que es la pregunta real detrás de "quiero 20": si el vendedor tira la
   mitad, 20 no son 20 — son 10 y una molestia.
5. **`palabras_conflicto` al prompt del circuito viejo también.** Hoy el circuito viejo la usa en
   `triage` (que informa pero no retiene, D36) y el pase único no la usa en ningún lado. Es una
   línea de prompt y cierra P1 en las dos rutas.

---

## 8. Orden, riesgo y qué se prueba

| # | Fase | Riesgo | Por qué en ese orden |
|---|---|---|---|
| 0 | Modo prueba que no escribe (§7.1) | ninguno | Sin esto, calibrar la voz nueva cuesta borradores reales |
| 1 | **Fase 1 — redacción** | bajo (texto + señales aditivas) | Es 6 de los 7 pedidos. Y tiene que ir **antes** del volumen |
| 2 | **F5.1 + F5.2 — timeouts y techo de visitas** | bajo | Van en el **mismo release** que la Fase 1: son el riesgo que la Fase 1 crea, no una mejora aparte |
| 3 | Fase 2 — vetos memorizados | bajo (colección nueva, aditiva) | Depende de los motivos que introduce la Fase 1 |
| 4 | Fase 4 — no repetir números | medio | Payload nuevo + regla nueva en el prompt |
| 5 | Fase 3 — recorrido | medio | Cinco archivos y un cursor nuevo, pero nada decide alcance |
| 6 | **F5.3 + F5.4 — los 20 y el panel** | medio | Último a propósito, no opcional: sube el volumen sobre reglas ya verificadas |

**Tests que no pueden faltar:**

- un chat con reclamo no recibe borrador, y si lo recibe queda con señal `CHAT_DISCONFORME`
  (`backend/tests/test_pase_unico.py`);
- un borrador con `!` o con una frase prohibida enciende su señal, y uno limpio no enciende ninguna
  (`backend/tests/test_redaccion.py`, nuevo, con el golden set);
- un contacto vetado sigue en `no_escribir` con 150 contactos tocados en la ventana — o sea: el
  veto **no se cae por la truncación**;
- dos chats distintos con el mismo número: el segundo no se registra y se cuenta como repetido;
- la tanda frena por `max_visitas_por_tanda` y devuelve `fin_de_ventana: false` con motivo
  `tope_de_visitas` (`agente/tests/test_borradores.py`);
- **el timeout del pase único sigue siendo menor que `cola.SEGUNDOS_PARA_DAR_POR_COLGADO`** — un
  test que compara las dos constantes y falla si alguien sube una sin la otra
  (`backend/tests/test_cola.py`, que es donde vive el techo);
- con `orden_recorrido = "mas_viejos_primero"`, el prompt lleva la variante nueva y el cursor de
  ventana avanza (`agente/tests/test_ejecutor.py`);
- el contrato panel↔backend (`backend/tests/test_contrato_panel.py`) con los campos nuevos — **en
  el mismo commit que `frontend/lib/panel.ts`**, que es la convención de la casa.

**Decisiones a registrar en `docs/06-DECISIONES.md` antes de implementar** (la última usada en
`main` es D39):

- **D40** — la redacción tiene dos niveles de personalización, y el bajo es una respuesta correcta.
- **D41** — la venta cerrada es una rama propia: post-venta o nada, nunca seguimiento.
- **D42** — los vetos se memorizan por contacto, con vencimiento, y entran primeros a `no_escribir`.
- **D43** — el recorrido del pase único tiene eje de dirección propio, con cursor por máquina.
- **D44** — la tanda del pase único frena por techo de visitas, no por timeout: el timeout sube a 35
  minutos y pasa a ser la red de abajo. Revisa el criterio escrito en `claude_code.py:55` ("si no
  alcanzaran, achicar la tanda"), que se decidió cuando la tanda sólo leía y tipeaba.

⚠️ **Choque de numeración conocido:** la rama local `trabajo-local-limite-uso` (commit `e75caf3`,
sin integrar) usa D38-D40 para otra cosa. Si esa rama se integra primero, esta numeración se corre.

---

## 9. Apéndice — Todo lo que cambia de valor, junto

Para no releer el plan al implementar. **Nada de esta tabla cambia el circuito viejo**
(`modo_borrador = "playwright"`).

### Configuración (`backend/app/core/configuracion.py` + `panel.CambioConfiguracion` + `frontend/lib/panel.ts`)

| Campo | Hoy | Queda | Fase |
|---|---|---|---|
| `tope_diario_borradores` | 20 | 20 | — |
| `chats_por_tanda` | 6 | **8** | F5.3 |
| `max_visitas_por_tanda` | *(no existe)* | **20** | F5.2 |
| `max_tandas_por_maquina` | 5 | **6** | F5.3 |
| `tope_por_corrida` | 25 | **30** | F5.3 |
| `antiguedad_min_dias` | 0 | 0 de fábrica; **21 desde el panel** | F3.2 |
| `antiguedad_max_dias` | 90 | 90 | — |
| `orden_recorrido` | *(no existe)* | `"mas_nuevos_primero"` por defecto; el pase único se opera en `"mas_viejos_primero"` | F3.1 |
| `frases_prohibidas` | *(no existe)* | lista de §2.F1.5 | F1.5 |
| `palabras_veto_chat` | *(no existe)* | lista de §2.F1.5 | F1.5 |
| `mensaje_post_compra` | *(no existe)* | `true` | F1.2 |
| `dias_veto_disconforme` | *(no existe)* | 365 | F2 |
| `dias_veto_ya_compro` | *(no existe)* | 180 | F2 |

> ⚠️ El default de `orden_recorrido` es el de hoy a propósito: **la migración no cambia el
> comportamiento de nadie** hasta que alguien toque el switch en el panel.

### Constantes de código

| Constante | Dónde | Hoy | Queda |
|---|---|---|---|
| `TIMEOUT_BORRADORES` | `agente/agente/jobs/claude_code.py:59` | 20 min | **35 min** |
| `MAX_NOMBRES` (`ya_vistos`) | `backend/app/core/pase_unico.py:38` | 60 | **120** |
| `MAX_NOMBRES_EN_LISTA` | `agente/agente/jobs/borradores.py:37` | 60 | **120** |
| `MAX_NO_ESCRIBIR` / `..._EN_LISTA` | `pase_unico.py:52` / `borradores.py:44` | 120 | 120 |
| `MAX_POR_TANDA` | `borradores.py:33` | 12 | 12 |
| `TIMEOUT_LISTAR` | `claude_code.py:53` | 25 min | 25 min |
| `SEGUNDOS_PARA_DAR_POR_COLGADO` | `backend/app/core/cola.py:56` | 60 min | 60 min |

### Vocabulario nuevo del reporte

Motivos de salteo (`borradores.MOTIVOS_DE_SALTEO`), hoy `{campo_ocupado, sin_tema, fuera_de_lista}`:

`disconforme` · `ya_compro` · `numero_repetido` · `tope_de_visitas`

Campos nuevos por chat: `tema` (3-6 palabras o `null`) y `cita` (literal, ≤80 caracteres, **entra a
`purgar_resumenes`**).

Señales nuevas (`backend/app/core/redaccion.py`, informativas, nunca bloqueantes):

`EXCESO_DE_SIGNOS` · `TONO_FORMAL` · `SIN_ANCLAJE` · `CHAT_DISCONFORME` · `NUMERO_REPETIDO`

### Archivos que se tocan

```
agente/prompts/prompt-borradores.txt          F1  (el grueso del plan)
agente/agente/jobs/borradores.py              F1, F3, F4, F5
agente/agente/jobs/claude_code.py             F5.1
agente/agente/jobs/ejecutor.py:125-140        F3, F4, F5
backend/app/core/pase_unico.py                F1.4, F2, F3, F4, F5
backend/app/core/redaccion.py                 F1.4  (nuevo)
backend/app/core/vetados.py                   F2    (nuevo)
backend/app/core/configuracion.py             F1.5, F3, F5
backend/app/core/esquema.py                   F2 (colección), F1.3 (purga de `cita`)
backend/app/core/vendedores.py                F3.3, F4
backend/app/api/panel.py                      F1.5, F3, F5
frontend/lib/panel.ts + textos.ts             F3, F5   ← mismo commit que el backend
frontend/app/config/page.tsx                  F3, F5
frontend/app/corridas/page.tsx                F5.4
```

---

## 10. Lo que cambió al implementar

Cuatro ajustes sobre lo planeado, todos anotados en su decisión:

1. **`palabras_veto_chat` es sólo disconformidad** (§2.F1.5). La familia "ya compré" vive en la rama
   VENTA CERRADA del prompt. Y la lista es distinta de `palabras_conflicto` a propósito.
2. **Un segundo borrador a la misma persona se registra igual, con señal `NUMERO_REPETIDO`**
   (Fase 4, causa 2). El plan decía "no se registra y se cuenta aparte"; pero el borrador *está* en
   WhatsApp, y esconderlo del panel es peor que el duplicado: la fila con la señal es lo que permite
   ir a borrarlo.
3. **La memoria de visitas es una colección (`visitas`), no un campo en `vendedores`**, con índice
   único por `(maquina, nombre)` y `dias_memoria_visitados = 30` en config. Entra a `ya_vistos`
   *adelante*, para caerse primero si hay que recortar.
4. **El cursor de la ventana se borra al llegar al mínimo** (F3.3). Un barrido terminado se queda
   terminado; una ventana terminada vuelve a empezar del extremo viejo — los ya contactados los
   protege `no_escribir`, y los salteados merecen otra mirada. Se reinicia a mano desde la tarjeta
   de la máquina, igual que el barrido.

Y una cosa que el plan daba por hecha y no lo era: **`antiguedad_min_dias` no cambia de fábrica.**
Ese valor también rige el circuito viejo (`LISTAR` en modo `recientes`), y ponerlo en 21 en
`POR_DEFECTO` rompía 22 tests de ese circuito — o sea, cambiaba lo que funciona. Queda en 0 y se
pone en 21 desde el panel, igual que `orden_recorrido`, que arranca en lo de siempre: **activar el
recorrido nuevo son dos cambios en el panel, no un deploy.** El apéndice §9 lo dice así.

---

## 11. Lo que este plan NO toca

Las tres reglas que no se negocian del prompt, el campo-no-vacío, `texto_enviado`, que nadie envíe,
y el circuito viejo entero (`modo_borrador = "playwright"`). Todo lo de acá mueve **qué se escribe**
y **a quién no**, nunca **quién aprieta enviar**.
