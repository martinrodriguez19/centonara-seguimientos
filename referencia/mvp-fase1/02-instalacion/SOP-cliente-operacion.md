# SOP — Operación diaria del sistema

**Para:** el responsable que opera el sistema día a día
**Versión:** 1.0 · **Estado:** MVP · **Instalado por:** >>> nombre y contacto

Este documento cubre **cómo usar el sistema**. La instalación es un documento aparte
(`SOP-instalacion.md`) y la hace el soporte técnico.

---

## 1. Qué hace el sistema

Una vez al día lee los chats recientes de WhatsApp de cada vendedor y genera un
borrador de mensaje de seguimiento para cada conversación.

**No envía nada.** Produce borradores para que vos los revises y decidas.

Flujo: `n8n dispara → cada PC lee sus chats → devuelve borradores → revisás → se usan`

---

## 2. Rutina diaria

### 2.1 Antes de disparar (5 min)

En cada máquina de vendedor:

- [ ] La computadora está encendida
- [ ] Chrome está abierto
- [ ] WhatsApp Web muestra los chats (no el QR)
- [ ] La ventana negra del agente está abierta y dice `Agente 'PC-x' escuchando`

> **El punto que más falla:** si alguien reinició la PC, la ventana del agente
> desapareció. Hay que volver a levantarla (sección 5.1).

### 2.2 Disparar (1 min)

1. Abrir n8n: `http://localhost:5678`
2. Abrir el workflow **MVP - Templates WhatsApp**
3. Botón **Test workflow** abajo

> El toggle "Active" arriba a la derecha **no dispara nada** en este workflow.
> Solo sirve para automatizaciones programadas, que todavía no están activas.

### 2.3 Esperar (2–5 min)

Los nodos quedan girando. Es normal: cada máquina abre WhatsApp, lee y redacta.
No cerrar la pestaña de n8n.

### 2.4 Revisar (10 min)

Abrir el nodo **Normalizar** → pestaña OUTPUT. Una fila por chat con:

| Campo | Qué es |
|---|---|
| `maquina` | de qué vendedor viene |
| `contacto` | nombre o número |
| `antiguedad` | cuándo fue el último mensaje |
| `ultimo_lo_mando` | `contacto` (esperan respuesta) o `yo` |
| `resumen` | de qué se habló, en una línea |
| `template` | el borrador |

**Cómo revisar:**

- Priorizá los que dicen `ultimo_lo_mando: contacto` — son los que quedaron sin respuesta
- Leé el `template` contra el `resumen`: ¿tiene sentido para esa conversación?
- Cuidado con los que dicen `{nombre}`: hay que completarlo antes de usar
- Si un borrador no representa el tono de la empresa, anotalo — sirve para ajustar

### 2.5 Distribuir

Hoy es manual: pasar los borradores aprobados a cada vendedor por el canal habitual.
La automatización de este paso está en la lista de mejoras.

---

## 3. Control semanal

- [ ] **Costo.** Revisar el consumo en la cuenta de Anthropic. Presupuesto acordado: >>> USD/mes
- [ ] **Cobertura.** ¿Las 8 máquinas devolvieron resultados esta semana? Si una falla siempre, avisar
- [ ] **Calidad.** ¿Cuántos borradores se usaron sin editar? Si son pocos, el prompt necesita ajuste
- [ ] **Altas y bajas.** Si entró o salió un vendedor, coordinar con soporte

---

## 4. Qué hacer cuando algo falla

### 4.1 Diagnóstico rápido

| Lo que ves | Qué significa | Qué hacer |
|---|---|---|
| Un nodo en rojo, los otros bien | esa máquina no respondió | ver 5.1 en esa PC |
| Todos los nodos en rojo | n8n no llega a la red, o está caído | ver 5.2 |
| Sale `sesion_no_iniciada` | WhatsApp Web pidió QR de nuevo | pedirle al vendedor que lo escanee |
| Sale `browser_no_disponible` | Chrome cerrado o extensión desconectada | abrir Chrome; si sigue, llamar a soporte |
| Sale texto raro en vez de borradores | el asistente encontró algo inesperado | copiar el mensaje completo y mandarlo a soporte |
| Devuelve menos chats de los pedidos | no había más chats recientes | normal, no es error |

### 4.2 Cuándo llamar a soporte

Llamá si:
- El mismo error se repite dos días seguidos
- Aparece cualquier mensaje sobre permisos o dispositivos
- El costo se dispara respecto de la semana anterior
- Un vendedor reporta que el sistema hizo algo que no debía

No hace falta llamar si:
- Fue un día puntual y al siguiente anduvo
- Una PC estaba apagada
- Un borrador salió mal redactado (eso se anota y se ajusta después)

---

## 5. Procedimientos

### 5.1 Relevantar el agente en una máquina

En esa PC, abrir PowerShell y pegar la línea de esa máquina (está en la planilla
de instalación, es distinta en cada una):

```powershell
cd C:\claude-agent; $env:DEVICE_ID="<el de esta PC>"; $env:CLAUDE_BIN="<ruta>"; $env:AGENT_TOKEN="<token>"; $env:MACHINE_NAME="PC-x"; $env:MODEL="claude-sonnet-5"; python agent.py
```

Tiene que aparecer `Agente 'PC-x' escuchando en 0.0.0.0:8787`. **Dejar la ventana abierta.**

> Guardá esta línea por máquina en un archivo de texto, listo para copiar y pegar.

### 5.2 Verificar que n8n llega a una máquina

Desde la computadora donde corre n8n:

```powershell
curl.exe -s http://<ip-de-la-pc>:8787/health
```

- Responde `{"ok": true, ...}` → la máquina está bien, el problema es de n8n
- No responde → la PC está apagada, el agente caído, o cambió la IP

### 5.3 Dar de baja a un vendedor

1. En su teléfono: WhatsApp → Dispositivos vinculados → cerrar la sesión de Chrome
2. Cerrar la ventana del agente en esa PC
3. Quitar o desconectar el nodo de esa máquina en n8n
4. Avisar a soporte para desinstalar

### 5.4 Frenar todo el sistema

Cerrar las ventanas negras del agente en todas las máquinas. Sin agente no hay
acceso, aunque n8n dispare.

---

## 6. Límites del sistema hoy

Conviene tenerlos presentes para no prometer de más:

- **Arranque manual.** Los agentes se levantan a mano y hay que dejar la terminal
  abierta. Si se reinicia una PC, hay que volver a levantarlo.
- **Sin persistencia.** Los resultados viven en la ejecución de n8n. Si se limpia,
  se pierden. Guardar lo importante fuera.
- **Sin alertas.** Si una máquina falla, nadie avisa: hay que mirar.
- **Sin envío.** Todo lo que sale del sistema se manda a mano.
- **Solo red interna.** Funciona con las máquinas en la misma red.

---

## 7. Responsabilidades

**Del cliente (vos):**
- Que los vendedores sepan qué hace el sistema y estén de acuerdo
- Revisar los borradores antes de que se usen
- Controlar el costo mensual
- Avisar a soporte ante fallas repetidas

**Del soporte técnico:**
- Instalación y reinstalación
- Errores técnicos y de permisos
- Ajustes al prompt y a los borradores
- Mejoras acordadas

**Sobre los datos:** el sistema lee conversaciones con clientes que no participaron
de esta decisión. Guardar la guía del vendedor firmada y mantener actualizado el
`CLAUDE.md` de cada máquina es parte de la operación, no un trámite.

---

## 8. Mejoras acordadas

| Mejora | Estado |
|---|---|
| Arranque automático de los agentes | pendiente |
| Guardado de resultados en planilla | pendiente |
| Panel de revisión | pendiente |
| Alertas por máquina caída | pendiente |
| Disparo automático a horario fijo | pendiente |
| Evaluación de API de WhatsApp Business | pendiente |

---

*Última actualización: >>> fecha · Soporte: >>> contacto*
