#!/usr/bin/env bash
#
# Atajo para la guía de instalación: existe para que el comando del SOP sea
# corto y se pueda tipear desde un papel sin equivocarse. Pasó: la URL larga
# quedaba recortada en el PDF y el que la copiaba recibía un 404.
#
# No instala nada él mismo: baja y corre el instalador real, que vive en
# agente/instalador/instalar.sh. Todo cambio va ahí, no acá.

# --http1.1: el curl de macOS 10.15 (7.64) se lleva mal con HTTP/2 contra la
# CDN de GitHub y contesta 503 a todo. Con HTTP/1.1 anda en todas las Macs.
set -Eeuo pipefail
curl -fsSL --http1.1 https://raw.githubusercontent.com/martinrodriguez19/centonara-seguimientos/main/agente/instalador/instalar.sh | bash
