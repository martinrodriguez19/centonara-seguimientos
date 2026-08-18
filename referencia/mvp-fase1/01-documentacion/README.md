# MVP — 2 PCs, Claude in Chrome, templates de seguimiento

Arquitectura: **n8n (central) → agente HTTP en cada PC → `claude -p --chrome` → JSON de vuelta.**

El disparo ocurre *dentro* de cada máquina, así que cada Claude Code habla con el
Chrome local vía native messaging. No hay ruteo en la nube ni competencia entre
dispositivos: PC-1 maneja su Chrome, PC-2 el suyo, al mismo tiempo.

```
        ┌──────────────┐
        │     n8n      │
        └──────┬───────┘
       POST /run│(paralelo)
        ┌───────┴───────┐
        ▼               ▼
   ┌─────────┐     ┌─────────┐
   │  PC-1   │     │  PC-2   │   agent.py :8787
   │ claude  │     │ claude  │   claude -p --chrome
   │ Chrome  │     │ Chrome  │   web.whatsapp.com (solo lectura)
   └─────────┘     └─────────┘
```

## En cada PC (una sola vez)

1. **Extensión** Claude in Chrome instalada (v1.0.36+) y Chrome abierto.
2. **Claude Code** instalado y logueado con `/login` — *no* con API key.
   La integración con Chrome no funciona con API key ni con token de
   `claude setup-token`: requiere sesión de plan Pro/Max/Team/Enterprise.
3. `claude --chrome` una vez en interactivo, aceptar el diálogo inicial y el
   permiso del skill `claude-in-chrome`. Verificar con `/chrome` que diga
   *Status: Enabled* y *Extension: Installed*.
4. En la configuración de la extensión, dar permiso al sitio `web.whatsapp.com`
   (los permisos por sitio se heredan de la extensión).
5. WhatsApp Web ya logueado en ese Chrome (QR escaneado a mano).
6. Pre-aprobar las tools para que el modo headless no se cuelgue esperando
   confirmación. En `~/.claude/settings.json` (o `.claude/settings.json` de la
   carpeta del agente):

```json
{
  "permissions": {
    "allow": ["mcp__claude-in-chrome"]
  }
}
```

7. Copiar `agent.py` y `prompt.txt` a la máquina y levantar:

```bash
export AGENT_TOKEN="un-token-largo"
export MACHINE_NAME="PC-1"      # PC-2 en la otra
python3 agent.py
```

8. Probar sin n8n:

```bash
curl http://localhost:8787/health
curl -X POST http://localhost:8787/run \
  -H "X-Agent-Token: un-token-largo" \
  -H "Content-Type: application/json" \
  -d '{"n_chats":5,"run_id":"test-1"}'
```

Si eso devuelve JSON con los 5 chats, el 90% del MVP ya está.

## En n8n

1. Importar `n8n-workflow-mvp.json`.
2. Reemplazar las IPs (`192.168.0.101` / `.102`) por las de tus PCs y el token
   en los headers de ambos nodos HTTP.
3. Si n8n corre en Docker en una de las dos máquinas, para llegar a esa misma
   máquina usá `http://host.docker.internal:8787` en vez de `localhost`.
4. Ejecutar el disparo manual y mirar la salida del nodo *Normalizar*: una fila
   por chat con `maquina`, `contacto`, `resumen` y `template`.

## Modo secuencial (plan B)

Si en algún momento querés espaciar las corridas en vez de paralelizarlas:
reemplazá las dos ramas por un nodo **Loop Over Items** con la lista de máquinas,
un **HTTP Request** adentro del loop y un **Wait** de 20 minutos antes de cerrar
el ciclo. Mismo agente, mismo prompt, cambia solo la orquestación.

## Límites deliberados de este MVP

- **No envía nada.** Solo lee y redacta. Enviar es otra decisión y otro sprint.
- Sin persistencia: la salida queda en la ejecución de n8n. Sumar Sheets/Postgres
  es un nodo más cuando el flujo ya funcione.
- Sin reintentos ni alertas. Si una PC no responde, el `neverError` deja pasar el
  error a la salida para que lo veas, nada más.
- El agente escucha en la LAN con un token compartido. Está bien para probar en
  tu red; no lo expongas a internet así.

## Dónde suele fallar la primera vez

| Síntoma | Causa | Fix |
|---|---|---|
| `Browser extension is not connected` | native messaging host no llega a la extensión | reiniciar Chrome y Claude Code, `/chrome` → Reconnect |
| El proceso queda colgado sin salir | prompt de permiso esperando input en modo headless | pre-aprobar las tools en `settings.json` (paso 6) |
| `modelo_no_devolvio_json` | el modelo agregó texto alrededor | mirar el campo `raw`, endurecer el cierre del prompt |
| `status: sesion_no_iniciada` | WhatsApp Web pidió QR | reescanear a mano en esa PC |
| Chrome tools apagadas pese a `--chrome` | sesión autenticada con API key | `/login` con la cuenta del plan |
