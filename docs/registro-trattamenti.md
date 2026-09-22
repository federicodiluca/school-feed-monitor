# Registro delle attività di trattamento — School Feed Monitor

Ai sensi dell'art. 30 GDPR. Documento interno del titolare; da aggiornare quando cambiano finalità, dati o fornitori.

| Campo | Valore |
|---|---|
| **Titolare** | Federico Di Luca, persona fisica — contatto: `CONTACT_EMAIL` (oggi schoolfeedmonitor@gmail.com) |
| **DPO** | Non nominato (non ricorrono i presupposti dell'art. 37) |
| **Ultimo aggiornamento** | 2026-09-22 (versione informativa: vedi `PRIVACY_VERSION` in `web/__init__.py`) |

> **Nota sull'architettura attuale.** Il sito non ha account, non chiede email e non registra i visitatori:
> le scelte dell'utente (fonti e parole chiave) restano nel suo browser, in cookie tecnici di prima parte.
> L'unico trattamento di dati personali riguarda chi usa **volontariamente il bot Telegram**.
> Di conseguenza non esistono più i trattamenti "account web" ed "email" delle versioni precedenti.

## Trattamento 1 — Iscritti al bot Telegram

| | |
|---|---|
| **Finalità** | Erogare il servizio richiesto: inviare su Telegram le notizie delle fonti e delle parole chiave scelte dall'utente |
| **Base giuridica** | Esecuzione del contratto / richiesta dell'interessato (art. 6.1.b): il trattamento nasce dal comando `/start` inviato dall'utente |
| **Interessati** | Personale scolastico e altri utenti che avviano il bot (maggiorenni) |
| **Categorie di dati** | Identificativo Telegram (chat id) e username; fonti seguite; parole chiave; orario del digest e data dell'ultimo invio |
| **Dove** | Tabelle `users`, `user_sources` del database SQLite (`data/sfm.db`) sulla macchina virtuale di hosting |
| **Destinatari / responsabili** | Google Cloud (hosting della VM, Stati Uniti — responsabile del trattamento, DPA e clausole contrattuali standard nei termini Google Cloud); Telegram (titolare autonomo, secondo la propria informativa) |
| **Trasferimenti extra-UE** | Stati Uniti, verso il fornitore di hosting, sulla base delle clausole contrattuali standard incluse nel contratto Google Cloud; Telegram secondo la propria informativa |
| **Conservazione** | Finché l'utente resta iscritto. Cancellazione immediata e definitiva con `/cancellami` (conferma richiesta) o su richiesta al titolare |
| **Misure di sicurezza** | Accesso al server limitato al titolare (chiave SSH); database non esposto in rete; token del bot solo in variabili d'ambiente, mai nel repository; backup del database **[da confermare al deploy: dove, cifratura, retention]** |

## Trattamento 2 — Scelte del visitatore del sito (cookie tecnici)

| | |
|---|---|
| **Finalità** | Ricordare nel browser le fonti e le parole chiave scelte, per mostrare "Le mie notizie" alle visite successive |
| **Base giuridica** | Nessun consenso richiesto: cookie tecnici strettamente necessari a fornire una funzione esplicitamente richiesta dall'utente (art. 122 Codice privacy; linee guida Garante cookie 2021) |
| **Dati** | `sfm_fonti` (elenco di identificativi numerici di fonti), `sfm_parole` (parole chiave), più il cookie di sessione usato solo per il token anti-CSRF dei moduli |
| **Dove** | Solo nel browser dell'utente. Il server **non** li memorizza, non li associa a nessun identificativo e non tiene profili |
| **Conservazione** | 1 anno o fino a quando l'utente usa "Dimentica le mie scelte" / cancella i cookie del browser |
| **Diritti** | Esercitabili dall'utente stesso: esportazione (`/configura/esporta.json`), cancellazione (`/configura/dimentica`) |

## Trattamento 3 — Codici di configurazione usa-e-getta

| | |
|---|---|
| **Finalità** | Passare al bot Telegram le fonti e le parole chiave scelte sul sito, senza chiedere altri dati |
| **Base giuridica** | Esecuzione del contratto / richiesta dell'interessato (art. 6.1.b) |
| **Dati** | Codice casuale + elenco di identificativi di fonti e parole chiave. **Nessun riferimento alla persona**: non contiene IP, email, identificativi Telegram né cookie |
| **Dove** | Tabella `configs` del database SQLite |
| **Conservazione** | Cancellato appena il codice viene usato dal bot; in ogni caso massimo 24 ore (pulizia automatica) |

## Trattamento 4 — Log delle notifiche inviate

| | |
|---|---|
| **Finalità** | Non inviare due volte la stessa notizia agli iscritti al bot |
| **Base giuridica** | Esecuzione del contratto (art. 6.1.b) |
| **Dati** | Identificativo utente interno, identificativo notizia, canale, tipo (alert/digest), data e ora |
| **Dove** | Tabella `deliveries` |
| **Conservazione** | 30 giorni (pulizia automatica), o fino alla cancellazione dell'utente |

## Trattamento 5 — Sicurezza e log tecnici

| | |
|---|---|
| **Finalità** | Prevenzione abusi, diagnosi di errori, funzionamento del servizio |
| **Base giuridica** | Legittimo interesse (art. 6.1.f): protezione del servizio e degli utenti |
| **Dati** | Indirizzo IP nei log del server web (se il sito è servito dalla VM; assente se il frontend è statico su GitHub Pages, dove i log restano di GitHub); nei log applicativi del bot: identificativo Telegram e parole chiave che hanno generato una notifica; messaggi di errore |
| **Dove** | File `data/logs/AAAA-MM-GG.log`, log del server web **[da configurare al deploy]**, memoria del processo |
| **Conservazione** | Log applicativi: `data_retention_days` (default 7, massimo consigliato 30); log del server: ≤ 30 giorni con rotazione **[da configurare al deploy]** |

## Trattamento 6 — Notizie pubbliche (non dati personali degli utenti)

| | |
|---|---|
| **Finalità** | Aggregare notizie pubblicate dai siti istituzionali |
| **Dati** | Titolo, link, estratto, data, fonte. Possono contenere nomi di persone presenti nelle notizie pubbliche (es. nomine, graduatorie): il titolare non li estrae né li indicizza, e li conserva solo per `data_retention_days`; la fonte originale resta il riferimento |
| **Conservazione** | `data_retention_days` giorni dalla raccolta |

## Diritti degli interessati — come sono esercitati

| Diritto | Come |
|---|---|
| Accesso e portabilità | Bot: comando `/dati` (restituisce tutto ciò che è memorizzato). Sito: `/configura/esporta.json` (dati che stanno nel browser dell'utente) |
| Rettifica | Bot: `/setkeywords`, `/follow`, `/unfollow`, `/digest`. Sito: pagina "Scegli le fonti" |
| Cancellazione | Bot: `/cancellami` con conferma (immediata, definitiva). Sito: "Dimentica le mie scelte" |
| Opposizione / limitazione / reclamo | Via email al titolare; reclamo al Garante per la protezione dei dati personali |

## Violazioni dei dati (artt. 33–34)

1. Contenere (revoca credenziali, spegnimento del servizio se necessario) e annotare data, natura, dati e utenti coinvolti.
2. Valutare il rischio per gli interessati.
3. Se c'è rischio: notifica al Garante entro 72 ore; se il rischio è elevato: comunicazione agli interessati (messaggio Telegram) senza ingiustificato ritardo.
4. Annotare l'evento e le misure prese in questo documento (sezione "Storico").

## Storico

- 2026-09-20 — prima stesura (versione con account web ed email).
- 2026-09-22 — rimossi account web, email e accesso Google: restano il bot Telegram, i cookie tecnici del sito e i codici di configurazione usa-e-getta. Hosting: VM Google Cloud (Stati Uniti).
