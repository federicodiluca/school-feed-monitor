# Deploy su Google Cloud (free tier) — versione "utility"

Obiettivo: bot Telegram + sito raggiungibile via `http://IP-DELLA-VM`, gratis, in ~20 minuti.
Il free tier di Google copre **una** VM `e2-micro` in `us-west1`, `us-central1` o `us-east1`
(30 GB di disco standard). Sono gli Stati Uniti: è scritto nella pagina privacy del sito.

## 1. Creare la VM

Console Google Cloud → *Compute Engine → VM instances → Create instance*:

| Campo | Valore |
|---|---|
| Region / Zone | `us-central1` (una qualsiasi delle tre del free tier) |
| Machine type | `e2-micro` (serie E2, "shared core") |
| Boot disk | Debian 12, disco **Standard persistent disk** 30 GB |
| Firewall | spunta **Allow HTTP traffic** |

Poi *Network interfaces → External IPv4 address → Reserve static external IP*: così l'indirizzo
non cambia a ogni riavvio (gratuito finché la VM è accesa).

## 2. Preparare la macchina

Dalla console, pulsante **SSH**:

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin git
sudo usermod -aG docker $USER && exit      # poi rientra con SSH

git clone https://github.com/federicodiluca/school-feed-monitor.git /opt/sfm
cd /opt/sfm
cp config.example.json config.json          # metti il token del bot
cp .env.example .env
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env
nano .env                                   # vedi sotto
```

`.env` minimo:

```ini
SECRET_KEY=...                       # generata sopra
APP_BASE_URL=http://34.56.78.90      # l'IP statico della VM
TELEGRAM_BOT_USERNAME=IlTuoBot       # senza @, per i link "apri il bot"
ADMIN_TELEGRAM_ID=121822622          # per gli avvisi del watchdog
CONTACT_EMAIL=schoolfeedmonitor@gmail.com
```

## 3. Avviare

```bash
docker compose up -d --build
docker compose logs -f bot        # Ctrl-C per uscire dai log
```

Il sito è su `http://IP-DELLA-VM`. Il primo avvio importa le 112 fonti del catalogo e le legge
**senza inviare notifiche** (ci mette qualche minuto).

## 4. Backup

```bash
crontab -e
# ogni notte alle 3, tiene 14 giorni di copie in /opt/sfm/backup
0 3 * * * cd /opt/sfm && sh scripts/backup.sh backup >> data/logs/backup.log 2>&1
```
Per portarti via una copia: `gcloud compute scp sfm-VM:/opt/sfm/backup/ultimo.db.gz .`

## 5. Aggiornare

```bash
cd /opt/sfm && git pull && docker compose up -d --build
```

## Note

- **1 GB di RAM**: bastano bot + web con 2 worker. Se la VM va in affanno, abbassa a 1 worker
  in `docker-compose.yml` e alza `polling_minutes` in `config.json`.
- **HTTPS e PWA**: servono un hostname. Il modo gratuito è
  [sslip.io](https://sslip.io): l'indirizzo `34-56-78-90.sslip.io` punta già al tuo IP. Basta
  aggiungere Caddy davanti al servizio `web` e mettere quell'hostname in `APP_BASE_URL`.
  Senza HTTPS il sito funziona lo stesso, ma il browser lo segna "non sicuro" e l'app non è
  installabile.
- **Scraping dagli USA**: su 112 fonti, una (USP Macerata) rifiuta le connessioni da IP esteri.
  Il watchdog la segnalerà come "in errore": è atteso, non è un guasto.
