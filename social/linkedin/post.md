Chi lavora nella scuola italiana ha un problema curioso: le notizie che contano (graduatorie, convocazioni, trasferimenti) escono su più di cento siti diversi (Ministero, Uffici Scolastici Regionali, uffici provinciali), ognuno con il suo ritmo e la sua grafica.

Io insegno informatica. Controllare a mano l'USP dove lavoro, quello dove vorrei trasferirmi, l'USR e il Ministero mi è sembrato il lavoro perfetto per un programma. Così è nato School Feed Monitor.

Cosa fa:
• legge 113 fonti, verificate una per una, ogni ora
• filtra per fonti, parole chiave e parole da escludere
• ti avvisa su Telegram appena esce qualcosa che ti riguarda, oppure con un riepilogo giornaliero
• ha anche un sito, senza registrazione

Tre scelte tecniche a cui tengo:
→ la macchina che lo fa girare non riceve connessioni: nessuna porta aperta, nessun dominio, nessun certificato da rinnovare. Genera il sito statico e lo pubblica su GitHub Pages
→ la configurazione viaggia dentro il link di Telegram, in meno di 64 caratteri: nessun account da creare
→ il catalogo delle fonti si ri-verifica da solo ogni settimana

È gratuito e open source (AGPL-3.0). Se conosci un ufficio scolastico con un sito che manca, è il contributo più utile che puoi dargli.

schoolfeedmonitor.federicodiluca.com
Codice: github.com/federicodiluca/school-feed-monitor

#opensource #python #telegram #scuola #docenti
