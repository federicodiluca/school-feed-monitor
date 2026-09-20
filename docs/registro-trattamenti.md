# Registro delle attività di trattamento — School Feed Monitor

Ai sensi dell'art. 30 GDPR. Documento interno del titolare; da aggiornare quando cambiano finalità, dati o fornitori.

| Campo | Valore |
|---|---|
| **Titolare** | Federico Di Luca, persona fisica — contatto: `CONTACT_EMAIL` (oggi schoolfeedmonitor@gmail.com) |
| **DPO** | Non nominato (non ricorrono i presupposti dell'art. 37) |
| **Ultimo aggiornamento** | 2026-09-20 (versione informativa: vedi `PRIVACY_VERSION` in `web/__init__.py`) |

## Trattamento 1 — Account e preferenze del servizio

| | |
|---|---|
| **Finalità** | Erogare il servizio richiesto: account web, scelta di fonti/parole chiave/canali/frequenza, invio delle notifiche |
| **Base giuridica** | Esecuzione del contratto (art. 6.1.b); consenso per l'invio delle comunicazioni (art. 6.1.a), revocabile dalla pagina Account |
| **Interessati** | Personale scolastico e altri utenti registrati (maggiorenni) |
| **Categorie di dati** | Email; hash della password; identificativo e username Telegram (se collegato); identificativo account Google ed email (se accesso con Google); fonti seguite; parole chiave; canali e orari; versione e data del consenso; data di verifica dell'email |
| **Dove** | Tabelle `users`, `user_sources`, `link_codes`, `email_tokens` del database SQLite (`data/sfm.db`) sul server di hosting |
| **Destinatari / responsabili** | Fornitore email (Brevo, Francia — responsabile del trattamento, DPA nelle condizioni del servizio); fornitore hosting **[da inserire: nome, paese, DPA]**; Telegram (solo se l'utente attiva il canale; titolare autonomo); Google (solo se l'utente sceglie l'accesso con Google; titolare autonomo) |
| **Trasferimenti extra-UE** | Nessuno da parte del titolare. Telegram e Google: solo su scelta dell'utente, secondo le rispettive informative |
| **Conservazione** | Finché esiste l'account. Cancellazione immediata e definitiva su richiesta dell'utente (pagina Account) o del titolare (account inattivi/abusi). Token email: 1–48 ore. Codici di collegamento Telegram: 15 minuti |
| **Misure di sicurezza** | Password con hash (scrypt); HTTPS; cookie di sessione HttpOnly/SameSite/Secure; CSRF; limitazione tentativi di accesso; Content-Security-Policy; accesso al server limitato al titolare; backup del database **[da confermare al deploy: dove, cifratura, retention]** |

## Trattamento 2 — Log delle notifiche inviate

| | |
|---|---|
| **Finalità** | Non inviare due volte la stessa notizia; mostrare nel riepilogo cosa è già stato segnalato |
| **Base giuridica** | Esecuzione del contratto (art. 6.1.b) |
| **Dati** | Identificativo utente, identificativo notizia, canale, tipo (alert/digest), data e ora |
| **Dove** | Tabella `deliveries` |
| **Conservazione** | 30 giorni (pulizia automatica), o fino alla cancellazione dell'account |

## Trattamento 3 — Sicurezza e log tecnici

| | |
|---|---|
| **Finalità** | Prevenzione abusi, diagnosi di errori, funzionamento del servizio |
| **Base giuridica** | Legittimo interesse (art. 6.1.f): protezione del servizio e degli utenti |
| **Dati** | Indirizzo IP (log del server web; in memoria per il limite ai tentativi di accesso); nei log applicativi del bot: identificativo Telegram, indirizzo email e parole chiave che hanno generato una notifica; messaggi di errore |
| **Dove** | Log del reverse proxy (**[da configurare al deploy]**), file `data/logs/AAAA-MM-GG.log`, memoria del processo |
| **Conservazione** | Log applicativi: `data_retention_days` (default 7, massimo consigliato 30); log del server: ≤ 30 giorni con rotazione **[da configurare al deploy]**; contatori in memoria: 15 minuti |

## Trattamento 4 — Notizie pubbliche (non dati personali degli utenti)

| | |
|---|---|
| **Finalità** | Aggregare notizie pubblicate dai siti istituzionali |
| **Dati** | Titolo, link, estratto, data, fonte. Possono contenere nomi di persone presenti nelle notizie pubbliche (es. nomine, graduatorie): il titolare non li estrae né li indicizza, e li conserva solo per `data_retention_days`; la fonte originale resta il riferimento |
| **Conservazione** | `data_retention_days` giorni dalla raccolta |

## Diritti degli interessati — come sono esercitati

| Diritto | Come |
|---|---|
| Accesso e portabilità | Pagina Account → "Scarica i tuoi dati (JSON)" |
| Rettifica | Pagine Preferenze/Account (email, password, preferenze) |
| Revoca del consenso | Pagina Account → "Revoca il consenso" (ferma subito le notifiche) |
| Cancellazione | Pagina Account → "Cancella l'account" (immediata, definitiva) |
| Opposizione / limitazione / reclamo | Via email al titolare; reclamo al Garante per la protezione dei dati personali |

## Violazioni dei dati (artt. 33–34)

1. Contenere (revoca credenziali, spegnimento del servizio se necessario) e annotare data, natura, dati e utenti coinvolti.
2. Valutare il rischio per gli interessati.
3. Se c'è rischio: notifica al Garante entro 72 ore; se il rischio è elevato: comunicazione agli utenti via email senza ingiustificato ritardo.
4. Annotare l'evento e le misure prese in questo documento (sezione "Storico").

## Storico

- 2026-09-20 — prima stesura.
