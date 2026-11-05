# Calcio · Serie A — prima versione

La voce **Calcio · Serie A** apre `/football`, una sezione separata dalle lotterie.
La fonte sportiva automatica rimane disattivata fino alla configurazione e verifica del fornitore.

## Funzionalità disponibili

- Archivio di partite con stagione, squadre, calcio d'inizio con fuso, stato e
  risultato finale. Reali e sintetiche rimangono separate.
- Demo: 168 risultati e 4 partite future fra squadre **fittizie**, seed 42.
  Date relative all'esecuzione; non sono incontri o probabilità della vera Serie A.
  Il demo si carica solo su richiesta, a database sintetico vuoto, e non sposta
  date o previsioni a ogni riapertura.
- Importazione atomica CSV/JSON normalizzato, massimo 5 MiB e 10.000 righe.
  Nessuna anteprima in questa versione: un errore annulla l'intero file.
- Probabilità 1–X–2 con Poisson indipendenti, intensità casa/trasferta derivate
  da gol fatti/subiti e regolarizzazione di cinque partite verso le medie del
  campionato. Minimo 30 risultati disponibili per il training.
- Per squadra: partite, gol fatti/subiti, conteggi casa/trasferta e ultime cinque
  V/P/S. Nessuna selezione automatica di puntate, quote o stake.
- Previsioni salvate prima del calcio d'inizio, snapshot di parametri/versione,
  hash del training, target e probabilità. Trigger SQLite/PostgreSQL impediscono
  modifica e cancellazione di previsioni e valutazioni.
- Valutazione dopo l'importazione del risultato, con esito, Brier e log-loss.
  Un cambio di calcio d'inizio rispetto allo snapshot impedisce il punteggio
  automatico, anziché attribuire una validazione ambigua.
- Backtest cronologico sugli ultimi 200 target eleggibili (API: da 1 a 500,
  massimo 3.000 risultati in archivio per run). Confronto con frequenze 1/X/2
  regolarizzate del solo passato. Rapporti persistenti, riapribili dalla pagina.
- Esportazione di partite, ultime 100 previsioni e ultimi 10 rapporti.

Il modello usa tutti i risultati precedenti nell'archivio selezionato, anche di
stagioni diverse. Non stima un decadimento temporale, né considera formazioni,
infortuni, mercato, allenatori o quote. Squadre con poca storia ricevono stime
regolarizzate verso la media, accompagnate da un avviso. Non è calibrato e non
ha una validazione prospettica su dati reali. Le percentuali non sono garanzie.

## Date e prevenzione del leakage

Per un risultato finale è obbligatorio `available_at`: istante con fuso in cui
il risultato è noto, successivo al kickoff e non futuro. Non si inventa un
orario per file contenenti solo la data. Il training richiede sia kickoff sia
disponibilità del risultato **strettamente precedenti** al cutoff. Nel backtest
il cutoff è il kickoff del target; risultati contemporanei o tardivamente noti
non entrano nel training. Per una previsione futura è l'ora di emissione.

Il backtest è descrittivo. Brier è la somma non dimezzata dei tre errori quadratici;
log-loss usa logaritmi naturali. Valori inferiori sono migliori; l'accuratezza
riporta la quota di esiti più probabili corretti. Nessuna metrica dimostra da
sola calibrazione, redditività o capacità su altri periodi.

## File normalizzati

Scaricare il modello vuoto dalla pagina. CSV UTF-8 separato da virgole; JSON
come lista di oggetti, non l'intero export (che contiene anche i rapporti).

| Campo | Contratto |
|---|---|
| id | Testo stabile, massimo 200 caratteri |
| season | Anno iniziale intero, ad esempio 2025 per 2025/26 |
| kickoff | ISO con fuso, ad esempio `2026-12-01T20:45:00+01:00` |
| home / away | Nomi distinti e coerenti fra tutti i file |
| status | SCHEDULED, FINISHED, POSTPONED o CANCELLED |
| home_goals / away_goals | Interi 0–20, solo se FINISHED; altrimenti vuoti/null |
| available_at | Obbligatorio per FINISHED, vuoto/null altrimenti |
| synthetic | Booleano JSON; `true`/`false` nel CSV, coerente con il caricamento |
| source | Fonte/documento di riferimento, massimo 200 caratteri |

Non si sovrascrivono risultati finali in conflitto. È ammesso aggiornare un
calendario, anche da SCHEDULED a FINISHED. La coppia casa/trasferta nella stessa
stagione non può essere duplicata con ID diversi. Non è presente una mappatura
automatica fra nomi diversi della stessa squadra: usare nomi coerenti.
Solo Serie A è prevista come competizione di questa prima versione; l'importatore
non certifica provenienza, licenza o appartenenza dei dati al campionato.

## Fonte automatica predisposta, non verificata live

È presente un adattatore per football-data.org API v4, competizione `SA`, con
aggiornamento esplicito di una stagione. Le risposte sono validate e importate
atomicamente; non si eseguono download all'avvio o in background non richiesti.
Partite in corso/sospese non producono un risultato né sono prevedibili. Si
accettano risultati finali dei tempi regolamentari, non supplementari/rigori.
`lastUpdated` della fonte è usato come disponibilità conservativa del risultato:
un aggiornamento tardivo esclude il risultato dai cutoff precedenti. Non
sostituisce un archivio storico delle pubblicazioni effettive.

**La fonte non è pronta per l'uso reale:** token assente; documentazione e
condizioni del fornitore irraggiungibili dalla rete di sviluppo (403). Endpoint
e parser sono predisposti e testati con fixture, non con risposte live di un
account autorizzato. Non sono confermati copertura, piano gratuito, profondità
dello storico o diritti di riutilizzo. Prima di attivarla verificare i dettagli su:

- https://www.football-data.org/documentation/quickstart
- https://www.football-data.org/terms

Richiede l'accesso di rete a `api.football-data.org` e, nel **server**, le variabili:

- `FOOTBALL_DATA_ENABLED=true`;
- `FOOTBALL_DATA_API_TOKEN`, inserito in modo sicuro nelle impostazioni del server,
  mai in chat o nel repository.

Il token viene inviato solo all'host fisso HTTPS; i redirect sono rifiutati.
Non compare nell'API di configurazione o nei messaggi d'errore. In assenza di
configurazione il pulsante è disattivato e l'API di sync restituisce 409 senza
contattare il fornitore. Non sono state aggiunte variabili al blueprint Render.

## Database e verifiche

Migrazione additiva a schema **4** per SQLite e PostgreSQL. Le tabelle calcio
sono distinte; le estrazioni e le previsioni delle lotterie vengono preservate.
Verificate persistenza, immutabilità, migrazione e transazioni su PostgreSQL 16
locale di test. Non sono stati usati database personali.

```sh
python -m unittest tests.test_football -v
# Con server su un database di test vuoto, Playwright e Chromium:
python tests/browser_football_smoke.py --url http://127.0.0.1:8024
```

La prova browser aggiunge solo il demo, salva una previsione e un backtest,
esporta i dati e controlla riapertura e mobile. I test scientifici verificano
assenza di leakage e formule del software, non prestazioni predittive reali.
