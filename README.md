# 🏫 School Feed Monitor

> Aggiornamenti dal mondo scuola (USR, USP, MIM…) filtrati per parole chiave, via Telegram ed email.

Un bot in **Python + Docker** che:

* raccoglie notizie da più siti (RSS/Feed)
* invia **alert immediati su Telegram** se trova keyword personalizzate
* genera un **report giornaliero** con le notizie del giorno
* gestisce automaticamente **log e retention**
* supporta **più utenti Telegram**, ciascuno con la propria configurazione
* memorizza le **news e i contenuti completi** su SQLite

---

## 🚀 Funzionalità principali

✅ **Polling periodico** dei feed (intervallo configurabile)  
✅ **Notifiche immediate** via Telegram su keyword specifiche  
✅ **Report giornaliero** automatico alle ore configurate  
✅ **Deduplica automatica** delle notizie già viste  
✅ **Gestione log e news** con cancellazione automatica dopo *N giorni*  
✅ **Supporto multi–utente** con SQLite  
✅ **Ricerca keyword precisa** con word boundaries (parole esatte)  
✅ **Gestione keyword avanzata** (aggiungi/rimuovi selettivamente)  
✅ **Supporto parole composte** con spazi nelle keyword  
✅ **Controllo duplicati intelligente** (case-insensitive)  
✅ **Contenuto completo** delle news memorizzato nel DB  
✅ **Comandi interattivi** con feedback dettagliato  
✅ **Fonti per utente**: ognuno sceglie quali fonti seguire  
✅ **Fonti custom** aggiunte da Telegram (RSS o pagine HTML senza feed, es. siti MIM)

---

## ⚙️ Configurazione iniziale

### 1️⃣ Crea la tua configurazione

Copia il file di esempio:

```bash
cp config.example.json config.json
```

### 2️⃣ Modifica `config.json`

Esempio base:

```json
{
  "telegram_token": "IL_TUO_TOKEN",
  "machine_name": "Server-01",
  "sites": [
    {
      "name": "USR Emilia Romagna",
      "url": "https://www.istruzioneer.gov.it/tutte-le-notizie/feed/"
    },
    {
      "name": "USR Marche",
      "url": "https://www.mim.gov.it/web/miur-usr-marche/novit%C3%A0-dall-usr-marche",
      "type": "html"
    }
  ],
  "daily_report_time": "18:00",
  "polling_minutes": 60,
  "data_retention_days": 10,
  "disable_web_page_preview": true
}
```

**Campi principali:**

* `telegram_token` → token del bot (ottenuto da [BotFather](https://core.telegram.org/bots#botfather))
* `machine_name` → nome della macchina o del container
* `sites` → fonti di base, visibili a tutti gli utenti (opzionale, altre fonti si aggiungono da Telegram). Ogni voce:
  * `name` → nome mostrato nelle notifiche e in `/sources`
  * `url` → feed RSS/Atom, oppure pagina HTML "lista notizie" se `type` è `html`
  * `type` → `rss` (default) o `html` (scraping della pagina, per i siti senza feed come quelli MIM/Liferay)
  * `default_follow` → `true` (default) seguita da tutti salvo `/unfollow`; `false` disponibile ma da attivare con `/follow`
* `daily_report_time` → orario (HH:MM) predefinito del report giornaliero (ogni utente potrà sceglierne uno proprio)
* `polling_minutes` → intervallo tra i controlli dei feed
* `data_retention_days` → giorni di conservazione di log e news
* `disable_web_page_preview` → nasconde le anteprime dei link (opzionale)

Solo `telegram_token` è obbligatorio; gli altri campi hanno un default.

**Catalogo fonti italiane** (`"catalog": "italy"`, attivo per default; `false` per disattivarlo): il bot include
automaticamente le fonti di [sfm/catalog/italy.json](sfm/catalog/italy.json) — notizie del MIM, tutti gli USR
regionali e gli USP provinciali (112 fonti verificate; poche province mancano ancora, vedi TODO.md). USR e USP sono *opt-in* (`default_follow: false`): ogni utente sceglie
la sua regione/provincia. Ogni voce ha `kind` (`usr`/`usp`/`mim`/`other`), `region` e `province`; gli stessi campi
si possono usare anche nelle `sites` di `config.json`. Per verificare che tutte le fonti siano leggibili:

```bash
python scripts/check_sources.py --catalog
```

**Variabili d'ambiente (opzionali):**

* `SFM_CONFIG` → percorso del file di configurazione (default `config.json`)
* `SFM_DB_PATH` → percorso del database SQLite (default `data/sfm.db`; un vecchio `data/checkfeed.db` viene spostato automaticamente)
* `SFM_LOG_DIR` → cartella dei log (default `data/logs`)
* `SFM_ENV_FILE` → percorso del file `.env` (default `.env`)

Le vecchie variabili `CHECKFEED_*` funzionano ancora (con un avviso) ma sono deprecate.

### 3️⃣ Email (opzionale)

Oltre a Telegram, le notifiche possono arrivare via **email**. Copia `.env.example` in `.env`
(ignorato da git: **non committare mai credenziali**) e scegli il backend con `EMAIL_BACKEND`:

* `smtp` → un server SMTP qualsiasi. Consigliato **Brevo** (piano gratuito, azienda UE):
  `SMTP_HOST=smtp-relay.brevo.com`, `SMTP_PORT=587`, `SMTP_USER`/`SMTP_PASSWORD` dal pannello *SMTP & API*
* `resend` → API di [Resend](https://resend.com) con `RESEND_API_KEY`
* `none` → disabilitato (default): le email vengono solo loggate

In tutti i casi serve `EMAIL_FROM` (mittente verificato presso il provider). Per verificare la configurazione:

```bash
python scripts/send_test_email.py tua@email.it          # alert di prova
python scripts/send_test_email.py tua@email.it digest   # report di prova
```

---

## 👥 Multi–utente con SQLite

Il bot salva gli utenti in **`data/sfm.db`**.

Ogni utente che invia `/start` viene registrato automaticamente e può:

* impostare le **proprie keyword** (`/setkeywords parola1, parola2, ...`)
* ricevere **solo le notizie rilevanti** per sé
* ricevere report e comandi personalizzati

Niente più config manuale: ogni utente Telegram ha il proprio profilo salvato in automatico.

### 📡 Fonti per utente

Le fonti vivono nel database (tabella `sources`); quelle di `config.json` vengono sincronizzate a ogni avvio.

* Di default ogni utente segue **tutte** le fonti di `config.json`; con `/sources` compare un pulsante per fonte: un tocco la attiva/disattiva (in alternativa `/follow n` e `/unfollow n` con il numero mostrato in elenco).
* Con `/addsource URL [nome]` un utente aggiunge una fonte nuova. Il bot verifica che sia leggibile:
  1. è un **feed RSS/Atom**? → usato direttamente;
  2. è una **pagina HTML che dichiara un feed** (`<link rel="alternate" type="application/rss+xml">`, tipico di WordPress)? → usa quel feed;
  3. altrimenti prova lo **scraping** della pagina come lista di notizie (`<article>` o titoli `h2/h3` con link, data italiana come "11 settembre 2026") — è il caso dei siti MIM/Liferay senza RSS;
  4. se non trova almeno 3 notizie, rifiuta la fonte.
* La fonte custom è seguita subito da chi l'ha aggiunta; gli altri la vedono in `/sources` e possono attivarla con `/follow`.
* Alla prima lettura le notizie già pubblicate vengono salvate **senza notifiche**, per non ricevere una raffica di alert.
* Notifiche, report giornaliero e `/latest` includono solo le fonti che l'utente segue.

---

## 💬 Comandi disponibili

| Comando                                     | Descrizione                                           |
| ------------------------------------------- | ----------------------------------------------------- |
| `/start`                                    | Registra l'utente e mostra informazioni complete      |
| `/stop`                                     | Sospende le notifiche per questo utente               |
| `/setkeywords parola1, parola2, COMPOSTA`   | **Aggiunge** parole chiave (separate da virgole)      |
| `/removekeywords parola1, parola2, ...`     | **Rimuove** keyword specifiche dall'elenco            |
| `/keywords`                                 | Mostra le tue keyword attualmente attive              |
| `/fetch`                                    | Aggiorna manualmente i feed                           |
| `/report`                                   | Genera e invia il report giornaliero                  |
| `/latest [n]`                               | Mostra le ultime *n* notizie (default: 5, max 50)     |
| `/sources`                                  | Elenco fonti con pulsanti ✅/❌ per attivarle/disattivarle |
| `/follow 1, 3` / `/follow all`              | Segui le fonti indicate                               |
| `/unfollow 2` / `/unfollow all`             | Smetti di seguire le fonti indicate                   |
| `/addsource URL [nome]`                     | Aggiunge una fonte (RSS o pagina notizie) con verifica |
| `/removesource n`                           | Rimuove una fonte aggiunta da te                      |
| `/commands` (o `/help`)                     | Elenco rapido di tutti i comandi disponibili          |

### 📡 **Esempio: aggiungere fonti**

```
/addsource https://fc.istruzioneer.gov.it/tutte-le-notizie/
✅ Fonte aggiunta: Ufficio VII – sede di Forlì-Cesena (n. 4)
📎 Tipo: feed RSS
🔗 https://fc.istruzioneer.gov.it/feed/
📰 Notizie trovate: 10 (salvate 10 nuove, senza notifica)

/addsource https://www.mim.gov.it/web/miur-usr-marche/novit%C3%A0-dall-usr-marche USR Marche
✅ Fonte aggiunta: USR Marche (n. 5)
📎 Tipo: pagina HTML (scraping)

/unfollow 2
✅ Non segui più: USP Rimini
```

### 🔍 **Ricerca keyword migliorata**
- Le keyword ora usano **ricerca esatta** delle parole
- "Rowe" **non** viene più trovato in "Crowe"  
- "Demir" **non** viene più trovato in "Ademir"
- Supporto per **parole composte** con spazi

### 🎯 **Gestione keyword intelligente**
- `/setkeywords` **aggiunge** alle keyword esistenti (non le sostituisce)
- `/removekeywords` **rimuove** solo quelle specificate  
- **Controllo duplicati** automatico (case-insensitive)
- Feedback dettagliato su operazioni eseguite

All'avvio, il bot invia automaticamente un messaggio di **recap con tutti i comandi e i feed monitorati**.

---

## 🌐 Web

Il layer web (Flask, pagine renderizzate lato server) gira come **processo separato** sullo stesso database:

```bash
pip install -r requirements.txt
# in .env: SECRET_KEY (obbligatoria), APP_BASE_URL (per canonical/sitemap/link nelle email)
python web.py            # sviluppo: http://127.0.0.1:5000  (FLASK_DEBUG=1 per l'autoreload)
python scripts/fetch_now.py   # riempie il DB con le notizie di tutte le fonti, senza notifiche (il sito non scarica da solo)
```

Pagine: home, registrazione (email + password, consenso privacy con versione e data), accesso, account
(cambio password, **export dei dati**, **revoca del consenso**, **cancellazione definitiva**), privacy e termini.
`robots.txt` e `sitemap.xml` sono generati; le pagine riservate sono `noindex`. Tema chiaro/scuro automatico con toggle.

**Dove insegni?** (`/preferenze/area`, proposto alla registrazione): scegli regione e province e segui in automatico
MIM + USR + USP giusti. **Preferenze** (`/preferenze`): fonti raggruppate per regione con ricerca istantanea, parole chiave, canali (email/Telegram), frequenza (solo riepilogo
oppure riepilogo + avvisi immediati), orario del riepilogo, aggiunta di nuove fonti con verifica.
**Telegram**: dalla pagina preferenze si genera un codice e lo si invia al bot con `/link CODICE`; se quella chat
usava già il bot, parole chiave e fonti vengono unite all'account web.
**Verifica email (double opt-in)**: alla registrazione arriva un link di conferma (valido 48 ore); finché l'indirizzo
non è confermato il canale email resta sospeso (gli account creati con Google sono già verificati).
**Accedi con Google**: opzionale, attivo se `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` sono impostati
(anche in questo caso il consenso privacy viene chiesto prima di creare l'account).

---

## 🐶 Watchdog

Ogni lettura aggiorna lo stato di salute della fonte (`source_health`); i job schedulati lasciano un heartbeat (`job_runs`).
Ogni 30 minuti il watchdog avvisa l'amministratore (`ADMIN_TELEGRAM_ID` e/o `ADMIN_EMAIL` in `.env`) **una sola volta** quando:

* una fonte fallisce da `WATCHDOG_SOURCE_FAILURES` letture consecutive (default 3);
* una fonte non produce notizie nuove da `WATCHDOG_SOURCE_SILENCE_HOURS` ore (default 72: probabile cambio di struttura della pagina);
* il fetch non gira da `WATCHDOG_JOB_STALE_MINUTES` minuti (default 3 × `polling_minutes`) o l'ultima esecuzione di un job è fallita.

Quando il problema rientra arriva un secondo avviso. In `/sources` le fonti in errore sono marcate con ⚠️.
Un watchdog interno non può accorgersi se muore l'intero processo: per quello imposta `HEALTHCHECK_PING_URL`
(es. [healthchecks.io](https://healthchecks.io), gratuito) e il bot lo "pinga" a ogni fetch riuscito.

---

## 🐳 Esecuzione con Docker

1. Clona il repository

2. Modifica `config.json` secondo le tue esigenze

3. Avvia il container:

   ```bash
   docker-compose up -d --build
   ```

I dati persistono in `data/`, inclusi log, news e database utenti.
`config.json` viene montato in sola lettura nel container: dopo una modifica basta `docker-compose restart`, senza rebuild.

---

## 🧪 Test

```bash
python -m venv .venv
.venv/Scripts/activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

I test girano su un database e una configurazione temporanei e non effettuano alcuna chiamata di rete.

---

## 📊 Output di esempio

**🔔 Notifica immediata**

```
🚨 Nuova notizia da USR Emilia Romagna
Concorso docenti AM2A – graduatoria aggiornata
https://www.istruzioneer.gov.it/...
```

**💬 Esempi di comandi**

```
/setkeywords scuola, docenti, GRADUATORIA FINALE
✅ Keyword aggiunte: scuola, docenti, GRADUATORIA FINALE
📝 Totale keyword: 3

/removekeywords docenti
✅ Keyword rimosse: docenti  
📝 Keyword rimanenti: scuola, GRADUATORIA FINALE

/keywords
📝 Le tue keyword attive (2):
• scuola
• GRADUATORIA FINALE
```

**🗓️ Report giornaliero**

```
📢 Report del 05/10/2025 — 3 notizie trovate

🗞️ USR Emilia Romagna — 05/10/2025 10:14
Titolo 1
Anteprima del contenuto...
```

**🧹 Log giornalieri**

```
data/logs/2025-10-05.log
```

---

## 🔧 Manutenzione automatica

* 🧹 Pulizia log e notizie vecchie ogni giorno
* 💾 Dati persistenti in `data/`
* 🧩 Deduplica feed per evitare duplicati
* 📁 Database in `data/sfm.db`

---

## 📜 Licenza

**GNU Affero General Public License v3.0 (AGPL-3.0)** — vedi [LICENSE](LICENSE).

Puoi usare, studiare, modificare e ridistribuire il codice; se lo modifichi e lo offri come servizio in rete,
devi rendere disponibile il codice sorgente delle tue modifiche sotto la stessa licenza.
Per usi commerciali con termini diversi, contatta l'autore.

Le versioni pubblicate prima del passaggio ad AGPL (fino al commit `a61119d`) restano disponibili sotto licenza MIT.

---

## 💪 Contributors

<a href="https://github.com/federicodiluca/school-feed-monitor/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=federicodiluca/school-feed-monitor" />
</a>
