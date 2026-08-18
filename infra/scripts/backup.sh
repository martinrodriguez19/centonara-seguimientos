#!/usr/bin/env bash
#
# Backup diario de MongoDB, cifrado, hacia Cloudflare R2 (T0.9).
# Corre como Cron Job de Render. También se puede correr a mano.
#
# El servidor sólo puede CIFRAR: tiene la clave pública, no la privada. Si esta
# máquina se compromete, quien entre puede generar backups y no puede leer
# ninguno.
#
# La retención de 30 días NO la hace este script: es una regla de ciclo de vida
# del bucket en R2. A propósito — el token de R2 es de sólo escritura, así que
# ni siquiera con la credencial robada se puede borrar el historial.
#
# Variables requeridas:
#   ENTORNO                staging | produccion
#   MONGO_URL              cadena de conexión, usuario con permisos mínimos (D14)
#   AGE_RECIPIENT          clave PÚBLICA de age
#   R2_ENDPOINT            https://<account>.r2.cloudflarestorage.com
#   R2_BUCKET              centonara-backups
#   R2_ACCESS_KEY_ID
#   R2_SECRET_ACCESS_KEY

set -Eeuo pipefail

for v in ENTORNO MONGO_URL AGE_RECIPIENT R2_ENDPOINT R2_BUCKET R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY; do
  if [ -z "${!v:-}" ]; then echo "FALTA la variable $v" >&2; exit 1; fi
done

# Un backup vacío que se sube sin chistar es peor que un backup que falla: te
# deja creyendo que estás cubierto.
#
# El chequeo es por CONTENIDO, no por tamaño. Un piso en bytes no sirve acá: el
# dump comprimido de una base con 5000 mensajes pesa unos 25 KiB, así que
# cualquier umbral alto aborta backups sanos y cualquiera bajo no detecta nada.
MINIMO_DOCS=${MINIMO_DOCS:-1}
MINIMO_BYTES=${MINIMO_BYTES:-512}   # sólo para detectar un dump truncado

marca=$(date -u +%Y%m%d-%H%M%S)
ruta="${ENTORNO}/$(date -u +%Y/%m)/seguimiento-${ENTORNO}-${marca}.archive.gz.age"
tmp=$(mktemp "${TMPDIR:-/tmp}/backup.XXXXXX")
trap 'rm -f "$tmp"' EXIT

echo "[1/5] verificando que hay algo que respaldar"
docs=$(mongosh "$MONGO_URL" --quiet --eval '
  db.getCollectionNames().reduce((t,c) => t + db.getCollection(c).countDocuments(), 0)' 2>/dev/null || echo error)
if [ "$docs" = "error" ]; then
  echo "ABORTA: no pude conectarme a la base. No se sube nada." >&2; exit 1
fi
echo "      documentos en la base: ${docs}"
if [ "$docs" -lt "$MINIMO_DOCS" ]; then
  echo "ABORTA: la base tiene ${docs} documentos, menos que el mínimo de ${MINIMO_DOCS}." >&2
  echo "Puede ser la base equivocada en MONGO_URL. No se sube nada." >&2
  exit 1
fi

echo "[2/5] mongodump"
mongodump --uri="$MONGO_URL" --archive --gzip > "$tmp.raw"
crudo=$(wc -c < "$tmp.raw" | tr -d ' ')
echo "      dump: ${crudo} bytes"
if [ "$crudo" -lt "$MINIMO_BYTES" ]; then
  echo "ABORTA: el dump pesa ${crudo} bytes. Está truncado. No se sube nada." >&2
  rm -f "$tmp.raw"; exit 1
fi

echo "[3/5] cifrado con age"
age --encrypt --recipient "$AGE_RECIPIENT" -o "$tmp" "$tmp.raw"
rm -f "$tmp.raw"
cifrado=$(wc -c < "$tmp" | tr -d ' ')

echo "[4/5] subida a R2 → ${ruta}"
export RCLONE_CONFIG_R2_TYPE=s3
export RCLONE_CONFIG_R2_PROVIDER=Cloudflare
export RCLONE_CONFIG_R2_ENDPOINT="$R2_ENDPOINT"
export RCLONE_CONFIG_R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true
rclone copyto "$tmp" "R2:${R2_BUCKET}/${ruta}"

echo "[5/5] verificación de que el objeto llegó"
remoto=$(rclone size --json "R2:${R2_BUCKET}/${ruta}" | sed -n 's/.*"bytes":\([0-9]*\).*/\1/p')
if [ "$remoto" != "$cifrado" ]; then
  echo "ABORTA: subió ${remoto} bytes y el archivo local pesa ${cifrado}." >&2; exit 1
fi

echo "OK — ${ruta} (${cifrado} bytes)"
echo
echo "Este script NO prueba que el backup sea restaurable: no puede, porque no"
echo "tiene la clave privada. Esa prueba es el procedimiento de"
echo "docs/RUNBOOK-backups.md §3 y se corre a mano, con periodicidad mensual."
