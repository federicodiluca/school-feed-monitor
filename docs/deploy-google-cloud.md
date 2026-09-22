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
| Firewall | non serve niente: nessun traffico in entrata |
| Network interfaces | External IPv4: **None** |

Senza IP pubblico servono due cose:

- **uscire verso internet** (scraping, Telegram, push su GitHub): *VPC network → Cloud NAT →
  crea un gateway* nella stessa regione, con "Source: primary IP ranges of all subnets".
- **entrare in SSH**: passa da IAP. Una sola volta, *VPC network → Firewall → Create*:
  direzione *Ingress*, sorgente `35.235.240.0/20`, porta TCP `22`, target: tutte le istanze.
  Poi dal tuo PC `gcloud compute ssh sfm-vm --tunnel-through-iap` (oppure il pulsante **SSH**
  della console, che usa IAP da solo quando non c'è IP pubblico).

> **Costi.** Il free tier copre la VM e il disco, non la rete: Cloud NAT è circa 1 $/mese di
> gateway più ~0,045 $/GB di traffico processato (lo scraping orario di 112 fonti sta sotto i
> 25 GB/mese). È più o meno quanto costerebbe tenere un IPv4 pubblico. Metti comunque un budget
> di 1 € con avviso al 100% in *Billing → Budgets & alerts*.

## 2. Preparare la macchina

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin git
sudo usermod -aG docker $USER && exit      # poi rientra

git clone https://github.com/federicodiluca/school-feed-monitor.git /opt/sfm
cd /opt/sfm
cp config.example.json config.json          # token del bot, fonti, orari
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
SITE_BUILD_CMD=docker compose run --rm -T bot python -m scripts.build_site --out /usr/src/app/data/site
SITE_OUT=data/site
```

Avvio del bot:

```bash
docker compose up -d --build
docker compose logs -f bot        # Ctrl-C per uscire
```

Il primo avvio importa le fonti del catalogo e le legge **senza inviare notifiche**.

## 3. Il push su GitHub senza password

Sulla VM:

```bash
ssh-keygen -t ed25519 -C "sfm-vm" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

Su GitHub: *repo → Settings → Deploy keys → Add deploy key*, incolla la chiave e **spunta
"Allow write access"**. Poi, sulla VM:

```bash
cd /opt/sfm
git remote set-url origin git@github.com:federicodiluca/school-feed-monitor.git
ssh -T git@github.com          # accetta l'host la prima volta
./scripts/publish_site.sh      # prima pubblicazione
```

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
cd /opt/sfm && git pull && docker compose up -d --build
```

## Note

- **1 GB di RAM**: il bot da solo ci sta comodo. Se la VM va in affanno, alza
  `polling_minutes` in `config.json`.
- **Scraping dagli USA**: su 112 fonti, una (USP Macerata) rifiuta le connessioni da IP esteri.
  Il watchdog la segnalerà come "in errore": è atteso, non è un guasto.
- **Il sito Flask serve ancora**: in locale (`python web.py`) è il modo più comodo per
  provare le modifiche prima di generarle; in produzione non viene esposto.
- **Se un giorno servisse un dominio**, il sito statico si sposta senza toccare la VM: cambia
  `SITE_BASE_URL`, rigenera, e punta il DNS su Pages.
