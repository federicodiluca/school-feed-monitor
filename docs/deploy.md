# Deploy: una macchina qualsiasi + sito su GitHub Pages

Come è fatto il servizio in produzione:

```
   VM (bot + scraping)                      GitHub                    Browser
   ┌────────────────────────────────┐  ┌──────────────────┐   ┌────────────────┐
   │ bot Telegram + scraping orario │  │ branch gh-pages  │   │ sito statico   │
   │ SQLite (data/sfm.db)           │─→│ (sito generato)  │──→│ + cookie miei  │
   │ scripts/publish_site.sh        │  │ GitHub Pages     │   └────────────────┘
   └────────────────────────────────┘  └──────────────────┘
```

La VM **non riceve connessioni**: nessuna porta aperta, nessun dominio, nessun certificato.
Genera il sito e lo spinge su `gh-pages`; a servirlo in HTTPS, gratis, ci pensa GitHub Pages.

**Dove conviene tenerla.** In Europa, meglio in Italia. Diversi siti istituzionali
(`istruzione.calabria.it`, `uspmc.sinp.net` e altri) lasciano cadere le connessioni che
arrivano da indirizzi IP esteri: da un server americano quelle fonti sono semplicemente
irraggiungibili. Se la macchina sta fuori dall'Europa serve il ponte di
[deploy/eu-proxy/](../deploy/eu-proxy/README.md); se sta in Italia non serve niente.

Requisiti: 1 GB di RAM, 10 GB di disco, Python 3.11+. Va bene qualunque VPS, anche il più
piccolo: il bot consuma pochissimo.

## 1. Preparare la macchina

Due strade, scegline una:

- **Docker**, se la macchina ce l'ha già: è la via più breve, tutto sta in `docker-compose.yml`.
  Dove sotto vedi il riquadro «con Docker», usa quello.
- **Python nudo**, consigliata sulle macchine piccole (1 GB): il demone Docker si mangia un
  quinto della memoria per nulla.

```bash
sudo apt-get update
sudo apt-get install -y git python3-venv python3-pip sqlite3

```bash
sudo apt-get update
sudo apt-get install -y git python3-venv python3-pip sqlite3   # con Docker bastano git e sqlite3

# la cartella è tua, non di root: niente sudo con git, mai
sudo mkdir -p /opt/sfm && sudo chown "$USER:$USER" /opt/sfm
```

## 2. La chiave per GitHub

La chiave va generata **sulla macchina** e con il tuo utente (non con `sudo`: root ha
un'altra `~/.ssh`). Serve a spingere il sito su `gh-pages`.

```bash
ls ~/.ssh/id_ed25519.pub 2>/dev/null || ssh-keygen -t ed25519 -C "sfm" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub     # questa riga va nei Deploy keys del repo, con "Allow write access"
ssh -T git@github.com         # deve rispondere "Hi federicodiluca/school-feed-monitor!"
```

Se risponde `Permission denied (publickey)`, la chiave su GitHub non è quella della macchina.

## 3. Il codice

```bash
git clone git@github.com:federicodiluca/school-feed-monitor.git /opt/sfm
cd /opt/sfm
python3 -m venv .venv                       # salta questa riga e la prossima se usi Docker
.venv/bin/pip install -r requirements.txt

cp config.example.json config.json && nano config.json     # token del bot e fonti
cp .env.example .env
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env
nano .env
```

`.env` minimo:

```ini
SECRET_KEY=...                                                   # generata sopra
APP_BASE_URL=https://federicodiluca.github.io/school-feed-monitor
SITE_BASE_URL=https://federicodiluca.github.io/school-feed-monitor
TELEGRAM_BOT_USERNAME=IlTuoBot
ADMIN_TELEGRAM_ID=123456789
CONTACT_EMAIL=schoolfeedmonitor@gmail.com
PYTHON=/opt/sfm/.venv/bin/python
SITE_OUT=data/site
```

Con Docker, al posto di `PYTHON=` metti:

```ini
SITE_OUT=data/site
SITE_BUILD_CMD=docker compose run --rm -T bot python -m scripts.build_site --out /usr/src/app/data/site
```

Il valore può restare senza virgolette: `.env` lo leggono sia Python sia gli script, e
prendono tutto quello che segue il primo `=`. Ricorda però che `docker compose run` usa
**l'immagine già costruita**: dopo ogni `git pull` rifai `docker compose up -d --build`,
altrimenti generi il sito con il codice vecchio.

## 4. Il database

Se stai spostando un'installazione esistente, **ferma prima il vecchio bot**: due processi con
lo stesso token si rubano i messaggi (Telegram risponde 409).

Sul vecchio server, a bot spento:

```bash
sqlite3 data/sfm.db "PRAGMA wal_checkpoint(TRUNCATE);"
sqlite3 data/sfm.db ".backup '/tmp/sfm.db'"      # una copia consistente, in un file solo
```

Portalo sulla nuova macchina in `/opt/sfm/data/sfm.db` (un database vecchio chiamato
`checkfeed.db` va bene lo stesso: al primo avvio viene rinominato da solo). Prima di usarlo
sul serio, prova le migrazioni su una copia:

```bash
cd /opt/sfm
cp data/sfm.db /tmp/prova.db
SFM_DB_PATH=/tmp/prova.db .venv/bin/python - <<'PY'
from sfm.db import init_db, get_conn
init_db()
c = get_conn()
print("schema version:", c.execute("PRAGMA user_version").fetchone()[0])
for t in ("users", "sources", "news", "user_sources"):
    print(t, c.execute(f"select count(*) from {t}").fetchone()[0])
PY
rm -f /tmp/prova.db*
```

Ti aspetti `schema version: 7` e gli utenti del bot tutti al loro posto. Con Docker la stessa
prova si fa con `docker compose run --rm -T -e SFM_DB_PATH=/usr/src/app/data/prova.db bot python`
(copiando prima il database in `data/prova.db`).

## 5. Avviare

```bash
cd /opt/sfm
sh scripts/backup.sh backup          # rete di sicurezza prima del primo avvio

sudo cp scripts/sfm-bot.service /etc/systemd/system/
sudo sed -i "s/%USER%/$USER/" /etc/systemd/system/sfm-bot.service
sudo systemctl daemon-reload && sudo systemctl enable --now sfm-bot
journalctl -u sfm-bot -f             # Ctrl-C per uscire
```

Con Docker, invece:

```bash
docker compose up -d --build
docker compose logs -f bot           # Ctrl-C per uscire
```

Il primo avvio importa le fonti del catalogo e le legge **senza inviare notifiche**: ci mette
qualche minuto. Manda `/start` al bot per controllare che risponda.

## 6. Pubblicare il sito

```bash
cd /opt/sfm
./scripts/publish_site.sh
```

Genera il sito in `data/site` e lo spinge su `gh-pages`. Su GitHub, una volta sola:
*repo → Settings → Pages → Deploy from a branch → `gh-pages`, cartella `/ (root)`*.
Dopo un minuto il sito è su `https://federicodiluca.github.io/school-feed-monitor`.

Due dettagli:

- `.nojekyll` (lo genera il build) evita che Pages tratti il sito come un blog Jekyll;
- il `robots.txt` che conta per Google è quello alla **radice del dominio**, cioè nel repo
  `federicodiluca.github.io`: aggiungi lì la riga
  `Sitemap: https://federicodiluca.github.io/school-feed-monitor/sitemap.xml`.

## 7. Automatismi

```bash
crontab -e
# sito aggiornato ogni ora, 10 minuti dopo lo scraping (se cambi la frequenza, allinea
# SITE_PUBLISH_MINUTES in .env: le pagine dicono quando arriva il prossimo aggiornamento)
10 * * * * cd /opt/sfm && ./scripts/publish_site.sh >> data/logs/publish.log 2>&1
# backup del database ogni notte alle 3 (14 giorni di copie in /opt/sfm/backup)
0 3 * * * cd /opt/sfm && sh scripts/backup.sh backup >> data/logs/backup.log 2>&1
```

Pages ricostruisce a ogni push; il limite indicativo è ~10 build all'ora, una all'ora sta
larga. Il branch `gh-pages` viene riscritto ogni volta con **un solo commit orfano**, così il
repository non cresce all'infinito.

## 8. Aggiornare il codice

```bash
cd /opt/sfm && git pull && .venv/bin/pip install -r requirements.txt
sudo systemctl restart sfm-bot

# con Docker
cd /opt/sfm && git pull && docker compose up -d --build
```

## Note

- **Il sito Flask serve ancora**: in locale (`python web.py`) è il modo più comodo per provare
  le modifiche prima di generarle; in produzione non viene esposto.
- **Watchdog**: avvisa su Telegram l'`ADMIN_TELEGRAM_ID` quando una fonte smette di funzionare
  o un job non gira. Con `HEALTHCHECK_PING_URL` puoi aggiungere un monitor esterno gratuito.
- **Se un giorno servisse un dominio**, il sito statico si sposta senza toccare la macchina:
  cambi `SITE_BASE_URL`, rigeneri, e punti il DNS su Pages.
