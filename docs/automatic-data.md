# Aggiornamento automatico Lotto

Il connettore corrente usa i servizi pubblici della pagina ufficiale
https://www.lotto-italia.it/lotto/estratti-ruote, sul dominio già consentito.
Il 5 novembre 2026 sono stati validati **500 concorsi completi per ruota**:
5.500 estrazioni reali, dal 13 giugno 2024 al 3 novembre 2026, in un database
di test separato. La richiesta da 1.000 è stata interrotta quando la fonte
non ha restituito il concorso dell'11 giugno 2024. Non è stata dichiarata riuscita.
È una copertura osservata, non un contratto stabile del servizio.

La finestra iniziale del browser, con la fonte automatica abilitata, è 500;
il training iniziale del backtest è 350. Si possono scegliere altre finestre:
se la fonte non le copre, l'operazione fallisce esplicitamente senza analisi
parziale o dati dimostrativi. Le chiamate API dirette devono specificare
`limit: 500` (e parametri di training coerenti) per usare la finestra verificata.

## Attivazione

`LOTTOPREDICT_OFFICIAL_SYNC_ENABLED=true` abilita la funzione. Il blueprint
Render è predisposto con questo valore; le modifiche locali devono ancora
essere pubblicate e distribuite. L'app locale mantiene la funzione disattivata
in assenza del valore `true`, così i test e gli avvii locali non scaricano dati
senza configurazione esplicita.

Il pulsante iniziale esegue l'analisi Lotto con aggiornamento automatico. Le
altre analisi, generazioni e prove aggiornano prima la fonte quando selezionata.
Il primo caricamento richiede diversi minuti; il browser mostra l'avanzamento.
Le richieste successive riutilizzano la cache persistente e una cache di successo
di un'ora. Nessun nuovo servizio a pagamento o credenziale è richiesto.

Recupero progressivo, ripresa, conflitti, completezza e limiti sono descritti in
[official-api-sync.md](official-api-sync.md). Non si possono ancora aggiornare
automaticamente SuperEnalotto, Win for Life, 10eLotto o MillionDAY.

## Separazione dei dati

Solo Lotto ordinario reale e tutte le undici ruote. Gli ID ufficiali sono
`lotto:YYYY-MM-DD`. Gli esperimenti sulla fonte ufficiale usano soltanto gli ID
della finestra completata: copie manuali dello stesso evento con ID diversi
non sono mescolate. L'archivio completo resta consultabile separatamente.
Una risposta incompatibile non sovrascrive estrazioni già presenti.

## Date e previsioni

La data del concorso è conservata con precisione `date`, a mezzanotte
Europe/Rome come riferimento. Non è un orario osservato. Le previsioni emesse
nel giorno del risultato possono essere non valutabili automaticamente;
la UI distingue questo caso dalle previsioni in attesa. Nessun orario viene
inventato per far risultare valida una previsione retrospettiva.

## ZIP storico

Lo ZIP collegato dalla pagina ufficiale rimane su
`https://www.brightstarlottery.it/STORICO_ESTRAZIONI_LOTTO/storico01-oggi.zip`.
Il dominio è nella bozza di configurazione ma non ancora nella rete attiva:
il download restituisce 403. Il parser ZIP esistente rimane non verificato
sul file reale e non viene usato come fallback. Lo storico più ampio richiede
una fonte accessibile e verificata: la nuova API non promette 1.000 concorsi.

La prova tecnica precedente su quattro concorsi è descritta in
[real-data-validation.md](real-data-validation.md). Nessuno di questi controlli
dimostra capacità predittiva o vantaggio sul caso.
