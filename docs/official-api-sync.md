# Sincronizzazione progressiva Lotto

Il connettore `data_sources/lotto_api.py` usa gli stessi due servizi pubblici
individuati negli script della pagina ufficiale:

- calendario dei concorsi, per anno/mese;
- risultato di un singolo concorso, per data.

Entrambi sono su `https://www.lotto-italia.it/gdl/estrazioni-e-vincite/`.
Non utilizza proxy alternativi, domini diversi, endpoint ipotizzati o lo ZIP
Brightstar. La rete di sviluppo già consente questo dominio.

## Comportamento

La finestra richiesta conta **concorsi completi per ruota**: 100 concorsi
corrispondono a 1.100 estrazioni totali. Si parte dal calendario corrente e
si procede a ritroso. Le date future vengono ignorate; un concorso di oggi
non ancora disponibile/completo è rimandato al prossimo aggiornamento. Una
risposta malformata o un concorso passato mancante interrompono il recupero,
senza saltare lacune o ridurre la finestra in silenzio.

Ogni concorso deve avere esattamente le undici ruote, una data corrispondente
alla richiesta e cinque numeri validi e distinti per ruota. Numeri principali,
ordine estratto e data di riferimento sono preservati. `date_precision=date`
impedisce di scambiare la mezzanotte per un orario effettivo di estrazione.
Opzioni e numeri aggiuntivi del servizio non diventano extra Lotto non verificati.

Un concorso validato viene salvato atomicamente con la ricevuta della fonte e
il suo SHA-256. Un'interruzione conserva i concorsi già validati: una richiesta
successiva li riutilizza, anche dopo il riavvio. I due concorsi più recenti
vengono ricontrollati; quelli più vecchi sono riutilizzati. Questo non garantisce
il rilevamento automatico di rettifiche remote su tutto lo storico. Un conflitto
con dati già salvati interrompe l'operazione senza sovrascrittura.

La finestra ufficiale utilizzabile da un esperimento viene aggiornata **solo**
quando l'intera richiesta è soddisfatta. Un aggiornamento fallito non lancia
l'analisi sui dati parziali e non ripiega sui sintetici. Le righe parziali
rimangono visibili nell'archivio completo, con fonte e data, ma non sono
presentate come un aggiornamento completo. È possibile richiedere esplicitamente
una finestra più piccola, quando la fonte non copre quella grande.

## Avanzamento e limiti

`GET /api/sources/status` mostra stato, concorsi completati/richiesti e ultimo
messaggio, senza risposte grezze. Durante il calcolo il browser legge questo
avanzamento periodicamente. La prima acquisizione può durare diversi minuti;
i controlli successivi usano una cache di successo di un'ora e i dati persistenti.
La coda usa un solo worker, come il deploy Render configurato.

Le risposte sono limitate a 2 MiB. Sono mantenuti TLS e controllo dei redirect;
errori transitori hanno al massimo due retry, senza retry dei divieti 403 o
degli errori TLS. Un Retry-After numerico lungo interrompe il tentativo senza
insistere. La ricerca non precede l'introduzione della Ruota Nazionale nel 2005.
Il servizio può avere una profondità storica inferiore: il calendario di un
mese antico **non dimostra** che i relativi risultati siano disponibili.

`LOTTOPREDICT_OFFICIAL_SYNC_ENABLED=true` abilita la funzione; `false` la
mantiene disattivata. Il parser ZIP precedente resta disponibile per verifiche,
ma non è usato come fallback implicito. Non servono nuove credenziali.

## Verifica live del 5 novembre 2026

Prima acquisizione di 100 concorsi: 1.100 righe valide. Estensione a 1.000:
500 concorsi completi validati e persistiti; il risultato successivo non era
disponibile e la richiesta è fallita esplicitamente. La richiesta successiva
da 500 ha riutilizzato 498 concorsi e ricontrollato i due più recenti, senza
aggiungere duplicati. La cache di successo è stata verificata dopo la riapertura
del database. Nessun dato è stato aggiunto al database dell'utente.
