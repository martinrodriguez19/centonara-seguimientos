# Sistema de Seguimiento Comercial — puesta en marcha en Windows

> El hermano de [`SOP-instalar-mac.md`](SOP-instalar-mac.md) para una PC con Windows 10 u 11.
> **La Parte 1 (en el panel) y la Parte 3 (encender el sistema) son las mismas y no se
> repiten acá**: leélas allá. Lo que cambia es la Parte 2, la que pasa en la computadora del
> vendedor, y el apéndice.
>
> Fecha: 10/09/2026. Windows vuelve al parque con [D48](06-DECISIONES.md): hay una PC en
> producción dejando borradores, instalada a mano. Este instructivo existe para la próxima, y
> para que ésa se actualice sola sin reinstalarla.

---

# Parte 2 — En la PC del vendedor

## 2.1 — Preparar Chrome (con el mouse)

Igual que en Mac, en el Chrome que el vendedor usa todos los días:

1. **Instalar la extensión Claude in Chrome** e iniciar sesión con la cuenta de Claude de
   **esta** máquina.
2. **Usarla una vez**: apretar el ícono de Claude y pedirle cualquier cosa. (Si te lo olvidás,
   no pasa nada: el agente encuentra solo el dato que necesita la primera vez que alguien la
   use. Antes había que reinstalar por esto.)
3. **Abrir `web.whatsapp.com`** y escanear el QR con el teléfono del vendedor.
4. **Dar el permiso de sitio**: ícono de Claude → **configuración → permisos de sitios →
   habilitar `web.whatsapp.com`**. No es el menú de Chrome; es el de adentro de la extensión.

## 2.2 — Un comando, y listo

Abrir **PowerShell** (tecla Windows, escribir `PowerShell`, Enter — **no** hace falta "como
administrador") y pegar esto:

```powershell
irm https://raw.githubusercontent.com/martinrodriguez19/centonara-seguimientos/main/agente/instalador/instalar.ps1 | iex
```

Es una sola línea. Instala lo que falte (`uv` y Claude Code), baja el programa a
`~\centonara-seguimientos`, averigua solo los datos de la máquina, registra tres tareas
programadas —Chrome al iniciar sesión, el agente, y el actualizador— y lo enciende. En el
camino:

- **Pregunta el identificador y el token** — los de la nota de la Parte 1.
- **Puede pedir iniciar sesión en Claude Code**, una única vez: correr `claude` en la
  PowerShell, entrar con la cuenta de esta máquina, salir con `/exit`, y volver a pegar el
  mismo comando.
- **Al final ofrece vincular el navegador de envío** (2.3). Conviene decir que sí ahí mismo,
  con el teléfono a mano.

Si algo falta, el instalador **lo dice en castellano y se detiene**. La respuesta es siempre
la misma: hacer lo que dice y volver a pegar el mismo comando.

Cuando termina dice **INSTALACIÓN COMPLETA**.

## 2.3 — Vincular el navegador que escribe los mensajes

Lo mismo que en Mac: un navegador aparte, con su propia sesión de WhatsApp. Si en su momento se
dijo que no, o si esa sesión vence más adelante:

```powershell
cd ~\centonara-seguimientos; uv run --directory agente python -m agente.main --vincular
```

⚠️ En Windows el circuito de envío (Playwright con carpeta dedicada) **no se probó todavía**:
la PC que está en producción deja borradores con la extensión, que es el circuito que no lo
necesita. Antes de habilitar envíos desde una PC, correr `--vincular` y
`--verificar-selectores` ahí y mirar que pasen.

## 2.4 — Una PC que ya funciona: agregarle sólo la actualización automática

Para una máquina instalada a mano y andando (la de Sofía), **no se reinstala nada**. Se le
agrega únicamente la tarea del actualizador, que desde ahí la mantiene en la versión que fija
el panel:

```powershell
cd ~\centonara-seguimientos; powershell -ExecutionPolicy Bypass -File agente\instalador\instalar.ps1 -SoloActualizador
```

Si el proyecto está en otra carpeta, agregar `-Repo "C:\la\carpeta"`. Registra la tarea, se
pone en la versión del panel, y termina. No toca el `.env`, ni cómo arranca el agente, ni Chrome.

---

# El día a día, una vez andando

Igual que en Mac, con una diferencia que conviene saber: cuando el actualizador deja una versión
nueva, **el agente se cierra solo y la tarea programada lo vuelve a levantar al minuto**. Es
normal verlo "sin conexión" un minuto en el panel después de una actualización.

---

# Si algo no anda

| Lo que se ve | Qué es |
|---|---|
| La máquina figura "sin conexión" más de unos minutos | La PC está apagada, sin internet, o la tarea no arrancó. En PowerShell: `Start-ScheduledTask "Centonara Agente"` |
| La tarjeta dice **atrasada** | El actualizador no pudo. El porqué está en `%LOCALAPPDATA%\Centonara\logs\actualizador.log` |
| Una alerta dice que la máquina *falla todo lo que toma* | Mirar el motivo en la corrida. Si habla de Chrome o del deviceId, es esta PC: abrir Chrome con el perfil de WhatsApp y usar la extensión una vez |
| `Claude in Chrome requires permission` | Falta el permiso de la extensión (2.1, punto 4) |

---

# Apéndice para quien mantiene el sistema

**Qué quedó instalado:** el proyecto en `~\centonara-seguimientos`; tres tareas en el
Programador de tareas (`Centonara Agente`, `Centonara Chrome`, `Centonara Actualizador`), que
corren como el usuario y en su sesión; una copia del actualizador en `~\.centonara\bin\`; y las
herramientas `uv` y `claude` en `~\.local\bin` / `%LOCALAPPDATA%\Programs`. Los logs, en
`%LOCALAPPDATA%\Centonara\logs\`. El agente escribe su marca de vida en `~\.centonara\estado\`.

**Cómo se reinicia el agente cuando hay versión nueva (D46).** El actualizador escribe
`agente\VERSION`; el agente lo ve entre dos jobs, lanza una copia de sí mismo desacoplada (con
la salida en `%LOCALAPPDATA%\Centonara\logs\agente.log`) y se va. No depende de cómo se lo
arrancó: sirve igual en una PC instalada a mano, con el agente en una consola, y con la tarea
programada. Si no pudiera lanzarlo, sale con código 75 y la tarea —si existe— lo reintenta al
minuto. Si el nuevo no vuelve a dar señales de vida, el actualizador restaura el árbol anterior.

**Actualizar a mano, sin esperar la hora:**

```powershell
powershell -ExecutionPolicy Bypass -File ~\centonara-seguimientos\agente\instalador\actualizar.ps1
```

**Volver a una versión anterior:** desde el panel, Configuración → *Versión del agente* →
pegar el commit. Todas las máquinas —Mac y Windows— van a ése en menos de una hora, sin tocar
ninguna.
