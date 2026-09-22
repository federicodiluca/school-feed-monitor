# School Feed Monitor — sito pubblicato

⚠️ **Questo branch è generato: non modificarlo a mano.** Viene riscritto per intero a ogni
pubblicazione con un `git push --force`, quindi qualunque modifica fatta qui sparisce al giro
successivo (di solito entro un'ora).

Il sito è <https://federicodiluca.github.io/school-feed-monitor>, servito da GitHub Pages a
partire da questo branch (Settings → Pages → branch `gh-pages`, cartella `/ (root)`).

## Da dove arriva

Il codice sta sul branch **`main`**: <https://github.com/federicodiluca/school-feed-monitor>

Sulla macchina di servizio, ogni ora:

1. `scripts/build_site.py` congela le pagine del sito Flask in HTML statico e scrive i due
   file JSON che il browser usa per filtrare (`data/news.json`, `data/sources.json`);
2. `scripts/publish_site.sh` crea un **commit orfano** con il risultato e lo spinge qui.

Il branch resta lungo un commit solo: è contenuto rigenerabile, la sua storia non serve a
nessuno e così il repository non si gonfia di 8.760 commit all'anno.

## Cosa c'è dentro

| | |
|---|---|
| `index.html`, `notizie/`, `configura/`, … | le pagine, già renderizzate (contenuto indicizzabile) |
| `notizie/fonte/<id>/<nome>/` | una pagina per ciascuna fonte |
| `data/news.json` | le notizie recenti, che il browser filtra senza chiamare nessun server |
| `data/sources.json` | l'elenco delle fonti con regione, provincia e posizione nel catalogo |
| `static/` | CSS, icone, `app.js` (tutta la logica lato browser) |
| `sw.js`, `static/site.webmanifest` | il sito è installabile come app (PWA) |
| `.nojekyll` | dice a Pages di servire i file così come sono |

## Se qualcosa non va

Una modifica al sito non si fa qui: si fa su `main` e poi si ripubblica. Per rigenerare
subito, sulla macchina di servizio:

```bash
cd /opt/sfm && git pull && ./scripts/publish_site.sh
```

Il sito non raccoglie niente di chi lo visita: le scelte restano in due cookie tecnici nel
browser. Vedi la pagina [privacy](https://federicodiluca.github.io/school-feed-monitor/privacy).
