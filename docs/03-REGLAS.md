# 03 — Reglas, guardrails y riesgos

> Leé esto antes de escribir la primera línea. Es corto a propósito.
>
> Esto **no es un documento de ciberseguridad**. Nadie está atacando el sistema. Lo que hay acá es
> lo que evita que el sistema le arruine el día a un cliente real o le haga perder la línea de
> WhatsApp a un vendedor. Es corrección, no defensa.

---

## 1. Las cinco reglas

### R1 — Verificar la identidad del contacto antes de escribir, y abortar si no coincide

El paso más importante del sistema. Ningún atajo, ninguna optimización, ningún "ya lo verificamos
antes". Se verifica **inmediatamente antes de escribir**, cada vez.

Si el header del chat no se puede leer, o no coincide, o el número no se puede resolver a E.164:
se aborta ese envío y se reporta. Nunca se escribe "por las dudas".

### R2 — El sistema falla cerrado

Ante cualquier duda, **no envía**. Timeout, selector que no aparece, respuesta ambigua, error
inesperado: no enviar. La opción segura es siempre la de no mandar el mensaje.

Nunca un `except: pass` en el camino de envío. Un error tragado en silencio ahí es un incidente.

### R3 — El modelo redacta; el código decide y envía

El modelo nunca decide a quién escribirle, cuántos mensajes mandar, ni cuándo. Sólo produce texto
que después pasa por validación. El paso de envío no lo involucra en absoluto.

Corolario: **un límite vive en código Python, nunca en un prompt.** Si alguien propone "se lo
pedimos al modelo en el prompt", la respuesta es no.

### R4 — Sólo se escribe a números de la lista de destinos permitidos

`configuracion.destinos_permitidos` gobierna a quién puede escribirle el sistema. Se verifica en
el backend al encolar y **otra vez en el agente antes de escribir**.

Mientras se construye, la lista tiene los números de prueba: es técnicamente imposible que un
cliente real reciba algo. Abrirla a `["*"]` es un acto deliberado que queda registrado.

Esta regla reemplaza a la vieja "el código de envío no existe hasta el sprint 4". Da la misma
garantía sin impedir construir y probar el envío desde el primer día.

### R5 — Todo lo que sale queda registrado, y el registro es inmutable

`auditoria` no acepta `update` ni `delete`. El día que un cliente reclame por un mensaje, esto es
lo único que responde — y si se puede editar, no responde nada.

**Está implementado en dos capas, que protegen de cosas distintas:**

1. **El rol de MongoDB con el que se conecta el backend no otorga `update` ni `remove` sobre esa
   colección.** Protege de un error en producción: aunque alguien escriba
   `base["auditoria"].update_one(...)`, la base lo rechaza.
2. **`core/auditoria.py` no expone ninguna forma de modificar.** Protege de que ese código se
   escriba en primer lugar.

Un detalle que condiciona el diseño: **MongoDB no sabe prohibir.** Los roles sólo otorgan, así que
no existe "readWrite pero sin update acá". Hay que enumerar colección por colección — si se diera
`readWrite` sobre la base entera, `update` sobre `auditoria` vendría incluido y no habría forma de
sacárselo. Por eso el rol está en `app/core/permisos.py` y no en una línea de configuración.

Y por eso el Mongo local levanta **con autenticación**: un servidor sin `--auth` no aplica roles, y
el test que verifica todo esto pasaría en verde sin probar nada.

Y: **`raw` y `stderr` siempre presentes en todo resultado de job, también en éxito.** Ante un
error se leen antes de suponer qué pasó.

---

## 2. Los ocho guardrails

Ocho, no veinte. Cada uno cubre un modo de falla que cuesta caro. El resto se agrega el día que
aparezca el caso, no antes.

| # | Guardrail | Por defecto | Backend | Agente | Al violarse |
|---|---|---|---|---|---|
| G1 | **Identidad del contacto coincide** (R1) | — | — | ✅ | aborta ese envío |
| G2 | **Destino en la lista permitida** (R4) | los de prueba | ✅ | ✅ | `DESTINO_NO_PERMITIDO` |
| G3 | Texto válido: no vacío, sin placeholders, ≤ largo máximo | 600 car. | ✅ | ✅ | `DESCARTADO` / `rechazado` |
| G4 | Topes: por máquina por día, y por corrida | 20 / 25 | ✅ | ✅ | no encola |
| G5 | Anti-duplicado por contacto | 7 días | ✅ | — | `DESCARTADO` / `rechazado` |
| G6 | Ventana horaria y días hábiles | 09–19, L–V | ✅ | ✅ | no envía |
| G7 | Pausa global o vendedor pausado (kill switch) | — | ✅ | ✅ | `423` |
| G8 | Campo de escritura vacío antes de escribir | — | — | ✅ | `CAMPO_NO_VACIO` |

**Los que están en las dos columnas se implementan dos veces a propósito.** No porque el agente
desconfíe del backend, sino porque un job puede quedar encolado y ejecutarse minutos después: el
tope o la pausa pueden haber cambiado en el medio. La segunda verificación es contra el paso del
tiempo, no contra el otro componente.

**G1 y G8 sólo existen en el agente** porque son las dos únicas cosas que se verifican mirando la
pantalla real.

**Cómo se testean.** `tests/test_guardrails.py`, un test por guardrail que **intenta violarlo** y
verifica que falla. Un test del camino feliz no prueba nada acá. Cobertura exigida: 100% del
archivo de guardrails y del de estados. El resto del proyecto no tiene umbral — la cobertura por
la cobertura no sirve.

---

## 3. Triage: qué se retiene

El triage no bloquea, **aparta**. La mayoría de los mensajes sale sin tocar nada.

| Señal | Detección | Por qué |
|---|---|---|
| `PALABRA_CONFLICTO` | El resumen del chat contiene: reclamo, problema, cancelar, factura, no me interesa, abogado, devolución, garantía, defectuoso, estafa, denuncia | Un seguimiento comercial sobre un reclamo abierto es el peor error posible |
| `SIN_RESPUESTA_PREVIA` | El contacto no respondió al último seguimiento que le mandamos | Insistir sobre silencio es lo que dispara "bloquear/reportar" |
| `IDENTIDAD_AMBIGUA` | No se pudo resolver el E.164, o el nombre coincide con más de un contacto | Duda sobre a quién se le escribe |
| `COMPROMISO_CONCRETO` | El borrador menciona precios, fechas, plazos o cantidades | Un dato inventado por el modelo se vuelve una promesa comercial |
| `CHAT_NO_COMERCIAL` | El resumen no tiene señales de intención comercial | Las líneas mezclan personal y trabajo |

Cualquiera → `RETENIDO`. Ninguna → `EN_ESPERA`.

**Las listas de palabras viven en `configuracion`, no hardcodeadas.** El cliente va a querer
agregar términos de su rubro.

> **Nota sobre la antigüedad.** La versión anterior de este documento retenía los chats de más de
> 60 días. Se sacó: el MVP validó que leer los chats recientes funciona, y la antigüedad de una
> conversación no es por sí sola una señal de riesgo — es, de hecho, el motivo por el que existe
> el sistema. Si con datos reales aparece que los chats viejos generan peores borradores, se
> vuelve a evaluar.

**Calibración.** Sobre borradores reales, el triage tiene que retener entre el 10% y el 20%, y un
humano tiene que estar de acuerdo con lo que retuvo. Si retiene el 40%, molesta y se va a
terminar apagando.

---

## 4. Ritmo de envío

Esto no es una formalidad: es lo único que se interpone entre la automatización y que Meta
bloquee la línea de trabajo de una persona.

| Parámetro | Valor | Por qué |
|---|---|---|
| Pausa entre envíos | aleatoria, 45–180 s | Los patrones regulares son lo que dispara bloqueos, no el volumen |
| Orden de la lista | aleatorizado | Que no sea siempre el mismo recorrido |
| Ventana horaria | 09:00–19:00, hábiles | Comportamiento plausible |
| Canario | los 3 primeros, después 10 min de espera | Si los 3 fallan, frena antes de romper 17 más |

**La pausa nunca es fija.** Un `sleep(60)` en el código de envío es un bug, no una simplificación.
Se implementa con `disponible_desde` escalonado en la cola, no bloqueando un hilo.

---

## 5. Privacidad

| Dato | Se guarda | Retención |
|---|---|---|
| Texto completo de mensajes del cliente | **No** | — |
| Resumen de una línea del último mensaje | Sí | 90 días |
| Texto que enviamos | Sí | indefinido |
| Adjuntos, imágenes, audios | **No** | — |
| Agenda del vendedor | **No** | — |
| Auditoría | Sí | indefinido |

Los clientes del cliente son terceros que no participaron de esta decisión. Guardar lo mínimo no
es sólo prudencia legal: es lo correcto. Marco aplicable: Ley 25.326 (Argentina).

---

## 6. Consentimiento de los vendedores

Salen mensajes firmados por el vendedor, desde su línea, que él puede no haber leído. Tiene que
saberlo.

No es un trámite ni un blindaje legal: **es una conversación por persona**, y es la diferencia
entre un vendedor que colabora con el sistema y uno que se entera cuando un cliente le pregunta
por un mensaje que él no escribió.

Antes de activar el envío real para una persona:

1. Se le explica qué hace el sistema y que envía en su nombre
2. Se le explica el riesgo de bloqueo de la línea, sin minimizarlo
3. Se registra en `vendedores.acepto_condiciones_en`
4. Sabe pausar su propia máquina desde el ícono de la barra de menú

**El backend no encola envíos para una máquina sin ese campo.** No bloquea ninguna fase de
desarrollo: bloquea activar a esa persona.

⚠️ El `SOP-vendedor.md` del MVP dice textual *"No envía ningún mensaje. Nunca."*. Deja de ser
cierto. Hay que reescribirlo **y retirar de circulación el viejo** — Drive, mails, impresos. El
punto que se olvida es el segundo.

---

## 7. Riesgos, ordenados por costo

### 7.1 Escribir en el chat equivocado

El más caro. Un seguimiento comercial en la conversación equivocada es un problema inmediato con
un cliente que paga.

**Mitigado por:** R1 (verificación por código, no por modelo), R4 (lista de destinos), comparación
E.164 exacta inmediatamente antes de escribir, aborto si el número no resuelve, y una prueba
deliberada de identidad incorrecta antes de habilitar el envío real.

**Si pasa:** kill switch, ver el alcance en `auditoria`, avisarle al vendedor **antes** de que el
cliente pregunte, no reanudar hasta entender la causa.

### 7.2 Bloqueo de una línea por WhatsApp

Automatizar WhatsApp Web va contra los términos de Meta. **El riesgo recae sobre la línea del
vendedor, no sobre nuestra infraestructura.**

Lo que dispara bloqueos no es principalmente el volumen: son los patrones de tiempo regulares,
escribir a números no agendados, que el receptor reporte, y textos idénticos a mucha gente. **No
hay umbral seguro publicado**: 15 mensajes automatizados pueden costar un número y 200 manuales
no.

**Mitigado por:** sólo chats existentes, pausas aleatorias, textos únicos por conversación, topes
conservadores, ventana hábil, y exclusión automática ante respuesta negativa.

**El cliente tiene que conocer este riesgo y decidir con eso a la vista**, incluyendo qué pasa si
una línea se bloquea: quién se hace cargo y cómo se recupera.

**Si pasa:** frenar esa máquina, frenar el alta de máquinas nuevas, investigar qué la diferenciaba.

### 7.3 Un mensaje inapropiado llega a un cliente

El modelo lee mal una conversación y redacta algo que no corresponde.

**Mitigado por:** el triage (aparta las señales de riesgo, que es donde se concentran los errores),
la revisión antes de enviar, y la pantalla de historial para detectar patrones y ajustar el prompt.

**Nota que importa:** los errores no se distribuyen al azar. El prompt funciona bien en el chat
típico precisamente porque es típico. El error cae en el caso raro, que suele ser también el más
caro. Por eso el triage no es redundante con "revisar unos cuantos al azar".

### 7.4 Los selectores de WhatsApp Web cambian

Probabilidad alta. Es cuestión de cuándo, no de si.

**Mitigado por:** un solo archivo de selectores con fecha de verificación, falla cerrada, y un
chequeo que corre antes de cada corrida. `SELECTOR_ROTO` frena la corrida entera, no sólo ese
mensaje. Costo esperado cuando pase: una corrida.

### 7.5 Menores

| Riesgo | Mitigación |
|---|---|
| Mac apagada cuando toca enviar | El mensaje vence a las 24 h y aparece en el historial |
| Sesión de WhatsApp caída | Diagnóstico + el ícono se pone en amarillo |
| El cliente responde y nadie contesta | Se le avisa al vendedor. El sistema **no** responde |
| Duplicados por reintento | `clave_idempotencia` única en base |
| Pérdida de datos | Backup diario cifrado, con restauración probada |
| Token filtrado | Uno por máquina. Se revoca borrando la máquina del panel |

---

## 8. Si encontrás un problema

1. Si puede hacer que salga un mensaje que no debía: **apretá el kill switch primero, avisá
   después.** Nadie te va a reprochar haber frenado el sistema de más.
2. Anotalo en [`06-DECISIONES.md`](06-DECISIONES.md) aunque el arreglo sea trivial.
