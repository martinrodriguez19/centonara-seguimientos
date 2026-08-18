# Brief de traspaso — Registro de número en WhatsApp Coexistence

> **Instrucciones de uso:** pegá este documento completo como primer mensaje de un
> chat nuevo. Está escrito para que Claude entienda el contexto sin haber
> participado de la sesión anterior.

---

## Contexto del proyecto

Estoy construyendo un sistema de asistencia comercial para un cliente con 8
vendedores. El objetivo: generar borradores de mensajes de seguimiento de WhatsApp
a partir de conversaciones existentes con clientes, con revisión humana antes de
usarlos. No se envía nada automáticamente.

**Primer intento (funcionó, pero se descarta):** automatización del navegador con
Claude in Chrome + Claude Code + un agente Python + n8n, una máquina por vendedor.
Funciona técnicamente pero tiene alto costo de soporte (8 PCs prendidas, Chrome
abierto, sesiones que expiran) y lee conversaciones leyendo la pantalla.

**Camino elegido:** WhatsApp Coexistence (Cloud API + app de WhatsApp Business en
el mismo número). Elimina toda la infraestructura de navegador y da acceso
estructurado a las conversaciones.

---

## Objetivo de esta sesión

Registrar **mi número personal actual** en WhatsApp Coexistence como prueba piloto,
antes de tocar los números de los 8 vendedores. Quiero llegar a tener un token de
acceso funcionando y poder leer/enviar por API sin perder el uso normal del teléfono.

---

## Lo que ya sé (verificado el 05/08/2026)

- Coexistence permite el mismo número en la app de WhatsApp Business y la Cloud API
  simultáneamente, con sincronización bidireccional en tiempo real.
- Se conservan funciones nativas: llamadas, estados, grupos.
- Se pueden importar hasta 6 meses de historial 1:1.
- Disponible globalmente desde mayo de 2026.
- Los mensajes enviados desde la app siguen siendo gratis; los de API pagan pricing
  por conversación.
- Hay un cambio de precios de Meta con fecha 1 de julio de 2026.

**Requisitos que encontré:**
- El número debe haber usado activamente la **app de WhatsApp Business** (no el
  WhatsApp común) por al menos **7 días**.
- App en versión **2.24.17 o superior**.
- Teléfono con cámara (hace falta escanear un QR).
- Cuenta de Meta Business (Business Manager) con la info legal completa: razón
  social, dirección, sitio web y teléfono.
- ⚠️ **El Business Manager no se puede cambiar después de registrar el número.**
- El flujo oficial de Embedded Signup para Coexistence está documentado para
  Solution Partners / Tech Providers, no para usuarios finales directos.

**Flujo de onboarding según la documentación:**
1. Elegir la opción de conectar una app de WhatsApp Business existente
2. Ingresar el número
3. Llega un mensaje a la app de WhatsApp Business con un código de confirmación y
   un botón para escanear QR
4. Se elige si se comparte el historial de mensajes
5. Se escanea el QR y se autoriza
6. Sigue el flujo estándar de registro de Cloud API
7. Devuelve los IDs de los activos (WABA ID, phone number ID) y el token

---

## Lo que necesito resolver en esta sesión

1. **Si estoy en WhatsApp común, cómo convertir a WhatsApp Business sin perder
   chats**, y confirmar que arranca el conteo de los 7 días.
2. **Qué camino me conviene**, dado que el flujo oficial es para Tech Providers:
   - ¿Me registro yo como Tech Provider creando una app en Meta for Developers?
   - ¿O uso un BSP que ya soporte Coexistence?
   - ¿Cuál es más rápido para una prueba de un solo número, y cuál escala mejor
     a 8 después?
3. **Paso a paso concreto** desde cero hasta tener el token en la mano.
4. **Cómo obtener un token permanente** (System User) en vez del temporal de 24 hs.
5. **Prueba mínima** para confirmar que funciona: leer un mensaje entrante por
   webhook y enviar uno de prueba.
6. **Qué pasa si me equivoco** — cómo desconectar y volver atrás sin romper el
   número. (Vi que hay un Disconnect en Configuración > Cuenta > Business Platform
   y que NO hay que desinstalar la app.)

---

## Cómo prefiero trabajar

- **Verificá con búsqueda web antes de darme pasos.** Coexistence se lanzó en mayo
  de 2025 y los flujos de Meta cambian seguido. Lo que escribí arriba puede estar
  desactualizado.
- Un paso a la vez, esperando que confirme antes de seguir. Ya perdí tiempo en la
  sesión anterior avanzando sobre pasos que no habían quedado bien.
- Decime explícitamente cuáles son irreversibles antes de que los haga.
- Soy técnico pero no experto en el ecosistema de Meta.

---

## Datos que voy a necesitar tener a mano

- [ ] Número de teléfono a registrar
- [ ] Cuenta de Facebook con acceso admin a un Business Manager
- [ ] Datos legales de la empresa (razón social, dirección, web)
- [ ] Teléfono con cámara disponible durante el proceso
- [ ] Tarjeta o método de pago para la cuenta de Meta

---

## Primera pregunta

Antes de que empecemos: mi número hoy está en **>>> WhatsApp común / WhatsApp
Business** (completar). ¿Cuál es el primer paso y qué debería hacer hoy mismo para
no perder tiempo con la espera de los 7 días?
