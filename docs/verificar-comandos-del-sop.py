"""Corre los comandos del SOP, para que la guía no mienta.

Existe porque pasó: el SOP decía

    ./agente/.venv/bin/python -m agente.main --datos

y eso falla con "No module named agente.main" desde la raíz del repositorio, que
es justo desde donde la guía dice pararse. El comando nunca se había corrido: se
escribió, se leyó bien, y estaba mal.

Se corre así:

    uv run --project agente python docs/verificar-comandos-del-sop.py

Dos resultados esperados que NO son fallas:
  - `cd centonara-seguimientos` falla si ya estás adentro
  - `--diagnostico` sale con código distinto de cero cuando algo está degradado

No corre los comandos que instalan cosas, arrancan servicios o cuestan dinero:
esos se listan con el motivo.

No los corre todos a ciegas: los que instalan cosas o arrancan servicios se
listan para revisar a mano. Los que sirven para averiguar algo se corren.
"""

import pathlib
import re
import subprocess

RAIZ = pathlib.Path(r"C:\Users\Usuario\Desktop\centonara-seguimientos")
SOP = RAIZ / "docs" / "SOP-instalar-mac.md"

# Los que no se corren acá, y por qué.
NO_CORRER = {
    "curl -LsSf": "instala uv",
    "npm install": "instala Claude Code",
    "git clone": "clona el repositorio",
    "launchctl": "solo macOS",
    "pgrep": "solo macOS",
    "~/Library/": "ruta de la Mac",
    "open ": "solo macOS",
    "cp .env.example": "pisaría el .env de esta máquina",
    "--sonda": "cuesta USD 0,50 y abre el navegador",
    "cd ~/centonara": "ruta de la Mac",
    "cd centonara-seguimientos": "entra a lo recién clonado, que acá no existe",
    "/Applications/Google": "solo macOS",
    "instalar-mac.sh": "solo macOS",
    "uv sync": "ya está sincronizado",
}

# Salidas distintas de 0 que igual significan que el comando anduvo. Sin esto,
# `--diagnostico` se marca como roto justamente cuando hace bien su trabajo.
SALIDAS_ESPERADAS = {
    "--diagnostico": {0, 3},  # 3 = degradado, que es lo que informa
}

# Traducciones para poder correr en Windows lo que el SOP escribe para macOS.
EN_WINDOWS = {
    "curl http://localhost:9222/json/version": "curl -s -m 5 http://localhost:9222/json/version",
    "curl https://backend-produccion-7yqr.onrender.com/health":
        "curl -s -m 90 https://backend-produccion-7yqr.onrender.com/health",
}


def comandos() -> list[str]:
    texto = SOP.read_text(encoding="utf-8")
    fuera = []
    for bloque in re.findall(r"```bash\n(.*?)```", texto, re.S):
        # Un bloque puede tener varias lineas y continuaciones con `\`.
        junto = re.sub(r"\\\n\s*", " ", bloque).strip()
        for linea in junto.splitlines():
            if linea.strip() and not linea.strip().startswith("#"):
                fuera.append(linea.strip())
    return fuera


def main() -> None:
    corridos = fallados = salteados = 0
    print(f"{len(comandos())} comandos en el SOP\n")

    for cmd in comandos():
        motivo = next((v for k, v in NO_CORRER.items() if k in cmd), None)
        if motivo:
            salteados += 1
            print(f"  [ - ] {cmd[:66]:68} ({motivo})")
            continue

        real = EN_WINDOWS.get(cmd, cmd)
        try:
            r = subprocess.run(
                real, shell=True, cwd=RAIZ, capture_output=True,
                text=True, timeout=180, encoding="utf-8", errors="replace",
            )
            esperadas = next(
                (v for k, v in SALIDAS_ESPERADAS.items() if k in cmd), {0}
            )
            ok = r.returncode in esperadas
        except Exception as e:  # noqa: BLE001
            ok, r = False, type("R", (), {"stderr": str(e), "returncode": -1})()

        corridos += 1
        if ok:
            print(f"  [OK ] {cmd[:66]}")
        else:
            fallados += 1
            print(f"  [MAL] {cmd[:66]}")
            print(f"        {(r.stderr or '').strip().splitlines()[-1][:100] if r.stderr else 'sin salida'}")

    print(f"\ncorridos: {corridos}   fallados: {fallados}   salteados: {salteados}")


main()
