# Confronto tra algoritmi

Funzionalità inclusa nella versione predisposta per Render.
Usa gli archivi già disponibili; non richiede che il download automatico sia
stato completato per eseguire una prova con dati sintetici.

## Interfaccia web

In **Confronto algoritmi** scegliere serie, finestra e parametri del backtest,
poi selezionare gli algoritmi. Casuale uniforme e frequenze sono sempre
inclusi. Gli altri selezionabili sono temporale, regressione logistica,
Random Forest, Gradient Boosting ed ensemble. Nessuna selezione aggiuntiva
esegue il confronto tra le sole due baseline.

Tutti i modelli vedono gli stessi target e soltanto il passato. Il seed e il
training iniziale, mobile/espansivo e la frequenza di riaddestramento sono
comuni. ML richiede almeno 40 estrazioni di training; ensemble almeno 100.
I limiti vengono verificati prima di avviare il job o il download automatico.
Modelli ML e ensemble possono richiedere tempo sulle risorse di Render free.

La tabella mostra media delle corrispondenze, IC bootstrap iid al 95%,
differenze dall'attesa teorica e dal generatore casuale campionato, p-value
Holm e una conclusione prudente. Il caso uniforme è indicato come riferimento,
non come un modello che abbia dimostrato prevedibilità.

Il grafico cumulativo permette di nascondere curve e leggere i valori dei
singoli target con puntatore o frecce della tastiera. La linea tratteggiata
è l'attesa teorica uniforme. Il grafico non ricalcola i modelli quando si
nasconde una curva. Dettagli, distribuzioni e tutti i target sono esportabili
nel JSON del risultato.

## Cronologia e riproducibilità

La selezione multipla viene salvata con i parametri. Aprendo l'esperimento
si ripristina la pagina del confronto; rieseguirlo crea un nuovo risultato
sui dati attuali, conservando il precedente.

Le previsioni e gli IC delle baseline non cambiano se si aggiungono o
riordinano altri modelli. I p-value corretti possono invece cambiare: aumenta
o cambia la famiglia dei confronti. `evaluation_version: "2"` identifica il
calcolo con stream bootstrap separati e riproducibili per modello. I risultati
storici già salvati non vengono riscritti.

## API e terminale

`POST /api/jobs` con `operation: "backtest"` può ricevere `models`, per esempio
`["temporal", "logistic"]`. Una lista vuota richiede solo le baseline.
Senza `models` resta valido il precedente campo singolo `model`. Liste
duplicate, nomi sconosciuti e liste su operazioni diverse dal backtest sono
rifiutati. Le credenziali del sito e l'header di scrittura restano obbligatori.

```sh
python -m machine_learning.cli backtest --game Lotto --variant ordinario --wheel Roma --synthetic --initial 700 --models temporal logistic
```

## Limiti statistici

Il test contro il nullo assume estrazioni uniformi indipendenti. Gli IC iid
sono descrittivi e possono non avere la copertura dichiarata in presenza
di dipendenze. Holm corregge i modelli della singola esecuzione; non corregge
la scelta retroattiva di finestre, seed o parametri tra molte esecuzioni.
Un risultato favorevole richiede una replica indipendente, non prova una
probabilità di vincita futura. Il confronto non sceglie automaticamente il
modello vincitore per puntare o ottimizzare l'ensemble sul test.
