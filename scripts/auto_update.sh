#!/usr/bin/env bash
# Aggiorna da solo il codice sulla VM, ma solo con commit che hanno passato i test su GitHub.
#
#   ./scripts/auto_update.sh            # da cron, ogni 12 ore (righe in docs/deploy.md)
#   ./scripts/auto_update.sh --dry-run  # dice cosa farebbe, senza toccare niente
#
# Passi: fetch di main → se è cambiato e il job "pytest" su GitHub è verde → backup del
# database → pull (solo fast-forward) → riavvio del bot (Docker o systemd) → dopo un minuto
# controlla che il bot sia ancora in piedi. Se no, torna al commit di prima e quel commit
# non viene più ritentato finché su main non arriva altro. Esito su Telegram all'admin.
#
# Variabili (in .env o nell'ambiente):
#   ADMIN_TELEGRAM_ID     chat a cui mandare l'esito (senza, scrive solo nel log)
#   SFM_DEPLOY_MODE       docker | systemd (default: docker se il container sfm-bot esiste)
#   PYTHON                interprete per pip, con systemd (default: .venv/bin/python)
#   AUTO_UPDATE_WAIT      secondi di attesa prima del controllo (default: 60)
#
# Con systemd il riavvio usa "sudo systemctl restart sfm-bot": da cron serve una regola
# sudoers senza password solo per quel comando (vedi docs/deploy.md).
set -euo pipefail

cd "$(dirname "$0")/.."

# Tutto dentro main(): bash legge lo script mentre lo esegue, e il pull può riscriverlo.
# Una funzione viene letta per intero prima di partire, quindi il pull non la tocca.
main() {
  . scripts/load_env.sh

  local dry_run=0
  [ "${1:-}" = "--dry-run" ] && dry_run=1

  local skip_file="data/.auto_update_skip"   # commit che ha già fallito: non si ritenta
  local branch="main"
  local wait="${AUTO_UPDATE_WAIT:-60}"

  exec 9>data/.auto_update.lock
  flock -n 9 || { log "un altro aggiornamento è in corso, esco"; return 0; }

  local current_branch
  current_branch="$(git rev-parse --abbrev-ref HEAD)"
  [ "$current_branch" = "$branch" ] || { log "la VM è sul branch '$current_branch', non su $branch: non aggiorno"; return 0; }

  git fetch -q origin "$branch"
  local old new
  old="$(git rev-parse HEAD)"
  new="$(git rev-parse "origin/$branch")"

  if ! git diff --quiet HEAD; then
    notify "⚠️ Aggiornamento automatico fermo: sulla VM ci sono modifiche locali a file del repo (git status). Serve un intervento a mano."
    return 1
  fi
  if [ "$old" = "$new" ]; then
    log "già aggiornato (${old:0:7})"
    return 0
  fi
  if ! git merge-base --is-ancestor "$old" "$new"; then
    notify "⚠️ Aggiornamento automatico fermo: la VM ha commit che main non ha (${old:0:7}). Serve un intervento a mano."
    return 1
  fi
  if [ -f "$skip_file" ] && [ "$(cat "$skip_file")" = "$new" ]; then
    log "${new:0:7} ha già fallito una volta, aspetto un commit nuovo"
    return 0
  fi

  local ci
  ci="$(ci_status "$new")"
  if [ "$ci" != "success" ]; then
    log "test su GitHub per ${new:0:7}: $ci — non aggiorno"
    return 0
  fi

  local mode="${SFM_DEPLOY_MODE:-}"
  if [ -z "$mode" ]; then
    if command -v docker >/dev/null 2>&1 && docker inspect sfm-bot >/dev/null 2>&1; then mode=docker; else mode=systemd; fi
  fi

  local changes
  changes="$(git log -n 15 --format='• %s' "$old..$new")"
  if [ "$dry_run" = 1 ]; then
    log "aggiornerei ${old:0:7} → ${new:0:7} ($mode):"
    printf '%s\n' "$changes"
    return 0
  fi

  log "aggiorno ${old:0:7} → ${new:0:7} ($mode)"
  sh scripts/backup.sh backup   # prima di tutto: le migrazioni del database non tornano indietro
  git merge -q --ff-only "$new"

  if deploy "$mode" && healthy "$mode" "$wait"; then
    rm -f "$skip_file"
    notify "✅ School Feed Monitor aggiornato (${old:0:7} → ${new:0:7}):
$changes"
    return 0
  fi

  log "il bot non è partito con ${new:0:7}, torno a ${old:0:7}"
  echo "$new" > "$skip_file"
  git reset -q --hard "$old"
  if deploy "$mode" && healthy "$mode" "$wait"; then
    notify "⚠️ Aggiornamento a ${new:0:7} fallito: il bot non restava in piedi. Tornato a ${old:0:7}, che funziona. Il backup del database è in backup/.
$changes"
  else
    notify "🚨 Aggiornamento a ${new:0:7} fallito e il bot non riparte nemmeno con ${old:0:7}. Serve un intervento a mano (backup del database in backup/)."
  fi
  return 1
}

log() { echo "[auto_update $(date '+%Y-%m-%d %H:%M')] $*"; }

# Esito del job "pytest" (workflow Test) per il commit: success, failure, pending, none...
# Repo pubblico: l'API di GitHub risponde senza token (60 richieste l'ora, ce ne basta una).
ci_status() {
  local repo
  repo="$(git remote get-url origin | sed -E 's#^(https://github\.com/|git@github\.com:)##; s#\.git$##')"
  curl -fsS -m 20 -H "Accept: application/vnd.github+json" \
      "https://api.github.com/repos/$repo/commits/$1/check-runs?check_name=pytest" \
    | python3 -c '
import json, sys
runs = json.load(sys.stdin).get("check_runs", [])
if not runs:
    print("none")
elif any(r["status"] != "completed" for r in runs):
    print("pending")
else:
    print("success" if all(r["conclusion"] == "success" for r in runs) else "failure")
' || echo "errore nel leggere lo stato"
}

deploy() {
  if [ "$1" = docker ]; then
    docker compose up -d --build --force-recreate --quiet-pull   # ricreato sempre: RestartCount riparte da 0
  else
    "${PYTHON:-.venv/bin/python}" -m pip install -q -r requirements.txt && sudo -n systemctl restart sfm-bot
  fi
}

# Il bot deve essere ancora in piedi dopo l'attesa, senza essersi riavviato nel frattempo
# (docker e systemd lo rilancerebbero da soli dopo un crash, nascondendolo).
healthy() {
  local mode="$1" wait="$2" before after
  if [ "$mode" = docker ]; then
    sleep "$wait"
    [ "$(docker inspect -f '{{.State.Running}} {{.RestartCount}}' sfm-bot 2>/dev/null)" = "true 0" ]
  else
    before="$(systemctl show -p NRestarts --value sfm-bot)"
    sleep "$wait"
    after="$(systemctl show -p NRestarts --value sfm-bot)"
    systemctl is-active -q sfm-bot && [ "$before" = "$after" ]
  fi
}

# Messaggio all'admin su Telegram. Solo libreria standard: con Docker, sull'host non ci sono
# le dipendenze del progetto.
notify() {
  log "$1"
  [ -n "${ADMIN_TELEGRAM_ID:-}" ] || return 0
  python3 - "$1" <<'PY' || log "invio su Telegram non riuscito"
import json, os, sys, urllib.parse, urllib.request
token = json.load(open("config.json"))["telegram_token"]
data = urllib.parse.urlencode({"chat_id": os.environ["ADMIN_TELEGRAM_ID"], "text": sys.argv[1],
                               "disable_web_page_preview": "true"}).encode()
urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=20)
PY
}

main "$@"; exit $?   # sulla stessa riga: bash la legge intera prima che il pull riscriva il file
