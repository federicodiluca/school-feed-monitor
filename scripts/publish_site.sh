#!/usr/bin/env bash
# Genera il sito statico e lo pubblica su GitHub Pages (branch gh-pages).
#
# Gira sulla VM, accanto al bot: nessuna porta aperta, nessun dominio, nessun HTTPS da
# gestire. Il branch gh-pages viene riscritto ogni volta con un solo commit (force push):
# è contenuto generato, non serve la sua storia e il repository non si gonfia.
#
#   ./scripts/publish_site.sh                 # usa le variabili di .env
#   SITE_BASE_URL=... ./scripts/publish_site.sh
#
# Variabili (in .env o nell'ambiente):
#   SITE_BASE_URL          URL pubblico del sito (default: quello di build_site.py)
#   SITE_REMOTE            remote git da usare (default: origin)
#   PYTHON                 interprete da usare (default: python3; con venv: /opt/sfm/.venv/bin/python)
#   TELEGRAM_BOT_USERNAME  username del bot, per i link "apri il bot"
set -euo pipefail

cd "$(dirname "$0")/.."

. scripts/load_env.sh

OUT="${SITE_OUT:-data/site}"
case "$OUT" in /*) ;; *) OUT="$PWD/$OUT" ;; esac   # serve assoluto: più avanti si lavora nel worktree
REMOTE="${SITE_REMOTE:-origin}"
BRANCH="gh-pages"
WORKTREE="${SITE_WORKTREE:-/tmp/sfm-gh-pages}"
TMPBRANCH="sfm-publish-$$"    # ramo usa-e-getta: quello vero vive solo su GitHub

if [ -n "${SITE_BUILD_CMD:-}" ]; then
  eval "$SITE_BUILD_CMD"           # es. dentro il container Docker
else
  "${PYTHON:-python3}" -m scripts.build_site --out "$OUT"
fi

[ -f "$OUT/index.html" ] || { echo "[publish_site] $OUT/index.html non c'è: la generazione non è andata a buon fine" >&2; exit 1; }

# worktree usa-e-getta: ogni pubblicazione è un commit orfano, così il branch resta
# lungo un commit solo anche pubblicando ogni ora
rm -rf "$WORKTREE"
git worktree prune
git worktree add --force --detach "$WORKTREE" HEAD

cd "$WORKTREE"
git checkout -q --orphan "$TMPBRANCH"
git rm -rq --cached . >/dev/null 2>&1 || true
find . -mindepth 1 -maxdepth 1 ! -name ".git" -exec rm -rf {} +
cp -r "$OUT/." .

git add -A
git -c user.name="School Feed Monitor" -c user.email="bot@school-feed-monitor" commit -qm "Sito aggiornato $(date -u '+%Y-%m-%d %H:%M UTC')"
git push --force "$REMOTE" "HEAD:$BRANCH"
echo "[publish_site] pubblicato su $BRANCH"

cd - >/dev/null
git worktree remove --force "$WORKTREE"
git branch -D "$TMPBRANCH" >/dev/null 2>&1 || true
