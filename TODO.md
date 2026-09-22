# TODO — School Feed Monitor

**Dove siamo (23/09/2026).** In produzione c'è la versione *utility*: bot Telegram + sito
statico su GitHub Pages, **senza account e senza dati dei visitatori**. La macchina è la VM
OCI di Milano (Docker); il sito è <https://federicodiluca.github.io/school-feed-monitor>,
pubblicato dal branch `gh-pages` con `scripts/publish_site.sh`.

La piattaforma completa (account, email, login Google, digest via email, verifica email,
reset password) **non è stata buttata**: vive nel branch `full-platform` e nella
[issue #2](https://github.com/federicodiluca/school-feed-monitor/issues/2). Questo file
tiene solo quello che riguarda la versione in produzione; il resto è lì.

---

## Da fare tu (fuori dal repo)

- [ ] **SEO — sitemap dichiarata alla radice del dominio.** Il sito sta in una sottocartella,
  quindi il `robots.txt` che Google legge è quello del repo `federicodiluca.github.io`:
  aggiungere lì `Sitemap: https://federicodiluca.github.io/school-feed-monitor/sitemap.xml`
- [ ] **Google Search Console**: registrare la proprietà come *prefisso URL*
  (`https://federicodiluca.github.io/school-feed-monitor/`) e inviare la sitemap
- [ ] **Cron sulla VM**: pubblicazione oraria del sito + backup notturno (righe in
  [docs/deploy.md](docs/deploy.md#7-automatismi))
- [ ] **Chiudere Google Cloud**: dopo aver messo al sicuro il database, arrestare il progetto
  (IAM → Impostazioni → Arresta). Ricorda che la prova gratuita scade il **12/12/2026**
- [ ] **Privacy e termini**: farli rileggere a una persona competente prima di dare il sito in
  giro sul serio
- [ ] **Monitor esterno** (facoltativo, gratis): `HEALTHCHECK_PING_URL` su healthchecks.io, così
  se la VM muore lo sai senza accorgertene dai messaggi mancanti

## Da fare sul codice

- [ ] **Fonti ancora mancanti** (10 province su 107 senza ufficio provinciale nel catalogo).
  Il configuratore le mostra comunque e ricadono sull'USR, ma una fonte dedicata sarebbe meglio.
  Motivo per ciascuna, verificato il 22-23/09/2026:
  - Benevento: il sito risponde 403 a qualunque client automatico (serve un browser vero)
  - Salerno: `uat-salerno.it` in errore 502 da giorni — **da riprovare**
  - Lecce: `usplecce.it` esiste ma non ha una lista di notizie leggibile
  - Viterbo: nessun dominio raggiungibile (`provveditoratostudiviterbo.it` non ha lista notizie)
  - Gorizia, Pordenone, Udine: il FVG pubblica solo a livello regionale (già nel catalogo)
  - Trento, Bolzano, Aosta: ordinamenti autonomi, nessun USP; servirebbero fonti ad hoc
- [ ] **Date "di comodo"**: le fonti HTML senza data pubblicata ricevono l'ora di raccolta, e
  così scavalcano notizie più rilevanti nell'ordinamento. Valutare di conservare la data solo
  quando è davvero nella pagina e ordinare a parità per fonte
- [ ] **Archivio sul sito statico**: oggi il browser filtra le ultime 1200 notizie (90 giorni).
  Oltre non si va: se serve, generare pagine per mese o per fonte+anno
- [ ] **Icona vera**: il set PNG/apple-touch/manifest c'è, ma l'icona è provvisoria
- [ ] **Accessibilità**: giro di verifica con tastiera e screen reader sulle pagine principali
- [ ] Ricontrollare ogni tanto il catalogo: `python scripts/check_sources.py --catalog`
  (il controllo settimanale in CI lo fa già, ma le fonti "recuperabili" sopra vanno riprovate a mano)

## Fatto nella versione utility (per memoria)

- [x] Sito senza account: preferenze in due cookie tecnici, nessun dato del visitatore sul server
- [x] Configuratore in un unico form: aree → fonti → parole chiave → «Salva e porta su Telegram»
- [x] Configurazione dentro il link di `/start` (`sfm/config_link.py`), con la stessa codifica
      in Python e in JavaScript, verificata da un test che confronta le due
- [x] Generatore del sito statico + pubblicazione su `gh-pages` con un commit orfano a giro
- [x] PWA: manifest, service worker, pagina offline
- [x] Comandi GDPR sul bot: `/dati`, `/cancellami`; registro dei trattamenti aggiornato
- [x] Catalogo: 113 fonti verificate; **tutte le 107 province** offerte nel configuratore
- [x] `config.json` non sovrascrive più i metadati del catalogo (era la causa delle fonti
      fuori regione e di quelle "seguite da tutti")
- [x] SEO: pagina `/fonti` (113 link interni), JSON-LD, `lastmod` nella sitemap, meta description
- [x] Chi blocca il bot viene sospeso invece di essere ritentato a ogni notizia
- [x] Ponte europeo (`deploy/eu-proxy/`) per le fonti che rifiutano gli IP esteri — non serve
      finché la macchina sta in Italia, ma è pronto
- [x] Licenza AGPL-3.0 con consenso di tutti i contributor
- [x] Watchdog: fonti in errore/silenziose, job fermi, riepilogo settimanale all'admin

## Monetizzazione (piano al 20/09/2026, invariato)

In ordine di priorità: prima le cose che non richiedono traffico né nodi fiscali nuovi.

1. [ ] **Vetrina dei propri servizi** (formazione docenti, sviluppo web, ripetizioni): footer e
   pagina "chi c'è dietro". Costo zero, nessun adempimento in più
2. [ ] **Inserzioni dirette e mirate** — uno slot nelle pagine pubbliche e una riga nel digest,
   vendute a mano a chi parla al personale scolastico: enti di formazione, percorsi 30/60 CFU e
   TFA sostegno, editori di manuali per concorsi, certificazioni. **Soglia per iniziare**: da
   fissare (indicativamente ≥1.000 iscritti attivi o ≥10.000 pagine viste al mese)
3. [ ] **Affiliazione mirata** su manuali e corsi, con link puliti e dichiarati
4. [ ] **Pubblicità di rete (AdSense o simili)** — solo con traffico organico consistente:
   impone banner di consenso e profilazione, contro il principio "niente tracker di terze parti"
5. [ ] Donazioni (Ko-fi/PayPal): trascurabile, ma gratis da mettere

- [ ] **Nodo da sciogliere prima del primo incasso — incompatibilità del pubblico impiego.**
  Per un docente di ruolo a tempo pieno l'attività commerciale è vietata e gli incarichi
  retribuiti vanno autorizzati dal dirigente (art. 53 D.lgs 165/2001, art. 508 D.lgs 297/1994);
  opere dell'ingegno e prestazioni occasionali autorizzate sono le vie sicure. Prima della
  prima ricevuta: parlarne con il dirigente e con un commercialista

## Fuori scope (deciso)

- Feature "interpelli" / bandi di supplenza (terreno dei competitor)
- Billing / pagamenti
- Abbonamenti o freemium (implicano partita IVA e attività continuativa)
- Account e email sul sito: sono nel branch `full-platform`, non in produzione
