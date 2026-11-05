# Distribuzione delle combinazioni: copertura e capacità predittiva

## Opzione aggiunta

In **Previsioni AI** e **Test combinazioni**, `Numeri disgiunti` produce lo stesso
numero di combinazioni, ma non riusa un numero in due combinazioni del gruppo.
Con cinque cinquine Lotto copre 25 numeri distinti. Il modello e il seed rimangono
selezionabili. Il primo ticket usa ancora il ranking; gli altri campionano dai
numeri rimasti, con gli stessi punteggi relativi del modello.

L'opzione standard **Ponderata** resta predefinita e il suo algoritmo/RNG non
cambia. Le vecchie previsioni e i rapporti non vengono riscritti. La strategia
è registrata nei parametri, nello snapshot, nella versione del generatore e
nel risultato; si ripristina riaprendo gli esperimenti. La versione standard
rimane `1`, quella disgiunta è `2-disjoint`.

La modalità disgiunta è possibile solo se ci sono abbastanza numeri: massimo
18 cinquine Lotto (90/5), 15 sestine SuperEnalotto (90/6), ecc. Non vengono
aggiunte giocate per riempire un budget: il numero richiesto resta invariato.
Richieste incompatibili vengono rifiutate prima di scaricare dati.

## Che cosa migliora

A parità di combinazioni aumenta il numero di numeri distinti coperti. Sotto
estrazioni uniformi, se l'unione delle combinazioni contiene U numeri, la
probabilità di almeno una corrispondenza nell'intero gruppo è:

`1 - C(N-U,k)/C(N,k)`

con popolazione N e k numeri estratti. La formula è verificata anche per
enumerazione completa su un gioco di test piccolo. Per cinque cinquine
Lotto disgiunte U=25 e la probabilità teorica è circa 81,21%. Nel primo test
Bari, la strategia standard aveva U medio=22 e probabilità media circa 76,14%.
Sono probabilità di **almeno un numero nell'intero gruppo**, non probabilità
di vincita economica, ambo, cinquina o redditività.

L'attesa di corrispondenze **per singola combinazione** rimane k²/N sotto il caso
uniforme. Coprire più numeri non crea informazione sull'estrazione successiva,
non calibra i punteggi e può peggiorare altri obiettivi o concentrare diversamente
le corrispondenze. Non esiste una garanzia di miglioramento degli ambi.

## Test equo

La baseline del test delle combinazioni applica **la stessa strategia** del
modello. Con la modalità disgiunta entrambi hanno 25 numeri diversi; confrontare
un modello disgiunto solo con un casuale sovrapposto confonderebbe copertura e
capacità di scegliere numeri. Gli stessi controlli temporali restano validi:
il target non entra nel training. Numero di combinazioni, seed e finestre sono
registrati. Il rapporto aggiunge la copertura media per concorso.

API: `ticket_strategy` vale `weighted` (default) o `disjoint`, per generate o
backtest con `evaluation_mode=tickets`. La CLI `machine_learning.cli generate`
accetta `--ticket-strategy disjoint`. La GUI desktop mantiene il comportamento
standard; questa selezione è aggiunta nel web e nella CLI.

## Confronto locale del 5 novembre 2026

Protocollo fissato prima di leggere i risultati: modello `frequency`, seed 42,
5 combinazioni per ciascuna delle ultime 100 estrazioni di Cagliari, Firenze,
Genova, Milano, Napoli, Palermo, Torino, Venezia e Nazionale. Nove ruote non
usate nel primo confronto Bari; esclusa anche Roma, già usata in altre prove.
Stessa finestra di 500 estrazioni e training minimo 350. Il periodo dei target
è 14 maggio–3 novembre 2026, sul database ufficiale di validazione già presente.
Nessun nuovo download e nessuna modifica al database dell'utente.

| Misura | Modello standard | Modello disgiunto | Casuale standard | Casuale disgiunto |
|---|---:|---:|---:|---:|
| Numeri distinti medi nel gruppo | 21,99 | 25 | 22,45 | 25 |
| Concorsi con almeno una corrispondenza / 900 | 682 | 728 | 702 | 735 |
| Concorsi con almeno due corrispondenze / 900 | 114 | 99 | 90 | 103 |
| Concorsi con almeno tre corrispondenze / 900 | 5 | 1 | 2 | 6 |
| Corrispondenze medie per combinazione | 0,28089 | 0,27311 | 0,27600 | 0,27756 |

Ogni colonna valuta 4.500 combinazioni; le soglie per concorso sono cumulative.
La copertura e la frequenza di almeno una corrispondenza migliorano. In questo
campione **gli ambi del modello peggiorano** rispetto alla strategia standard;
non è dimostrata maggiore accuratezza del modello rispetto al suo casuale.
Per questo la nuova strategia resta opzionale e non viene promossa come più
accurata. Il test non è prospettico, non certifica indipendenza fra ruote né
premi, e non si selezionano parametri a posteriori per ottenere un esito favorevole.
Una validazione prospettica richiede nuove estrazioni non ancora osservate.
