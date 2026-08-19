# Runbook — Backups y restauración (T0.9)

> Un backup sin restauración probada no es un backup. Este documento existe para
> que la primera vez que restaures no sea el día que lo necesitás.

---

## 1. Qué se respalda

| | |
|---|---|
| Qué | La base `seguimiento` completa, por entorno |
| Cuándo | Todos los días a las 05:00 de Argentina (08:00 UTC) |
| Dónde | Cloudflare R2, bucket `centonara-backups` |
| Cifrado | `age`, con clave pública. **El servidor no puede descifrar lo que genera** |
| Retención | 30 días, por regla de ciclo de vida del bucket |
| Ruta | `{entorno}/{año}/{mes}/seguimiento-{entorno}-{AAAAMMDD-HHMMSS}.archive.gz.age` |

Las 05:00 no son arbitrarias: la corrida sale a las 13:00 y la generación arranca a las 08:00. Un
backup compitiendo por la base dentro de esa ventana es exactamente lo que no queremos.

## 2. Por qué el servidor no puede leer sus propios backups

La clave privada de `age` no está en Render, ni en el repositorio, ni en ninguna variable de
entorno. Sólo está la pública, que **cifra y nada más**.

Consecuencia buscada: si alguien se mete en el servicio de backup, puede generar backups nuevos y
no puede leer ninguno de los existentes. El token de R2 es de sólo escritura, así que tampoco puede
borrar el historial — de ahí que la retención de 30 días sea una regla del bucket y no una línea
del script.

Consecuencia que hay que aceptar: **el script no puede verificar que el backup sea restaurable.**
Nadie que no tenga la clave privada puede. Por eso la prueba de §3 se corre a mano.

### Custodia de la clave privada

Dos copias, en lugares distintos:

1. El gestor de contraseñas
2. Una copia fuera de línea —impresa o en un pendrive— en poder de otra persona

Con una sola copia, el día que se pierda los 30 días de backups son ruido cifrado. Con cero copias
fuera del servidor, cifrar no protegía de nada.

## 3. Prueba de restauración — mensual, y obligatoria antes de cerrar el Sprint 0

Se corre **el primer lunes de cada mes**. Lleva unos 10 minutos.

1. Bajá el backup más reciente de staging desde el panel de R2.

2. Restauralo sobre una base vacía. Nunca sobre una que tenga datos: el script se niega, pero no
   dependas de eso.

   ```
   ./infra/scripts/restaurar.sh \
       seguimiento-staging-AAAAMMDD-HHMMSS.archive.gz.age \
       "mongodb+srv://usuario:clave@host/prueba_restauracion"
   ```

3. **Verificá el contenido, no el código de salida.** El script cuenta los documentos y falla si la
   base quedó vacía, pero el conteo tenés que mirarlo vos: si `mensajes` tiene 12 documentos y
   esperabas 4000, la restauración técnicamente funcionó y el backup no sirve.

4. Borrá `prueba_restauracion`.

5. Anotá la fecha y el resultado al final de este documento.

> **Por qué el paso 3 está subrayado.** Al construir esto, `mongorestore` devolvió éxito y restauró
> cero documentos: la URI con nombre de base actuaba como filtro y no coincidía con nada dentro del
> archivo. El comando no falló. Sólo contar lo detectó.

## 4. Si el backup falla

El Cron Job de Render deja el log de la corrida. El script aborta **antes de subir nada** en dos
casos, y los dos dicen qué pasó:

| Mensaje | Qué significa |
|---|---|
| `la base tiene 0 documentos` | `MONGO_URL` apunta a la base equivocada, o la base está vacía |
| `el dump pesa N bytes. Está truncado` | `mongodump` se cortó a la mitad |

Nunca sube un backup que no pasó esas dos verificaciones. Un archivo vacío en el bucket es peor que
la ausencia de archivo: te deja creyendo que estás cubierto.

## 5. Registro de restauraciones probadas

| Fecha | Quién | Entorno | Resultado |
|---|---|---|---|
| 2026-08-18 | infraestructura | local | ✅ 5009 documentos, canario presente |
