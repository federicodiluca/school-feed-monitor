# Carica .env nell'ambiente, da includere con ". scripts/load_env.sh" (dalla radice del repo).
#
# Legge .env come lo legge Python (sfm/env.py): il valore è tutto quello che segue il primo
# "=", anche con spazi dentro. Non usiamo ". ./.env" perché una riga tipo
#   SITE_BUILD_CMD=docker compose run ...
# la shell la eseguirebbe invece di assegnarla.
if [ -f .env ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ""|"#"*) continue ;; *"="*) ;; *) continue ;; esac
    key="${line%%=*}"
    value="${line#*=}"
    key="$(printf '%s' "$key" | tr -d '[:space:]')"
    case "$value" in
      \"*\") value="${value#\"}"; value="${value%\"}" ;;
      "'"*"'") value="${value#'}"; value="${value%'}" ;;
    esac
    [ -n "$key" ] || continue
    export "$key=$value"
  done < .env
fi
