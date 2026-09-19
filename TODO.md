# TODO — evoluzione web + email (branch `webapp`)

Posizionamento: **aggiornamenti generali dal mondo scuola** (USR, USP, MIM, normativa, graduatorie,
trasferimenti, classi di concorso) filtrati per parole chiave e fonti scelte dall'utente.
Differenziatori: **doppio canale** (Telegram + email) e **scelta della frequenza** (digest giornaliero
di default, alert immediato opzionale).

## Step MVP

- [x] 1. Refactor core/adapter: `matching` + `notifier` + `channels/telegram_channel` (`7b9bb95`)
- [x] 2. Modello dati multi-canale/multi-frequenza + migrazioni versionate + `deliveries` (`6ef66c4`)
- [x] 3. Canale email — backend intercambiabile: **API Resend** oppure **server SMTP** (env, mai segreti nel repo) (`574274a`)
- [x] 4. Digest giornaliero (batch, orario per utente) + alert istantaneo dopo ogni ciclo di fetch, dedup su `deliveries`
- [x] 5. Isolamento fallimenti per fonte + watchdog (fonte muta da troppe ore / job fermo → avviso all'admin)
- [x] 6a. Web base (Flask SSR): registrazione, login, account, consenso/revoca/export/cancellazione (GDPR), SEO base, tema chiaro/scuro
- [x] 6b. Preferenze (fonti, keyword, canali, frequenza, orario), aggiunta fonti, collegamento Telegram (`/link`), login Google, landing pubblica
- [x] 6c. Onboarding "Dove insegni?" con più regioni (dove insegni + dove miri) e province per regione; fonti raggruppate per area con ricerca
- [x] 7a. Pagine notizie: `/notizie` pubblica con filtri e pagine per fonte (SEO), `/le-mie-notizie` con recap per giorno
- [x] 7b. Restyling UI — design system a token (chiaro/scuro), hero con anteprima, card, form e filtri coerenti (da rifinire su feedback)

## Requisiti trasversali (richiesti esplicitamente)

- [ ] **SEO** — priorità altissima: SSR, `<title>`/meta description/OpenGraph, canonical, `sitemap.xml`, `robots.txt`, URL parlanti, HTML semantico, pagine pubbliche indicizzabili
- [x] Licenza AGPL-3.0: consenso al rilicenziamento ricevuto da tutti i contributor (Fabio, 14/09/2026)
- [ ] **GDPR — nessun rischio**: privacy policy e termini, consenso esplicito con timestamp e versione, **revoca dei consensi** dall'area utente, export ed eliminazione dell'account (diritto all'oblio), minimizzazione dati, registro trattamenti, provider email/hosting in UE dove possibile, niente tracker di terze parti senza consenso
- [x] **Login Google** (OAuth 2.0 / OpenID Connect) oltre a email+password — serve creare il client nella Google Cloud Console
- [x] **Server SMTP** come alternativa all'API Resend per l'invio email (in uso con Brevo)
- [x] **Tema chiaro/scuro** (rispetta `prefers-color-scheme`, toggle manuale)
- [ ] **Icona app e favicon** — per ora favicon SVG provvisoria; manca il set completo (PNG, apple-touch-icon, manifest) con un'icona vera

## Dopo l'MVP

- [ ] **Catalogo completo fonti italiane — requisito di base prima dell'apertura al pubblico** — stato al 19/09/2026: **112/112 fonti verificate** = MIM (2) + **18/18 USR** + **91 USP** (~97 province su 107). Non recuperabili al momento, con motivo: Benevento (pagina anti-bot: serve un browser), Salerno (elenco caricato via JavaScript), Caserta (sito nuovo con 1 sola notizia), Lecce (solo archivio documenti senza date), Viterbo (sito in errore), UAT Udine/Gorizia/Pordenone (liste vuote lato server; le notizie passano dall'USR FVG), Trentino-Alto Adige e Valle d'Aosta (nessun USR). Da ricontrollare ogni tanto con `scripts/check_sources.py`
- [x] Verifica email (double opt-in) prima di attivare il canale email
- [ ] Reset password ("password dimenticata") via email — tabella token già pronta
- [ ] Pubblicità in pagina (solo quando ci sarà trazione)
- [ ] Deploy (Hetzner + Coolify valutato; oppure free tier Google)
- [ ] **Database**: SQLite (WAL) va bene finché bot e web stanno sullo stesso host con disco persistente (VPS/Coolify). Se l'hosting è serverless o multi-host → Postgres, oppure Litestream/Turso per replicare SQLite. Decidere insieme all'hosting; nel frattempo tenere l'SQL specifico SQLite concentrato in `sfm/db*.py`
- [x] Rename del repo → `school-feed-monitor` (fatto)
- [x] Rename degli identificatori interni: `SFM_*` (le `CHECKFEED_*` restano lette con avviso), `data/sfm.db` (spostamento automatico), package `sfm/`, container `sfm-bot` (19/09/2026)

## Fuori scope (deciso)

- Feature "interpelli" / bandi di supplenza (terreno dei competitor)
- Billing / pagamenti
