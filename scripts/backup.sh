#!/bin/sh
# Backup del database (coerente anche con il bot in esecuzione) + pulizia dei vecchi.
# Uso:  sh scripts/backup.sh [cartella]   — es. da cron: 0 3 * * * sh /opt/sfm/scripts/backup.sh
set -eu
DIR="${1:-backup}"
DB="${SFM_DB_PATH:-data/sfm.db}"
KEEP_DAYS=14

mkdir -p "$DIR"
STAMP=$(date +%Y%m%d-%H%M)
docker compose exec -T bot python -c "
import sqlite3, sys
src = sqlite3.connect('${DB}')
dst = sqlite3.connect('/usr/src/app/data/_backup.db')
src.backup(dst); dst.close(); src.close()
" 2>/dev/null || python -c "
import sqlite3
src = sqlite3.connect('${DB}'); dst = sqlite3.connect('data/_backup.db')
src.backup(dst); dst.close(); src.close()
"
gzip -c data/_backup.db > "$DIR/sfm-$STAMP.db.gz"
rm -f data/_backup.db
find "$DIR" -name 'sfm-*.db.gz' -mtime +$KEEP_DAYS -delete
echo "Backup: $DIR/sfm-$STAMP.db.gz"
