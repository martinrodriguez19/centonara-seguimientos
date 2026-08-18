# Guía de descarga e instalación

**Para:** el cliente, antes de la visita de instalación
**Tiempo:** 15–20 minutos por computadora
**No hace falta saber programar.** Son descargas y comandos para copiar y pegar.

> Hacer esto **en cada computadora de vendedor**. La parte 5 (n8n) va en una sola
> computadora, la que va a coordinar el sistema.

---

## Antes de empezar: ¿la computadora sirve?

Verificá estas tres cosas. Si alguna falla, avisá antes de la visita.

**Windows 10 (versión 1809 o posterior) o Windows 11, de 64 bits.**
Tecla Windows + R → escribir `winver` → Enter. Aparece la versión.
Para 32 vs 64 bits: Configuración → Sistema → Acerca de → "Tipo de sistema".
Windows de 32 bits no sirve.

**Al menos 4 GB de RAM (8 GB recomendado).**
En la misma pantalla de "Acerca de".

**Conexión a internet estable.**

---

## Parte 1 — Google Chrome

Si ya está instalado, saltear.

1. Ir a **google.com/chrome**
2. Descargar e instalar
3. Abrirlo

> Tiene que ser Chrome. Edge y Brave no están soportados para esto.

---

## Parte 2 — Python

1. Ir a **python.org/downloads**
2. Botón amarillo grande "Download Python"
3. Abrir el archivo descargado

⚠️ **En la primera pantalla del instalador, marcar la casilla de abajo que dice
"Add python.exe to PATH".** Es la más importante de todo el proceso. Si se olvida,
hay que desinstalar y volver a empezar.

4. "Install Now"
5. Al terminar, si aparece "Disable path length limit", hacer clic

**Verificar:** abrir PowerShell (tecla Windows → escribir `powershell` → Enter) y pegar:

```powershell
python --version
```

Tiene que aparecer un número como `Python 3.13.1`.

**Si se abre la Microsoft Store en vez de eso:**
Configuración → Aplicaciones → Configuración avanzada de aplicaciones →
Alias de ejecución de aplicaciones → desactivar `python.exe` y `python3.exe`.
Cerrar PowerShell, abrirlo de nuevo y reintentar.

---

## Parte 3 — Claude Code

No necesita ningún otro programa previo.

1. Abrir PowerShell (**no** hace falta como administrador)
2. Pegar y Enter:

```powershell
irm https://claude.ai/install.ps1 | iex
```

3. Esperar a que termine (menos de un minuto)
4. **Cerrar PowerShell y abrirlo de nuevo** — sin esto no va a encontrar el programa

**Verificar:**

```powershell
claude --version
```

Tiene que aparecer un número de versión.

**Si dice que no reconoce el comando:** cerrar y reabrir PowerShell otra vez. Si
sigue, es un problema de configuración que resuelve el soporte en la visita.

---

## Parte 4 — Extensión de Chrome

1. Con Chrome abierto, ir a la **Chrome Web Store**
2. Buscar la extensión **Claude** (de claude.com)
3. "Añadir a Chrome"
4. Confirmar

No configurar nada todavía. Eso se hace en la visita.

---

## Parte 5 — n8n (SOLO en la computadora coordinadora)

Esta parte va en **una sola** computadora, no en las de los vendedores.

**Primero Node.js:**

1. Ir a **nodejs.org**
2. Descargar la versión **LTS** (el botón de la izquierda)
3. Instalar dejando todo por defecto

**Verificar:**

```powershell
node --version
```

Tiene que decir **v22.22 o superior**. Si dice un número menor, avisar al soporte.

**Después n8n:**

```powershell
npx n8n
```

La primera vez tarda varios minutos en descargar. Cuando termine, abrir
`http://localhost:5678` en el navegador y crear el usuario.

Para cerrarlo: Ctrl+C en esa ventana.

---

## Parte 6 — Cuentas Anthropic

Cada computadora de vendedor necesita una cuenta con plan pago (Pro, Max o Team).
**El plan gratuito no funciona para esto.**

Coordinar con el soporte si van cuentas individuales o un plan Team.

**No hace falta iniciar sesión ahora.** Eso se hace en la visita, junto con la
configuración de permisos.

---

## Checklist final por computadora

Antes de la visita, en cada máquina de vendedor:

- [ ] Windows 10 (1809+) o 11, 64 bits, 4 GB o más de RAM
- [ ] Chrome instalado
- [ ] `python --version` responde
- [ ] `claude --version` responde
- [ ] Extensión Claude agregada a Chrome
- [ ] Cuenta Anthropic con plan pago disponible
- [ ] El vendedor leyó la guía y está de acuerdo
- [ ] El vendedor va a estar presente para escanear el QR

En la computadora coordinadora:

- [ ] `node --version` dice v22.22 o superior
- [ ] n8n abre en `http://localhost:5678`

---

## Lo que hace el soporte en la visita

No intentar estos pasos por adelantado:

- Iniciar sesión en Claude Code
- Configurar permisos de la extensión
- Vincular WhatsApp Web (con el vendedor presente)
- Identificar cada computadora en el sistema
- Copiar los archivos del sistema
- Configurar el arranque automático
- Conectar todo en n8n
- Probar de punta a punta

---

## Si algo no funciona

Anotar en qué paso fue y qué mensaje apareció (una foto de la pantalla sirve).
No hay problema si algo queda a medias: se resuelve en la visita. Lo importante es
que las descargas grandes estén hechas para no perder tiempo.

**Soporte:** >>> nombre y contacto
