# Prova funzionale con estrazioni reali — 4 novembre 2026

È stato individuato un servizio pubblico usato dagli script della pagina
https://www.lotto-italia.it/lotto/estratti-ruote, sul dominio già consentito.
Non è una replica del file ZIP bloccato: fornisce risultati di singoli concorsi
ed è distinto dal connettore storico presente nell'app.

Servizi effettivamente consultati via HTTPS, con POST di sola lettura:

- `/gdl/estrazioni-e-vincite/calendario-estrazioni-del-lotto.json`
  con anno e mese, come nel codice del sito;
- `/gdl/estrazioni-e-vincite/estrazioni-del-lotto.json`
  con la data del concorso nel formato `YYYYMMDD`.

## Esito osservato

Quattro concorsi (29, 30 e 31 ottobre e 3 novembre 2026), undici ruote ciascuno:
**44 estrazioni reali**, validate e usate solo in un database temporaneo eliminato
a fine prova. Nessun archivio dell'utente è stato modificato.

Verificati: anteprima senza scrittura, importazione di 33 righe di training,
analisi della serie Roma, generazione di due combinazioni dei soli numeri
principali, inserimento delle 11 righe obiettivo, corrispondenze calcolate
correttamente, immutabilità, seconda importazione con 44 duplicati e zero
nuove righe, separazione dal sintetico e riapertura del database.

La valutazione è un **replay storico tecnico**, non una previsione emessa prima
del concorso: esclusivamente nel database temporaneo l'orologio del salvataggio
viene simulato dodici ore prima della data obiettivo. Non è una validazione
prospettica, una prova di vantaggio sul caso o un controllo statistico su uno
storico sufficiente. Tre concorsi di training non validano alcun modello.
La fonte fornisce una data di concorso: l'app conserva `date_precision=date`
e non tratta la mezzanotte di riferimento come ora osservata.

## Ripetizione

Dalla radice del repository, con le dipendenze web installate:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/validate_official_sample.py
```

Lo script legge al massimo due calendari e quattro concorsi recenti, controlla
date e completezza delle ruote, usa sempre un database temporaneo e restituisce
un rapporto JSON con gli SHA-256 delle risposte. Non espone un percorso per
scrivere nel database personale. Non è eseguito dai test offline o all'avvio
web. La disponibilità dei servizi futuri e la profondità dello storico non
sono garantite da questa prova.

Al momento di questa prova del 4 novembre il connettore automatico non era ancora
implementato. Il 5 novembre è stato aggiunto il recupero progressivo e verificato
su 500 concorsi completi, senza modifiche alla rete o instradamenti alternativi:
[official-api-sync.md](official-api-sync.md). Lo ZIP Brightstar resta bloccato.
