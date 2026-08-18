#!/usr/bin/env bash
#
# Restauración de un backup cifrado (T0.9).
#
# Se corre A MANO, desde una máquina de confianza, con la clave privada de age.
# La clave privada NUNCA vive en un servidor: si estuviera ahí, cifrar no
# serviría de nada.
#
#   ./restaurar.sh <archivo.age> <uri-mongo-destino> [clave-privada] [base-origen]
#
# El destino tiene que ser una base VACÍA y el script se niega a escribir sobre
# una que tenga datos.

set -Eeuo pipefail

archivo=${1:?falta el archivo .age}
destino=${2:?falta la URI de Mongo de destino, con el nombre de la base incluido}
clave=${3:-$HOME/.centonara-age-key.txt}
base_origen=${4:-seguimiento}

[ -f "$archivo" ] || { echo "no existe: $archivo" >&2; exit 1; }
[ -f "$clave"   ] || { echo "no existe la clave privada: $clave" >&2; exit 1; }

# mongorestore con --archive restaura sobre la base que viene DENTRO del
# archivo e ignora la de la URI. Sin el remapeo de abajo, restaurar un backup
# de producción sobre una base de pruebas pisaría producción.
sin_query=${destino%%\?*}
query=""; [ "$destino" != "$sin_query" ] && query="?${destino#*\?}"
base_destino=${sin_query##*/}
prefijo=${sin_query%/*}
# mongorestore toma la base de la URI como si fuera --db, y eso choca con el
# remapeo: filtra por una base que dentro del archivo no existe y restaura CERO
# documentos sin devolver error. Por eso se le pasa la URI sin base.
uri_sin_base="${prefijo}/${query}"
if [ -z "$base_destino" ]; then
  echo "La URI tiene que incluir el nombre de la base de destino." >&2
  echo "  mal:  mongodb+srv://.../"                                 >&2
  echo "  bien: mongodb+srv://.../seguimiento_restaurado"           >&2
  exit 1
fi

echo "origen  : ${base_origen}  (dentro del archivo)"
echo "destino : ${base_destino}"
echo

echo "[1/3] comprobando que el destino está vacío"
colecciones=$(mongosh "$destino" --quiet --eval 'db.getCollectionNames().length' 2>/dev/null || echo error)
[ "$colecciones" = "error" ] && { echo "no pude conectarme al destino" >&2; exit 1; }
if [ "$colecciones" != "0" ]; then
  echo "ABORTA: ${base_destino} ya tiene ${colecciones} colecciones." >&2
  echo "Restaurá sobre una base vacía. Si de verdad querés pisarla, borrala vos primero." >&2
  exit 1
fi

echo "[2/3] descifrando"
tmp=$(mktemp "${TMPDIR:-/tmp}/restore.XXXXXX"); trap 'rm -f "$tmp"' EXIT
age --decrypt --identity "$clave" -o "$tmp" "$archivo"

echo "[3/4] mongorestore (${base_origen} → ${base_destino})"
mongorestore --uri="$uri_sin_base" --archive="$tmp" --gzip \
  --nsFrom="${base_origen}.*" --nsTo="${base_destino}.*"

# mongorestore devuelve 0 aunque no haya restaurado nada. Contar es la única
# forma de saber si sirvió.
echo "[4/4] verificando que los datos están"
resumen=$(mongosh "$destino" --quiet --eval '
  const r = db.getCollectionNames().sort().map(c => c + "=" + db.getCollection(c).countDocuments());
  print(r.length ? r.join("  ") : "SIN COLECCIONES");
  print("TOTAL:" + db.getCollectionNames().reduce((t,c) => t + db.getCollection(c).countDocuments(), 0));')
echo "$resumen" | head -1
total=$(echo "$resumen" | sed -n 's/^TOTAL://p')
if [ "${total:-0}" -eq 0 ]; then
  echo "FALLÓ: mongorestore terminó sin error pero ${base_destino} quedó vacía." >&2
  exit 1
fi

echo
echo "Restauración verificada: ${total} documentos en ${base_destino}."
echo "Contrastá el conteo contra lo esperado — ver docs/RUNBOOK-backups.md §3."
