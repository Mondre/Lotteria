# Verifica delle combinazioni su più estrazioni

La pagina **Test combinazioni**, raggiungibile anche da Previsioni AI, verifica
le ultime N estrazioni della serie selezionata. Ogni target viene escluso dal
training: si generano nuove combinazioni sul solo prefisso precedente e si
confrontano con i numeri effettivamente estratti. Le combinazioni già mostrate
nel generatore non vengono confrontate con un'estrazione che potrebbe essere
entrata nel loro training.

## Uso

1. Selezionare gioco, variante, una sola ruota e archivio reale/sintetico.
2. Aprire **Test combinazioni**, scegliere modello, seed, combinazioni per
   estrazione, numero di target e training minimo.
3. La finestra deve contenere almeno training minimo + target: ad esempio,
   500 estrazioni, training minimo 350, test sulle ultime 100, 5 combinazioni.
   In questo esempio il primo training usa 400 estrazioni e cresce fino a 499.
   Una finestra mobile limita ulteriormente il prefisso, sempre senza futuro.
4. Avviare la verifica. Ogni target riaddestra il modello; il campo della
   frequenza di riaddestramento del backtest tradizionale non è applicato.
   Modelli ML ed ensemble possono richiedere tempo.

Massimo 200 target e 2.000 combinazioni del modello per run. La baseline casuale
ha la stessa numerosità, combinazioni distinte per concorso, regole e finestre.
Gli stream casuali sono separati e deterministici per seed e target: ripetere
lo stesso test sugli stessi dati restituisce lo stesso risultato.

## Come leggere i risultati

- **Per estrazione**: quanti concorsi hanno almeno una combinazione sopra la
  soglia. Più combinazioni con due numeri nello stesso concorso contano come
  una sola estrazione con almeno due corrispondenze.
- **Per combinazione**: quante combinazioni raggiungono ciascuna soglia e
  corrispondenze medie. I denominatori sono mostrati esplicitamente.
- **Casuale campionato**: un secondo insieme di combinazioni casuali per ogni
  target. Il suo risultato può oscillare con il seed.
- **Caso teorico**: distribuzione ipergeometrica per una singola combinazione
  sotto estrazioni uniformi indipendenti. Non viene estesa alle combinazioni
  multiple assumendo erroneamente che siano indipendenti.
- **Dettaglio**: numeri effettivi del target, ultima estrazione usata nel
  training, combinazioni, numeri indovinati e corrispondenze; inizialmente mostra
  l'ultimo target. Il selettore consente di ispezionare gli altri.

Le soglie sono cumulative: un terno contribuisce anche alla soglia di almeno
un ambo. Per Lotto si mostrano i nomi ambo/terno/quaterna/cinquina come numero
di corrispondenze, **non come premi certificati**. Mancano importo e sorte
realmente giocata. Non sono calcolati ricavi, profitto o rendimento.

L'intervallo bootstrap è descrittivo, sulla differenza media dal casuale e
aggregato per concorso, non sulle combinazioni dipendenti di uno stesso target.
Con meno di 20 target non viene mostrato. Dipendenze temporali possono comunque
invalidarlo; non è un test di significatività. Provare molti seed/modelli e
scegliere dopo il più favorevole rende la valutazione esplorativa, non una
validazione indipendente.

## Persistenza

Il rapporto è un esperimento `backtest` con `evaluation_mode=tickets`, conservato
nel database. Si riapre da **Esperimenti salvati**, si esporta in JSON e si può
rieseguire creando un nuovo rapporto sui dati attuali. Non viene registrato come
previsione realmente emessa prima di un concorso passato. Il registro delle
previsioni future rimane distinto. Gli hash del training sono salvati per target.

## Prima prova reale locale

Sul database di validazione ufficiale, modello `frequency`, seed 42, ruota Bari,
500 estrazioni disponibili, 5 combinazioni per ognuna delle ultime 100
(14 maggio–3 novembre 2026), training espansivo minimo 350:

| Soglia | Estr. modello / 100 | Estr. casuale / 100 |
|---|---:|---:|
| Almeno un numero | 75 | 85 |
| Almeno due numeri | 12 | 14 |
| Almeno tre numeri | 1 | 0 |
| Almeno quattro numeri | 0 | 0 |
| Cinque numeri | 0 | 0 |

Corrispondenze medie per combinazione: modello 0,286, casuale campionato 0,310,
attesa teorica 0,27778. Non è dimostrato un vantaggio del modello: il singolo
terno non basta a concluderlo. È una riproduzione retrospettiva con parametri
espliciti, non una verifica delle combinazioni specifiche dello screenshot,
non una previsione prospettica e non una stima dei premi. Nessun database o
sito dell'utente è stato modificato per questa prova; nessun download aggiuntivo.

## Strategie di distribuzione

La nuova opzione `ticket_strategy=disjoint` evita numeri ripetuti fra combinazioni
dello stesso gruppo. La baseline casuale applica la stessa opzione; le medie di
copertura sono mostrate per entrambi. Non viene cambiato il default ponderato.
Il confronto esplorativo non ha mostrato un miglioramento affidabile della
capacità predittiva: vedere [ticket-coverage.md](ticket-coverage.md).

## Win for Life Classico

Attivando il Numerone, il test valuta separatamente i 10 numeri principali e
il numero extra, sia per il modello sia per il casuale. Mostra anche i conteggi
congiunti, senza convertirli in categorie premio. Il target completo è escluso
dal training. Dettagli e limiti in [winforlife.md](winforlife.md).
