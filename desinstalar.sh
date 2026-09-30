#!/usr/bin/env bash
#
# Atajo para la guía: el hermano de instalar.sh. Deja la Mac como si el agente
# nunca se hubiera instalado (ver agente/instalador/desinstalar.sh). Existe
# para que el comando sea corto y se pueda tipear desde un papel.
#
#   curl -fsSL --http1.1 https://github.com/martinrodriguez19/centonara-seguimientos/raw/main/desinstalar.sh | bash
#
# Las opciones (--todo, --si) se pasan así:
#
#   curl -fsSL --http1.1 …/desinstalar.sh | bash -s -- --todo

set -Eeuo pipefail
curl -fsSL --http1.1 https://raw.githubusercontent.com/martinrodriguez19/centonara-seguimientos/main/agente/instalador/desinstalar.sh | bash -s -- "$@"
