# Deploy: VM su Google Cloud + sito su GitHub Pages

Come è fatto il servizio in produzione:

```
   VM Google Cloud (e2-micro, free tier)         GitHub                    Browser
   ┌────────────────────────────────┐      ┌──────────────────┐     ┌────────────────┐
   │ bot Telegram + scraping orario │      │ branch gh-pages  │     │ sito statico   │
   │ SQLite (data/sfm.db)           │─push→│ (sito generato)  │─────│ + cookie miei  │
   │ scripts/publish_site.sh        │      │ GitHub Pages     │     └────────────────┘
   └────────────────────────────────┘      └──────────────────┘
```

La VM **non riceve connessioni**: nessuna porta aperta, nessun dominio, nessun certificato.
Genera il sito e lo spinge su `gh-pages`; a servirlo (in HTTPS, gratis) ci pensa GitHub Pages.
Il sito non ha account né form: fonti e parole chiave restano nei cookie del visitatore e
viaggiano verso il bot dentro il link `t.me/…?start=…` (vedi `sfm/config_link.py`).

## 1. La VM

Console Google Cloud → *Compute Engine → VM instances → Create instance*:

| Campo | Valore |
|---|---|
| Region / Zone | `us-central1`, `us-west1` o `us-east1` — **solo queste tre** sono nel free tier |
| Machine type | `e2-micro` (serie E2) |
| Boot disk | Debian 12, **Standard persistent disk**, 30 GB |
| Firewall | non spuntare niente: nessun traffico in entrata |
| Network interfaces | External IPv4: **Ephemeral** (vedi sotto) |

La VM non riceve connessioni: l'IP pubblico serve solo a lei per **uscire** (leggere le fonti,
parlare con Telegram, spingere su GitHub) e a te per entrare in SSH.

Volendo si può togliere del tutto l'IP pubblico, ma allora servono due pezzi in più:
un **Cloud NAT** nella regione della VM (*VPC network → Cloud NAT*, source: primary IP ranges
of all subnets) per farla uscire, e una regola firewall *Ingress* da `35.235.240.0/20` su TCP 22
per entrare in SSH attraverso IAP. Costa più o meno quanto l'IP: si fa per ridurre la superficie
esposta, non per risparmiare.

> **Costi.** Il free tier copre la VM `e2-micro` e i 30 GB di disco standard; l'indirizzo IPv4
> pubblico è fatturato a parte (~3 $/mese) ma finché sei nella prova gratuita viene pagato dal
> credito. Per vedere se lo stai pagando: *Billing → Report*, raggruppa per **SKU** e cerca
> "External IP Charge on a Standard VM". Metti comunque un budget di 1 € con avviso al 100% in
> *Billing → Budgets & alerts*.

## 2. Preparare la macchina

Su una e2-micro (1 GB di RAM) conviene **niente Docker**: il demone si mangia un quinto della
memoria disponibile. Bot e generatore girano in un virtualenv, gestiti da systemd e cron.

```bash
sudo apt-get update
sudo apt-get install -y git python3-venv python3-pip

# la cartella è tua, non di root: niente sudo con git, mai
sudo mkdir -p /opt/sfm && sudo chown "$USER:$USER" /opt/sfm
```

### La chiave per GitHub

La chiave va generata **sulla VM** e con il tuo utente (non con `sudo`: root ha un'altra
`~/.ssh`). Se l'hai già fatto, salta il `ssh-keygen`.

```bash
ls ~/.ssh/id_ed25519.pub 2>/dev/null || ssh-keygen -t ed25519 -C "sfm-vm" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub        # questa riga va nei Deploy keys del repo, con "Allow write access"
ssh -T git@github.com            # deve rispondere "Hi federicodiluca/school-feed-monitor!"
```

Se `ssh -T` dice `Permission denied (publickey)`, la chiave incollata su GitHub non è quella
della VM: ricontrolla che sia il contenuto esatto del `.pub` qui sopra.

### Il codice

```bash
git clone git@github.com:federicodiluca/school-feed-monitor.git /opt/sfm
cd /opt/sfm
python3 -m venv .venv
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

### Il bot come servizio

```bash
sudo cp scripts/sfm-bot.service /etc/systemd/system/
sudo sed -i "s/%USER%/$USER/" /etc/systemd/system/sfm-bot.service
sudo systemctl daemon-reload && sudo systemctl enable --now sfm-bot
journalctl -u sfm-bot -f          # Ctrl-C per uscire
```

Il primo avvio importa le fonti del catalogo e le legge **senza inviare notifiche**: ci mette
qualche minuto. Manda `/start` al bot per controllare che risponda.

> Se preferisci Docker (`docker compose up -d --build`) funziona comunque: metti in `.env`
> `SITE_BUILD_CMD=docker compose run --rm -T bot python -m scripts.build_site --out /usr/src/app/data/site`
> e salta il servizio systemd.

## 3. La prima pubblicazione

```bash
cd /opt/sfm
./scripts/publish_site.sh
```

Genera il sito in `data/site` e lo spinge su `gh-pages`. Se il repo era stato clonato in
HTTPS, prima: `git remote set-url origin git@github.com:federicodiluca/school-feed-monitor.git`.

## 4. Accendere GitHub Pages

*repo → Settings → Pages → Source: Deploy from a branch → branch `gh-pages`, cartella `/ (root)`.*
Dopo un minuto il sito è su `https://federicodiluca.github.io/school-feed-monitor`.

Due dettagli:

- il file `.nojekyll` (lo genera il build) evita che Pages tratti il sito come un blog Jekyll;
- il `robots.txt` che conta per Google è quello alla **radice del dominio**, cioè nel repo
  `federicodiluca.github.io`: aggiungi lì la riga
  `Sitemap: https://federicodiluca.github.io/school-feed-monitor/sitemap.xml`.

## 5. Pubblicare ogni ora

```bash
crontab -e
# sito aggiornato ogni ora, 10 minuti dopo lo scraping
10 * * * * cd /opt/sfm && ./scripts/publish_site.sh >> data/logs/publish.log 2>&1
# backup del database ogni notte alle 3 (14 giorni di copie in /opt/sfm/backup)
0 3 * * * cd /opt/sfm && sh scripts/backup.sh backup >> data/logs/backup.log 2>&1
```

Pages ricostruisce a ogni push; il limite indicativo è ~10 build all'ora, una all'ora sta
larga. Il branch `gh-pages` viene riscritto ogni volta con **un solo commit orfano**, così il
repository non cresce all'infinito.

## 6. Aggiornare il codice

```bash
cd /opt/sfm && git pull && .venv/bin/pip install -r requirements.txt
sudo systemctl restart sfm-bot
```

## Note

- **1 GB di RAM**: il bot da solo ci sta comodo. Se la VM va in affanno, alza
  `polling_minutes` in `config.json`.
- **Prova gratuita**: i 300 $ di credito durano 90 giorni; alla scadenza, se non passi a un
  account a pagamento, Google **ferma le risorse**. Segnati la data e decidi prima.
- **Scraping dagli USA**: su 112 fonti, una (USP Macerata) rifiuta le connessioni da IP esteri.
  Il watchdog la segnalerà come "in errore": è atteso, non è un guasto.
- **Il sito Flask serve ancora**: in locale (`python web.py`) è il modo più comodo per
  provare le modifiche prima di generarle; in produzione non viene esposto.
- **Se un giorno servisse un dominio**, il sito statico si sposta senza toccare la VM: cambia
  `SITE_BASE_URL`, rigenera, e punta il DNS su Pages.
