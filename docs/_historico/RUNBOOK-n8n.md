# Runbook — n8n

> n8n hace horarios, avisos e integraciones. **Cero lógica de negocio** (D8).
> Todo lo que, si falla, hace salir un mensaje que no debía salir, vive en FastAPI.

---

## 1. Reclamar la cuenta de dueño — el primer minuto cuenta

n8n eliminó la autenticación por variables de entorno en la versión 1.0. Desde entonces usa gestión
de usuarios: **en el primer acceso, quien entre crea la cuenta de dueño.** No hay contraseña
preconfigurada.

Consecuencia directa: entre que Render deja el servicio en `Live` y que alguien reclama la cuenta,
**cualquiera que llegue a esa URL puede quedársela**. Y quien controla n8n controla el cron que
dispara la corrida de las 08:00.

**Por eso esto es un paso del despliegue, no una tarea para después:**

1. Apenas el servicio quede en `Live`, abrí su URL. Está en el panel de Render, arriba
2. Completá la pantalla de alta: correo, nombre y contraseña
3. Guardá esas credenciales en el gestor de contraseñas, con el nombre del entorno
4. Verificá que al recargar te pida iniciar sesión

Producción y staging son **dos instancias independientes**: dos altas, dos contraseñas distintas.
Si repetís la contraseña, quien entra a staging entra a las dos.

> Si abrís la URL y te muestra la pantalla de alta cuando ya la habías reclamado, no es un error de
> la pantalla: alguien borró el volumen, o estás mirando el otro entorno. Frená y averiguá cuál de
> las dos antes de crear nada.

## 2. Qué NO se configura por variables

| Variable | Estado |
|---|---|
| `N8N_BASIC_AUTH_ACTIVE` · `_USER` · `_PASSWORD` | **Eliminadas en n8n 1.0.** Si las cargás, n8n las ignora en silencio: ni siquiera aparecen en su lista de deprecaciones. Dan una falsa sensación de que el editor está protegido |
| `N8N_ENCRYPTION_KEY` | Sí se usa. La genera Render, cifra las credenciales que n8n guarda. **Si se pierde, esas credenciales quedan ilegibles** |
| `N8N_PUBLIC_API_DISABLED` | Sí se usa. La API pública es otra vía de autenticación con sus propias claves. No la usamos |

## 3. Los workflows se versionan

Viven en `n8n/workflows/` como JSON (D8). **El editor no es la fuente de verdad**: es cómodo para
mirar y tocar, pero lo que vale es lo que está en el repositorio.

Al cambiar un workflow: exportalo desde el editor y commiteá el JSON en el mismo PR que el cambio.

Los tres workflows previstos (`02` §4.4):

1. Cron 08:00 → `POST /api/corridas`
2. Cron 12:45 → si hay retenidos, avisar al dueño
3. Webhook desde el backend → alertas

## 4. Si algo parece un guardrail, está en el lugar equivocado

Un tope que vive en un nodo de n8n **lo desconecta cualquiera con acceso al editor**. Si mirando un
workflow encontrás algo que decide *si* un mensaje sale —un tope, una ventana horaria, un filtro de
destinatarios— eso incumple D8 y R1: se reporta y se mueve a FastAPI.

n8n decide **cuándo se dispara** una corrida. Nunca **si** un mensaje sale.

## 5. Si el despliegue falla sin errores en el log de n8n

n8n **no lee la variable `PORT`**. Escucha en `N8N_PORT`, y por defecto en 5678. Render publica el
servicio en el puerto que indica `PORT` —10000 por defecto— y si no detecta nada escuchando ahí, da
el despliegue por fallido aunque n8n haya arrancado perfecto.

El síntoma es confuso: el log de n8n dice `n8n ready on ::, port 5678` y todo parece bien, pero
Render marca el deploy en rojo.

Por eso el blueprint fija `N8N_PORT: 10000`. Si alguna vez volvés a ver ese síntoma, revisá que esa
variable siga puesta.
