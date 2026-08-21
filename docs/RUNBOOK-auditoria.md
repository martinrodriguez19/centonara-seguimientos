# Runbook — el usuario de la base y la auditoría inmutable

> Cómo se configura en Atlas lo que en local hace `infra/mongo/01-usuario-app.js`.
>
> **Esto no es una recomendación de seguridad.** Es lo que hace que la regla R5 sea cierta: el
> registro de lo que salió no se puede editar ni borrar, ni siquiera desde el backend.

---

## 1. Por qué hace falta un rol a medida

MongoDB **no sabe prohibir**. Los roles sólo otorgan: no existe "readWrite sobre la base pero sin
`update` en esta colección".

Con el rol `readWrite` que ofrece la consola de Atlas, el backend podría editar la auditoría. La
única forma de que no pueda es **no otorgárselo**, y para eso hay que enumerar colección por
colección.

De ahí sale este runbook. La definición vive en `backend/app/core/permisos.py`, que es lo que
testea la suite; acá está cómo aplicarla.

---

## 2. Crear el rol en Atlas

Atlas › Database Access › **Custom Roles** › Add New Custom Role.

Nombre: `app_seguimiento`. Y estos privilegios, sobre la base `seguimiento`:

| Colección | Acciones |
|---|---|
| `vendedores`, `corridas`, `mensajes`, `jobs`, `configuracion` | `find` `insert` `update` `remove` `createIndex` `createCollection` `listIndexes` `listCollections` `dropCollection` |
| **`auditoria`** | **`find` `insert` `createIndex` `listIndexes` `listCollections`** |
| *(toda la base)* | `listCollections` `createCollection` |

⚠️ **La fila del medio es todo el punto de este documento.** Sin `update` y sin `remove`.

Si preferís hacerlo con `mongosh` en vez de la consola, el comando exacto lo genera el código:

```bash
cd backend
uv run python -c "import json; from app.core import permisos; print(json.dumps(permisos.comando_crear_rol('seguimiento'), indent=2))"
```

---

## 3. Crear el usuario

Database Access › Add New Database User.

- Autenticación: contraseña. Que la genere Atlas.
- Rol: **`app_seguimiento`**, sobre la base `seguimiento`. Ninguno más — nada de `readWriteAnyDatabase`.
- La cadena de conexión resultante va en `MONGO_URL` de Render. En ningún otro lado.

---

## 4. Verificar que quedó bien

No lo des por hecho: es fácil que un click de más agregue `readWrite` y nadie lo note hasta que
haga falta la auditoría.

```javascript
// Conectado con el usuario de la aplicación, NO con el admin
use seguimiento

db.auditoria.insertOne({ que: "prueba", quien: "runbook", cuando: new Date() })
// → debe funcionar

db.auditoria.updateOne({ que: "prueba" }, { $set: { que: "alterado" } })
// → debe fallar con "not authorized"

db.auditoria.deleteOne({ que: "prueba" })
// → debe fallar con "not authorized"

db.mensajes.updateOne({ x: 1 }, { $set: { x: 2 } }, { upsert: true })
// → debe funcionar: el rol restringe la auditoría y sólo la auditoría
```

Los cuatro resultados tienen que ser los cuatro. Si el segundo o el tercero funcionan, el rol quedó
mal y **la regla R5 no se está cumpliendo**, aunque el código esté bien.

El documento de prueba queda ahí y no se puede borrar. Es coherente: si se pudiera borrar, no
habría hecho falta este runbook.

---

## 5. Qué NO resuelve esto

Un administrador de Atlas puede borrar la colección entera. El rol protege a la aplicación de sí
misma, no al proyecto de quien tiene las llaves.

Y está bien que así sea: el modo de falla realista no es un atacante, es un desarrollador
escribiendo `auditoria.update_one(...)` un martes a la tarde para "arreglar un registro mal
cargado". Contra eso, esto alcanza.

---

## 6. En local

Lo hace solo. `infra/mongo/01-usuario-app.js` corre la primera vez que se levanta el contenedor con
el volumen vacío:

```bash
docker compose -f infra/docker-compose.dev.yml up -d
```

Si cambiaste el rol y querés reaplicarlo, hay que recrear el volumen:

```bash
docker compose -f infra/docker-compose.dev.yml down -v
docker compose -f infra/docker-compose.dev.yml up -d
```

⚠️ `down -v` borra los datos locales. En local no importa; el comando es el mismo en producción y
ahí sí, así que conviene no tenerlo en el historial del shell equivocado.
