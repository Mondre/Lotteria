# Pubblicazione su Render con database Neon

Questa configurazione non richiede un disco Render. Il database è esterno e
non viene cancellato da un deploy del servizio web. Non sono stati creati o
modificati servizi negli account dell'utente. Controllare limiti e disponibilità
dei piani gratuiti nelle due dashboard prima di confermare.

## 1. Neon

1. Accedere a Neon e creare un nuovo progetto, per esempio `lottopredict`.
2. Scegliere una regione europea, preferibilmente la stessa regione usata
   dal servizio Render (per esempio Frankfurt se disponibile in entrambi).
3. Nel progetto aprire **Connect**, selezionare database e ruolo del progetto
   e abilitare **Connection pooling** se offerto.
4. Copiare la connection string PostgreSQL completa fornita da Neon.
   È una credenziale: inserirla solo nel campo segreto `DATABASE_URL` di Render.
   Non inviarla in chat, non salvarla in GitHub, `render.yaml` o nel sorgente.

L'app richiede un URL `postgresql://...` o `postgres://...`. Preservare i
parametri forniti da Neon, incluso `sslmode`. Per host remoti il driver impone
TLS con verifica del certificato e del nome host (`verify-full`, CA di sistema).
Il ruolo deve poter creare tabelle, indici, funzioni e trigger nel database
dedicato. L'app inizializza lo schema al primo avvio e controlla la versione.

## 2. Repository GitHub

Render deve leggere la versione aggiornata del codice dal repository
`Mondre/Lotteria`. La pubblicazione dell'ambiente Codex non equivale a un push
su GitHub. Prima del deploy verificare nel ramo selezionato la presenza di
`database/postgres.py`, `database/postgres_schema.sql`, `web/app.py`,
`requirements-web.txt` e `render.yaml`.
Non caricare `.venv`, database SQLite, file `.env` o credenziali.

## 3. Render: nuovo Web Service

Usare un **nuovo servizio** per non modificare gli altri siti già presenti.
È possibile importare `render.yaml` con **New → Blueprint** oppure creare
un Web Service collegando il repository e impostando:

| Campo | Valore |
|---|---|
| Runtime | Python |
| Root Directory | Vuota, se i file sono nella radice del repository |
| Build Command | `pip install -r requirements-web.txt` |
| Start Command | `uvicorn web.app:create_app --factory --host 0.0.0.0 --port $PORT --workers 1` |
| Health Check Path | `/api/health` |
| Instance Type | Free, se disponibile e sufficiente |
| Region | Stessa regione europea del database, quando possibile |

**Non aggiungere un disco e non creare un database Render.**

Variabili in **Environment**:

| Nome | Valore |
|---|---|
| `DATABASE_URL` | Connection string di Neon, campo segreto |
| `LOTTOPREDICT_WEB_USERNAME` | Username scelto per accedere al sito, senza `:` |
| `LOTTOPREDICT_WEB_PASSWORD` | Password privata di almeno 12 caratteri, preferibilmente generata da un password manager |
| `PYTHON_VERSION` | `3.12.14` |
| `OPENBLAS_NUM_THREADS` | `1` |
| `OMP_NUM_THREADS` | `1` |

L'username/password proteggono il sito e tutte le API dati. È un accesso
personale condiviso, non un sistema multiutente. Il browser mostra il dialogo
di autenticazione. Per cambiare accesso aggiornare le variabili e riavviare.

`LOTTOPREDICT_DATA_DIR` non è necessario per il database remoto. Non configurare
`LOTTOPREDICT_ALLOWED_HOSTS=*`: il dominio Render viene riconosciuto
automaticamente. Per un dominio personalizzato impostare questa variabile
con l'hostname aggiuntivo, senza `https://` né `/`.

## 4. Deploy e verifica

Salvare le variabili e avviare il deploy. Quando risulta **Live**, aprire
l'URL HTTPS effettivamente assegnato da Render e inserire le credenziali del sito.

Verificare:

1. Senza credenziali il sito chiede autenticazione; `/api/health` restituisce
   soltanto `{"status":"ok"}` senza login, per i controlli Render.
2. In Impostazioni è indicato PostgreSQL. Non vengono mostrati DSN o password.
3. Caricare il demo sintetico, controllare archivio e analisi.
4. Dopo un riavvio/deploy del servizio, il numero di estrazioni resta invariato.

L'app non usa SQLite su Render se manca `DATABASE_URL`: si arresta con un
messaggio di configurazione, così non dà una falsa impressione di persistenza.
Un errore TLS o di accesso non attiva fallback o disabilita verifiche.

## Limiti e dati esistenti

- I piani gratuiti possono sospendere app e database inattivi: il primo accesso
  può richiedere tempo. Quote e condizioni possono cambiare.
- Render free non è un sistema di elaborazione durevole per lavori lunghi:
  un riavvio può interrompere un calcolo. Tenere un solo worker; la coda e i
  risultati non salvati sono in memoria e non vengono recuperati al riavvio.
- Estrazioni, registro, previsioni salvate e relative corrispondenze sono invece
  persistenti su Neon. Esportare i risultati degli esperimenti prima di riavviare.
- Il pool dell'app usa al massimo tre connessioni e le importazioni riusano una
  transazione per archivio. I limiti delle righe rimangono quelli documentati.
- Gli archivi SQLite preesistenti **non vengono copiati automaticamente**.
  Desktop e CLI restano su SQLite locale; per il sito importare i propri file
  tramite la UI web. Non eliminare i vecchi database senza una migrazione verificata.
- Nessuna fonte reale, regola ufficiale o capacità predittiva diventa verificata
  in conseguenza della pubblicazione.

## Test di sviluppo PostgreSQL

Usare solo un database di test dedicato, mai quello di produzione.
Impostare `LOTTOPREDICT_TEST_DATABASE_URL` nel processo di test e avviare:

```sh
python -m unittest tests.test_postgres -v
```

Ogni test crea e rimuove uno schema isolato. Sono verificati riapertura del
database, importazione di 1.000 demo, duplicati concorrenti, rollback, previsioni
immutabili e valutazione dopo l'arrivo del risultato. I test PostgreSQL sono
esplicitamente saltati se la variabile non è configurata.
