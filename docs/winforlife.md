# Win for Life Classico

Prima implementazione locale del formato configurato: 10 numeri distinti da
1 a 20 e un Numerone da 1 a 20, che può coincidere con un numero principale.
Le regole rimangono `verified: false`: premi, importi, categorie e calendario
ufficiale non sono certificati né calcolati.

## Prova dal sito

1. Aprire **Win for Life** nella navigazione.
2. Caricare la demo sintetica oppure importare risultati reali.
3. In Previsioni lasciare attiva l'opzione Numerone per generare combinazioni
   complete nel formato preliminare.
4. In Test combinazioni selezionare modello, training e target: il rapporto
   confronta ogni combinazione con estrazioni escluse dal suo training,
   usando anche una baseline casuale con lo stesso budget.

La demo contiene 1.000 estrazioni finte con orari distanziati di un'ora:
non riproduce il calendario ufficiale ed è separata dall'archivio reale.
L'importazione della stessa demo è idempotente.

## Risultati reali

Il dialogo di importazione offre un modello CSV specifico con colonne:
`game,variant,draw_id,occurred_at,numbers,numerone,synthetic`.
Usare `Win for Life`, `classico`, un identificativo effettivo del concorso,
data e ora effettive con fuso, dieci numeri principali e Numerone intero.
Una semplice data senza ora non è accettata: non viene inventato un concorso.
L'inserimento manuale dispone di un campo Numerone dedicato.

Il formato JSON esistente `extras: {"numerone": 5}` rimane valido. Se viene
fornita anche la colonna `numerone`, i valori devono coincidere ed essere interi.
La procedura mantiene anteprima, conferma, controllo duplicati ed esportazione.

Il download automatico non è implementato: l'accesso a `www.winforlife.it`
dall'ambiente ha restituito un blocco proxy 403. Non è stata inventata un'API
né collegata la sincronizzazione Lotto a questo gioco.

## Modelli e valutazione

`include_numerone=true` è opzionale nell'API di generazione e nel backtest
`evaluation_mode=tickets`; resta falso per compatibilità con i vecchi client.
La CLI di generazione espone `--include-numerone`. Gli altri giochi non
accettano questa opzione. Il desktop mantiene la generazione dei principali.

Il Numerone utilizza uno stream casuale separato: abilitarlo non cambia i
principali generati con lo stesso seed. La baseline usa una distribuzione
uniforme; il modello temporale usa le ultime 50 osservazioni con smoothing;
gli altri modelli usano frequenze storiche smussate. Per ML ed ensemble il
Numerone non è una previsione ML. I punteggi non sono probabilità calibrate.

Il backtest mostra corrispondenze principali, Numerone corretto per
combinazione e per estrazione, e conteggi congiunti delle due misure.
Non assume indipendenza fra principali e Numerone. Sotto un riferimento
uniforme si attendono 5 principali su 10 e un Numerone corretto nel 5% delle
singole combinazioni: valori elevati sui principali non dimostrano vantaggio.
La strategia senza sovrapposizioni ammette al massimo due combinazioni.

Le previsioni salvate conservano anche il Numerone e la sua valutazione
immutabile. La risposta storica mantiene `matches` dei principali e aggiunge
il risultato separato del Numerone. Non serve una nuova migrazione oltre
allo schema 4 esistente. I vecchi risultati mantengono il loro formato.

I test usano dati sintetici e verificano generazione, importazione, esclusione
del target, persistenza SQLite/PostgreSQL e flusso browser. Non costituiscono
una misura di accuratezza su estrazioni reali Win for Life.
