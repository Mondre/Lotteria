# Aggiornamento automatico — attivazione sospesa fino alla verifica reale

## Stato della verifica

Il 4 novembre 2026 sono state consultate direttamente queste pagine ufficiali:

- [Archivio estrazioni Lotto](https://www.lotto-italia.it/lotto/estratti-ruote)
- [Come si gioca](https://www.lotto-italia.it/lotto/come-si-gioca)
- [Regolamenti](https://www.lotto-italia.it/lotto/regolamenti)
- [Indicazioni robots](https://www.lotto-italia.it/robots.txt)

La pagina dell'archivio offre esplicitamente file ZIP testuali. Il collegamento
per il periodo dal 2001 a oggi punta a:

`https://www.brightstarlottery.it/STORICO_ESTRAZIONI_LOTTO/storico01-oggi.zip`

L'URL è stato trovato nella pagina, non ipotizzato. Il dominio dell'archivio è
diverso dal dominio delle pagine: la policy di rete attuale consente le pagine
ma rifiuta il download ZIP con HTTP 403 del proxy. L'aggiunta di
`www.brightstarlottery.it` è salvata nella bozza dell'ambiente e non è stata
pubblicata. Non sono state aggirate le restrizioni di rete.

**Il contenuto reale dello ZIP e il suo formato non sono ancora verificati.**
Il parser è implementato e testato con fixture artificiali in formato
`data / sigla ruota / cinque numeri`, ma questo non dimostra che il file
attualmente pubblicato usi proprio tale struttura. Prima del rilascio bisogna
scaricare il file consentito, controllarne il formato e confrontare alcuni
concorsi con la pagina/bollettino ufficiale. Il formato non riconosciuto
interrompe l'aggiornamento senza inserire dati parzialmente interpretati.

## Flusso implementato

Per il **Lotto ordinario**, il pulsante **Analizza i dati reali** o l'avvio
di un esperimento con archivio **Fonte ufficiale (Lotto)** esegue:

1. Controllo della cache persistente, valida un'ora e per la finestra già caricata.
2. Se necessario, lettura della pagina ufficiale e scoperta del link ZIP.
3. Download HTTPS limitato, con verifica TLS e redirect soltanto verso i domini
   ufficiali esplicitamente ammessi dall'applicazione.
4. Lettura dello ZIP in memoria, senza estrarre file sul filesystem.
5. Selezione degli ultimi 1.000 concorsi completi comuni alle undici ruote,
   o della finestra maggiore richiesta, fino a 10.000. Se la fonte ne offre
   meno, la disponibilità effettiva è riportata e non vengono inventate righe.
6. Validazione, confronto con i risultati esistenti e importazione atomica.
   Un conflitto sospende tutto: nessuna sovrascrittura automatica dei numeri.
7. Analisi o previsione usando esclusivamente gli ID dei concorsi verificati
   nell'ultimo aggiornamento, senza contare due volte copie manuali con altri ID.

**Aggiorna storico ufficiale** forza un nuovo controllo. Il controllo non
avviene a ogni apertura di pagina e non richiede un cron a pagamento:
l'aggiornamento è su richiesta prima del calcolo. La cache sopravvive ai
riavvii di Render grazie al database PostgreSQL.

Il demo sintetico non scarica dati reali. **Archivio completo** e la modalità
senza aggiornamento mantengono disponibili i dati locali e l'importazione
manuale. I risultati di un download fallito non vengono sostituiti con demo
né presentati come aggiornati. Per gli altri giochi il connettore automatico
non è ancora verificato: l'interfaccia lo indica e non inventa una fonte.

## Date senza orario

Il parser dello storico conserva la precisione `date`: mezzanotte
`Europe/Rome` serve solo come riferimento tecnico per ordinare il giorno e
non è presentata come ora osservata dell'estrazione. La UI mostra soltanto
la data; esportazioni e modelli conservano l'indicazione di precisione.

La valutazione delle previsioni su un risultato senza ora è conservativa:
devono corrispondere ID e giorno italiano, e la previsione deve essere stata
emessa prima dell'inizio di quel giorno. Le previsioni dello stesso giorno
non vengono valutate quando manca un orario che dimostri la precedenza.
Questo evita confronti retroattivi o orari d'estrazione inventati.

Gli ID costruiti dal connettore sono `lotto:AAAA-MM-GG`, distinti per ruota
dalla chiave del database. Per una previsione futura collegata a tale fonte
va usata questa convenzione, non un identificativo arbitrario.

## Persistenza e compatibilità

La migrazione alla versione 3 aggiunge la precisione della data e la tabella
degli aggiornamenti. Le estrazioni precedenti mantengono precisione `instant`;
numeri, log, previsioni e risultati non vengono cancellati. Sono stati testati
sia SQLite sia PostgreSQL, incluso l'aggiornamento da schema versione 2.

Le regole restano marcate preliminari. La presenza di una fonte ufficiale
e una buona copertura dei test non certificano tutte le regole storiche,
le varianti o una capacità predittiva superiore al caso.

## Verifiche effettuate

- Lettura reale della pagina ufficiale e individuazione del collegamento ZIP.
- Parser e sincronizzazione con fixture chiaramente artificiali.
- Duplicati, conflitti, rollback, cache, riavvio e migrazioni su PostgreSQL.
- API: aggiornamento prima dei calcoli, esclusione del demo e dei duplicati manuali.
- Browser: avvio con un clic e successivo uso della cache con una fonte simulata.
- Download e importazione dello ZIP ufficiale reale: **ancora bloccati dalla rete**.

Il codice del connettore è incluso nella release ma resta disattivato per
impostazione predefinita. Solo dopo la verifica dello ZIP reale si potrà
abilitare `LOTTOPREDICT_OFFICIAL_SYNC_ENABLED=true`. Cronologia e confronto
algoritmi non richiedono questa attivazione e funzionano con gli archivi disponibili.
