# Confronti futuri Lotto

La pagina **Confronti futuri** registra una verifica prima del concorso,
anziché rigenerare combinazioni dopo aver visto il risultato. Non promette
maggiore accuratezza: permette di misurarla senza riutilizzare dati già
osservati per scegliere i parametri.

## Uso

1. Scegliere Lotto ordinario, una ruota e la finestra di storico. Per dati reali
   usare **Fonte ufficiale (Lotto)** abilitata; per una prova tecnica usare il demo.
2. Aprire **Confronti futuri** e indicare una data di concorso ufficiale futura,
   modello, seed, quantità e strategia di distribuzione delle combinazioni.
   La data è scelta dall'utente: il software non presume calendari o orari.
3. Registrare il confronto entro il giorno precedente, nel fuso Europe/Rome.
   La mezzanotte è solo un riferimento per la data del risultato, non l'ora
   prevista o osservata dell'estrazione.
4. Il server acquisisce lo storico ufficiale (o legge quello sintetico), genera
   entrambi i gruppi e li salva insieme. Il casuale ha la stessa numerosità e
   strategia del modello e lo stesso hash del training/regole.
5. Dopo il concorso premere **Acquisisci risultati ufficiali** oppure aggiornare
   la fonte da un'altra pagina. Quando arriva l'estrazione con ID canonico
   `lotto:YYYY-MM-DD`, stessa ruota e archivio, entrambe le previsioni vengono
   valutate dal motore già esistente.

Non esiste uno scheduler: aprire il sito o consultare l'elenco non esegue un
aggiornamento automatico della fonte. **Aggiorna elenco** legge soltanto i dati
persistenti; il pulsante di acquisizione invoca esplicitamente la fonte. Il demo
non genera automaticamente risultati futuri: eventuali esiti sintetici vanno
importati in un database di test, mai scambiati per risultati reali.

## Cosa viene bloccato

Date già passate o relative al giorno corrente sono rifiutate prima del job.
La restrizione conserva una precedenza certa anche quando lo storico ha solo
la data e manca l'orario osservato del risultato. Partite sportive e altri
giochi non rientrano in questo registro.

Le due previsioni vengono salvate nella stessa transazione: se la seconda
fallisce, la prima viene annullata. I trigger esistenti impediscono aggiornamento
e cancellazione dei payload e dei risultati. Una richiesta identica per stesso
protocollo, concorso, ruota e archivio restituisce lo snapshot originale senza
creare altre previsioni. Non viene rigenerata una previsione precedente per
farla apparire migliore dopo un aggiornamento dello storico.

Lo snapshot include modello/versione, seed, strategia, quantità, limite storico,
regole e hash del training. La baseline usa uno stream riproducibile distinto.
Le due voci sono visibili anche nel registro generale delle previsioni; la
pagina dedicata le presenta come coppia modello/casuale.

## Risultati e protocolli

La metrica primaria è fissata prima: **concorsi con almeno due corrispondenze
in almeno una combinazione**. La media delle corrispondenze per combinazione
rimane nei dati esportati come misura secondaria. Nessun premio o profitto
viene calcolato.

Ogni protocollo conserva modello, versione, regole, ruota, archivio, seed,
quantità, strategia e finestra. Protocolli differenti non sono sommati in un
unico tasso. Solo coppie complete, registrate prima della data e valutate su
un medesimo risultato, entrano nei conteggi. In assenza di risultati compare
**Nessun risultato**, non una percentuale inventata. Coppie incomplete o non
confrontabili sono escluse dalla valutazione; le incomplete sono segnalate.

L'elenco è limitato alle ultime 2.000 previsioni marcate come confronto (due per
coppia, al massimo 1.000 confronti). I riepiloghi e l'export riguardano questa
finestra; i record precedenti rimangono nel database. Nessun nuovo schema o
servizio esterno è richiesto: si usano le tabelle immutabili già presenti.
L'esito del job in RAM è temporaneo, ma la coppia è consultabile dopo un riavvio.

I conteggi sono descrittivi: non viene dichiarato automaticamente un vantaggio
significativo, una probabilità di vincita o una redditività. Creare molti
protocolli e scegliere dopo quello più favorevole richiede una nuova verifica
indipendente; non costituisce una conferma del modello.

## API e verifiche

- `POST /api/prospective-lotto`: selezione, modello, seed, combinazioni,
  `ticket_strategy` e `target_day` ISO `YYYY-MM-DD`; restituisce un job.
- `GET /api/prospective-lotto?wheel=Roma&synthetic=false`: coppie e riepiloghi,
  esportabili dalla pagina in JSON.

Autenticazione e controlli d'origine sono gli stessi del sito. Nessuna giocata,
notifica o pubblicazione è effettuata. Verificati atomicità, deduplicazione,
immutabilità e arrivo successivo dei risultati con orologi simulati nei soli
database di test SQLite/PostgreSQL; questi test non sono previsioni reali.
La prova browser copre registrazione, riapertura, export e mobile.
