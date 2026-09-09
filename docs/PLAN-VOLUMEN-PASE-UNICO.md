# Plan — Volumen y control del pase único

> Tres pedidos del cliente sobre el pase único (D38): **decidir cuántos borradores se dejan**,
> **elegir la dirección del recorrido**, y **cortar cuando a un contacto ya se le dejaron dos o
> tres**. El foco está en el primero, que es el que hoy no se puede ni explicar.
>
> Fecha: 07/09/2026.
>
> **Estado: la Fase 1 está implementada** — Sprints 1 y 2, más el arreglo de la truncación del
> Sprint 4. Decisión registrada como [D39](06-DECISIONES.md). 722 tests de backend y 313 del
> agente en verde, ruff limpio en los dos. **El frontend no se pudo verificar en la máquina de
> desarrollo** (sin `node_modules` y sin red al registry): la tarjeta nueva se revisó a mano y le
> falta pasar por `pnpm typecheck`. Las Fases 2 y 3 siguen siendo propuesta.
>
> **El hallazgo que ordena todo el plan:** el sistema *sabía* por qué paraba en 6 borradores
> —lo calculaba en `pase_unico.py`— y **tiraba ese dato a la basura**. No lo logueaba, no lo
> guardaba, y quien lo llamaba descartaba el retorno. Por eso el Sprint 1 no tocó ningún número:
> hizo visible el porqué. Subir topes a ciegas es cambiar un síntoma que no medimos.
>
> **La regla que gobernó el alcance:** nada de lo que se suma puede empeorar lo que hoy funciona.
> Cinco de las sugerencias originales podían, y están gateadas o afuera — el detalle en la
> sección 0.

---


## 0. Qué se hizo, qué se gateó, y qué quedó afuera

El pedido tenía una condición: **no arriesgar lo que hoy funciona.** Cada sugerencia se revisó
contra eso antes de escribirla. Cinco podían romper algo, y ninguna se implementó tal como estaba
propuesta.

### Lo que podía romper, y cómo quedó

| Sugerencia | El riesgo concreto | Cómo quedó |
|---|---|---|
| Arreglar `fin_de_ventana` **solo** | Salto de 6 a 25 el mismo día del deploy: corridas de ~100 min y 4× el costo, sin que nadie lo decidiera | Salió **junto** con `tope_diario_borradores` y `max_tandas_por_maquina`. El volumen es ahora un número del panel, no un efecto secundario |
| Tope por contacto sin arreglar la truncación | Los "agotados" empujan fuera de los 60 lugares a los recientes → **un segundo borrador a un cliente** | La truncación se arregló **primero** (ya está). El tope por contacto va después, en Fase 3 |
| `G9` bloqueante en el circuito viejo | Descarta mensajes por un contador nuevo, sin haber visto nunca sus números | Nace **apagado** (`max_borradores_por_contacto = 0` = sin límite). Se prende cuando el panel muestre los datos reales |
| `tope_por_maquina` **reemplazando** al global | 3 máquinas × 25 = 75 borradores sin que nadie lo pidiera | El tope de corrida pasó a contarse por máquina, pero **el tope diario lo tapa**: el techo real es 20 por máquina por día |
| Meter `BORRADOR_DEJADO` en `enviados_hoy` | Cambia G4 del circuito de **envío**, que anda bien | **Descartado.** Contador nuevo y aparte (`borradores_dejados_hoy`) |
| Dry run que no escribe | Toca el recorrido que hoy funciona | **Afuera.** Útil, pero no se paga con el riesgo ahora |
| Cursor para `recientes` | Estado nuevo entre corridas: puede saltear gente | **Afuera.** Es eficiencia, no corrección: `no_escribir` ya cubre lo importante |

### Por qué el circuito viejo no corre ningún riesgo

Todo lo de la Fase 1 vive en la ruta del pase único. `modo_borrador = "playwright"` —que sigue
siendo el default de fábrica— pasa por `corridas._payload_listar` y nunca toca
`pase_unico.encolar_tanda`. Los dos únicos archivos compartidos que se tocaron sumaron cosas sin
cambiar ninguna:

- `mensajes.py` — una función nueva. `enviados_hoy` quedó intacta.
- `configuracion.py` — dos campos nuevos. Ninguno existente cambió de valor.

---
## 1. Cómo se decide hoy el volumen

No hay una perilla de volumen. Hay cuatro cosas que se multiplican y se pisan:

| Qué | Dónde | Hoy |
|---|---|---|
| `chats_por_tanda` | `configuracion.py:75` | 6 (tope duro 12 en `panel.py:677` y `borradores.py:33`) |
| `tope_por_corrida` | `configuracion.py:81` | 25, **compartido entre todas las máquinas** |
| Cuántas tandas se encadenan | `pase_unico.py:286-304` | sin límite; para cuando el modelo dice basta |
| Cuánto tarda cada tanda | `claude_code.py:59` | hasta 20 min |

El volumen real por corrida es:

```
min( tope_por_corrida (global),  tandas × chats_por_tanda,  chats que quedan en la ventana )
```

Cada tanda es **una invocación completa del modelo con navegador**. Llegar a 25 con tandas de 6
son 5 tandas encadenadas: hasta ~100 minutos por máquina, en serie. Eso no es un detalle de
implementación — es el techo real, y es lo que hay que poner adelante del cliente cuando pida
"más volumen".

---

## 2. Diagnóstico: por qué salen 6-7 y no 25

Cuatro hipótesis, en orden de probabilidad. Las cuatro son verificables con el Sprint 1.

### H1 — El modelo marca `fin_de_ventana: true` al llegar a los 6 *(la más probable)*

El bloque de recorrido del modo `recientes` (`agente/agente/jobs/borradores.py:80-88`) dice:

> *Frena cuando hayas dejado {{N_CHATS}} borradores, **o** cuando los chats que veas sean ya más
> viejos que {{ANTIGUEDAD_MAX}} días. Si frenaste porque ya no queda ningún chat dentro de la
> ventana, marcá `"fin_de_ventana": true`.*

Dos causas de freno, una sola instrucción de marcado, y ninguna que diga cuándo va `false`. Un
modelo que dejó 6 borradores y además scrolleó hasta ver chats viejos tiene todos los motivos
para poner `true`. Y `true` corta la cadena en seco: `pase_unico.py:287-288` pone
`fin = "fin_de_ventana"`, no encola tanda siguiente, y `_terminar_si_no_queda_nada` cierra la
corrida **en verde, con 6 borradores**.

Que sea eso es casi seguro por contraste: el bloque de barrido (`borradores.py:90-110`) sí
desambigua —lista `true` y `false` con su significado y cierra con *"Ante la duda, false"*—
justo porque ahí el problema se pensó. El de `recientes` quedó sin esa mitad.

El "6-7" que reporta el cliente encaja: una máquina corta en 6 (una tanda), otra alcanza a
encadenar una segunda que trae 1 y ahí sí se queda sin ventana.

### H2 — La segunda tanda vuelve vacía

`armar_payload` manda `no_escribir` (`pase_unico.py:139-153`) con todo contacto tocado en los
últimos `dias_anti_duplicado` (7) — incluidos los 6 de la tanda anterior. Con
`antiguedad_max_dias = 90` y una lista de chats corta, la segunda pasada puede no encontrar nada
nuevo: `pase_unico.py:291-292` lo marca `tanda_vacia` y corta. Es un final correcto, pero hoy es
indistinguible de H1.

### H3 — El tope de 25 es global y las máquinas se lo comen entre ellas

`pase_unico.py:186-189` cuenta los `BORRADOR_DEJADO` de la corrida **sin filtrar por máquina**, y
`:206` achica la tanda siguiente con esa cuenta. Con tres vendedores, el que reporta primero se
lleva el presupuesto y a los otros les toca una tanda recortada. No explica el 6-7 en una máquina
sola, pero **es la pared contra la que va a chocar cualquier aumento de volumen.** El circuito
viejo tiene el mismo criterio (`corridas.py:602-616`), así que el arreglo vale para los dos.

### H4 — El sistema sabe la respuesta y la tira

`Procesado.fin` se calcula en `:288`, `:292` y `:304`, se devuelve… y `agente.py:291` ignora el
retorno. El log de `:266` cuenta `registrados`, `salteados` y `repetidos` — **nunca el motivo del
final**. Hoy no hay forma de distinguir H1 de H2 sin leer a mano el `raw` del job.

---

## 3. Sprint 1 — Que se vea por qué paró *(medio día, sin cambios de comportamiento)*

Nada de esto cambia un solo borrador. Es lo que convierte "salen 6-7" en un dato.

- **S1.1** — `fin` entra al log de `pase_unico_procesado` (`pase_unico.py:266`), junto con el
  `n_chats` pedido y el `fin_de_ventana` crudo del reporte.
- **S1.2** — Cada tanda deja su renglón en la corrida: `tandas: [{n, maquina, visitados, dejados,
  salteados, fin}]`. Escritura aditiva con `$push`, nunca bloqueante — vale la misma regla que
  todo `procesar_reporte`: si esto falla se pierde una fila del panel, nunca un borrador.
- **S1.3** — El panel lo dice en castellano en la tarjeta de la corrida: *"Paró porque el
  recorrido dijo que no quedan chats en la ventana"* / *"…porque se alcanzó el tope"* / *"…porque
  la tanda no visitó ningún chat"* / *"…porque la tanda falló"*.

**Criterio de salida:** después de una corrida real, alguien puede decir en una frase por qué
salieron N borradores. Sin eso, los sprints siguientes son adivinanza.

---

## 4. Sprint 2 — El volumen se decide *(el foco del pedido)*

### S2.1 — Arreglar `fin_de_ventana` en modo recientes *(la palanca más grande, y es texto)*

`RECORRIDO_RECIENTES` pasa a desambiguar igual que el de barrido: qué significa `true`, qué
significa `false`, y *"Ante la duda, false"*. Explícito: **llegar a `{{N_CHATS}}` es `false`** —
el sistema sigue desde ahí en la tanda siguiente.

Es una edición de prompt de cinco líneas y, si H1 es cierta, sola lleva de 6 a lo que el tope
permita. **Va primero, antes de tocar ningún número:** subir el tope con este bug adentro no
cambia nada, porque no es el tope el que está frenando.

### S2.2 — El tope deja de ser un pozo común

Nuevo `tope_por_maquina_por_corrida` (default = el `tope_por_corrida` actual, para que la
migración no cambie nada). `encolar_tanda` filtra `dejados` por `maquina`, y `tope_por_corrida`
queda como paraguas global. Recién con esto "quiero más volumen" escala con la cantidad de
vendedores en vez de repartir 25 entre todos.

### S2.3 — Un límite de tandas que no sea el tope

Nuevo `max_tandas_por_maquina` (default 6). Hoy la cadena sólo la corta el tope o el modelo; con
topes más altos eso es una corrida de horas y una factura sin techo. Este número es la perilla
honesta de **tiempo**: 6 tandas × 20 min ≈ 2 h por máquina en el peor caso.

### S2.4 — El techo de la tanda se queda en 12, y se explica

La tentación es subir `chats_por_tanda`. La respuesta es no, y el motivo ya está escrito en
`claude_code.py:55-59`: la tanda corta existe para que una falla pierda una tanda y no la
corrida. **El volumen se sube con más tandas, no con tandas más grandes.** Subir el techo de 12
sólo después de medir el timeout con datos de máquina real.

### S2.5 — El panel muestra la aritmética, no tres números sueltos

Una tarjeta "Volumen" que diga, con los valores actuales:

> *Hasta **N borradores por máquina** por corrida, en tandas de **Y**. Como mucho **Z** tandas.
> Estimado: **~M minutos** y **~$K** por máquina.*

El costo ya se acumula por corrida (`corridas.costo_usd`); el estimado sale del promedio de las
últimas tandas. Es lo que hace que la perilla se pueda usar sin que nadie se sorprenda.

---

## 5. Sprint 3 — La dirección del recorrido

**Buena noticia: la mitad ya existe.** `modo_lectura` (`configuracion.py:60`) es exactamente eso
—`recientes` = de arriba hacia abajo, `barrido` = del fondo del historial hacia hoy— y el pase
único ya lo respeta (`pase_unico.py:87-89`). Lo que falta es que se llame así en el panel y que
el eje sea de verdad independiente.

- **S3.1 — Renombrar en el panel *(cero riesgo)*.** "Los más recientes" → **"De arriba hacia
  abajo (los más nuevos primero)"**; "Barrido del historial" → **"De abajo hacia arriba (los más
  viejos primero)"**, manteniendo la explicación del cursor.
- **S3.2 — El eje de verdad.** Hoy "de abajo para arriba" **obliga** a barrido, y barrido
  *ignora la ventana de antigüedad*: se va al fondo del WhatsApp. "Los más viejos **dentro de los
  últimos 90 días**" hoy no se puede pedir. Nuevo `orden_recorrido:
  "mas_nuevos_primero" | "mas_viejos_primero"`, que sólo afecta al bloque `RECORRIDO_RECIENTES`.
  Toca: `configuracion.POR_DEFECTO`, el `Literal` de `panel.py:671`, `armar_payload`,
  `ejecutor.py:125-139`, dos variantes del bloque en `borradores.py`, y el toggle del panel.
- **⚠️ Lo que hay que decir en el panel:** en `recientes` no hay cursor. Yendo de abajo para
  arriba dentro de la ventana, cada corrida arranca en el mismo lugar; lo único que evita repetir
  es `no_escribir`. El cursor persistente es exclusivo del barrido
  (`vendedores.registrar_barrido`).

---

## 6. Sprint 4 — Tope de borradores por contacto

**El pedido:** si a un cliente ya se le dejaron dos o tres, se corta.

Hoy sólo existe `dias_anti_duplicado` (7 días, `guardrails.py:253-259`): frena repetir *esta
semana*, no acumular seis seguimientos en seis meses.

- **S4.1** — Nuevos `max_borradores_por_contacto` (default 3) y
  `ventana_borradores_por_contacto_dias` (default 180). Con ventana, no perpetuo: un cliente que
  no compró en marzo puede volver a interesar en noviembre, y un tope sin vencimiento es una
  lista negra que nadie decidió armar.
- **S4.2 — Preventivo, que es el único que sirve en el pase único.** Los "agotados" entran a
  `no_escribir` (`pase_unico.py:139-153`), **antes** que los recientes, porque la lista se trunca.
  Es la única barrera real: cuando el reporte vuelve, el borrador ya está escrito en WhatsApp.
- **S4.3 — La red abajo.** `G9_TOPE_POR_CONTACTO` en `guardrails.revisar`: **bloqueante** en el
  circuito viejo, **señal** en el pase único — el mismo patrón que ya usan las señales de
  `_registrar_dejado`. Honestidad sobre lo que hace: una señal no des-escribe el borrador; marca
  la fila para que alguien lo borre a mano. Vale para el caso raro, no para el normal.
- **⚠️ `contacto_id` vs nombre.** El tope es por persona, pero el pase único sólo ve nombres. Se
  cuenta por `contacto_nombre` para la lista preventiva (que ya es por máquina) y por
  `contacto_id` para el guardrail.

### El problema que S4 destapa, y que hay que arreglar sí o sí

`_no_escribir` termina en `sorted(...)[:60]` (`pase_unico.py:153`). **La truncación es
alfabética.** Con más de 60 contactos tocados en la ventana, los nombres de la T a la Z se caen
de la lista en silencio — y a esos se les vuelve a escribir. Hoy con 6-7 borradores no se nota;
con volumen alto y una lista de agotados que sólo crece, es el bug que va a aparecer.

Dos arreglos, los dos chicos:

1. **Filtrar por relevancia en vez de truncar por alfabeto.** En `recientes` sólo pueden aparecer
   contactos cuyo último mensaje esté dentro de `antiguedad_max_dias`: filtrar por eso achica la
   lista a los que el modelo realmente puede ver, y de paso la vuelve correcta.
2. **Ordenar por lo que importa y recién ahí cortar:** agotados primero, después los más
   recientes. Y subir `MAX_NOMBRES` para `no_escribir` a ~120, medido contra el tamaño del prompt.

Lo mismo aplica a `ya_vistos` (`:122`, `[-60:]`): con volumen alto, un chat ya visitado puede
volver a caer fuera de la lista. No es grave —el campo-no-vacío lo saltea— pero se paga leerlo.

---

## 7. Cinco sugerencias que no pediste y valen la pena

1. **El tope diario no cuenta los borradores.** `enviados_hoy` (`mensajes.py:277-289`) filtra por
   `EN_ESPERA | ENVIANDO | ENVIADO` — **`BORRADOR_DEJADO` no está**. O sea: `tope_diario_maquina`
   no limita nada en el pase único, y dos corridas en un día dejan el doble sin que ningún tope
   se entere. Con el volumen actual da igual; con el que pedís, no. Hay que decidirlo explícito:
   o entra al conteo, o se crea `tope_diario_borradores`. **Recomiendo lo segundo:** son cosas
   distintas —uno protege la línea del vendedor, el otro protege su bandeja— y mezclarlos hace
   que aflojar uno afloje el otro sin querer.
2. **Un recorrido de prueba que no escribe.** El mismo prompt sin los pasos c y d: reporta qué
   chats *tomaría* y qué diría, sin dejar nada. Es la forma barata de calibrar volumen, dirección
   y ventana antes de gastar borradores reales en la línea de un vendedor. Como el pase único es
   una sola pasada, sale casi gratis.
3. **Cursor también para `recientes`.** Hoy `ya_vistos` muere con la corrida. Si el tope corta a
   la mitad, la corrida siguiente vuelve a leer los mismos chats de arriba para saltearlos por
   `no_escribir`: se paga la lectura y no queda nada. Un cursor por máquina, como el del barrido,
   lo arregla.
4. **Dos métricas antes de aflojar.** `tasa_de_edicion` ya existe (`mensajes.py:339`). Faltan
   **tasa de descarte** y **borradores por contacto** en el panel. Son las dos que dicen si el
   volumen nuevo sigue siendo útil o si el vendedor está tirando la mitad — que es la pregunta
   real detrás de "quiero más".
5. **Registrar las decisiones como D39-D41.** Convención de la casa: el tope por máquina, el eje
   de dirección y el tope por contacto son decisiones con contrapartida, no configuración. Que
   queden escritas evita volver a discutirlas en tres meses.

---

## 8. Orden, riesgo y tests

| # | Qué | Riesgo | Por qué en ese orden |
|---|---|---|---|
| 1 | S1 — instrumentación | ninguno | Sin esto, todo lo demás es adivinanza |
| 2 | S2.1 — prompt de `fin_de_ventana` | bajo | Si H1 es cierta, sola resuelve el pedido principal |
| 3 | S4 §"el problema que destapa" — truncación alfabética | bajo | Es un bug hoy y empeora con volumen |
| 4 | S2.2 / S2.3 — tope por máquina y tope de tandas | medio | Migración de config; los defaults no cambian nada |
| 5 | S3 — dirección | bajo | Toca cinco archivos pero ninguno decide alcance |
| 6 | S4 — tope por contacto | medio | Guardrail nuevo: `guardrails.py` exige 100% de cobertura |
| 7 | S2.5 / §7.4 — panel | bajo | Se hace cuando los números ya son estables |

**Lo que no se toca:** las tres reglas del prompt, el campo-no-vacío, `texto_enviado`, y que nadie
envíe. Todo este plan mueve **cuántos** y **en qué orden**, nunca **qué** se escribe ni **quién**
aprieta enviar.

**Tests:** cada sprint agrega sus casos a `backend/tests/test_pase_unico.py` y
`agente/tests/test_ejecutor.py`. Los que no pueden faltar:

- la cadena **no** se corta cuando el modelo devuelve `fin_de_ventana: false` habiendo llegado a
  `n_chats` (S2.1);
- dos máquinas en la misma corrida llegan cada una a su tope sin comerse el de la otra (S2.2);
- la cadena corta en `max_tandas_por_maquina` aunque sobre tope (S2.3);
- con 80 contactos tocados, los agotados **siguen** en `no_escribir` (S4, truncación);
- el contacto con 3 borradores no vuelve a aparecer, y el que tiene 2 sí (S4).
