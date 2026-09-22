#!/bin/sh
# Backup del database (coerente anche con il bot in esecuzione) + pulizia dei vecchi.
# Uso:  sh scripts/backup.sh [cartella]
#       da cron: 0 3 * * * cd /opt/sfm && sh scripts/backup.sh backup >> data/logs/backup.log 2>&1
# Interprete: $PYTHON, altrimenti il venv del progetto, altrimenti python3.
set -eu
DIR="${1:-backup}"
DB="${SFM_DB_PATH:-data/sfm.db}"
KEEP_DAYS=14

if [ -n "${PYTHON:-}" ]; then
  PY="$PYTHON"
elif [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="$(command -v python3 || command -v python)"
fi
[ -n "$PY" ] || { echo "Nessun interprete Python trovato (imposta PYTHON)" >&2; exit 1; }

mkdir -p "$DIR"
STAMP=$(date +%Y%m%d-%H%M)
"$PY" -c "
import sqlite3
src = sqlite3.connect('${DB}'); dst = sqlite3.connect('data/_backup.db')
src.backup(dst); dst.close(); src.close()
"
gzip -c data/_backup.db > "$DIR/sfm-$STAMP.db.gz"
rm -f data/_backup.db
find "$DIR" -name 'sfm-*.db.gz' -mtime +$KEEP_DAYS -delete
echo "Backup: $DIR/sfm-$STAMP.db.gz"
