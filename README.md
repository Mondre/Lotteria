# Lotteria

## LottoPredict AI

Applicazione Python 3.12+ / PySide6 per analisi sperimentali dei giochi a
estrazione. Non presuppone schemi prevedibili e non promette vincite.
I punteggi dei modelli **non sono probabilità di vincita**.

## Versione web

La nuova interfaccia browser riutilizza database, importazione, statistiche,
modelli e backtesting del desktop. Non richiede PySide6 e non scarica risorse
da CDN. Include dashboard responsive, filtri per gioco/variante/ruota,
archivi reali e sintetici separati, importazione CSV/Excel/JSON, analisi,
pattern, Monte Carlo, combinazioni, previsioni immutabili, confronto con il
caso e registro. I calcoli usano una coda in background.

```sh
python -m pip install -r requirements-web.txt
python web_main.py
```

Su Windows si può usare `start_web.bat` dopo l'installazione delle dipendenze
nel virtualenv. Il server ascolta **solo sul computer locale**, porta 8000;
aprire nel browser del medesimo computer l'indirizzo `http://127.0.0.1:8000`.
È possibile scegliere un'altra porta con `--port`.

Nel cloud o per tenere un archivio web distinto dal desktop:

```sh
.venv/bin/python web_main.py --data-dir /workspace/shared/lottopredict-web
```

Per condividere l'archivio desktop indicare la stessa directory dati usata dal
desktop. Il demo si carica solo premendo il relativo pulsante: aggiunge 1.000
estrazioni sintetiche Lotto/Roma, senza modificare dati reali. Le importazioni
sono parziali e riportano righe aggiunte, duplicate e rifiutate. Le date nella
UI sono visualizzate nel fuso Europe/Rome.

La coda esegue una sola operazione per volta e accetta al massimo quattro
operazioni in attesa/esecuzione. Conserva gli ultimi 20 risultati in memoria,
che scadono al riavvio. Esportare in JSON i risultati da conservare. Estrazioni,
registri e previsioni salvate rimangono invece nel database configurato. Una previsione può
essere salvata solo da una generazione completata sul server, con ID e data
futura; il browser non può sostituirne arbitrariamente il payload.

La versione locale usa SQLite. La versione web sceglie PostgreSQL quando
`DATABASE_URL` è impostata e rifiuta di ripiegare su SQLite in caso di errore.
Su Render PostgreSQL e accesso protetto sono obbligatori. In locale l'accesso
si può attivare impostando `LOTTOPREDICT_WEB_USERNAME` e
`LOTTOPREDICT_WEB_PASSWORD` (almeno 12 caratteri). Il browser chiede le credenziali
con il dialogo HTTP Basic; online si usa esclusivamente HTTPS.
Il server controlla host e origine delle scritture. Render fornisce il proprio
dominio tramite `RENDER_EXTERNAL_HOSTNAME`, accettato automaticamente;
per domini aggiuntivi usare `LOTTOPREDICT_ALLOWED_HOSTS`, senza schemi o percorsi.
La configurazione di deploy è descritta in [docs/render-neon.md](docs/render-neon.md).
Non è ancora stato eseguito un deploy su un account Render/Neon reale.
Non è presente un connettore remoto arbitrario nella UI web; la CLI resta locale.

Test web (non richiedono un server avviato):

```sh
python -m pip install -r requirements-web-test.txt
python -m unittest tests.test_web -v
```

Per ripetere la verifica browser opzionale, installare Playwright e Chromium,
avviare il server con una directory dati di test e usare
`python tests/browser_smoke.py --chromium /percorso/chromium`.
Il test aggiunge solo dati sintetici e salva schermate in `/tmp/lottopredict-browser`;
`--url` e `--output` permettono di cambiare destinazione e cartella degli output.

Verificati anche in Chromium: dashboard vuota e demo, analisi, combinazioni,
backtesting, registro e layout mobile. La verifica PySide6 menzionata sotto
riguarda esclusivamente l'interfaccia desktop.

## Stato e limiti

Implementati: database SQLite con migrazioni, validazione, importazioni
CSV/Excel/JSON, connettore HTTPS configurabile, statistiche, simulazioni,
modelli ML, combinazioni, backtesting e registro di previsioni immutabili.
La GUI comprende le nove sezioni richieste; importazioni e calcoli pesanti
usano thread di background. I servizi sono utilizzabili anche da terminale.

**La GUI desktop non è stata eseguita:** PySide6 non è installato e il test
desktop viene esplicitamente saltato in sua assenza. Il precedente problema
di installazione non riguarda il nuovo workflow web, verificato in Chromium.
La verifica delle fonti ufficiali e l'acquisizione di dati reali restano da completare.
Le regole incluse sono preliminari (`verified: false`).
XGBoost e il pacchetto Windows non sono stati verificati.

## Installazione e avvio

Windows 10/11, Python 3.12 a 64 bit, terminale nella cartella del progetto:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

In seguito usare `start.bat`. Su Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

Qt richiede una sessione grafica e le librerie native della piattaforma.
Il database viene creato fuori dal checkout in `%LOCALAPPDATA%\LottoPredictAI`
su Windows, `~/.local/share/LottoPredictAI` sugli altri sistemi.
`LOTTOPREDICT_DATA_DIR` permette di cambiare percorso. Nel cloud:

```sh
export LOTTOPREDICT_DATA_DIR=/workspace/shared/lottopredict
.venv/bin/python main.py
```

Non occorre un server esterno. Il registro applicativo JSON ruota automaticamente;
il registro delle operazioni è persistente in SQLite.

## Regole e archivi

`config/games.json` configura Lotto (ruote separate), SuperEnalotto,
10eLotto (modalità separate), Win for Life Classico con Numerone e MillionDAY.
Le regole **non sono verificate presso fonti ufficiali** e non modellano tutte
le varianti, i premi, le opzioni o le evoluzioni storiche dei regolamenti.
Gli extra richiesti dalla variante devono essere presenti nell'archivio.
Analisi e generazione attualmente riguardano **solo i numeri principali**,
escludendo extra e Numerone; le combinazioni non sono giocate complete.

L'inserimento manuale rifiuta numeri fuori intervallo, duplicati interni, varianti
sconosciute, ruote errate, date future e date senza fuso.
Gli identificativi sono univoci per gioco/variante/ruota/tipo di archivio.
Duplicati identici non vengono aggiunti; contenuti incompatibili sono rifiutati,
senza sovrascrivere. Dati reali e sintetici sono sempre separati.

GUI, `main.py --check` e importatore CLI accettano `--rules percorso/regole.json`.
Le CLI scientifiche utilizzano attualmente la configurazione predefinita.

## Importazioni e aggiornamento

Nell'Archivio scegliere **Importa file / aggiorna da fonte configurabile**.
Nella versione web **Importa archivio → Controlla file** esegue prima
un'anteprima senza salvare estrazioni o log. Sono contate nuove righe,
duplicati identici, conflitti e righe non valide, anche all'interno dello
stesso file. Si vedono le prime 20 righe e fino a 100 errori. Solo
**Conferma importazione** salva le righe valide; l'archivio viene ricontrollato
per gestire eventuali modifiche nel frattempo. Un checksum impedisce di
confermare per errore un file diverso da quello esaminato.

Il dialogo offre un modello CSV vuoto: non contiene estrazioni dimostrative
che possano essere scambiate per dati reali. In **Archivio estrazioni** sono
disponibili anche **Inserisci estrazione** (con fonte, data e ora ISO con fuso,
eventuali extra) ed **Esporta selezione JSON** (fino a 10.000 righe della
serie filtrata). L'export contiene il flag sintetico, così una successiva
importazione non può scambiare il demo per dati reali. Non è un backup
completo del database: non comprende previsioni e log.

Formati: CSV UTF-8 con virgola, punto e virgola o tab; XLSX (primo foglio);
JSON (lista di oggetti). Intestazioni:

| Campo | Formato |
|---|---|
| game | Nome configurato, es. `Lotto` |
| variant | Variante, es. `ordinario` |
| draw_id | Identificativo testuale, anche in Excel |
| occurred_at | Testo ISO con fuso, es. `2025-01-01T20:00:00+01:00` |
| numbers | Lista JSON di interi oppure testo `1 2 3 4 5` |
| wheel | Ruota Lotto; vuoto per gli altri giochi |
| extras | Oggetto JSON, es. `{"numerone": 5}` per Win for Life |
| synthetic | Facoltativo; booleano oppure testo `true`/`false` |

I primi cinque campi sono obbligatori; ruota ed extra quando richiesti dalla
variante. Le date Excel devono essere testo ISO con fuso: non si inventa un
fuso per celle data native. Campi opzionali sconosciuti vengono ignorati;
intestazioni duplicate, chiavi JSON duplicate e celle CSV oltre le
intestazioni vengono rifiutate per evitare interpretazioni ambigue.

L'importazione è **parziale**: salva le righe valide e registra gli errori per
riga. Il rapporto distingue aggiunte, duplicati e rifiuti. Limiti: 25 MiB,
100.000 righe, XLSX decompresso massimo 100 MiB. I dati marcati sintetici non
possono essere importati nell'archivio reale.

```sh
python -m data_sources.cli --file archivio.csv
python -m data_sources.cli --file examples/synthetic_lotto_roma.json --synthetic
```

Codici uscita: 0 elaborato; 2 righe rifiutate, con possibile importazione parziale;
1 errore generale. Il demo incluso contiene **1.000 estrazioni uniformi
sintetiche Lotto/Roma**, senza corrispondenza con un calendario reale.
Rigenerazione: `python -m data_sources.synthetic nuovo_demo.json --seed 42`.

Il connettore accetta un URL HTTPS autorizzato in uno dei formati normalizzati:
inserirlo nella GUI oppure usare `--url URL --format json` nell'importatore.
Non esistono fonti ufficiali preconfigurate, URL inventati o scraping di pagine.
Il connettore importa l'archivio disponibile e non garantisce che la fonte
fornisca 1.000 estrazioni per ogni gioco. Non inserire credenziali negli URL.
Il dominio deve essere consentito dalla configurazione di rete del cloud.

## Analisi statistiche

- Frequenze assolute e per estrazione, finestre 10/25/50/100/250/500/1000,
  attesa teorica, deviazione standard, Z e IC marginali Wilson al 95%.
- Ritardi attuali, massimi osservati, distribuzione e media degli intervalli
  completati, confronto con media geometrica teorica. Intervalli ai bordi
  censurati esclusi dalla media. Un ritardo alto non aumenta la probabilità futura.
- Coppie/terzine: test binomiali unilaterali e correzione Holm su tutte le
  combinazioni della famiglia, comprese quelle non osservate.
- Somma, pari/dispari, alto/basso, fasce, consecutivi, distanze e ripetizioni.
- Cambiamenti tra due metà (Fisher) e sovrapposizioni a lag 1/2/5/10 con 199
  permutazioni riproducibili. Famiglie Holm separate. Non è una ricerca
  esaustiva di periodicità. Test temporali limitati a serie da 20 a 10.000 righe.
- Monte Carlo: 100.000–1.000.000 di estrazioni uniformi senza reinserimento,
  seed configurabile, confronto di media/varianza delle somme con la teoria.

Non si mescolano serie incompatibili. Gli IC marginali non sono simultanei.
I test binomiali assumono indipendenza sotto il nullo; le correzioni non
comprendono tutti i possibili esperimenti o run successivi.

```sh
python -m lotto_statistics.cli --game Lotto --variant ordinario --wheel Roma --synthetic --limit 1000
python -m lotto_statistics.cli --game Lotto --variant ordinario --monte-carlo --samples 100000 --seed 42
```

GUI: tabelle ordinabili, esportazione JSON, grafici Matplotlib con zoom, pan e
salvataggio. CLI: risultati JSON, conservabili con redirezione del terminale.

## Modelli, previsioni e backtesting

Modelli: `uniform`, `frequency` (regolarizzata verso la frequenza teorica),
`temporal` (ultime 50 estrazioni), `logistic`, `random_forest`,
`gradient_boosting`, `ensemble`. Per `xgboost` installare `requirements-optional.txt`.

I supervisionati richiedono almeno 40 estrazioni. Feature: ultima estrazione e
frequenze mobili 10/25/50; target sempre successivo alle feature.
Gli iperparametri sono fissi, senza ricerca automatica sul test. I punteggi di
inclusione non sono calibrati.

L'ensemble richiede almeno 100 estrazioni e valuta frequenze, temporale e
logistica su almeno 30 target interni, in ordine cronologico. Usa solo candidati
con vantaggio significativo sul caso, corretto Holm; i pesi sono proporzionali
al vantaggio misurato. In assenza di candidati ammessi torna al caso uniforme.

```sh
python -m machine_learning.cli generate --game Lotto --variant ordinario --wheel Roma --synthetic --model frequency --combinations 5
python -m machine_learning.cli backtest --game Lotto --variant ordinario --wheel Roma --synthetic --initial 700 --model temporal
```

Il walk-forward confronta sempre uniforme e frequenze oltre al modello scelto.
Ogni run è limitato a 5.000 target per contenere il costo dei test esatti.
Training espansivo o `--train-window`; riaddestramento `--retrain-every` (default
10); previsione di ogni target usando solo il passato. Le date devono essere
strettamente crescenti. Il confronto riporta media, distribuzione corrispondenze,
differenze dal caso teorico e campionato, stabilità tra due metà, IC bootstrap
iid descrittivi, test esatto della somma di ipergeometriche sotto il nullo
uniforme indipendente, correzione Holm tra modelli del run. Dipendenze temporali
possono invalidare gli IC iid. Non scegliere parametri dopo aver osservato il
test. Ensemble e riaddestramenti ML frequenti possono essere costosi.

Il generatore produce combinazioni distinte dei numeri principali: prima dal
ranking con ex aequo casuali, poi da campionamento pesato. Il punteggio relativo
non è probabilità di vincita. La generazione segnala la mancanza di validazione
associata: non eredita risultati da un backtest diverso.

Per salvare una previsione indicare ID e data futura nella GUI oppure aggiungere
`--target-id ID --target-date DATA_ISO` al comando generate. Ogni versione
conserva hash dello storico e delle regole, modello, seed e combinazioni.
Non si salva su un risultato già presente. Trigger del database impediscono modifica
e cancellazione di previsioni e risultati. Importando l'estrazione con ID/data
esattamente corrispondenti vengono registrate le corrispondenze.
Lo storico è consultabile nella GUI. Il nuovo training è manuale e le vecchie
previsioni non vengono riscritte.

## Test e packaging

```sh
python -m unittest discover -s tests -v
python main.py --check
QT_QPA_PLATFORM=offscreen python main.py --smoke-test
```

Il terzo comando è per Linux headless e richiede Qt installato. I test coprono
regole, persistenza, importazioni, statistiche, simulazioni, leakage, baseline,
ensemble e immutabilità; i dati sono sintetici e temporanei. Il test GUI è
saltato esplicitamente se Qt manca. Nel cloud limitare il parallelismo con
`OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2`.

Su Windows installare `requirements-dev.txt` e avviare `build_windows.bat`.
Output: `dist\LottoPredictAI\LottoPredictAI.exe`, con regole JSON incluse.
PyInstaller deve essere eseguito e verificato su Windows, non da Linux.

## Architettura e lavoro restante

`main.py`, `ui/`, `database/`, `games/`, `data_sources/`, `lotto_statistics/`,
`machine_learning/`, `predictions/`, `backtesting/`, `visualizations/`, `tests/`,
`config/`. `lotto_statistics` evita di oscurare il modulo standard `statistics`.
Dominio e servizi non importano Qt e sono riutilizzabili via web.

Prima di considerare completo il prodotto: ripristinare rete e verificare GUI;
verificare fonti e regole ufficiali, incluse le evoluzioni storiche; aggiungere
connettori specifici per archivi reali; analizzare extra e varianti aggiuntive;
arricchire la dashboard analitica, integrare Plotly/Pandas dove utile;
verificare XGBoost e packaging Windows. Acquisizione attuale tramite librerie
standard HTTPS, non ancora Requests/BeautifulSoup.
I test sintetici verificano il software, non capacità predittiva su dati reali.
