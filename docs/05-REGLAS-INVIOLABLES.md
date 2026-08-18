# 05 — Reglas inviolables

> **Leé esto antes de escribir la primera línea de código.**
>
> Este documento no describe buenas prácticas. Describe los límites que el sistema no puede
> cruzar. Si una tarea del sprint parece requerir violar una de estas reglas, la tarea está mal
> planteada: parála y escalá.

---

## 1. Las ocho reglas

### R1 — Un guardrail vive en código Python, nunca en un prompt ni en n8n

Un prompt se puede reinterpretar. Un nodo de n8n lo desconecta cualquiera con acceso al editor.
Un `if` en FastAPI con un test que lo cubre, no.

Si alguien propone "se lo pedimos al modelo en el prompt", la respuesta es no.

### R2 — Verificar la identidad del contacto antes de escribir, y abortar si no coincide

Es el paso más importante del sistema. Ningún atajo, ninguna optimización, ningún "ya lo
verificamos antes". Se verifica **inmediatamente antes de escribir**, cada vez.

Si el header del chat no se puede leer, o no coincide, o el número no se puede resolver a E.164:
**se aborta ese envío y se reporta.** Nunca se escribe "por las dudas".

### R3 — El sistema falla cerrado

Ante cualquier duda, el sistema **no envía**. Timeout, selector que no aparece, respuesta
ambigua, error inesperado: no enviar. La opción segura es siempre la de no mandar el mensaje.

Nunca escribas un `except: pass` en el camino de envío.

### R4 — El modelo redacta; el código decide y envía

El LLM nunca decide a quién escribirle, cuántos mensajes mandar, ni cuándo. Sólo produce texto que
después pasa por validación. El paso de envío no involucra al modelo en absoluto.

### R5 — Todo lo que sale queda registrado, y el registro es inmutable

`auditoria` no acepta `update` ni `delete`. Se configura a nivel de MongoDB, no por convención.

### R6 — Sin consentimiento del vendedor, no se envía

Si `vendedores.acepto_condiciones_en` es `null`, el backend rechaza encolar envíos para esa
persona. Salen mensajes en su nombre desde su línea: tiene que constar que lo sabe. Ver §6.

### R7 — Del Sprint 0 al 3, el código de envío no existe en el repositorio

No es un olvido: es una decisión. Mientras se construyen las fundaciones queremos que sea
técnicamente imposible que salga un mensaje. No agregues "por las dudas" un método `enviar()` que
todavía no toca.

### R8 — `raw` y `stderr` siempre presentes, también en éxito

Todo resultado de job los incluye. Ante un error, se leen **antes** de suponer qué pasó. Toda la
arquitectura está diseñada para que existan; usalos.

---

## 2. Guardrails — la tabla completa

Todos se verifican **dos veces**: en el backend antes de encolar, y en el agente antes de ejecutar.
La duplicación es intencional: el agente no confía en el backend.

| # | Guardrail | Valor por defecto | Backend | Agente | Al violarse |
|---|---|---|---|---|---|
| G1 | Placeholder sin resolver (`{...}`, `{{...}}`, `[...]`, `XXX`, `TODO`) | — | ✅ | ✅ | `RECHAZADO` |
| G2 | Texto vacío o sólo espacios | — | ✅ | ✅ | `RECHAZADO` |
| G3 | Texto más largo que el máximo | 600 car. | ✅ | ✅ | `RECHAZADO` |
| G4 | Tope de mensajes por corrida | 25 | ✅ | — | corta la corrida |
| G5 | Tope diario por máquina | 20 | ✅ | ✅ | no encola |
| G6 | Tope diario global | 160 | ✅ | — | no encola |
| G7 | Anti-duplicado por contacto | 7 días | ✅ | ✅ | `RECHAZADO` |
| G8 | Ventana horaria | 09:00–19:00, hábiles | ✅ | ✅ | no envía |
| G9 | Contacto en lista de exclusión | — | ✅ | ✅ | `RECHAZADO` |
| G10 | `run_id` sin generación previa | — | ✅ | — | `400` |
| G11 | Mensaje vencido (>24 h) | 24 h | ✅ | ✅ | `VENCIDO` |
| G12 | Ventana de veto no cumplida | 300 min | ✅ | — | no encola |
| G13 | Pausa global activa | — | ✅ | ✅ | `423` |
| G14 | Vendedor pausado | — | ✅ | ✅ | no encola |
| G15 | Vendedor sin consentimiento (R6) | — | ✅ | — | no encola |
| G16 | Identidad del contacto no coincide (R2) | — | — | ✅ | aborta ese envío |
| G17 | Campo de escritura no vacío | — | — | ✅ | aborta ese envío |
| G18 | Canario falló | 3 msj / 10 min | ✅ | — | frena la corrida |
| G19 | Presupuesto diario excedido | USD 15 | ✅ | — | frena la corrida |
| G20 | Señal de triage encendida | ver §3 | ✅ | — | `RETENIDO` |

### Cómo se testean

Existe `tests/test_guardrails.py` con **un test por guardrail que intenta violarlo y verifica que
falla**. Es el único archivo de tests que es obligatorio antes de cerrar el Sprint 6.

Cobertura mínima exigida: **100% de las funciones de guardrails.** El resto del proyecto no tiene
umbral de cobertura.

---

## 3. Triage — qué se retiene

El triage no bloquea: **aparta**. El 80–90% de los mensajes sale sin tocar nada.

| Señal | Detección | Por qué |
|---|---|---|
| `PALABRA_CONFLICTO` | El resumen del chat entrante contiene: reclamo, problema, cancelar, factura, no me interesa, abogado, devolución, garantía, defectuoso, estafa, denuncia | Un seguimiento comercial sobre un reclamo abierto es el peor error posible |
| `SIN_RESPUESTA_PREVIA` | El contacto no respondió al último seguimiento del sistema | Insistir sobre silencio es lo que dispara "bloquear/reportar" |
| `CONVERSACION_VIEJA` | `antiguedad_dias > 60` | El contexto que leyó el modelo probablemente ya no aplica |
| `IDENTIDAD_AMBIGUA` | No se pudo resolver el E.164, o el nombre coincide con más de un contacto | Duda sobre a quién se le escribe |
| `COMPROMISO_CONCRETO` | El borrador menciona precios, fechas, plazos o cantidades | Un dato inventado por el modelo se vuelve una promesa comercial |
| `CHAT_NO_COMERCIAL` | El resumen no tiene señales de intención comercial | Las líneas mezclan personal y trabajo |
| `FUERA_DE_RANGO` | Largo o tono fuera de lo esperado | Señal barata de que algo salió raro |

Cualquiera → `RETENIDO`. Ninguna → `EN_ESPERA`.

**Las listas de palabras viven en `configuracion`, no hardcodeadas.** El cliente va a querer
agregar términos de su rubro.

---

## 4. Ritmo de envío

| Parámetro | Valor | Por qué |
|---|---|---|
| Pausa entre envíos | aleatoria 45–180 s | Los patrones regulares son lo que dispara bloqueos, no el volumen |
| Orden de la lista | aleatorizado | Que no sea siempre el mismo recorrido |
| Ventana horaria | 09:00–19:00, lunes a viernes | Comportamiento humano plausible |
| Canario | 3 primeros, luego 10 min de espera | Si los 3 fallan, frena antes de romper 17 más |

**La pausa nunca es fija.** Un `sleep(60)` en el código de envío es un bug, no una simplificación.
Se implementa como `disponible_desde` escalonado con jitter en la cola.

---

## 5. Privacidad y datos

### Qué se guarda y qué no

| Dato | Se guarda | Retención |
|---|---|---|
| Texto completo de mensajes del cliente | **No** | — |
| Resumen de una línea del último mensaje | Sí | 90 días (TTL) |
| Texto que enviamos | Sí | indefinido |
| Adjuntos, imágenes, audios | **No** | — |
| Agenda completa del vendedor | **No** | — |
| Auditoría | Sí | indefinido |

Los clientes del cliente son **terceros que no participaron de esta decisión**. Guardar lo mínimo
no es sólo prudencia legal: es lo correcto.

Marco aplicable: Ley 25.326 de Protección de Datos Personales (Argentina). El cliente debe tener
una política escrita, aunque sea breve, y conocerla.

### Seguridad técnica

- TLS en todo. Nunca token en texto plano sobre HTTP.
- **Un token por máquina**, rotable y revocable individualmente. El MVP usaba uno compartido: si
  se filtraba había que cambiarlo en las 8.
- Tokens hasheados con Argon2id. Nunca en claro en la base.
- Secretos en variables de entorno o gestor. Nunca en el `.bat`, nunca versionados.
- **MongoDB Atlas: aislamiento por credenciales, no por red** (D14). El clúster tiene endpoint
  público con TLS; lo que lo protege son las credenciales y la lista de IPs. En concreto: TLS
  obligatorio, un usuario por servicio con permisos mínimos, credenciales distintas entre staging y
  producción, rotación documentada, y proyectos de Atlas separados. La lista de IPs es reducción de
  superficie, no aislamiento.
- Backups diarios cifrados, con restauración probada.
- Rate limiting en los endpoints del agente.
- **El backend nunca manda texto de prompt al agente** (ver `04` §2.2).

---

## 6. Consentimiento de los vendedores — bloqueante para el Sprint 5

El `SOP-vendedor.md` del MVP dice, textual:

> *"No envía ningún mensaje. Nunca."*
> *"Nadie va a mandar nada en tu nombre sin que pase por revisión."*

**Ambas frases dejan de ser ciertas.** Salen mensajes firmados por el vendedor, desde su línea, en
un horario en que él está trabajando, que puede no haber leído.

Requisitos antes de activar envío real para un vendedor:

1. SOP reescrito y entregado, describiendo el sistema real
2. Explicación del riesgo de bloqueo de la línea (`11-RIESGOS.md`)
3. Confirmación explícita e individual, registrada en `vendedores.acepto_condiciones_en`
4. El vendedor sabe cómo pausar su propia máquina desde el ícono de la bandeja

**Esto no es un trámite documental.** Es la diferencia entre un vendedor que colabora con el
sistema y uno que se entera cuando un cliente le pregunta por un mensaje que él no mandó. Y es la
única tarea del roadmap que no depende del equipo técnico: empezala en paralelo al Sprint 0,
porque puede tardar más que cualquier sprint.

---

## 7. Qué hacer si encontrás un problema de seguridad

1. **No lo arregles solo y sigas.** Avisá al tech lead ese día.
2. Si el problema puede hacer que salga un mensaje que no debía: **apretá el kill switch primero,
   avisá después.** Nadie te va a reprochar haber frenado el sistema de más.
3. Documentalo en `10-DECISIONES.md` aunque el arreglo sea trivial.
