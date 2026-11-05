# Grafici descrittivi

Nelle analisi web sono disponibili ritardi attuali per numero e distribuzione
delle somme dei numeri principali. Selezionando **Esplora** nella tabella si vede
anche l'andamento della frequenza cumulativa di quel numero, con il riferimento
teorico uniforme. Puntatore e frecce sinistra/destra esplorano i punti; Home/End
raggiungono gli estremi. I valori selezionati sono riportati anche come testo.

La frequenza cumulativa usa sempre il prefisso cronologico della serie; non usa
estrazioni successive al punto mostrato. Per contenere le dimensioni dei risultati
sono salvati al massimo 201 punti per numero, includendo primo e ultimo.
L'asse orizzontale conta estrazioni, non giorni. I segmenti tra i punti campionati
non ricostruiscono ogni oscillazione intermedia. Sono dati descrittivi, non previsioni.

I ritardi sono conteggi di estrazioni senza uscita entro la finestra selezionata.
Se il numero non è mai stato osservato, il valore è censurato al bordo della serie.
Un ritardo alto non aumenta la probabilità futura. Le somme sono raggruppate in
al massimo 20 intervalli; la somma delle frequenze è il numero di estrazioni.

I grafici usano il risultato salvato, anche riaprendo la cronologia. Nei vecchi
esperimenti privi di andamento il software lo segnala: non lo ricalcola su dati
nuovi. Una riesecuzione aggiunge la serie in un nuovo esperimento.

Nel desktop il dialogo **Grafico interattivo** offre frequenze, ritardi, somme e
andamento per numero, con zoom, pan e salvataggio Matplotlib. Le stesse regole
sui dati salvati e sugli andamenti mancanti restano valide.

## Extra configurati

Le nuove analisi includono una sezione separata per ogni extra configurato:
Jolly, SuperStar e Numerone. Mostra presenze e frequenza osservata per valore,
compresi i valori mai osservati. Ogni campo extra conta un valore per estrazione.
Non si sommano queste presenze a quelle dei numeri principali; non si presume
indipendenza o uniformità e non si calcolano test teorici sugli extra.
La generazione e il backtest continuano a riguardare solo i numeri principali.
Gli extra si vedono anche nelle righe dell'archivio e vengono preservati
nell'esportazione. Nei vecchi risultati privi di questa sezione non vengono
aggiunti conteggi ricavati dai dati attuali: serve una nuova esecuzione.
