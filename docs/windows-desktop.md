# Verifica desktop e pacchetto Windows

Il 4 novembre 2026 sono stati eseguiti su Linux con Qt offscreen: apertura delle
finestre desktop, inserimento manuale, analisi di un archivio sintetico in un
thread Qt e rendering dei grafici Matplotlib. Questo controllo non equivale
all'esecuzione di un file `.exe` su Windows.

## Windows locale

Usare Python 3.12 a 64 bit, poi dalla cartella del progetto:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m unittest tests.test_ui -v
build_windows.bat
```

Lo script crea `dist/LottoPredictAI/LottoPredictAI.exe` e avvia la verifica del
pacchetto. La cartella `LottoPredictAI` va distribuita interamente: l'eseguibile
non è autonomo rispetto ai file `_internal`. Il pacchetto non è firmato.

`scripts/check_windows_package.py` avvia il pacchetto fuori dal checkout,
con database e directory di lavoro temporanei, esegue `--check` e
`--smoke-test` con timeout e controlla l'integrità del database. Non usa archivi
personali. Un errore di build o verifica produce un codice di uscita non zero.

## Verifica su GitHub Actions

È predisposto `.github/workflows/windows-desktop.yml`, avviabile manualmente
con **Actions → Verifica desktop Windows → Run workflow** dopo aver pubblicato
il file sul repository. Installa Python 3.12, esegue i test, crea il pacchetto,
lo verifica e conserva un artefatto scaricabile per 7 giorni. Il workflow ha
sola lettura sul repository e non pubblica release o siti. Non è ancora stato
eseguito su Windows: il risultato va verificato quando sarà disponibile.

I test PostgreSQL richiedono un database dedicato e vengono saltati quando
`LOTTOPREDICT_TEST_DATABASE_URL` non è impostata. La verifica manuale finale
su Windows deve includere apertura visibile, leggibilità, importazione di un
file e scrittura/esportazione in una cartella utente.
