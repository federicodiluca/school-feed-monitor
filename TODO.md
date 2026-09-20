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
- [ ] **GDPR — nessun rischio** — stato al 20/09/2026: ✅ informativa (titolare, dati, basi giuridiche, destinatari incl. Brevo/Google/Telegram, conservazione, diritti, breach, minori), termini con esclusione di responsabilità, consenso con versione+data e ri-consenso, revoca, export JSON, cancellazione definitiva, double opt-in, solo cookie tecnico (niente banner), nessuna risorsa di terze parti (test automatico). ⏳ Prima dell'apertura: (a) inserire hosting/paese nell'informativa; (b) far rileggere privacy e termini a una persona competente; (c) attivare HTTPS e rotazione dei log del server (≤30 giorni) al deploy; (d) registro dei trattamenti minimale (un documento con: finalità, categorie di dati, destinatari, conservazione) — non obbligatorio per un titolare persona fisica con trattamento occasionale, ma ~30 minuti di lavoro e mette al riparo
- [x] Pagina "Chi siamo e contatti" (`/chi-siamo`), email pubblica configurabile (`CONTACT_EMAIL`)
- [x] Disclaimer/esclusione di responsabilità nei Termini (§3) + riga nel footer di ogni pagina
- [x] **Login Google** (OAuth 2.0 / OpenID Connect) oltre a email+password — serve creare il client nella Google Cloud Console
- [x] **Server SMTP** come alternativa all'API Resend per l'invio email (in uso con Brevo)
- [x] **Tema chiaro/scuro** (rispetta `prefers-color-scheme`, toggle manuale)
- [ ] **Icona app e favicon** — per ora favicon SVG provvisoria; manca il set completo (PNG, apple-touch-icon, manifest) con un'icona vera

## Dopo l'MVP

- [ ] **Catalogo completo fonti italiane — requisito di base prima dell'apertura al pubblico** — stato al 19/09/2026: **112/112 fonti verificate** = MIM (2) + **18/18 USR** + **91 USP** (~97 province su 107). Non recuperabili al momento, con motivo: Benevento (pagina anti-bot: serve un browser), Salerno (elenco caricato via JavaScript), Caserta (sito nuovo con 1 sola notizia), Lecce (solo archivio documenti senza date), Viterbo (sito in errore), UAT Udine/Gorizia/Pordenone (liste vuote lato server; le notizie passano dall'USR FVG), Trentino-Alto Adige e Valle d'Aosta (nessun USR). Da ricontrollare ogni tanto con `scripts/check_sources.py`
- [x] Verifica email (double opt-in) prima di attivare il canale email
- [x] Reset password ("password dimenticata") via email
- [x] Controllo periodico del catalogo: watchdog rileva fonti in errore/silenziose/con dominio "deviato"; riepilogo settimanale all'admin (lunedì 8:00); GitHub Actions riverifica le 112 fonti ogni lunedì e i test a ogni push
- [x] Badge "già segnalata" nel digest (email e Telegram)
- [ ] **Deploy — impostazione decisa (20/09/2026): un solo VPS in UE, sempre acceso, con disco persistente.** Niente serverless (servono scheduler sempre vivo e volume per SQLite) e niente Coolify (si mangia ~1 GB): `docker compose` + Caddy come reverse proxy. Rosa finale, prezzi mensili IVA 22% inclusa:
  - **OVH VPS-1 — €4,65** (2 vCore, 4 GB, 40 GB NVMe, backup giornaliero incluso, SLA 99,9%, DC in UE, impegno 12 mesi, upgrade in place dal pannello): **preferito**, unico che include i backup e ha una via di crescita senza migrazione
  - netcup nano G11s — €3,16 (2 vCore, 2 GB, 60 GB, prepagato 6/12 mesi, SLA 99%, Norimberga): il minimo assoluto, ma sui tariffari piccoli l'upgrade in place non è previsto → crescere = migrare
  - Hetzner CX23 — €7,31 (2 vCPU, 4 GB, 40 GB, fatturazione a ore, ridimensionabile, nessun vincolo): il più caro, il più flessibile
  - Scartati: Contabo (oversubscription e IP riciclati → più blocchi anti-bot sullo scraping), Combell (€8,72 a regime), Bluehost (24 mesi anticipati, titolare USA), IONOS (€12 a regime sul taglio equivalente), UpCloud (SLA ottimo ma 1 GB / 10 GB sul taglio economico)
- [ ] **Deploy — cose da mettere in conto**: dominio `.it` (~€9/anno), DNS gratuito (Hetzner DNS Console o Cloudflare), record **SPF + DKIM + DMARC** di Brevo (senza DMARC Gmail scarta gli invii in volume), TLS via Let's Encrypt, backup settimanale con `sqlite3 .backup` prima dello snapshot, `HEALTHCHECK_PING_URL` su healthchecks.io, DPA firmato con l'hosting e hosting/DNS nel registro dei trattamenti
- [x] **Database — deciso (20/09/2026)**: SQLite (WAL) sul VPS unico con disco persistente; niente Postgres finché bot e web stanno sullo stesso host. L'SQL specifico SQLite resta concentrato in `sfm/db*.py` per tenere aperta la porta a un cambio futuro
- [x] Rename del repo → `school-feed-monitor` (fatto)
- [x] Rename degli identificatori interni: `SFM_*` (le `CHECKFEED_*` restano lette con avviso), `data/sfm.db` (spostamento automatico), package `sfm/`, container `sfm-bot` (19/09/2026)

## Monetizzazione (piano al 20/09/2026)

In ordine di priorità: prima le cose che non richiedono traffico né nodi fiscali nuovi.

1. [ ] **Vetrina dei propri servizi** (formazione docenti, sviluppo web, ripetizioni): footer e pagina "chi c'è dietro". Costo zero, nessun adempimento in più, sfrutta il pubblico che già passa di qui
2. [ ] **Inserzioni dirette e mirate** — una riga sponsorizzata nel digest email più uno slot nelle pagine pubbliche, vendute a mano a chi parla ai docenti precari: enti di formazione, percorsi 30/60 CFU e TFA sostegno, case editrici di manuali per concorsi, certificazioni linguistiche e informatiche. È la via con il valore per contatto più alto e senza tracker di terze parti. **Soglia per iniziare a vendere**: da fissare (indicativamente ≥1.000 iscritti attivi o ≥10.000 pagine viste/mese, dati alla mano)
3. [ ] **Affiliazione mirata** su manuali e corsi, con link puliti e dichiarati. Marginale ma a costo zero
4. [ ] **Pubblicità di rete (AdSense o simili)** — solo con traffico organico consistente. Attenzione: impone CMP e consenso al profiling, appesantisce i Core Web Vitals e va contro il requisito "niente tracker di terze parti senza consenso". Da valutare solo se il punto 2 non decolla
5. [ ] Donazioni (Ko-fi/PayPal): trascurabile, ma gratis da mettere

- Fuori scope per ora: **abbonamenti / freemium**. Il billing è già fuori scope e un canone ricorrente implica partita IVA e attività continuativa
- [ ] **Nodo da sciogliere prima del primo incasso — incompatibilità del pubblico impiego.** Per un docente di ruolo a tempo pieno l'attività commerciale/imprenditoriale è vietata, gli incarichi retribuiti vanno autorizzati dal dirigente (art. 53 D.lgs 165/2001, art. 508 D.lgs 297/1994), mentre opere dell'ingegno e prestazioni occasionali autorizzate sono le vie sicure. Prima di emettere la prima ricevuta per un'inserzione: parlarne con il dirigente e con un commercialista, per capire se resta prestazione occasionale o diventa attività d'impresa

## Fuori scope (deciso)

- Feature "interpelli" / bandi di supplenza (terreno dei competitor)
- Billing / pagamenti
