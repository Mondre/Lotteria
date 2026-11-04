# Cronologia persistente degli esperimenti

La pagina **Esperimenti salvati** conserva analisi, combinazioni, backtest e
simulazioni completati, oltre ai tentativi scientifici falliti. Non richiede un
servizio esterno aggiuntivo: usa lo stesso database SQLite o PostgreSQL dell'app.
Questa funzionalità è inclusa nella versione predisposta per Render.

Per ogni esecuzione vengono registrati ID, tipo, parametri richiesti, data di
avvio e conclusione, risultato completo oppure messaggio di errore. La lista è
paginata e filtrabile per tipo; non scarica tutti i risultati numerici per
mostrare una pagina della cronologia.

- **Apri** carica il risultato originale senza riaddestrare o ricalcolare.
- **Riesegui** usa i parametri registrati sui dati attuali e salva un nuovo ID.
  Non modifica l'esperimento precedente e non garantisce che i dati siano gli stessi.
- I risultati riaperti possono essere esportati con **Esporta JSON**.
- Da una generazione salvata è ancora possibile registrare una previsione
  futura, con gli stessi controlli di data e immutabilità delle altre generazioni.

I parametri comprendono gioco, variante, ruota, selezione reale/sintetica,
finestra storica, modello, seed e impostazioni di backtesting. Non includono
password, stringhe di connessione o contenuti dei file caricati.

La risposta di completamento viene restituita dopo il salvataggio. Se il
database non permette di conservare il risultato, il job è segnalato come
fallito, non come un successo persistente. Non vengono creati risultati vuoti
per sostituire calcoli interrotti.

La coda e i job ancora attivi rimangono nel processo web: un riavvio non riprende
automaticamente il lavoro. In quel caso si può rilanciare la richiesta. Le
anteprime e i rapporti di importazione sono temporanei; le estrazioni importate
e i registri rimangono persistenti. Non è stata introdotta una cancellazione
automatica degli esperimenti; la cronologia usa spazio nel piano database scelto.

Le API della cronologia richiedono la stessa autenticazione del sito. Non ci
sono endpoint di modifica dei risultati salvati. Consultare un esperimento
favorevole non equivale a dimostrare prevedibilità: rimangono valide le ipotesi
dei test, i confronti con il caso e i limiti dei confronti multipli.
