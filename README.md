# School Feed Monitor

Le notizie del mondo scuola — Ministero, Uffici Scolastici Regionali e Provinciali — raccolte
da oltre cento siti, filtrate per le fonti e le parole chiave che scegli tu, e portate dove
guardi: un sito da consultare e un bot Telegram che ti avvisa.

Sito: **<https://federicodiluca.github.io/school-feed-monitor>** · Licenza: **AGPL-3.0**

Nasce da un problema concreto: chi lavora nella scuola deve tenere d'occhio l'USP dove
insegna, magari quello dove punta al trasferimento, l'USR e il Ministero — ognuno con il suo
sito, i suoi tempi e la sua grafica. Questo programma li legge al posto tuo.

## Com'è fatto

```
   macchina di servizio (una VM qualsiasi, in Europa)        GitHub              browser
   ┌──────────────────────────────────────────────┐   ┌──────────────────┐   ┌─────────────┐
   │ main.py      bot Telegram + scraping orario  │   │ branch gh-pages  │   │ sito        │
   │ sfm/         nucleo: fonti, parsing, match   │──→│ (sito generato)  │──→│ + cookie    │
   │ web/         il sito (Flask, server-side)    │   │ GitHub Pages     │   │   del       │
   │ scripts/     generatore + pubblicazione      │   └──────────────────┘   │   visitatore│
   │ data/sfm.db  SQLite                          │                          └─────────────┘
   └──────────────────────────────────────────────┘
```

Tre pezzi, un solo codice:

- **il bot** (`main.py`) legge le fonti ogni ora, salva le notizie nuove, avvisa subito chi ha
  una parola chiave che corrisponde e manda un riepilogo giornaliero;
- **il sito** (`web/`) è un'app Flask renderizzata lato server — in sviluppo la apri e la provi
  come un sito normale;
- **il generatore** (`scripts/build_site.py`) congela quelle stesse pagine in HTML statico più
  due file JSON, e `scripts/publish_site.sh` li pubblica su GitHub Pages.

In produzione la macchina **non riceve connessioni**: nessuna porta aperta, nessun dominio,
nessun certificato da rinnovare. Pubblica e basta.

## Niente account, niente dati dei visitatori

Il sito non ha registrazione e non salva nulla di chi lo visita: le fonti e le parole chiave
scelte restano in **due cookie tecnici** nel browser (`sfm_fonti`, `sfm_parole`). Per portare
la stessa configurazione sul bot non serve un account: la configurazione viaggia **dentro il
link** di Telegram (`sfm/config_link.py`), impacchettata in meno di 64 caratteri.

Gli unici dati personali trattati sono quelli di chi usa il bot: identificativo della chat,
fonti e parole chiave. Il bot risponde a `/dati` (cosa è memorizzato) e `/cancellami`
(cancellazione immediata). Dettagli in [docs/registro-trattamenti.md](docs/registro-trattamenti.md).

## Le fonti

`sfm/catalog/italy.json` contiene **113 fonti verificate una per una**: MIM, 18 USR e i siti
degli uffici provinciali, ognuna con regione e provincia. Il configuratore propone tutte le
**107 province italiane**: per quelle senza un ufficio con sito proprio si ricade sulle
notizie regionali dell'USR, e la pagina lo dice.

`config.json` può aggiungere fonti sue. Se una coincide con una del catalogo — stesso URL o
stesso nome — è considerata la stessa fonte: tiene il suo URL ed eredita regione, provincia e
il fatto di essere opzionale.

Il catalogo si ri-verifica da solo ogni settimana (`.github/workflows/check-sources.yml`), e a
mano con:

```bash
python scripts/check_sources.py --catalog
```

## Provare in locale

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
cp config.example.json config.json      # token del bot (oppure lascialo finto: il sito parte lo stesso)
cp .env.example .env                    # SECRET_KEY, vedi dentro

python web.py                           # il sito su http://127.0.0.1:5000
python main.py                          # il bot (serve un token vero)
python -m scripts.build_site --out site --base-url http://localhost:8000   # il sito statico
```

Per riempire il database senza aspettare lo scheduler: `python scripts/fetch_now.py`.

## Comandi del bot

| Comando | Cosa fa |
|---|---|
| `/start` | registra l'utente e mostra fonti e impostazioni |
| `/start CODICE` | applica la configurazione creata sul sito |
| `/stop` | sospende le notifiche |
| `/setkeywords a, b` · `/removekeywords a` · `/keywords` | gestione delle parole chiave |
| `/sources` · `/follow n, m` · `/unfollow n, m` | quali fonti seguire |
| `/addsource URL [nome]` · `/removesource n` | fonti aggiunte da te |
| `/latest [n]` · `/fetch` · `/report` | ultime notizie, aggiornamento manuale, riepilogo |
| `/dati` · `/cancellami` | cosa conservo su di te · cancella tutto |

## Test

```bash
.venv/bin/python -m pytest -q          # ~270 test
npm install                            # facoltativo: jsdom, per la prova del sito nel browser finto
```

La suite non tocca mai la rete (le richieste HTTP sono bloccate nei test) e usa un database
temporaneo. Oltre ai test Python, `tests/site_check.js` carica il sito generato in un browser
finto e verifica filtri, configuratore, cookie e link a Telegram: se `node` e `jsdom` non ci
sono, quel test si salta.

## Struttura

| Cartella | Cosa c'è |
|---|---|
| `sfm/` | il nucleo: lettura fonti, parsing, deduplica, match delle parole chiave, digest, watchdog, catalogo |
| `web/` | il sito Flask: notizie, configuratore, pagine legali, SEO |
| `scripts/` | generazione e pubblicazione del sito, verifica del catalogo, backup, servizio systemd |
| `deploy/eu-proxy/` | ponte per leggere le fonti che bloccano gli IP esteri (serve solo se la macchina non è in Europa) |
| `tests/` | la suite, con il controllo del sito statico in jsdom |
| `docs/` | deploy e registro dei trattamenti |

## Messa in produzione

Guida completa: **[docs/deploy.md](docs/deploy.md)** — vale per qualunque macchina, con o senza
Docker. In sintesi: la VM fa girare il bot, ogni ora genera il sito e lo spinge sul branch
`gh-pages`, GitHub Pages lo serve in HTTPS.

Un'avvertenza che conta più di quanto sembri: **tienila in Europa**. Diversi siti
istituzionali (`istruzione.calabria.it`, `uspmc.sinp.net`) lasciano cadere le connessioni
dagli indirizzi esteri; da un server americano quelle fonti sono irraggiungibili e serve il
ponte in `deploy/eu-proxy/`.

## Configurazione

`config.json` (token, fonti, orari) e `.env` (chiavi e URL) non vanno mai committati: sono in
`.gitignore`, e gli esempi sono in `config.example.json` e `.env.example`. Le variabili
d'ambiente sono documentate lì dentro, una per una.

## Contribuire

Segnalazioni e proposte: [issue su GitHub](https://github.com/federicodiluca/school-feed-monitor/issues).
Se conosci una fonte che manca — un USP con un sito che non abbiamo — è il contributo più
utile: apri una issue con l'URL della pagina delle notizie.

Grazie a Fabio Di Giuseppe per i contributi al bot (vedi [NOTICE](NOTICE)).
