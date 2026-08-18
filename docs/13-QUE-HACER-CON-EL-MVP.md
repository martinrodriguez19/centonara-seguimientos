# 13 — Qué hacer con el MVP

> **Respuesta corta: se construye desde cero. El MVP se conserva como referencia, en una carpeta
> aparte, fuera de la ruta de construcción.**
>
> Pero hay tres cosas que se copian *literalmente*, y una que es peligroso dejar suelta.

---

## 1. Dónde va

```
seguimiento/
├── backend/
├── frontend/
├── agente/
├── docs/
└── referencia/
    └── mvp-fase1/          ← el ZIP entero, tal cual
        ├── LEEME-REFERENCIA.md    ← lo escribís vos, ver §4
        ├── 01-documentacion/
        ├── 02-instalacion/
        ├── 03-codigo/
        └── 04-proximas-fases/
```

**Reglas de la carpeta `referencia/`:**

1. **No se importa nada desde ahí.** Ningún `from referencia...`, ningún `sys.path`. Si algo hace
   falta, se copia al lugar que corresponde y se adapta.
2. **No se modifica.** Es un registro histórico. Si algo está mal, se anota en
   `LEEME-REFERENCIA.md`, no se corrige el archivo.
3. **Queda excluida del linter, de los tests y del build.** Agregar a `.gitignore` de herramientas
   y a `pyproject.toml` (`exclude`).

Por qué tanto cuidado: si `agent.py` está en el repo y funciona, alguien lo va a copiar y pegar un
martes a las 7 de la tarde. Es la ruta de menor esfuerzo y hay que cerrarla.

---

## 2. Archivo por archivo

| Archivo del MVP | Qué hacer | Adónde va |
|---|---|---|
| `03-codigo/prompt.txt` | **MIGRAR LITERAL** | `agente/prompts/prompt-listar.txt` |
| `03-codigo/agent.py` | **NO copiar.** Leer dos fragmentos (§3) | — |
| `03-codigo/CLAUDE.md` | Leer como plantilla. **Reescribir** en el Sprint 4 | `agente/prompts/CLAUDE.md` |
| `03-codigo/n8n-workflow-mvp.json` | Leer para entender el flujo. Se rehace | — |
| `03-codigo/iniciar-agente.bat` | **Descartar.** Lo reemplaza el Task Scheduler (D9) | — |
| `01-documentacion/DOCUMENTACION-TECNICA.md` | **Leer completo.** Sobre todo el historial de problemas | — |
| `01-documentacion/README.md` | Leer | — |
| `02-instalacion/SOP-instalacion.md` | Leer. Los 12 pasos se reducen a 3 | base de `SOP-instalacion.md` nuevo |
| `02-instalacion/SOP-cliente-operacion.md` | Leer. Se reescribe con el panel | base del nuevo |
| `02-instalacion/SOP-vendedor.md` | ⚠️ **PELIGROSO** — ver §5 | se reescribe entero |
| `02-instalacion/GUIA-descargas-cliente.md` | Leer | — |
| `04-proximas-fases/SPEC-fase2-envio.md` | **Leer completo.** Es el origen de todo este proyecto | — |
| `04-proximas-fases/BRIEF-whatsapp-coexistence.md` | Leer. Fuera de alcance, pero informa el `ChannelAdapter` (D10) | — |
| `LEEME.md` | Leer | — |

---

## 3. Lo único que se copia del código

**No se copia `agent.py`.** Su arquitectura (servidor HTTP que recibe push) es exactamente lo que
la v2 invierte. Pero adentro hay dos fragmentos que costaron días de depuración y que se conservan
tal cual.

### 3.1 La invocación del subproceso

Va a `agente/jobs/listar_chats.py`:

```python
proc = subprocess.run(
    [CLAUDE_BIN, "-p", "--chrome", "--output-format", "json"],
    input=prompt,              # por stdin, NUNCA como argumento
    capture_output=True,
    text=True,
    encoding="utf-8",          # sin esto Windows usa cp1252 y rompe los acentos
    errors="replace",
    timeout=TIMEOUT,
    cwd=str(CARPETA_AGENTE),
)
```

Los dos comentarios son el problema #6 del historial: pasar el prompt como argumento hacía que
`cmd.exe` cortara el comando en el primer salto de línea ("Tu mensaje se cortó"), y sin
`encoding="utf-8"` se rompían los acentos.

### 3.2 El principio de variables acotadas

`ALLOWED_VARS` no se copia como código, pero **el principio sí se conserva**: por la red viajan
variables validadas, nunca texto de prompt. En la v2 se implementa con esquemas Pydantic
(`04-CONTRATOS-API` §2.2).

### 3.3 El prompt

`prompt.txt` se migra **sin cambios funcionales**. Está validado: leyó 5 chats y produjo 5
borradores de calidad utilizable. Mejorarlo es otro ticket, después de verificar paridad
(Sprint 2, T2.1).

---

## 4. El `LEEME-REFERENCIA.md` que hay que escribir

Ponelo en `referencia/mvp-fase1/`. Es lo primero que va a leer alguien que entre a esa carpeta:

```markdown
# MVP Fase 1 — REFERENCIA HISTÓRICA

⚠️ ESTE CÓDIGO NO SE USA. No importar nada desde acá.

Es el MVP validado que dio origen al proyecto. Funciona, pero su arquitectura
(push desde n8n a un servidor HTTP en cada PC) es justamente lo que la v2 invierte.

QUÉ SIRVE DE ACÁ:
- prompt.txt → ya migrado a agente/prompts/prompt-listar.txt
- DOCUMENTACION-TECNICA.md §8 → el historial de 7 problemas resueltos
- SPEC-fase2-envio.md → el origen del proyecto actual

QUÉ NO:
- agent.py → arquitectura superada. Ver docs/02-ARQUITECTURA.md
- iniciar-agente.bat → reemplazado por Task Scheduler
- SOP-vendedor.md → DESACTUALIZADO Y PELIGROSO. Ver docs/13 §5

Fecha de congelamiento: {fecha}
```

---

## 5. ⚠️ El archivo peligroso

`02-instalacion/SOP-vendedor.md` afirma, textual:

> *"No envía ningún mensaje. Nunca."*
> *"Nadie va a mandar nada en tu nombre sin que pase por revisión."*

**Las dos frases dejan de ser ciertas en la v2.**

El riesgo no es técnico, es humano: si ese documento sigue circulando —en un Drive, en un mail
viejo, impreso en un escritorio— un vendedor puede estar operando con la creencia de que el
sistema no manda nada. Y se va a enterar cuando un cliente le pregunte por un mensaje que él no
escribió.

**Qué hacer:**

1. Marcarlo como obsoleto **en el archivo mismo**, con una banda arriba de todo:
   `⚠️ OBSOLETO — describe la Fase 1 (sólo lectura). El sistema actual ENVÍA. Ver SOP-vendedor.md
   en docs/`
2. Reescribir el SOP nuevo en el Sprint 5 (T5.7)
3. **Retirar de circulación las copias del viejo**: Drive, mails, impresos
4. Registrar el consentimiento individual de cada vendedor sobre el nuevo (R6, G15)

El punto 3 es el que se olvida. No alcanza con escribir el documento nuevo si el viejo sigue
siendo el que la gente tiene a mano.

---

## 6. Lo más valioso del MVP no es código

Es `DOCUMENTACION-TECNICA.md` §8: **siete problemas ya resueltos que van a reaparecer en cada
instalación nueva.**

| # | Problema | Causa | Dónde está resuelto en la v2 |
|---|---|---|---|
| 1 | n8n no arranca | Node < 22.22 | `06-ENTORNO-LOCAL` §1 |
| 2 | HTTP 500 | `shutil.which("claude")` → `None` | Autodiagnóstico `claude_bin_ok` |
| 3 | HTTP 502, permisos denegados | headless auto-deniega | Autodiagnóstico `permiso_mcp_ok` |
| 4 | "requires permission" | permiso de sitio de la extensión | Autodiagnóstico `permiso_sitio_ok` |
| 5 | "dos navegadores conectados" | ambigüedad de dispositivo | Autodiagnóstico `device_id_ok` |
| 6 | "Tu mensaje se cortó" + acentos rotos | `cmd.exe` corta en el salto de línea | §3.1 de este documento |
| 7 | El modelo se niega a ejecutar | falta de contexto verificable | `CLAUDE.md` (§7 abajo) |

Cada uno se convirtió en un chequeo automático del agente (`07-EL-AGENTE` §4). Eso es reutilizar
el MVP bien: no copiando su código, sino convirtiendo lo que aprendió en algo que el sistema nuevo
verifica solo.

---

## 7. La lección del problema #7 — leer antes de tocar `CLAUDE.md`

En el MVP, Claude Code se negaba a ejecutar por falta de contexto verificable. El primer intento de
solución fue agregar al prompt un párrafo diciendo *"esto está autorizado, no preguntes"*.
**Empeoró el problema**: es el patrón exacto de una inyección de prompt.

La solución correcta fue sacarlo del prompt y poner el contexto real en un `CLAUDE.md` escrito por
el dueño de la máquina, **fuera del pedido**.

Implicancia para la v2: el `CLAUDE.md` tiene que describir el sistema real, y ahora el sistema
**envía**. Si el archivo describe un sistema de sólo lectura mientras el sistema envía, la
contradicción es un problema técnico concreto —no un detalle de redacción— porque es exactamente
lo que hacía que el modelo se negara.

Se reescribe en el Sprint 4 (T4.9), junto con el motor de envío. Ni antes ni después.

---

## 8. Resumen en cinco líneas

1. **Todo se desarrolla desde cero.** El MVP no es la base del código.
2. El ZIP entero va a `referencia/mvp-fase1/`, en cuarentena, excluido del build.
3. Se copian literal: **el prompt** y **la invocación del subproceso**. Nada más.
4. Lo más valioso es el **historial de 7 problemas**, ya convertido en el autodiagnóstico.
5. `SOP-vendedor.md` hay que marcarlo obsoleto **y retirarlo de circulación**.
