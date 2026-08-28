# Runbook — Re-vincular la sesión de WhatsApp del motor de envío

> La sesión del navegador dedicado (D24) expira sola y el vendedor no la ve en ningún lado.
> Este documento es lo que se sigue cuando el panel dice "sesión dedicada vencida" — o cuando
> una corrida falla con `SESION_CAIDA` de verdad.

---

## 1. Qué es esta sesión y por qué se cae

El motor de envío no usa el Chrome del vendedor: escribe desde un **navegador propio** con
carpeta de datos propia, vinculado a la línea del vendedor como un **segundo dispositivo**
(`WhatsApp → Dispositivos vinculados`). Esa sesión expira como cualquier dispositivo vinculado:
por inactividad, porque WhatsApp la venció, o porque alguien la cerró desde el teléfono.

Cuando se cae, **ningún borrador ni envío sale de esa Mac** hasta re-vincular. Desde la vigía de
sesión, el agente lo revisa al arrancar y cada unas horas, y el panel lo muestra como alerta
urgente con esta acción. Antes de eso, la única señal era una corrida fallando.

## 2. Síntomas

| Señal | Dónde se ve |
|---|---|
| Alerta "La sesión de WhatsApp del motor de X venció" | Panel |
| Chequeo `whatsapp_sesion: falla` | Tarjeta de la máquina en el panel |
| Jobs con código `SESION_CAIDA` y detalle "pide escanear el código" | Detalle de la corrida |

⚠️ Un `SESION_CAIDA` aislado con la alerta del panel en verde ya no debería pasar (el orden
navegar→preguntar se corrigió el 28/08). Si pasa, anotalo: es un dato.

## 3. Procedimiento

**Tiempo estimado: 5 minutos.** Hace falta estar en la Mac del vendedor y tener su teléfono a
mano (el QR se escanea desde SU WhatsApp).

1. En la Mac, abrir Terminal y correr el agente con el flag de vinculación:

   ```
   cd ~/centonara-agente && uv run python -m agente.main --vincular
   ```

2. Se abre la ventana del navegador dedicado con un código QR.

3. En el **teléfono del vendedor**: `WhatsApp → Configuración → Dispositivos vinculados →
   Vincular un dispositivo` → escanear el QR de la pantalla.

4. Esperar el mensaje `Listo: la sesión quedó vinculada y guardada.` La ventana se cierra sola.

5. Si el agente corría como servicio, no hace falta reiniciarlo: la vigía va a ver la sesión
   nueva en su próxima revisión, y el próximo envío la usa directamente.

## 4. Verificación

1. En el panel, la alerta de sesión vencida desaparece con el próximo latido posterior a la
   revisión de la vigía (o al reiniciar el agente, que revisa al arrancar).
2. En el teléfono del vendedor, `Dispositivos vinculados` muestra el dispositivo nuevo.
3. Opcional pero recomendado tras un incidente: una corrida de prueba de 1 mensaje a un número
   de `destinos_permitidos`.

## 5. Ojo con los límites de WhatsApp

- WhatsApp permite **hasta 4 dispositivos vinculados** por línea. Si el vendedor ya tiene su
  Chrome, una tablet y otra cosa, vincular el motor puede requerir cerrar alguno. No cerrar el
  del Chrome del vendedor sin avisarle: ahí trabaja.
- Cada re-vinculación es un dispositivo "nuevo" para WhatsApp. Si la sesión se cae seguido,
  anotarlo — la frecuencia de expiración es justamente lo que `conexion.py` dice que hay que
  medir.

## 6. Registro de ejecuciones

| Fecha | Máquina | Quién | ¿Siguió el documento sin preguntar? |
|---|---|---|---|
| _pendiente_ | | | |
