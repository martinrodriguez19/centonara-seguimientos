# Guía de ejecución — todos los prompts en orden

> **Cómo usar este archivo.** Recorrelo de arriba abajo. Cada bloque te dice la fase, el agente, la
> superficie donde pegarlo y el prompt listo para copiar.
>
> Los prompts base de cada agente están en [`EQUIPO.md`](EQUIPO.md) y van cargados una vez, en el
> proyecto de cada uno. Esto es lo que va **en el chat**, uno por vez.
>
> **No hay plazos.** Cada bloque termina cuando se cumple su criterio.

---

## Índice

| Fase | Nombre | Prompts | Hardware |
|---|---|---|---|
| 1 | Núcleo | 8 | Cualquier máquina |
| 2 | Panel | 6 | Cualquier máquina |
| 3 | Generación | 7 | Cualquier máquina con Chrome y WhatsApp Web |
| 4 | Envío | 15 | Cualquier máquina; línea de prueba sólo al final |
| 5 | macOS y alta | 6 | **Macs** |
| | **Total** | **42** | |

**Las fases 1 a 4 se hacen desde Windows.** El MVP se validó ahí, así que `claude -p --chrome`, la
extensión y WhatsApp Web funcionan. Y Playwright contra una página web es el mismo en todos lados:
los selectores que se escriban en la fase 4 valen igual para la Mac.

**La fase 5 es lo único que necesita Macs**, y es plomería: cómo arranca el programa, qué permisos
pide el sistema, cómo se instala.

---

# FASE 1 — Núcleo

**Termina cuando:** se da de alta una máquina, un agente la toma, aparece online, y el kill switch
la frena en menos de 10 segundos.

---

## 1. Arranque — Coordinador

**F1** · **A1 Coordinador** · Pegar en: **Chat**

```
Arranca el proyecto Centonara Seguimientos. Tu primera tarea no es técnica.

1. Leé los siete documentos de docs/ (01 a 07) y decime qué contradicciones o huecos encontrás.
2. Hacé la lista de lo que NO depende del equipo técnico: una línea de WhatsApp de prueba y 3
   contactos que acepten mensajes (hacen falta recién al final de la fase 4), el acuerdo escrito
   sobre el riesgo de bloqueo de líneas, las Macs, y los asientos de Claude.
3. Preparame el pedido al cliente, diciendo qué bloquea cada cosa y cuándo.

Contexto: el parque es macOS y arrancamos con unas 5 máquinas, pero la cantidad tiene que ser
variable. El cliente tiene Claude Enterprise. Hay un solo entorno, producción. No hay plazos.

UNA COSA URGENTE, aunque esté en la fase 5: confirmar con el administrador del Enterprise que la
extensión Claude in Chrome esté habilitada por política de la organización. Si está restringida,
el sistema no funciona en ninguna máquina y no se arregla desde el código. Es una llamada, no una
tarea técnica, y conviene hacerla ahora y no dentro de cuatro fases.
```

- [ ] Enviado — [ ] Terminado

---

## 2. F1.1 — Limpiar la infraestructura

**F1** · **A2 Plataforma** · Pegar en: **Claude Code**

```
Fase 1, tarea F1.1. Antes de escribir lógica de negocio, bajemos la infraestructura a lo que el
sistema necesita.

render.yaml tiene que quedar con tres servicios: backend, panel y el cron de backup. Se eliminan
los dos de n8n y todo lo de staging.

Por qué, para que no lo deshagas después:
- n8n hacía tres crons. Ahora los hace APScheduler dentro del proceso de FastAPI (D18). Además
  desde la versión 1.0 no tiene autenticación básica: la cuenta de dueño se la queda quien llegue
  primero a la URL. VERIFICÁ SI ALGUNA DE LAS DOS INSTANCIAS ESTUVO EXPUESTA antes de borrarlas.
- Staging existía para probar sin romper producción. No hay usuarios ni mensajes reales saliendo,
  así que se prueba en producción (D17). Lo que protege es la lista de destinos permitidos.

También: dejá el CI, borrá el workflow de staging, sacá del deploy a producción la guarda de
ventana horaria (D19), y del compose local sacá n8n y Mailpit.

Marcame cada paso irreversible antes de ejecutarlo.
```

- [ ] Enviado — [ ] Terminado

---

## 3. F1.2 — Normalización a E.164

**F1** · **A2 Plataforma** · Pegar en: **Claude Code**

```
Fase 1, tarea F1.2. core/contactos.py.

Mostrame PRIMERO los casos de test, después la implementación. Cubrí al menos estos formatos
argentinos, que tienen que dar todos el mismo resultado:
  11 4440-5036 · +54 11 4440 5036 · 0111544405036 · +549 11 4440-5036 · 1544405036

Y los que tienen que fallar: vacío, letras, número de otro país, longitud inválida.

Cobertura exigida: 100%.

Por qué importa tanto una función tan chica: si esto falla, el anti-duplicado falla y un contacto
recibe dos mensajes. Y es lo que se compara contra el header del chat antes de escribir, así que
un falso negativo aborta envíos correctos y un falso positivo escribe en el chat equivocado.
```

- [ ] Enviado — [ ] Terminado

---

## 4. F1.3 y F1.4 — Datos y estados

**F1** · **A2 Plataforma** · Pegar en: **Claude Code**

```
Fase 1, tareas F1.3 y F1.4.

1. Las seis colecciones e índices de 02-ARQUITECTURA §3.2, en un script IDEMPOTENTE. Correrlo dos
   veces no rompe nada. No te olvides del TTL de 90 días sobre el resumen de la conversación (D1).
2. core/estados.py con las transiciones de §3.1. Una transición no declarada lanza excepción.

Son SEIS estados, no doce: BORRADOR, RETENIDO, EN_ESPERA, ENVIANDO, ENVIADO, DESCARTADO. Lo que
antes eran estados distintos (rechazado, vetado, vencido, fallido) ahora es el campo `motivo`.

Escribí un test que intente CADA transición inválida y verifique que falla. Sólo EN_ESPERA puede
pasar a ENVIANDO, en un único método, sin atajos.
```

- [ ] Enviado — [ ] Terminado

---

## 5. F1.5 — La cola

**F1** · **A2 Plataforma** · Pegar en: **Claude Code**

```
Fase 1, tarea F1.5. core/cola.py sobre MongoDB: encolar, tomar de forma atómica con
findOneAndUpdate, reportar, reintentar, y disponible_desde para el espaciado.

Escribí un test con varios consumidores concurrentes que verifique que NINGÚN job se entrega dos
veces. Es la parte donde una condición de carrera se traduce en un mensaje duplicado a un cliente.

El espaciado se implementa con disponible_desde y jitter, NUNCA con time.sleep. Un ritmo fijo es
lo que dispara bloqueos de línea; un sleep en el camino de envío es un bug, no una simplificación.

Los reintentos son por código de motivo, no genéricos. La tabla está en 02-ARQUITECTURA §4.1.
```

- [ ] Enviado — [ ] Terminado

---

## 6. F1.6 y F1.7 — Máquinas y endpoints del agente

**F1** · **A2 Plataforma** · Pegar en: **Claude Code**

```
Fase 1, tareas F1.6 y F1.7.

1. Alta, baja y edición de máquinas. Cada alta genera un token que se muestra UNA vez y se guarda
   hasheado. Revocar es borrar la máquina. La cantidad es variable y se administra desde el panel:
   nada en el código puede asumir un número fijo.

2. Los cuatro endpoints de 02-ARQUITECTURA §4.1: /registrar, /jobs/proximo, /jobs/{id}/resultado,
   /latido.

Sobre /jobs/proximo: es un GET normal que devuelve un job o 204. NO es long-poll. El plan anterior
tenía long-poll de 25 s, que dependía de que Render y Cloudflare sostuvieran conexiones largas,
cosa que nunca se verificó. Con máquinas consultando cada 10 segundos, un GET alcanza.

El payload NUNCA lleva texto de prompt. Escribí un test que intente meter texto arbitrario y
verifique que el esquema de Pydantic lo rechaza.
```

- [ ] Enviado — [ ] Terminado

---

## 7. F1.8 y F1.9 — El bucle del agente y el diagnóstico

**F1** · **A4 Agente** · Pegar en: **Claude Code**

```
Fase 1, tareas F1.8 y F1.9.

1. El bucle: registro al arrancar, GET /api/agente/jobs/proximo cada 10 s, manejo de 204 y 423,
   latido cada 30 s, reintentos con backoff.
   Criterio: se corta la red 5 minutos, se reconecta, y el agente sigue SIN reiniciar.
   Al apagar, si hay un job en curso hay que abortarlo y reportarlo como fallido. Un envío a
   medias del que nadie se enteró es peor que un fallo.

2. Los nueve chequeos de diagnóstico de 04-AGENTE §4.

Estamos desarrollando en Windows y el destino es macOS. El bucle es Python puro y corre igual en
los dos. Del diagnóstico, los chequeos que dependen del sistema operativo reportan "n/a" donde no
aplican y NO fallan: el agente tiene que poder correr acá.

Lo que importa del diseño: el panel tiene que mostrar QUÉ chequeo falló, no un error genérico. En
el MVP los siete problemas conocidos eran un HTTP 502 mudo y había que adivinar.

Mostrame el diseño del bucle antes de escribirlo.
```

- [ ] Enviado — [ ] Terminado

---

## 8. F1.10 y F1.11 — Kill switch y auditoría

**F1** · **A2 Plataforma** · Pegar en: **Claude Code**

```
Fase 1, tareas F1.10 y F1.11.

1. Kill switch: POST /api/sistema/pausa. Los jobs dejan de entregarse con 423. Medí cuánto tarda
   desde que se aprieta hasta que un agente deja de recibir trabajo: menos de 10 segundos. Probá
   también que al despausar todo vuelve sin reiniciar nada.

2. core/auditoria.py, más un rol de MongoDB que sólo permita insert y find sobre esa colección.
   Verificá que un update falla A NIVEL DE BASE DE DATOS, no por convención de código. Escribí el
   test que lo intenta.

La auditoría es lo único que responde el día que un cliente se queje de un mensaje. Si se puede
editar, no responde nada.
```

- [ ] Enviado — [ ] Terminado

---

# FASE 2 — Panel

**Termina cuando:** alguien que no es del equipo entra, entiende qué está viendo, da de alta una
máquina y dispara una corrida sin ayuda.

---

## 9. Arranque de la fase 2 — Panel

**F2** · **A3 Panel** · Pegar en: **Claude Code**

```
Arranca la fase 2. Sos dueño de todas las pantallas.

Leé 01-PROYECTO y 02-ARQUITECTURA §4.2 antes de escribir nada.

QUIÉN LO USA: una o dos personas, no técnicas, en una empresa que vende materiales. El dueño entra
al mediodía, mira, aprieta y se va. No va a leer un manual.

EL CRITERIO NO ES QUE LAS PANTALLAS FUNCIONEN. Es que el cliente las use sin ayuda y entienda qué
está viendo.

Confirmame tu alcance y proponeme el orden de las pantallas.
```

- [ ] Enviado — [ ] Terminado

---

## 10. F2.1 — Login

**F2** · **A2 Plataforma** · Pegar en: **Claude Code**

```
Fase 2, tarea F2.1. Login del panel: una contraseña en variable de entorno (PANEL_PASSWORD) y una
cookie de sesión firmada. Sin Auth.js, sin magic links, sin correo saliente (D22).

Sin cookie, todo devuelve 401. Test incluido.

Entran una o dos personas. El magic link resolvía el problema de administrar muchos usuarios, que
no tenemos.
```

- [ ] Enviado — [ ] Terminado

---

## 11. F2.2 y F2.3 — Estado y alta de máquinas

**F2** · **A3 Panel** · Pegar en: **Claude Code**

```
Fase 2, tareas F2.2 y F2.3.

1. Pantalla de estado: las máquinas dadas de alta, si están online, y QUÉ chequeo de diagnóstico
   falló si alguna está degradada. Más el contador de mensajes del día.

2. Alta y baja de máquinas. Al dar de alta, el token se muestra UNA vez, con un aviso de que no se
   va a volver a ver.

La cantidad de máquinas es variable y la administra el cliente: nada en la interfaz puede asumir
un número fijo, ni "las 5" ni "las 8".

Mostrame el planteo de jerarquía visual antes de escribir componentes.
```

- [ ] Enviado — [ ] Terminado

---

## 12. F2.4 y F2.5 — El botón y el kill switch

**F2** · **A3 Panel** · Pegar en: **Claude Code**

```
Fase 2, tareas F2.4 y F2.5.

1. El botón que dispara una corrida, con el progreso visible. Devuelve al instante y encola.

2. El kill switch, VISIBLE SIN SCROLL en todas las pantallas.

Sobre el kill switch: el dueño lo va a usar con las manos temblando algún día. Que se vea, que
diga qué hace, y que confirme antes de ejecutar — pero con UNA sola confirmación, no tres. Una
guarda que molesta se termina esquivando.
```

- [ ] Enviado — [ ] Terminado

---

## 13. F2.6 — Modo prueba inconfundible

**F2** · **A3 Panel** · Pegar en: **Claude Code**

```
Fase 2, tarea F2.6. El modo prueba tiene que ser visualmente inconfundible: una banda de color en
toda la aplicación, no un texto chico en una esquina.

Criterio: alguien mira la pantalla dos segundos y sabe en qué modo está.

Confundir prueba con real es de los errores más caros que puede cometer un operador, y es el tipo
de error que se comete apurado.
```

- [ ] Enviado — [ ] Terminado

---

## 14. F2.7 — Configuración

**F2** · **A3 Panel** · Pegar en: **Claude Code**

```
Fase 2, tarea F2.7. Pantalla de configuración: topes, ventana horaria, palabras del triage, y la
lista de destinos permitidos.

El cliente tiene que poder cambiar un tope sin tocar código ni pedirnos nada.

La lista de destinos permitidos es especial: es lo que decide a quién puede escribirle el sistema
(regla R4). Ponerla en "todos" tiene que ser un acto deliberado, con una confirmación que explique
qué significa, y queda registrado en auditoría con quién y cuándo.
```

- [ ] Enviado — [ ] Terminado

---

# FASE 3 — Generación

**Termina cuando:** una corrida real genera borradores y el dueño los revisa en el panel.

> Acá aparece el navegador. Funciona en Windows: es lo que hacía el MVP. Hace falta Claude Code, la
> extensión Claude in Chrome, y una sesión de WhatsApp Web iniciada.
>
> Sigue sin poder enviar: `destinos_permitidos` está vacía.

---

## 15. F3.1 — Job LISTAR

**F3** · **A4 Agente** · Pegar en: **Claude Code**

```
Fase 3, tarea F3.1. Implementá el job LISTAR con exactamente esta invocación:

  proc = subprocess.run(
      [CLAUDE_BIN, "-p", "--chrome", "--output-format", "json"],
      input=prompt,              # por stdin, NUNCA como argumento
      capture_output=True, text=True,
      encoding="utf-8",
      errors="replace", timeout=TIMEOUT,
      cwd=str(CARPETA_AGENTE),   # para que encuentre CLAUDE.md
  )

Los dos detalles marcados vienen del MVP en Windows: como argumento, cmd.exe cortaba el comando en
el primer salto de línea; sin encoding explícito se rompían los acentos. Como estamos
desarrollando en Windows, los dos siguen siendo obligatorios acá.

El prompt ya está escrito en agente/prompts/prompt-listar.txt, migrado del MVP sin cambios
funcionales. Se arma acá sustituyendo las variables que mandó el backend. El agente nunca ejecuta
texto que vino por la red.

Una salida que no parsea como JSON se reporta como fallo CON EL raw COMPLETO, sin reventar el
agente. Ese raw es lo primero que se lee cuando algo falla.

Es la primera vez que el sistema nuevo toca WhatsApp Web. Si algo del MVP dejó de funcionar
—versiones nuevas de Claude Code, de la extensión o de WhatsApp— se va a ver acá. Traeme el error
textual, no una interpretación.
```

- [ ] Enviado — [ ] Terminado

---

## 16. F3.2 — Job REDACTAR

**F3** · **A4 Agente** · Pegar en: **Claude Code**

```
Fase 3, tarea F3.2. REDACTAR, separado de la lectura. Un job por chat, llamada de texto plano,
SIN NAVEGADOR.

Criterio verificable: redactar 20 borradores no abre ninguna pestaña.

Por qué importa: es el paso más frecuente del sistema, y sacarlo del circuito del navegador es
donde está el ahorro de costo del proyecto. El MVP hacía todo en una sola invocación con el
navegador abierto.

El prompt ya está en agente/prompts/prompt-redactar.txt. Leelo antes: tiene una sección de cosas
prohibidas —inventar precios, fechas o plazos; dejar placeholders— que importan más que el estilo,
porque un dato inventado por el modelo se convierte en una promesa comercial.
```

- [ ] Enviado — [ ] Terminado

---

## 17. F3.3 y F3.4 — Variables acotadas y persistencia

**F3** · **A2 Plataforma** · Pegar en: **Claude Code**

```
Fase 3, tareas F3.3 y F3.4.

1. El equivalente de ALLOWED_VARS del MVP, con esquemas Pydantic: por la red viajan variables
   validadas, nunca texto de prompt. Un intento de inyectar texto arbitrario lo rechaza el
   esquema, no un if.

2. Persistir chats y borradores. ⚠️ El resumen de la conversación es de UNA LÍNEA. Nunca la
   conversación completa, nunca los últimos N mensajes (D1). TTL de 90 días.

Para el punto 2, hacé una revisión manual sobre datos reales y confirmame que no quedó texto de un
cliente más allá del resumen. Los clientes del cliente son terceros que no participaron de esta
decisión.
```

- [ ] Enviado — [ ] Terminado

---

## 18. F3.5 — Triage

**F3** · **A2 Plataforma** · Pegar en: **Claude Code**

```
Fase 3, tarea F3.5. core/triage.py con las CINCO señales de 03-REGLAS §3.

Son cinco, no siete. Se sacó CONVERSACION_VIEJA porque contradecía el criterio validado del MVP:
leer los chats recientes funciona, y la antigüedad de una conversación no es por sí sola una señal
de riesgo. Es, de hecho, el motivo por el que existe el sistema.

Las listas de palabras van en la colección `configuracion`, NO hardcodeadas: el cliente va a
querer agregar términos de su rubro.

Criterio: sobre borradores reales, retiene entre el 10% y el 20%, y un humano está de acuerdo con
lo que retuvo. Si retiene el 40%, molesta y se va a terminar apagando — y un triage apagado es
peor que no tenerlo, porque el equipo cree que está protegido.
```

- [ ] Enviado — [ ] Terminado

---

## 19. F3.6 y F3.7 — Revisar borradores

**F3** · **A3 Panel** · Pegar en: **Claude Code**

```
Fase 3, tareas F3.6 y F3.7. La pantalla donde el dueño revisa una corrida.

Estructura: los RETENIDOS arriba, porque requieren decisión. Los que están listos abajo. Cada
retenido muestra POR QUÉ se retuvo, con la señal en palabras humanas, no el nombre de la constante.

Acciones: editar el texto, vetar, liberar un retenido.

Lo más importante: ENVIAR ES UN ACTO EXPLÍCITO. La corrida genera y se detiene ahí. No hay
temporizador y nada sale por inacción. El botón de enviar dice cuántos mensajes van a salir, con
el número.

Fricción proporcional: vetar tres es un click; liberar veinte retenidos de una vez pide confirmar
escribiendo la cantidad.

Editar revalida todo en el backend: si el dueño escribe {nombre} a mano, se rechaza igual que si
lo hubiera escrito el modelo. Mostrale ese error de forma que se entienda qué hizo mal.
```

- [ ] Enviado — [ ] Terminado

---

## 20. F3.8 — Costo y tasa de edición

**F3** · **A2 Plataforma** · Pegar en: **Claude Code**

```
Fase 3, tarea F3.8. Registrar costo_usd por job y por corrida, y mostrarlo en el panel.

Después corré una corrida completa real y traeme el costo medido de generar los borradores, más la
proyección a 5 máquinas todos los días hábiles.

No lo medimos antes a propósito: el número importa antes de encender las máquinas, no antes de
escribir código. Si sale alto, lo que se ajusta es n_chats y la frecuencia, no la arquitectura.

Agregá también la tasa de edición: qué proporción de borradores reescribe el humano. Es la métrica
de calidad del prompt, y la más importante de todas. Si el dueño reescribe el 80%, el sistema no
está aportando valor y hay que saberlo antes de que lo diga él.
```

- [ ] Enviado — [ ] Terminado

---

## 21. Paridad con el MVP — Coordinador

**F3** · **A1 Coordinador** · Pegar en: **Chat**

```
Terminó la generación. La pregunta que cierra la fase es una sola: ¿los borradores son tan buenos
como los del MVP?

Armame la forma de responderla sin autoengaño. Pensaba en tomar 20 borradores de una corrida real,
mezclarlos con los del MVP, y que alguien del cliente los puntúe sin saber cuál es cuál.

Si son peores, quiero saberlo ahora y no en la fase 5. El prompt es lo único que se migró literal
justamente porque su calidad estaba validada; si la perdimos en el camino, algo se rompió en la
migración y es barato de arreglar acá.
```

- [ ] Enviado — [ ] Terminado

---

# FASE 4 — Envío

**Termina cuando:** salieron tres mensajes reales, al contacto correcto, con alguien mirando.

> Se desarrolla en Windows. Playwright contra una página web es el mismo en todos lados.
>
> ⚠️ **El orden no es negociable: la prueba de que el sistema aborta va antes del primer envío
> real.** Todo lo anterior se hace en modo prueba, sin línea de WhatsApp dedicada.

---

## 22. Arranque de la fase 4 — Agente

**F4** · **A4 Agente** · Pegar en: **Claude Code**

```
Arranca la fase 4: el envío. A partir de acá escribís el código que le puede mandar un mensaje a
un cliente real de nuestro cliente.

Dos reglas que no se negocian, y quiero que me las repitas antes de empezar:
- Verificación de identidad del contacto inmediatamente antes de escribir, cada vez
- El sistema falla cerrado: ante cualquier duda, no escribe

Y una tercera que es la que hace que esto sea seguro de construir: mientras
configuracion.destinos_permitidos esté vacía o tenga sólo números de prueba, es técnicamente
imposible que un cliente real reciba algo. Verificá que esté así antes de correr nada.

Confirmame el plan y el orden antes de escribir.
```

- [ ] Enviado — [ ] Terminado

---

## 23. F4.1 — La lista de destinos permitidos

**F4** · **A2 Plataforma** · Pegar en: **Claude Code**

```
Fase 4, tarea F4.1. configuracion.destinos_permitidos, verificada en DOS lugares: en el backend al
encolar, y en el agente antes de escribir.

Formato: una lista de E.164, o ["*"] para permitir todos.

La duplicación no es porque el agente desconfíe del backend. Es porque un job puede quedar
encolado y ejecutarse minutos después, y en el medio la lista puede haber cambiado. La segunda
verificación es contra el paso del tiempo.

Cambiar la lista queda en auditoria, con quién y cuándo. Pasarla a ["*"] es el acto que habilita
el sistema para clientes reales: deliberado, visible y reversible.

Esto reemplaza a la regla anterior de que el código de envío no existiera en el repositorio (D21).
Es mejor garantía, porque sigue sirviendo después de que el código existe.

Test: un número fuera de la lista devuelve DESTINO_NO_PERMITIDO en los dos lados.
```

- [ ] Enviado — [ ] Terminado

---

## 24. F4.2 — Cómo se conecta al Chrome

**F4** · **A4 Agente** · Pegar en: **Claude Code**

```
Fase 4, tarea F4.2. Elegí cómo Playwright se conecta al navegador, con evidencia.

Las dos opciones están en 04-AGENTE §8:
A) CDP sobre el Chrome del vendedor, lanzado con --remote-debugging-port
B) Perfil persistente dedicado, manejado por Playwright

Criterio: cuál sobrevive a que el vendedor cierre el navegador, reinicie la máquina y trabaje
normalmente durante media jornada.

Se evalúa acá, en Windows. Lo que cambia en macOS es cómo se lanza Chrome con la bandera, no cuál
estrategia es mejor. Anotá esa diferencia para la fase 5 y seguí.

Cosas que quiero que midas explícitamente:
- Si el vendedor cierra Chrome, ¿se pierde la sesión?
- Si el vendedor está escribiendo en el mismo chat, ¿qué pasa?
- Con la opción B: es un SEGUNDO dispositivo vinculado a esa línea de WhatsApp. Ocupa uno de los
  cuatro lugares que WhatsApp permite, y es una sesión más que se puede caer sin que nadie la vea.

Va primero porque cambia cómo se escribe todo lo demás de la fase.
```

- [ ] Enviado — [ ] Terminado

---

## 25. F4.3 — Selectores

**F4** · **A4 Agente** · Pegar en: **Claude Code**

```
Fase 4, tarea F4.3. Todos los selectores de WhatsApp Web en UN archivo:
agente/adaptadores/selectores.py, con la fecha de última verificación de cada uno.

Ningún selector puede aparecer fuera de ese archivo. Cuando WhatsApp Web cambie —va a cambiar— se
toca un solo lugar.

Escribí también la función que verifica que todos siguen respondiendo: va a correr antes de cada
corrida (F4.9).
```

- [ ] Enviado — [ ] Terminado

---

## 26. F4.4 — Verificación de identidad ⚠️ la tarea más importante del proyecto

**F4** · **A4 Agente** · Pegar en: **Claude Code**

```
Fase 4, tarea F4.4. Es la tarea más importante del proyecto.

Implementá los pasos 0 a 6 de 04-AGENTE §7:
destino en la lista permitida → buscar el contacto → abrir el chat → LEER el header →
RESOLVER a E.164 → COMPARAR → abortar si no coincide.

Si el número no se puede resolver: abortar. Si el header no se puede leer: abortar. Nunca escribir
"por las dudas", nunca "ya lo verificamos antes".

Casos adversos que TIENEN que abortar correctamente:
- dos contactos con el mismo nombre
- contacto sin nombre agendado, sólo número
- un grupo
- un número que no tiene WhatsApp
- un chat archivado

Escribí este código pensando en que alguien lo va a leer buscando el error que hace que un mensaje
comercial llegue al chat equivocado. Porque alguien lo va a leer así: es el único archivo del
proyecto que pide revisión de otra persona antes de mergear.

Mostrame el diseño antes de implementar.
```

- [ ] Enviado — [ ] Terminado

---

## 27. F4.5, F4.6 y F4.7 — Escritura, modo prueba, confirmación

**F4** · **A4 Agente** · Pegar en: **Claude Code**

```
Fase 4, tareas F4.5 a F4.7.

1. Escribir el texto EXACTO: sin reformular, sin completar placeholders, respetando acentos y
   saltos de línea. Byte a byte idéntico al que llegó. Verificar antes que el campo esté vacío: si
   hay algo escrito, alguien está usando ese chat en este momento y se aborta.

2. Modo prueba: hace los pasos 0 a 8 y se detiene ANTES de apretar enviar. Reporta qué habría
   hecho, en un informe legible por un humano: por contacto, qué chat se abrió, qué número se
   resolvió, qué se habría escrito.

3. Confirmación en el hilo después de enviar. Sin confirmación en 15 segundos → SIN_CONFIRMAR y
   alerta. Nunca se asume que salió: "apreté enviar" y "el mensaje salió" no son lo mismo.
```

- [ ] Enviado — [ ] Terminado

---

## 28. F4.8 y F4.9 — Motivos y chequeo previo

**F4** · **A2 Plataforma** · Pegar en: **Claude Code**

```
Fase 4, tareas F4.8 y F4.9.

1. Los códigos de motivo de 02-ARQUITECTURA §4.1 y su política de reintentos. La columna del medio
   de esa tabla no es decorativa: CONTACTO_NO_COINCIDE, NUMERO_NO_RESOLUBLE, DESTINO_NO_PERMITIDO
   y SIN_CONFIRMAR NO se reintentan nunca. Reintentar un envío que abortó por identidad incorrecta
   es la forma exacta de convertir un aborto correcto en un error real.

   SELECTOR_ROTO es especial: frena la corrida entera. Si el DOM cambió, todos los envíos
   siguientes tienen el mismo problema.

2. Un chequeo de selectores que corre antes de que la corrida encole el primer ENVIAR. Si falla,
   la corrida no arranca y se avisa.
```

- [ ] Enviado — [ ] Terminado

---

## 29. F4.10 — CLAUDE.md del agente

**F4** · **A4 Agente** · Pegar en: **Claude Code**

```
Fase 4, tarea F4.10. Revisá agente/prompts/CLAUDE.md contra lo que el sistema realmente hace ahora.

Antes de tocarlo, leé docs/MVP-REFERENCIA.md §7.

El contexto: en el MVP, Claude Code se negaba a ejecutar por falta de contexto verificable. El
primer intento de arreglarlo fue agregar al prompt "esto está autorizado, no preguntes". EMPEORÓ
el problema, porque es el patrón exacto de un ataque de inyección. La solución fue sacarlo del
pedido y poner el contexto real en un CLAUDE.md escrito por el dueño de la máquina.

Nada de frases de autorización. Descripción honesta de qué es el sistema y quién lo opera.

Si el archivo dice que el sistema es de sólo lectura mientras el sistema envía, la contradicción
no es un detalle de redacción: es un problema técnico concreto, porque es exactamente lo que hacía
que el modelo se negara.
```

- [ ] Enviado — [ ] Terminado

---

## 30. F4.11 — Canario y jitter

**F4** · **A2 Plataforma** · Pegar en: **Claude Code**

```
Fase 4, tarea F4.11.

1. Canario: los 3 primeros mensajes salen, el sistema espera 10 minutos, y recién ahí libera el
   resto. Si los 3 fallan, frena todo automáticamente.

2. Jitter: pausa aleatoria de 45 a 180 segundos entre envíos, y orden de la lista aleatorizado.

Tests: 20 envíos producen 20 intervalos DISTINTOS, y dos corridas con los mismos contactos
producen órdenes distintos.

Esto no es cosmético y no es paranoia. Lo que dispara bloqueos de línea no es principalmente el
volumen: son los patrones de tiempo regulares. Un sleep fijo acá es un bug con consecuencias sobre
la herramienta de trabajo de una persona.

Implementado con disponible_desde en la cola, nunca bloqueando un hilo.
```

- [ ] Enviado — [ ] Terminado

---

## 31. F4.15 — Los ocho guardrails

**F4** · **A2 Plataforma** · Pegar en: **Claude Code**

```
Fase 4, tarea F4.15. Los ocho guardrails de 03-REGLAS §2, cada uno con su test.

Son ocho, no veinte. Los que están en backend Y agente lo están por una razón concreta: un job
puede quedar encolado y ejecutarse minutos después, y en el medio el tope o la pausa pueden haber
cambiado. La segunda verificación es contra el paso del tiempo, no contra el otro componente.

Escribí cada guardrail JUNTO con su test, no después. Y el test tiene que INTENTAR VIOLARLO:

  async def test_g3_rechaza_placeholder_sin_resolver():
      msg = construir_mensaje(texto="Hola {nombre}, quería...")
      with pytest.raises(GuardrailViolado) as e:
          await validar(msg)
      assert e.value.codigo == "GUARDRAIL_PLACEHOLDER"

Cobertura exigida: 100% en core/guardrails.py y core/estados.py.

Los guardrails viven en tu código. Nunca en un prompt. Si alguna vez parece más fácil pedírselo al
modelo, la respuesta es no.
```

- [ ] Enviado — [ ] Terminado

---

## 32. F4.12 — Las 50 verificaciones

**F4** · **A5 QA** · Pegar en: **Claude Code**

```
Fase 4, tarea F4.12. Diseñá y ejecutá 50 verificaciones de identidad de contacto, en modo prueba.

Antes de ejecutar nada, mostrame el plan: qué 50 casos, en qué orden, y qué evidencia se guarda de
cada uno.

Incluí obligatoriamente los casos adversos: dos contactos con el mismo nombre, contacto sin nombre
agendado, un grupo, un número sin WhatsApp, un chat archivado, y el mismo contacto guardado con
dos nombres distintos.

Criterio: 0 falsos positivos, 0 mensajes escritos por error.

Pensá como alguien que QUIERE que el sistema escriba en el chat equivocado. Encontrá la forma. Si
no encontrás ninguna, no terminaste de buscar.
```

- [ ] Enviado — [ ] Terminado

---

## 33. F4.16 — Caos

**F4** · **A5 QA** · Pegar en: **Claude Code**

```
Fase 4, tarea F4.16. Rompé el sistema a propósito, con una corrida en curso:

- apagar una máquina a mitad de corrida
- cortar la red de una máquina
- matar el proceso del agente
- matar MongoDB
- reiniciar el backend con jobs tomados
- llenar el disco

Criterio, en TODOS los escenarios: nunca se envía dos veces, y nunca se pierde un registro de algo
que sí salió.

Documentá cada escenario y su resultado. Esto se le muestra al cliente: es lo que responde la
pregunta "¿qué pasa si se corta la luz?".
```

- [ ] Enviado — [ ] Terminado

---

## 34. F4.13 — Prueba de identidad incorrecta ⚠️ va antes del primer envío real

**F4** · **A5 QA** · Pegar en: **Claude Code**

```
Fase 4, tarea F4.13. Antes de que este sistema mande un solo mensaje real, verificá que aborta
cuando debe.

Encolá deliberadamente un mensaje con un contacto_id que NO corresponde al chat que se va a abrir.

Criterio: el sistema aborta, reporta CONTACTO_NO_COINCIDE, y NO ESCRIBE NADA en ningún chat.
Verificá en el DOM que el campo de escritura quedó vacío. No alcanza con que el log diga que
abortó: quiero la evidencia de que la pantalla quedó limpia.

Hacé lo mismo con un número que no está en destinos_permitidos.

Esta prueba va ANTES del bloque siguiente. Probamos que frena, y recién después lo dejamos enviar
de verdad. Si se hace al revés, el primer envío real es también la primera vez que confiamos en
algo que no probamos.
```

- [ ] Enviado — [ ] Terminado

---

## 35. F4.14 — Los tres mensajes

**F4** · **A4 Agente** · Pegar en: **Claude Code**

```
Fase 4, tarea F4.14. Vamos a enviar los tres primeros mensajes reales, con el equipo mirando en
vivo.

Antes de ejecutar, confirmame las cinco cosas:
- Los 3 contactos aceptaron recibirlos
- F4.13 pasó: el sistema aborta cuando el contacto no coincide
- destinos_permitidos tiene exactamente esos 3 números y ninguno más
- El tope de 3 mensajes está activo
- El kill switch está probado y sé usarlo

Después de cada envío, pará y esperá mi confirmación antes del siguiente. Uno por vez.

Si algo se ve raro en el primero, frenamos. No hay ninguna razón para apurar esto.
```

- [ ] Enviado — [ ] Terminado

---

## 36. 🚪 PUERTA — ¿seguimos?

**F4** · **A1 Coordinador** · Pegar en: **Chat**

```
Se enviaron los tres mensajes reales. Preparame la presentación para el cliente:

1. Los 3 mensajes tal como los recibió el destinatario, con captura del lado del receptor
2. El costo medido por mensaje enviado, proyectado a 5 máquinas
3. El estado de los riesgos de 03-REGLAS §7, con lo que aprendimos en el camino
4. Qué falta para que lo use todo el equipo comercial: es la fase 5, que son las Macs

La presentación tiene que permitirle decir que no. Si sólo permite decir que sí, está mal armada.

Incluí explícitamente el riesgo de bloqueo de líneas, sin suavizarlo: automatizar WhatsApp Web va
contra los términos de Meta, no hay umbral seguro publicado, y el riesgo recae sobre la línea de
trabajo de sus vendedores. Si va a avanzar, que avance sabiendo eso.
```

- [ ] Enviado — [ ] Terminado

---

# FASE 5 — macOS y alta de máquinas

**Termina cuando:** las máquinas operan varios días seguidos sin intervención técnica.

> **Es la única fase que necesita Macs.** Todo lo de acá es plomería: cómo arranca el programa, qué
> permisos pide el sistema, cómo se instala. Nada cambia lo que el producto hace.

---

## 37. F5.5 — El Enterprise ⚠️ empezar antes que el resto de la fase

**F5** · **A1 Coordinador** · Pegar en: **Chat**

```
Aunque esta tarea esté en la fase 5, hay que empezarla mucho antes. Necesito confirmar tres cosas
con el administrador del Claude Enterprise del cliente:

1. Que pueda asignarle un asiento a cada vendedor. Probablemente hoy no sean miembros de la
   organización.
2. QUE LA EXTENSIÓN CLAUDE IN CHROME ESTÉ HABILITADA POR LA POLÍTICA DE LA ORGANIZACIÓN. Si está
   restringida, el sistema no funciona en ninguna máquina y no es algo que se arregle desde el
   código.
3. Que el límite de uso por asiento aguante una corrida diaria de 20 chats con el navegador
   abierto.

Armame las preguntas. La del medio es la que puede frenar el proyecto entero.

Nota: una API key NO sirve como alternativa — desactiva la integración con Chrome (D2). Y una
cuenta compartida entre máquinas tampoco: además del problema de términos de servicio, las
máquinas compiten por la misma cuota y se frenan entre ellas justo cuando corren todas juntas.
```

- [ ] Enviado — [ ] Terminado

---

## 38. F5.1 — Portar el agente a macOS

**F5** · **A4 Agente** · Pegar en: **Claude Code**

```
Fase 5, tarea F5.1. Primera vez que el agente corre en una Mac.

El código ya existe y funciona en Windows. Lo que hay que descubrir es qué pide macOS y no pide
Windows. Corrélo y documentá:

- qué permisos pidió el sistema operativo y en qué momento (Automatización, acceso al disco)
- si Gatekeeper molestó, y con qué
- si algún selector de WhatsApp Web se comporta distinto
- cuáles de los nueve chequeos de diagnóstico hay que implementar de verdad ahora, porque en
  Windows reportaban n/a

Dos de los siete problemas del MVP no deberían aparecer: el corte de cmd.exe en el salto de línea
y los acentos rotos por cp1252 son problemas de Windows. Confirmame si es así.

Después, agregá al diagnóstico un chequeo `permisos_macos` que verifique lo que descubriste y diga
QUÉ falta y dónde se concede. Nada de esto está en la documentación del MVP, porque el MVP era
Windows: estás escribiendo la lista que nadie tiene.
```

- [ ] Enviado — [ ] Terminado

---

## 39. F5.2 y F5.3 — LaunchAgent e instalador

**F5** · **A4 Agente** · Pegar en: **Claude Code**

```
Fase 5, tareas F5.2 y F5.3.

1. LaunchAgent en ~/Library/LaunchAgents/, con RunAtLoad y KeepAlive. El plist de ejemplo está en
   04-AGENTE §2.
   TIENE que ser un LaunchAgent y no un LaunchDaemon: Chrome, la extensión y el native messaging
   viven en la sesión interactiva del usuario, y un daemon corre fuera de esa sesión y no ve ese
   Chrome. No es configurable (D9).
   Criterio: se reinicia la Mac, se loguea, y el agente ya corre.

2. Instalador de tres pasos: correr el script, pegar el token, escanear el QR.
   El script clona en /opt/centonara, crea el venv, escribe config.json, escribe
   ~/.claude/settings.json con el permiso MCP, fija el deviceId, instala el LaunchAgent, y corre el
   diagnóstico MOSTRANDO QUÉ FALTA — incluidos los permisos que hay que conceder a mano.

Nada de PyInstaller por ahora: en macOS, Gatekeeper vuelve a poner el binario en cuarentena cada
vez que se reemplaza, lo que rompería cualquier autoactualización. Actualizar es git pull más un
kickstart del LaunchAgent.

Probalo en al menos dos Macs distintas antes de darlo por terminado.
```

- [ ] Enviado — [ ] Terminado

---

## 40. F5.4 — Ícono en la barra de menú

**F5** · **A4 Agente** · Pegar en: **Claude Code**

```
Fase 5, tarea F5.4. Ícono en la barra de menú con rumps: estado (verde, amarillo, rojo, pausado),
última corrida, y "pausar por hoy".

Criterio: un vendedor pausa su máquina sin ayuda. Probalo con alguien que no sea del equipo.

Es chico en esfuerzo y grande en soporte: es lo único que le da al vendedor control visible sobre
algo que corre en su computadora. El SOP le promete transparencia; esto la hace real.
```

- [ ] Enviado — [ ] Terminado

---

## 41. F5.6 — Los SOPs, y retirar el viejo

**F5** · **A6 Documentación** · Pegar en: **Cowork**

```
Fase 5, tarea F5.6. Dos entregas.

PRIMERO, los tres SOPs:
- SOP-instalacion.md — tres pasos, para alguien que no participó del proyecto
- SOP-vendedor.md — el sistema ENVÍA
- SOP-operacion.md — la rutina del dueño, el kill switch, qué hacer si algo sale mal

El del vendedor es el delicado. Tiene que decir sin vueltas: que el sistema manda mensajes en su
nombre, desde su línea, que él puede no haber leído; que su WhatsApp puede terminar bloqueado y
que el riesgo es real; cómo pausar; y qué decir si un cliente le pregunta por un mensaje que él no
escribió. Escribí para alguien que no sabe nada de tecnología y no minimices el riesgo: va a ser
la base de una conversación por vendedor y tiene que resistir preguntas incómodas.

SEGUNDO, y es lo que se olvida: RETIRAR DE CIRCULACIÓN el SOP viejo del MVP. Dice textual "No
envía ningún mensaje. Nunca." y ya no es cierto. Hacé la lista de dónde puede estar —Drive, mails,
copias impresas, grupos de WhatsApp del equipo— y confirmá con el cliente que se retiró de cada
lugar.

No alcanza con escribir el documento nuevo si el viejo sigue siendo el que la gente tiene a mano.
```

- [ ] Enviado — [ ] Terminado

---

## 42. F5.7 y F5.8 — Consentimientos y alta escalonada

**F5** · **A1 Coordinador** · Pegar en: **Chat**

```
Fase 5, tareas F5.7 y F5.8. Vamos a activar el sistema, de a una máquina.

1. Repasá conmigo el checklist antes de tocar la primera Mac:
   - instalador probado en dos Macs distintas
   - los tokens generados, uno por máquina
   - el SOP verificado por alguien que no lo escribió
   - una conversación de consentimiento con cada vendedor, registrada en acepto_condiciones_en
   - el kill switch probado, y el dueño sabe usarlo
   - los vendedores capacitados ANTES, no el día de la instalación

2. Armame el plan de alta escalonada. Una máquina primero. Después dos. Después el resto. Nunca
   todas juntas.

Y recordame lo más importante: INSTALAR NO ES ACTIVAR. Se instalan y se dejan pausadas.

Regla de freno: ante cualquier señal de degradación —mensajes que no llegan, una queja, un
contacto que bloquea— se frena el alta de máquinas nuevas y se investiga. Es la regla que evita
perder cinco líneas en vez de una.
```

- [ ] Enviado — [ ] Terminado

---

# Cierre

- [ ] Las máquinas operan varios días seguidos sin intervención técnica
- [ ] Ninguna línea bloqueada
- [ ] Ningún mensaje al contacto equivocado
- [ ] Costo mensual dentro del presupuesto
- [ ] El dueño explica el sistema en una frase y sabe cómo frenarlo
- [ ] El SOP viejo retirado de todos lados
