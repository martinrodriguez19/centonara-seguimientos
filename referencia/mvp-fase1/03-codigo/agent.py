#!/usr/bin/env python3
"""
Agente local del MVP.

Corre en CADA computadora. Escucha en la LAN y, cuando n8n le pega,
ejecuta Claude Code en modo headless con la integracion de Chrome activada.

Solo stdlib. Sin dependencias.

Uso:
    export AGENT_TOKEN="cambiar-esto"
    python3 agent.py            # escucha en 0.0.0.0:8787

Endpoints:
    GET  /health  -> {"ok": true, "machine": "PC-1", "claude": "2.1.x"}
    POST /run     -> corre el prompt y devuelve el JSON que produjo Claude
"""

import json
import os
import shutil
import socket
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# --- Config ---------------------------------------------------------------

TOKEN = os.environ.get("AGENT_TOKEN", "cambiar-esto")
MACHINE = os.environ.get("MACHINE_NAME", socket.gethostname())
PORT = int(os.environ.get("AGENT_PORT", "8787"))
TIMEOUT = int(os.environ.get("RUN_TIMEOUT", "600"))  # 10 min
DEVICE_ID = os.environ.get("DEVICE_ID", "")  # deviceId del Chrome LOCAL de esta PC
MODEL = os.environ.get("MODEL", "")  # vacio = default de la cuenta. Ej: claude-sonnet-5
PROMPT_FILE = Path(__file__).parent / "prompt.txt"
CLAUDE_BIN = os.environ.get("CLAUDE_BIN") or shutil.which("claude") or "claude"

# El prompt es FIJO y vive en disco. n8n solo manda variables acotadas
# (cuantos chats, id de corrida). Asi el agente no ejecuta texto arbitrario
# que venga por la red.
ALLOWED_VARS = {"n_chats", "run_id"}


# --- Core -----------------------------------------------------------------

def build_prompt(variables: dict) -> str:
    base = PROMPT_FILE.read_text(encoding="utf-8")
    n_chats = int(variables.get("n_chats", 5))
    n_chats = max(1, min(n_chats, 10))  # cota dura
    run_id = str(variables.get("run_id", "manual"))[:64]
    return (base
            .replace("{{N_CHATS}}", str(n_chats))
            .replace("{{RUN_ID}}", run_id)
            .replace("{{DEVICE_ID}}", DEVICE_ID))


def run_claude(prompt: str) -> dict:
    cmd = [CLAUDE_BIN, "-p", "--chrome", "--output-format", "json"]
    if MODEL:
        cmd += ["--model", MODEL]

    # El prompt va por STDIN, no como argumento. En Windows, claude.CMD pasa por
    # cmd.exe, que corta el comando en el primer salto de linea: un prompt
    # multilinea como argumento llega mutilado.
    # encoding utf-8 explicito: si no, Windows decodifica con cp1252 y rompe los acentos.
    proc = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT,
        cwd=str(Path(__file__).parent),
    )
    raw = (proc.stdout or "").strip()

    if proc.returncode != 0:
        return {
            "ok": False,
            "error": "claude_exit_nonzero",
            "returncode": proc.returncode,
            "stderr": proc.stderr[-2000:],
            "stdout": raw[-2000:],
        }

    # --output-format json envuelve la respuesta; el texto final del modelo
    # queda en "result". Adentro esperamos nuestro propio JSON.
    try:
        envelope = json.loads(raw)
        inner = envelope.get("result", raw)
    except json.JSONDecodeError:
        inner = raw

    try:
        payload = json.loads(_strip_fences(inner))
        return {"ok": True, "data": payload}
    except json.JSONDecodeError:
        # No parseo: devolvemos crudo para poder debuggear el prompt.
        return {"ok": False, "error": "modelo_no_devolvio_json", "raw": inner[-4000:]}


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


# --- HTTP -----------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, body: dict):
        blob = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def _authorized(self) -> bool:
        return self.headers.get("X-Agent-Token", "") == TOKEN

    def do_GET(self):
        if self.path != "/health":
            return self._send(404, {"error": "not_found"})
        version = "?"
        try:
            version = subprocess.run(
                [CLAUDE_BIN, "--version"], capture_output=True, text=True, timeout=20
            ).stdout.strip()
        except Exception as exc:  # noqa: BLE001
            version = f"error: {exc}"
        self._send(200, {"ok": True, "machine": MACHINE, "claude": version})

    def do_POST(self):
        if self.path != "/run":
            return self._send(404, {"error": "not_found"})
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})

        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "json_invalido"})

        variables = {k: v for k, v in body.items() if k in ALLOWED_VARS}

        # Chequeos previos explicitos: dan un error entendible en vez de un 500 mudo.
        if not PROMPT_FILE.exists():
            return self._send(500, {"ok": False, "machine": MACHINE,
                                    "error": "falta_prompt_txt",
                                    "detalle": f"no existe {PROMPT_FILE}"})
        if shutil.which(CLAUDE_BIN) is None and not Path(CLAUDE_BIN).exists():
            return self._send(500, {"ok": False, "machine": MACHINE,
                                    "error": "claude_no_encontrado",
                                    "detalle": f"'{CLAUDE_BIN}' no esta en el PATH de este proceso",
                                    "path": os.environ.get("PATH", "")[:1500]})

        try:
            result = run_claude(build_prompt(variables))
        except subprocess.TimeoutExpired:
            return self._send(504, {"ok": False, "machine": MACHINE, "error": "timeout"})
        except Exception as exc:  # noqa: BLE001
            return self._send(500, {"ok": False, "machine": MACHINE,
                                    "error": type(exc).__name__, "detalle": str(exc)[:1000]})

        result["machine"] = MACHINE
        result["run_id"] = variables.get("run_id", "manual")
        self._send(200 if result.get("ok") else 502, result)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{MACHINE}] {fmt % args}\n")


if __name__ == "__main__":
    if TOKEN == "cambiar-esto":
        print("AVISO: estas usando el token por defecto. Cambialo.", file=sys.stderr)
    if not DEVICE_ID:
        print("AVISO: DEVICE_ID vacio. Con mas de un Chrome conectado, "
              "Claude no va a saber cual usar y la corrida va a fallar.", file=sys.stderr)
    print(f"Agente '{MACHINE}' escuchando en 0.0.0.0:{PORT} (claude: {CLAUDE_BIN})")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
