# Runbook — Rollback (T0.8)

> Se prueba antes de necesitarlo, no la primera vez que haga falta.

---

## 1. Lo primero: qué NO hace

**El rollback vuelve la aplicación. No vuelve los datos.**

Volver al despliegue anterior deja los servicios corriendo el código de antes. MongoDB Atlas queda
exactamente como está: los documentos que se escribieron, se escribieron.

Si el problema es que salió un mensaje que no debía salir, **el rollback no lo trae de vuelta.**
Para eso está el kill switch, y va primero:

> *Si el problema puede hacer que salga un mensaje que no debía: apretá el kill switch primero,
> avisá después. Nadie te va a reprochar haber frenado el sistema de más.* — `05` §7

Si el despliegue incluyó una migración que transformó datos, revertir el código deja la aplicación
vieja leyendo datos con forma nueva. Eso es peor que el problema original. En ese caso el rollback
de código no alcanza y hay que restaurar desde backup (`RUNBOOK-backups.md` §3).

## 2. Cuándo usarlo

| Situación | Rollback | Otra cosa |
|---|---|---|
| El panel no carga tras desplegar | ✅ | |
| El backend devuelve 500 en todo | ✅ | |
| Los agentes no reciben jobs | ✅ | |
| Salió un mensaje que no debía | ❌ | **Kill switch primero** |
| Datos corruptos por una migración | ❌ | Restaurar desde backup |

## 3. Procedimiento

**Tiempo estimado: 3 minutos.** No hace falta acceso a la consola de nadie más que Render.

1. Entrá a `dashboard.render.com` y elegí el servicio afectado.

2. Pestaña **Events**. Vas a ver la lista de despliegues, el más reciente arriba.

3. Ubicá el último despliegue que funcionaba. Si no estás seguro cuál era, mirá la hora del primer
   síntoma y tomá el anterior.

4. `Rollback to this deploy` → confirmar.

5. **Repetí para cada servicio que se desplegó junto.** Un despliegue toca varios a la vez; volver
   uno solo deja el sistema mitad y mitad, que suele ser peor que el problema. Anotá cuáles antes
   de empezar.

6. Esperá a que los servicios queden en `Live`.

## 4. Verificación — no alcanza con que diga Live

1. `https://app.centonara-ia.com` carga y muestra el panel
2. `/health` devuelve `{"ok": true, "mongo": true, "entorno": "produccion"}`
3. En el panel, las máquinas vuelven a aparecer en línea
4. En Uptime Kuma, los chequeos vuelven a verde

Si el punto 2 falla, el problema no era el código: mirá Atlas.

## 5. Después

1. Avisá en el canal del equipo: qué se revirtió, a qué versión, y por qué.
2. **No vuelvas a desplegar lo mismo "a ver si ahora anda".** Reproducí el problema en staging.
3. Si el rollback fue fuera de la ventana horaria, revisá si la ventana está bien elegida (D15).
4. Si tocaba el camino de envío, se anota en `06-DECISIONES.md`.

## 6. Registro de ejecuciones

Una fila por vez que se ejecute, sea simulacro o incidente real.

| Fecha | Quién | Entorno | Motivo | ¿Siguió el documento sin preguntar? |
|---|---|---|---|---|
| _pendiente_ | Martín Rodríguez | produccion | primer simulacro | |

> **El simulacro no se puede correr todavía:** hace falta que staging tenga dos versiones
> desplegadas para tener de dónde volver, y eso depende de T0.7, que a su vez depende de T0.3 y
> T0.4.
>
> La prueba real de este documento no es que el rollback funcione: es que quien lo ejecute **no
> tenga que preguntar nada**. Si hay que preguntar, el que falló es el documento.
