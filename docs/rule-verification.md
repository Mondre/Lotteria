# Verifica delle regole — 4 novembre 2026

Il controllo riguarda il **formato dei numeri principali** confrontato con pagine
ufficiali del concessionario, non una certificazione del regolamento completo.
`verified` resta `false`: premi, opzioni, extra e validità storica non sono stati
convalidati. La pagina Impostazioni mostra fonti, data, ambito e limiti per variante.
Non è stato modificato il formato degli archivi già salvati.

| Gioco / varianti | Controllo effettuato | Fonte consultata |
|---|---|---|
| Lotto ordinario | 5 numeri da 1 a 90; elenco delle 11 ruote attuali | https://www.lotto-italia.it/lotto/come-si-gioca/ruote-del-lotto |
| 10eLotto, tre modalità | Ventina di numeri da 1 a 90; modalità distinte ogni 5 minuti, legata al Lotto, immediata | https://www.lotto-italia.it/10-e-lotto/come-si-gioca |
| MillionDAY ordinario | 5 numeri da 1 a 55 | https://www.lotto-italia.it/millionday/come-giocare |
| SuperEnalotto | Non verificato: il proxy rifiuta `www.superenalotto.it` (403) | Nessuna pagina consultabile |
| Win for Life Classico | Non verificato: il proxy rifiuta `www.winforlife.it` (403) | Nessuna pagina consultabile |

Le prime tre pagine sono state scaricate via HTTPS durante questa verifica.
Le informazioni di controllo sono conservate in `review` nelle rispettive
regole di `config/games.json`, disponibili anche tramite `/api/config`.
I campi verificati sono espliciti: la mancata presenza di extra nella configurazione
non significa che il gioco ufficiale ne sia privo.

## Limiti da conservare nell'uso

- Lotto: Numero Oro, Simbolotto, Ambetto, Lotto Più e premi esclusi.
  La pagina ufficiale data l'introduzione della Ruota Nazionale al 4 maggio 2005;
  l'app non verifica automaticamente le regole vigenti all'epoca di ogni estrazione.
- 10eLotto: Numero Oro, Doppio Oro, Extra e Special Time esclusi. Nessuna
  ricostruzione automatica della ventina dai primi due estratti delle ruote:
  usare il risultato ufficiale della modalità corretta.
- MillionDAY: Extra e premi esclusi; concorsi distinti devono avere ID e
  orari distinti. Il software non deduce concorsi o calendario dalla sola data.
- SuperEnalotto e Win for Life: conservata la configurazione preliminare,
  inclusi Jolly/SuperStar e Numerone; nessuna nuova conferma di regole o extra.

La generazione produce solo numeri principali e non rappresenta una giocata
completa delle opzioni. Il controllo del formato non dimostra capacità predittiva.
Non si estende la verifica dei giochi accessibili a quelli bloccati.
