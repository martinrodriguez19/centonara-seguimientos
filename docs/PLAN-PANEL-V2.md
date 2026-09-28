# Plan — Panel v2: menos ruido, configuración en botones, detalle por máquina y estadísticas

> **El pedido.** El sistema anda bien, pero el panel no se puede usar: el inicio está lleno de
> errores y advertencias, la barra de arriba grita en rojo y confunde al cliente, y la configuración
> es una página de 1.500 líneas donde prender algo tan simple como el envío automático cuesta
> encontrarlo y aplicarlo. Se pide: (1) una sección aparte para errores y avisos, (2) configuración
> por secciones con switches y botones, (3) sacar las alertas de la barra superior, (4) sólo tema
> claro, con un estilo más tecnológico y tarjetas de máquina nuevas, (5) una página de detalle por
> máquina, (6) una sección de estadísticas, (7) una barra de navegación de 3 ítems con submenús.
>
> Fecha: 28/09/2026. Base: `develop` en `e065e5e`. Estado: **implementado entero el mismo día**
> (sprints 0 a 6). Decisiones D54–D56 en `06-DECISIONES.md`. Las respuestas del dueño a las
> preguntas abiertas están en §10 y aplicadas; lo que cambió al implementar, en §11.
>
> **La regla que ordena el plan: el backend y el agente no se tocan.** Todo sale de los endpoints
> que ya existen (`GET /estado`, `/alertas`, `/configuracion`, `/corridas`, `/corridas/{id}`,
> `/corridas/{id}/mensajes`, `/corridas/{id}/metricas`, `/metricas`, `/historial`, `/vetados`) y
> de las mismas mutaciones que el panel ya usa. Ningún campo nuevo, ningún endpoint nuevo, ningún
> cambio de comportamiento. La única excepción está en §7: un campo más, de sólo lectura, en las
> alertas (aprobado).

---

## 0. Qué hay hoy, verificado en el código

| Tema | Qué hay hoy | Dónde |
|---|---|---|
| Inicio | Banda de modo + barra con 4 links, kill switch, tema y salir + aviso de frenado + **todas las alertas** + botón de corrida + métricas + máquinas. Todo en una columna | `app/panel/page.tsx` |
| Alertas | 13 tipos (`selector_roto`, `sin_confirmar`, `enviado_a_no_contactar`, `canario_fallido`, `maquina_caida`, `maquina_degradada`, `maquina_desactualizada`, `version_esperada_desconocida`, …). Se pintan **todas** arriba del botón, cada una como un `Aviso` grande | `backend/app/core/alertas.py`; `components/alertas.tsx` |
| Barra superior | Encima de la barra, `BandaModo` a todo el ancho: verde en prueba, **roja** con "destinos abiertos" o "envío automático". Siempre visible | `components/banda-modo.tsx` |
| Navegación | No hay layout común: cada página arma su propio encabezado y su "Volver al panel". El inicio tiene Corridas · Configuración · Historial · Comandos + Frenar + Tema + Salir | cada `page.tsx` |
| Configuración | **Una sola página de 1.495 líneas** con ~15 tarjetas en fila: destinos, qué chats, cómo se dejan borradores, volumen, redacción, etiquetas, topes, ventana y ritmo, corrida automática, envío automático, versión del agente, empezar de cero. El envío automático está casi al final y se prende **escribiendo `ENVIAR`** en un input | `app/config/page.tsx:686-765` |
| Tema | Claro / oscuro / automático, con script en línea en el `<head>`, bloque `.dark` en `globals.css`, 9 usos de `dark:` | `app/layout.tsx`, `components/tema.tsx`, `app/globals.css` |
| Tarjeta de máquina | 483 líneas: estado, latido, versión, modo, cursores de barrido/ventana, aviso de chequeos, aviso de consentimiento, tope diario editable y 5 botones de acción — todo a la vista a la vez | `components/maquina.tsx` |
| Diálogos | 8 `confirm()` del navegador sueltos (reiniciar barrido/ventana, etc.), cuando el propio código ya dice que `confirm()` es malo en Mac | `grep -rn "confirm(" frontend/` |
| Métricas | Un bloque en el inicio con 7/30/90 días | `components/metricas.tsx` |

Dos restricciones que salen del código y hay que respetar:

- **`backend/tests/test_contrato_panel.py` lee los `export type` de `frontend/lib/panel.ts`** y los
  compara con las respuestas reales. Cualquier tipo "derivado" que inventemos para la pantalla
  (agregados por máquina, series por día) **no va en `panel.ts`**: va en un archivo nuevo
  `lib/derivados.ts`. Si no, el test de contrato del backend se pone rojo.
- **Las alertas no tienen campo `maquina`**: traen `codigo`, `titulo`, `detalle`, `accion`,
  `corrida_id`. El nombre de la máquina viene adentro del título. Para filtrar alertas por máquina
  en el front hay que matchear por nombre (ver §5 y §7).

---

## 1. La estructura nueva

### 1.1 Un layout común (route group, sin cambiar URLs)

Mover las páginas autenticadas a `app/(panel)/` con un `layout.tsx` que dibuja la barra una sola
vez. Los route groups de Next no cambian las URLs: `/panel`, `/config`, `/corridas`, `/historial`,
`/corrida/[id]`, `/revision/[corrida]`, `/comandos` siguen donde están — el middleware, el e2e y
cualquier link guardado siguen andando.

```
app/
  (auth)/login/            ← queda igual
  (panel)/
    layout.tsx             ← NUEVO: barra + contenedor
    panel/                 ← "Inicio"
    maquinas/              ← NUEVO: lista
    maquinas/[maquina]/    ← NUEVO: detalle
    corridas/  corrida/[id]/  revision/[corrida]/  historial/
    errores/               ← NUEVO: errores y avisos
    estadisticas/          ← NUEVO
    config/                ← se parte en secciones (§3)
    comandos/
```

### 1.2 La barra: 3 menús y nada que grite

```
[◆ Centonara]   Operación ▾   Análisis ▾   Ajustes ▾          [● Prueba]  [⏻ Frenar]  [MR ▾]
```

| Menú | Submenú |
|---|---|
| **Operación** | Inicio · Máquinas · Corridas · Revisar la última corrida |
| **Análisis** | Estadísticas · Errores y avisos `(3)` · Historial |
| **Ajustes** | Envío y horarios · Qué chats y cuántos · Mensajes · Seguridad · Sistema · Instalar una máquina (Comandos) |

- A la derecha quedan sólo tres cosas: un **chip de modo** chico (§2.2), el **freno** (se queda:
  es un control de seguridad, no una alerta — ver D-previas sobre "un freno al que hay que ir a
  buscar no es un freno") y un menú de usuario con "Salir".
- El contador de "Errores y avisos" es un **puntito neutro con número**, no un cartel. Si hay algo
  urgente el puntito es rojo; nada más.
- En celular colapsa a un botón ☰ que abre los mismos tres grupos.
- Implementación: `components/navegacion/barra.tsx` con `DropdownMenu` de `radix-ui` (ya es
  dependencia). Marca el ítem activo con `usePathname()`.

---

## 2. Errores y avisos: fuera del inicio y fuera de la barra

### 2.1 Página `/errores`

Toma todo lo que hoy se pinta arriba del inicio (`<Alertas />`, `<AvisoFrenado />`, los avisos
dentro de cada tarjeta de máquina) y lo junta en un lugar:

- **Dos grupos**: *Urgente* (`nivel: "urgente"`) y *Para mirar* (`nivel: "aviso"`).
- **Filtro por máquina** (chips con los nombres de `GET /estado`; filtra por el campo `maquina` de la alerta, §7).
- Cada alerta como **fila compacta** (ícono · título · máquina · "qué hacer" desplegable), no como
  el `Aviso` gigante de hoy. La acción de `canario_fallido` (Ver corrida / Reanudar) se mantiene
  tal cual — reutiliza `AccionDeAlerta`.
- **"Ya lo vi"** por alerta, guardado en `localStorage` con la clave `codigo+titulo+corrida_id`.
  Es sólo visual: la alerta la sigue calculando el backend y desaparece sola cuando se resuelve
  la causa. Una "vista" que vuelve a cambiar de detalle (otro número) reaparece.
- Además de las alertas del backend, la página muestra los **problemas de cada máquina** que hoy
  viven en su tarjeta: chequeos fallando, sin consentimiento, versión atrasada, modo `simulado`.
  Salen de `GET /estado` (`chequeos_fallando`, `actualizada`, `modo_agente`), sin backend nuevo.

### 2.2 La banda de modo pasa a chip

`BandaModo` deja de ocupar todo el ancho arriba de todo. Queda como chip en la barra:

| Situación | Chip | Al pasar el mouse / tocar |
|---|---|---|
| Destinos acotados, sin envío automático | `● Prueba` gris-verde | "El sistema sólo puede escribirle a los N números de la lista." |
| Destinos abiertos | `● Real` ámbar | "Puede escribirle a cualquier contacto." + link a Seguridad |
| Envío automático prendido | `● Envío automático` rojo | "El pase único envía sin revisión dentro del horario." + link a Envío |

⚠️ Esto **revisa una decisión vieja** (la banda a todo el ancho para "saber en dos segundos si esto
le puede escribir a un cliente real"). La razón para revisarla: el cliente la lee como un error
permanente. El chip sigue diciendo lo mismo en el mismo lugar de todas las pantallas, sólo que sin
gritar. Se anota como decisión nueva (D54) al implementar.

### 2.3 Qué queda en el inicio

Una **sola línea** cuando hay urgentes: *"2 cosas urgentes para revisar → Ver errores"*. Sin
urgentes, nada. Los avisos (nivel `aviso`) no aparecen en el inicio.

---

## 3. Configuración en secciones y switches

### 3.1 Partir la página

`app/(panel)/config/` pasa a ser un layout con menú lateral (en celular, pestañas arriba) y una
subruta por sección. `/config` redirige a `/config/envio`.

| Sección | Qué tiene (lo que hoy está desparramado) |
|---|---|
| **Envío y horarios** `/config/envio` | ⭐ **Envío automático** (switch) · **Corrida automática** (switch + hora + días) · Horario de envío (inicio/fin/días) · Pausa entre envíos |
| **Qué chats y cuántos** `/config/lectura` | Modo de lectura (recientes / barrido) · Orden del recorrido · Silencio mín./máx. · Chats por tanda · Tope de borradores · Tandas y visitas por máquina |
| **Mensajes** `/config/mensajes` | Cómo se dejan (circuito / pase único / con respaldo) · Contexto de la empresa · Post-venta · Etiquetas de contacto · Largo máximo · Frases prohibidas |
| **Seguridad** `/config/seguridad` | Destinos permitidos · Palabras de veto / conflicto · Días de veto (disconforme, ya compró) · Anti-duplicado · Topes por máquina y por corrida · Vetados (`GET /vetados`) |
| **Sistema** `/config/sistema` | Versión del agente · Memoria de visitados · **Empezar de cero** (zona roja, al final, como hoy) |

Los componentes que ya existen (`Volumen`, `Etiquetas`, `CorridaProgramada`, `EnvioAutomatico`,
`VentanaDeEnvio`, `ContextoEmpresa`, `DestinosPermitidos`, `EmpezarDeCero`, …) **se mueven** a
`components/config/*.tsx` sin reescribir su lógica: siguen llamando a `guardarConfiguracion` con
el mismo `Partial<Configuracion>`. El cambio es de lugar y de forma, no de datos.

### 3.2 Los controles

- **`<Interruptor>`** nuevo (`components/ui/interruptor.tsx`, sobre `radix-ui` Switch) para todo
  lo que es sí/no: envío automático, corrida automática, post-compra, etc.
- **`<Opciones>`** (segmented control) para lo que hoy son dos o tres `Button` sueltos con
  `variant` cambiante: modo de lectura, orden, modo de borrador.
- **Cada fila igual**: nombre · una línea de ayuda · control a la derecha. El texto largo de
  explicación va a un "¿Qué hace esto?" desplegable, no a un párrafo fijo.
- **Guardado inmediato** con aviso flotante ("Guardado") y el valor viejo en el aviso para
  deshacer con un click ("Deshacer" vuelve a mandar el valor anterior).

### 3.3 El envío automático, concretamente

Hoy: tarjeta casi al final, input donde hay que escribir `ENVIAR`, botón "Prender".
Propuesta: primera fila de la primera sección.

```
Envío automático                                              [  ○──]
El pase único envía el mensaje en vez de dejarlo como borrador.
Sólo dentro del horario (09:00 a 19:00, lun a vie).
```

Al prender el switch se abre **un** diálogo del panel (`Confirmacion peligrosa`, el que ya usa el
freno): *"Los mensajes van a salir sin que nadie los revise. ¿Prender?"* → [Cancelar] [Prender].
Apagar no pide nada (mismo criterio que "reanudar no confirma nada" del freno). El `PATCH` es el
mismo de hoy: `{ envio_automatico: true }`.

### 3.4 Acciones rápidas (sugerencia)

Arriba de la configuración, tres botones que resuelven lo que más se hace:

- **Pausar todo por hoy** → el mismo `POST /sistema/pausa` del freno.
- **Correr ahora** → el mismo `dispararCorrida("generacion")` del botón del inicio.
- **Probar las máquinas** → `dispararCorrida("diagnostico")`.

---

## 4. Tema claro único y estilo nuevo

### 4.1 Sacar el oscuro

- Borrar `components/tema.tsx` y el `<SelectorDeTema />` de la barra.
- Borrar el script `ELEGIR_TEMA` y el `suppressHydrationWarning` de `app/layout.tsx`.
- Borrar el bloque `.dark { … }` y el `@custom-variant dark` de `globals.css`; quitar los 9 `dark:`.
- `color-scheme: light` en `:root`, para que los controles nativos no se oscurezcan solos.
- Limpiar la clave `tema` de `localStorage` una vez (no hace falta, pero evita basura).

### 4.2 "Más tecnológico y moderno"

Tokens nuevos en `globals.css` (sólo claro), manteniendo la regla de que los colores de estado
no se usan para decorar:

| Token | Hoy | Propuesta |
|---|---|---|
| `--background` | `#faf8f6` (papel cálido) | `#f6f7f9` (gris frío muy claro) |
| `--card` | `#ffffff` | `#ffffff` + borde `#e4e7ec` + sombra `0 1px 2px rgb(16 24 40 / .05)` |
| `--foreground` | `#211a16` | `#0f172a` |
| `--muted-foreground` | `#6e6560` | `#64748b` |
| `--accion` / `--ring` | `#35606f` | `#0891b2` (cian), suave `#e0f5f9` |
| `--primary` | `#2b2724` | `#0f172a` |
| `--radius` | `0.5rem` | `0.75rem` |

- Números y identificadores en **JetBrains Mono** con `tabular-nums` (latidos, contadores, IDs).
- Títulos en Inter semibold con `tracking-tight`; Poppins queda sólo para el logotipo del login.
- Estados con **punto de color** (y pulso suave en "online") en vez de píldoras llenas.
- Un fondo sutil de grilla en el encabezado de cada página (`background-image` con
  `linear-gradient` de 1 px), nada más: el resto limpio.
- ⚠️ Revisa la "regla de reparto" de `globals.css` (neutros cálidos de Centonara). Va como D55.

### 4.3 La tarjeta de máquina nueva

```
┌──────────────────────────────────────────────┐
│ ● Rocío                        hace 12 s  ⋯ │
│   mac-rocio · v a1b2c3d ✓                    │
│                                              │
│   Hoy   14 / 20 borradores   ████████░░░    │
│                                              │
│   ⚠ 1 chequeo fallando                       │
│                                   Ver detalle →│
└──────────────────────────────────────────────┘
```

- Arriba: punto de estado + nombre + latido relativo; abajo, id y versión en mono.
- **Uso de hoy contra el tope**, con barra. El número sale de las tandas de las corridas de hoy
  (`GET /corridas` → `tandas[].dejados` con `maquina` igual), calculado en `lib/derivados.ts`.
- Los problemas se reducen a **un chip** ("1 chequeo fallando", "Sin consentimiento",
  "Desactualizada") que lleva al detalle. El `Aviso` grande de hoy desaparece de la tarjeta.
- Las 5 acciones (pausar por hoy, activar/desactivar, tope, rotar token, dar de baja) van a un menú
  `⋯`. "Pausar por hoy" puede quedar además como botón visible si se usa mucho.
- Barrido y cursor de la ventana se mudan al detalle.
- Toda la tarjeta es clickeable hacia `/maquinas/[maquina]`.

---

## 5. Detalle por máquina `/maquinas/[maquina]` (extra)

Todo con endpoints existentes. Nada nuevo del lado del agente: la máquina ya reporta lo que
reporta, la página sólo lo junta.

| Pestaña | Qué muestra | De dónde sale |
|---|---|---|
| **Resumen** | Estado, último latido (se refresca cada 5 s), versión reportada vs. esperada, modo del agente, puede enviar, tope diario, uso de hoy, cursores de barrido y ventana con "Reiniciar" (en diálogo, no `confirm()`) | `GET /estado` → `maquinas[]` |
| **Chequeos** | Tabla de `diagnostico` con ok / falla / no aplica y qué hacer en cada uno (el diálogo "Ver chequeos" de hoy, como página) | `GET /estado` |
| **Actividad** | Últimas corridas en que participó: pedidos, dejados, salteados, vetados, motivos de salteo, corte y error de su tanda. Gráfico chico de dejados por corrida | `GET /corridas?limite=50` → `tandas[]` filtradas |
| **Mensajes** | Los mensajes de esta máquina en las últimas 3 corridas, con estado y etiqueta; link a la revisión | `GET /corridas/{id}/mensajes` → filtrar `maquina` |
| **Errores** | Las alertas de esta máquina + sus problemas propios | `GET /alertas` (campo `maquina`) + `GET /estado` |
| **Historial** | Eventos de auditoría donde `quien` es esta máquina o el `detalle` la nombra | `GET /historial?limite=500` filtrado en el cliente |
| **Acciones** | Las mismas 5 de la tarjeta + "Probar esta máquina" | mutaciones existentes |

Límites honestos: el backend **no guarda historial de latidos** (sólo el último), así que no hay
gráfico de "cuándo estuvo online" sin tocar el back. Y el filtro por máquina del historial depende
de lo que cada evento guarda en `quien`/`detalle`; hay que verificarlo evento por evento al
implementar.

Además, `/maquinas` como lista: la grilla de tarjetas + el alta de máquina (`AltaMaquina`) que hoy
está en el inicio.

---

## 6. Estadísticas `/estadisticas` (extra)

El bloque `<Metricas />` sale del inicio y crece a página propia. Selector 7 / 30 / 90 días arriba.

- **Números del período** (lo que ya trae `GET /metricas`): enviados, mensajes, corridas, costo,
  costo por enviado, **tasa de edición** (la que importa, en rojo si pasa de 50 %), tasa de
  retención.
- **Por día**: borradores dejados y enviados por día, sumando `tandas` de `GET /corridas`.
- **Por máquina**: ranking de dejados, salteados y errores por máquina en el período.
- **Por qué se salteó**: suma de `tandas[].motivos` — responde "¿por qué dejó tan pocos?".
- **Por qué falló**: `fallidos` por código (ya viene en `/metricas`).
- **Costo**: costo por corrida en el tiempo.

Gráficos: barras y líneas en **SVG propio** (`components/graficos/*.tsx`, ~150 líneas), sin sumar
dependencias. Si más adelante se quieren tooltips ricos o zoom, se evalúa `recharts`.

Límite: `GET /corridas` devuelve hasta 50 corridas. Con una corrida por día alcanza para ~50 días;
para 90 días puede quedar corto. La página lo dice ("basado en las últimas 50 corridas") en vez de
mostrar un número incompleto como si fuera total.

---

## 7. Lo único que toca el backend (aprobado, aditivo)

Agregar `maquina: str | None` a `Alerta.como_dict()` en `backend/app/core/alertas.py` (las alertas
por máquina ya tienen la variable `maquina` a mano). Es un campo más en una respuesta de sólo
lectura: no cambia ninguna regla, ningún job, ningún agente. Con eso el filtro por máquina deja de
depender de matchear nombres en el título. Se hace en el sprint 2, con su test en
`backend/tests/test_alertas.py`, y se suma `maquina: string | null` al tipo `Alerta` de
`lib/panel.ts` en el mismo commit (el test de contrato lo exige). Las alertas globales
(`selector_roto`, `version_esperada_desconocida`, …) mandan `null`.

---

## 8. Otras mejoras sugeridas

1. **Inicio "Hoy"**: 4 números arriba (enviados/borradores hoy · próxima corrida · máquinas online
   `3/4` · errores abiertos), el botón de corrida, y las tarjetas. Nada más.
2. **Reemplazar los 8 `confirm()`** por el `Confirmacion` del panel.
3. **Búsqueda rápida `⌘K`** para saltar a una máquina, una corrida o una sección de config.
4. **Notificación del navegador** (opcional, con permiso) cuando aparece una alerta urgente con la
   pestaña en segundo plano — reemplaza la necesidad de tener la banda roja siempre a la vista.
5. **Estados vacíos y de carga** consistentes (`Esqueleto` ya existe) en todas las páginas nuevas.
6. **Migas de pan** en páginas de detalle (Operación › Máquinas › Rocío).
7. **Textos**: todo lo nuevo en `lib/textos.ts`, como exige el README del frontend.

---

## 9. Sprints

Cada sprint deja el panel usable y se puede desplegar solo. Ninguno toca `backend/` ni `agente/`.

| # | Qué | Archivos principales | Listo cuando |
|---|---|---|---|
| **0** | Tema claro único + tokens nuevos | `globals.css`, `layout.tsx`, borrar `tema.tsx` | No queda `dark` en el código; `pnpm typecheck lint test` verde |
| **1** | Layout común + barra de 3 menús + chip de modo | `app/(panel)/layout.tsx`, `components/navegacion/*`, mover páginas al grupo | Todas las URLs viejas andan; cada página perdió su encabezado propio |
| **2** | `/errores` + sacar alertas del inicio y de las tarjetas + campo `maquina` en alertas (§7) | `app/(panel)/errores/page.tsx`, `components/alertas.tsx`, `backend/app/core/alertas.py` | El inicio sin alertas muestra sólo la línea de urgentes |
| **3** | Configuración en secciones + `Interruptor` + `Opciones` | `app/(panel)/config/**`, `components/config/*`, `components/ui/interruptor.tsx` | Envío automático se prende con un switch + un diálogo; mismos `PATCH` que hoy |
| **4** | Tarjeta nueva + `/maquinas` + `/maquinas/[maquina]` | `components/maquina.tsx`, `lib/derivados.ts`, páginas nuevas | Se puede diagnosticar una máquina sin entrar a la Mac ni a los logs |
| **5** | `/estadisticas` + gráficos SVG | `app/(panel)/estadisticas/page.tsx`, `components/graficos/*` | `<Metricas />` ya no está en el inicio |
| **6** | Pulido: `confirm()` → diálogos, celular, `⌘K`, decisiones D54–D56 en `06-DECISIONES.md` | varios | e2e `recorrido.spec.ts` actualizado y verde |

**Pruebas en cada sprint**: `pnpm lint && pnpm typecheck && pnpm test` y el e2e. Actualizar
`tests/banda-modo.test.tsx` (pasa a probar el chip) y sumar tests de `Interruptor`, del filtro de
errores y de los cálculos de `lib/derivados.ts`. Correr además `backend/tests/test_contrato_panel.py`
para confirmar que `lib/panel.ts` no cambió de forma.

---

## 10. Respuestas del dueño (28/09/2026)

1. **Chip de modo**: sólo el chip, sin franja. Aplica a §2.2 también con envío automático prendido.
2. **Envío automático**: switch + un diálogo con botón; deja de pedirse escribir `ENVIAR` (§3.3).
3. **Acento**: cian `#0891b2` (§4.2). La paleta cálida de Centonara queda sólo en el login.
4. **Backend**: se permite el campo `maquina` en las alertas (§7, sprint 2).

---

## 11. Lo que cambió al implementar

- **`GET /corridas` no trae las tandas.** Sólo las trae el detalle, `GET /corridas/{id}`. Todo lo
  que se cuenta por máquina y por día (el "hoy" de cada tarjeta, la actividad, las estadísticas)
  pide el detalle de las corridas que necesita (`useCorridasConTandas` en `lib/consultas.ts`); una
  corrida terminada no se vuelve a pedir. Sin tocar el backend.
- **"Probar esta máquina" no está en el detalle.** El backend no tiene cómo diagnosticar una sola
  máquina; el diagnóstico de todas está en Ajustes y en el inicio, y los chequeos de cada una se
  actualizan con cada latido.
- **"Sin conexión" no es un error.** El backend no alerta por una Mac apagada sin trabajo
  esperando, y el panel tampoco: el punto rojo de la tarjeta alcanza.
- **Las acciones rápidas de Ajustes quedaron en una** ("Probar las máquinas"). Frenar ya está en la
  barra, y "Generar seguimientos" en el inicio con su confirmación; duplicarlas era más ruido.
- **No se expusieron ajustes nuevos** (frases prohibidas, palabras de veto, días de veto): el pedido
  era simplificar, y D29 los sacó del panel a propósito.
- **Los tests del panel ahora corren** (Vitest y Playwright estaban escritos pero sin sus
  dependencias en el lockfile). Se instalaron, se actualizaron los de `Enviar` a D36, y el CI tiene
  el paso de tests.
- **Sin gráficos de conexión**: el servidor guarda sólo el último latido de cada máquina.

