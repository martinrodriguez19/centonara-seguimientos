# 01 — Contexto del proyecto

> Este documento asume que no sabés nada del proyecto. Empezá acá.

---

## 1. El problema del negocio

Nuestro cliente es una empresa con **8 vendedores**. Cada vendedor atiende a sus clientes por
WhatsApp desde su celular y su computadora.

El problema es viejo y conocido: **las conversaciones se enfrían**. Un cliente pregunta por un
producto el lunes, el vendedor responde, y ahí queda. Nadie vuelve a escribir. A los 15 días esa
venta ya no existe. No porque el cliente haya dicho que no, sino porque nadie insistió.

Hacer el seguimiento a mano funciona, pero es tedioso y es lo primero que se cae cuando el día se
complica. Un vendedor con 200 conversaciones abiertas no va a revisar cuáles necesitan un mensaje.

## 2. Qué hace el sistema

Todos los días, para cada vendedor:

1. **Lee** sus conversaciones recientes de WhatsApp Web
2. **Detecta** cuáles quedaron sin respuesta o llevan mucho tiempo frías
3. **Redacta** un mensaje de seguimiento para cada una, usando el contexto real de esa
   conversación (no una plantilla genérica)
4. **Envía** esos mensajes a las 13:00

El valor está en el punto 3. No es un "hola, ¿seguís interesado?" masivo — es un mensaje que hace
referencia a lo que efectivamente se habló. Eso es lo que un modelo de lenguaje hace bien y una
plantilla no.

**Volumen objetivo: 15 a 20 mensajes por vendedor por día.** Con 8 vendedores, unos 160 diarios.

## 3. Lo que el sistema NO es

Aclaraciones importantes porque la confusión es habitual:

- **No es un chatbot.** No responde a los clientes. Manda un mensaje y ahí termina su trabajo. Si
  el cliente responde, la conversación la sigue el vendedor, como siempre.
- **No es envío masivo.** No manda el mismo texto a mucha gente. Cada mensaje es distinto y va a
  una conversación que ya existía.
- **No contacta desconocidos.** Sólo escribe en chats abiertos, a gente que ya habló con el
  vendedor antes.
- **No usa la API oficial de WhatsApp.** Usa WhatsApp Web, el mismo que usa una persona. Esto
  tiene consecuencias, ver `11-RIESGOS.md`.

## 4. Cómo se ve desde afuera

### Para el dueño de la empresa

Entra a una página web, aprieta un botón, y a las 13:00 salieron los mensajes. Si quiere, entre
la generación y el envío puede entrar a una pantalla y frenar alguno. Si no entra, sale todo
igual.

### Para el vendedor

Prende la computadora a la mañana e inicia sesión. Nada más. Un iconito en la barra de tareas le
dice que el sistema está funcionando, y le permite pausarlo si ese día no quiere que salga nada.
Nunca abre una terminal ni ejecuta nada.

### Para el cliente final

Recibe un mensaje de WhatsApp de su vendedor de siempre, desde el número de siempre. No sabe —ni
tiene por qué saber— que lo redactó un sistema.

## 5. Por qué esto es delicado

Leelo aunque tengas prisa.

Los mensajes salen **desde la línea personal del vendedor, en su nombre, sin que él los lea**.
Del otro lado hay clientes reales de un negocio real.

Los tres errores que importan:

| Error | Consecuencia |
|---|---|
| Mandar el mensaje al contacto equivocado | Un cliente recibe algo destinado a otro. Puede incluir datos comerciales de un tercero |
| Mandar un mensaje inapropiado al contacto correcto | Ej.: un "¿avanzamos con el pedido?" a alguien que ayer puso un reclamo |
| Mandar demasiados mensajes o a destiempo | WhatsApp bloquea la línea del vendedor. Pierde su herramienta de trabajo |

Ninguno de los tres es hipotético. El primero y el tercero ya están documentados como riesgos
principales en el spec original. Todo el diseño del sistema está organizado alrededor de que
estos tres no pasen.

## 6. De dónde venimos: el MVP

Ya existe una **Fase 1 funcionando y validada**. Sirve para entender qué está probado y qué no.

**Lo que el MVP hace hoy:**

```
n8n → HTTP POST → agent.py (Python, puerto 8787) → claude -p --chrome
    → extensión Claude in Chrome → web.whatsapp.com (SOLO LECTURA)
```

Corre en **una** máquina Windows 11. Lee 5 chats, genera 5 borradores contextualizados. La calidad
de los borradores fue validada como utilizable. **No envía nada** — el prompt tiene una
instrucción explícita de no tocar el campo de escritura.

**Lo que aprendimos del MVP y nos llevamos:**

| Aprendizaje | Por qué importa |
|---|---|
| El prompt debe ir por **stdin**, no como argumento | En Windows, `cmd.exe` corta el comando en el primer salto de línea |
| Hay que forzar `encoding="utf-8"` | Si no, Windows usa cp1252 y rompe los acentos |
| Hace falta `settings.json` con el permiso de Chrome | Sin eso el modo headless auto-deniega todo |
| El permiso de sitio de la extensión es una capa **distinta** | Se configura a mano, una vez por máquina |
| Hay que fijar el `deviceId` | Con más de un Chrome, el sistema no sabe cuál usar |
| Hace falta un `CLAUDE.md` en la carpeta del proyecto | Sin contexto verificable, el modelo se niega a ejecutar |

**El aprendizaje más importante, y el menos obvio:** el primer intento de resolver el último punto
fue agregar al prompt un párrafo que decía *"esto está autorizado, no preguntes"*. **Empeoró el
problema**, porque es exactamente el patrón de un ataque de inyección de prompt. La solución
correcta fue sacarlo del pedido y poner el contexto real en un archivo del proyecto, escrito por
el dueño de la máquina.

Regla que se deriva de eso y que aplica a todo el proyecto: **el contexto y los permisos no se
declaran dentro del pedido.** Van en la configuración, fuera de lo que el modelo recibe como
instrucción.

## 7. Qué vamos a construir

El MVP es un conjunto de scripts. La v2 es un producto:

| | MVP (hoy) | v2 (lo que vamos a hacer) |
|---|---|---|
| Máquinas | 1 | 8 |
| Envío | no | sí |
| Interfaz | archivo `.bat` y terminal | página web |
| Estado | una planilla | base de datos |
| Red | todo en la misma LAN, IP fija | cada PC desde donde sea |
| Arranque | manual | automático al prender |
| Auditoría | no hay | completa |
| Límites | ninguno | topes duros en código |

**Se construye desde cero.** Lo único que se migra tal cual es `prompt.txt`, porque su calidad
está validada y no tiene sentido volver a iterarlo.

## 8. Glosario

Términos que vas a ver en toda la documentación.

| Término | Significa |
|---|---|
| **Agente** | El programa que corre en la PC de cada vendedor. No confundir con "agente de IA" |
| **Backend** | El servidor central (FastAPI), en Render. El cerebro |
| **Panel** | La aplicación web (Next.js) que usa el dueño |
| **Corrida** (`run`) | Una ejecución completa del ciclo de un día |
| **Job** | Una unidad mínima de trabajo. Ej.: "redactar el mensaje para este chat" |
| **Borrador** | Un mensaje redactado que todavía no salió |
| **Veto** | Frenar un mensaje antes de que se envíe |
| **Triage** | Clasificación automática que aparta los mensajes de riesgo |
| **Retenido** | Mensaje apartado por el triage. Necesita una decisión humana |
| **Guardrail** | Un límite implementado en código que el sistema no puede cruzar |
| **Modo prueba** (`dry-run`) | Hace todo el proceso menos apretar enviar |
| **Kill switch** | Botón que frena todo el sistema de inmediato |
| **Canario** | Mandar unos pocos mensajes primero y esperar, antes de liberar el resto |
| **n8n** | Herramienta visual de automatización. Acá se usa sólo para horarios y avisos |
| **Claude in Chrome** | Extensión que permite a un modelo operar el navegador |
| **E.164** | Formato internacional de teléfono: `+5491144405036` |
| **Coexistence** | API oficial de WhatsApp Business. Fuera de alcance por ahora |

## 9. Stack

| Capa | Tecnología |
|---|---|
| Panel | Next.js (App Router) + TypeScript + Tailwind + shadcn/ui |
| Autenticación | Auth.js con magic link por email |
| Backend | Python 3.12 + FastAPI + Pydantic v2 |
| Base de datos | MongoDB |
| Cola de trabajos | MongoDB (sin Redis — el volumen no lo justifica) |
| Orquestación | n8n (sólo horarios y notificaciones) |
| Agente | Python + Playwright, empaquetado con PyInstaller |
| Infraestructura | Render (servicios administrados) + MongoDB Atlas + Cloudflare. Docker Compose sólo en local |
| Errores | Sentry |
| CI | GitHub Actions |

Deliberadamente **fuera**: Kubernetes, microservicios, colas distribuidas, multi-región. Son 8
usuarios y 160 mensajes por día. La complejidad ahí no compra nada y cuesta soporte.
