# MVP Fase 1 — REFERENCIA HISTÓRICA

## ⚠️ ESTE CÓDIGO NO SE USA. No importar nada desde acá.

Es el MVP validado que dio origen al proyecto. **Funciona**, y esa es justamente la razón por la
que hay que tener cuidado: su arquitectura —n8n empujando por HTTP a un servidor en cada PC— es
exactamente lo que la v2 invierte (D6). Copiar de acá no ahorra tiempo, lo gasta.

Hay un job del CI que hace fallar la construcción si algún archivo fuera de esta carpeta importa
algo de adentro. No es desconfianza: es que a las siete de la tarde de un martes, copiar y pegar es
la ruta de menor esfuerzo.

## Qué sirve de acá

| Archivo | Para qué |
|---|---|
| `03-codigo/prompt.txt` | Se migra **literal** a `agente/prompts/prompt-listar.txt` en el Sprint 2 (T2.1), después de verificar paridad |
| `01-documentacion/DOCUMENTACION-TECNICA.md` §8 | **Lo más valioso del MVP**: siete problemas ya resueltos que reaparecen en cada instalación. Ya están convertidos en el autodiagnóstico del agente (`07-EL-AGENTE` §4) |
| `04-proximas-fases/SPEC-fase2-envio.md` | El origen de este proyecto. Leer completo |
| `03-codigo/agent.py` | **Sólo dos fragmentos**, citados en `docs/13` §3.1 y §3.2. El archivo entero, no |
| `03-codigo/CLAUDE.md` | Plantilla. Se **reescribe** en el Sprint 4, ver `docs/06` §6 |

## Qué no

| Archivo | Por qué |
|---|---|
| `03-codigo/agent.py` | Arquitectura superada. Ver `docs/02-ARQUITECTURA.md` |
| `03-codigo/iniciar-agente.bat` | Lo reemplaza Task Scheduler (D9). Además tenía el token en texto plano |
| `03-codigo/n8n-workflow-mvp.json` | Se rehace. n8n deja de ser el cerebro (D8) |
| `02-instalacion/SOP-vendedor.md` | **Desactualizado y peligroso.** Ver `docs/13` §5 |

## Modificaciones hechas al congelar

La regla es que esta carpeta no se toca. Se hicieron dos excepciones, las dos por seguridad, y se
anotan acá para que el registro histórico siga siendo honesto:

| Fecha | Archivo | Qué se cambió | Por qué |
|---|---|---|---|
| 2026-08-18 | `02-instalacion/SOP-vendedor.md` | Banda de OBSOLETO al principio | Afirma que el sistema nunca envía. Si esa copia circula, un vendedor opera con información falsa sobre mensajes que salen en su nombre (`docs/13` §5) |
| 2026-08-18 | `04-proximas-fases/SPEC-fase2-envio.md` | Teléfono de un tercero reemplazado por el del responsable del proyecto (`+54 9 11 3927-3345`) | Era dato personal de alguien que no participó de ninguna de estas decisiones (`05` §5). No se dejó un marcador tipo `XXXX` a propósito: un número inválido invita a que alguien lo "complete" con uno inventado, que puede ser de una persona real. Un número nuestro es el único ejemplo que no le llega a un desconocido |

Ningún otro archivo fue modificado. Si encontrás algo mal, **anotalo acá; no corrijas el archivo.**

**Fecha de congelamiento: 2026-08-18**
