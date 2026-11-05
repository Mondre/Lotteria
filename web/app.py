import base64
import binascii
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
import json
import hashlib
import os
import secrets
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, StrictInt, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from database.factory import create_store
from database.store import Store
from data_sources.sync import Synchronizer, KEY as LOTTO_SOURCE_KEY
from games.rules import RuleRegistry
from web.jobs import Jobs

STATIC = Path(__file__).parent / "static"
ModelName = Literal["uniform", "frequency", "temporal", "logistic", "random_forest", "gradient_boosting", "ensemble"]


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    game: str = "Lotto"
    variant: str = "ordinario"
    wheel: str = "Roma"
    synthetic: bool = False
    limit: int = Field(default=1000, ge=1, le=10000)
    official_only: bool = False


class Experiment(Selection):
    operation: Literal["analyze", "generate", "backtest", "simulate"]
    model: ModelName = "frequency"
    models: list[ModelName] | None = Field(default=None, max_length=7)
    combinations: int = Field(default=5, ge=1, le=100)
    initial: int = Field(default=700, ge=2, le=9999)
    train_window: int | None = Field(default=None, ge=2, le=10000)
    retrain_every: int = Field(default=10, ge=1, le=1000)
    seed: int = Field(default=42, ge=0, le=2147483647)
    auto_update: bool = True
    evaluation_mode: Literal["single", "tickets"] = "single"
    test_targets: int = Field(default=100, ge=1, le=200)

    @model_validator(mode="after")
    def validate_models(self):
        if self.evaluation_mode == "tickets":
            if self.operation != "backtest" or self.models is not None:
                raise ValueError("La verifica combinazioni richiede backtest e un solo modello")
            if self.test_targets * self.combinations > 2000:
                raise ValueError("Massimo 2.000 combinazioni per run: ridurre target o combinazioni")
            if self.initial + self.test_targets > self.limit:
                raise ValueError("La finestra deve contenere training iniziale e tutti i target richiesti")
        if self.models is not None:
            if self.operation != "backtest":
                raise ValueError("Il confronto multimodello è disponibile solo per il backtesting")
            if len(set(self.models)) != len(self.models):
                raise ValueError("Selezionare ogni modello una sola volta")
        if self.operation == "backtest":
            from machine_learning.models import minimum_history
            required = minimum_history(self.models if self.models is not None else [self.model])
            if min(self.initial, self.train_window or self.initial) < required:
                raise ValueError(f"Servono almeno {required} estrazioni per il training dei modelli selezionati")
        return self


class SavePrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    target_id: str = Field(min_length=1, max_length=200)
    target_date: datetime


class ManualDraw(BaseModel):
    model_config = ConfigDict(extra="forbid")
    game: str
    variant: str
    wheel: str = ""
    synthetic: bool = False
    draw_id: str = Field(min_length=1, max_length=200)
    occurred_at: AwareDatetime
    numbers: list[StrictInt] = Field(min_length=1, max_length=90)
    extras: dict[str, StrictInt] = Field(default_factory=dict)
    source: str = Field(min_length=1, max_length=200)



def create_app(store: Store | None = None, allowed_hosts: list[str] | None = None,
               synchronizer: Synchronizer | None = None) -> FastAPI:
    username = os.environ.get("LOTTOPREDICT_WEB_USERNAME", "")
    password = os.environ.get("LOTTOPREDICT_WEB_PASSWORD", "")
    public = os.environ.get("RENDER") == "true"
    if bool(username) != bool(password) or (public and not (username and password)):
        raise ValueError("Configurare LOTTOPREDICT_WEB_USERNAME e LOTTOPREDICT_WEB_PASSWORD prima dell'avvio")
    if username and (":" in username or len(password) < 12):
        raise ValueError("Username senza ':' e password di almeno 12 caratteri richiesti")
    hosts = list(allowed_hosts) if allowed_hosts is not None else os.environ.get("LOTTOPREDICT_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
    if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
        hosts.append(os.environ["RENDER_EXTERNAL_HOSTNAME"])
    hosts = [host.strip() for host in hosts if host.strip()]
    if public and "*" in hosts:
        raise ValueError("Su Render configurare host espliciti, non '*'")
    store = store or create_store()
    synchronizer = synchronizer or Synchronizer(store, enabled=os.environ.get("LOTTOPREDICT_OFFICIAL_SYNC_ENABLED") == "true")
    jobs = Jobs(store)
    from football.routes import register

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            jobs.pool.shutdown(wait=True)
            store.close()

    app = FastAPI(title="LottoPredict AI", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.store, app.state.jobs = store, jobs
    app.state.synchronizer = synchronizer
    register(app, store, jobs)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    @app.middleware("http")
    async def headers_and_origin(request: Request, call_next):
        if username and not (request.url.path == "/api/health" and request.method in ("GET", "HEAD")):
            valid = False
            try:
                scheme, encoded = request.headers.get("authorization", "").split(" ", 1)
                supplied = base64.b64decode(encoded, validate=True).decode("utf-8")
                supplied_user, separator, supplied_password = supplied.partition(":")
                user_ok = secrets.compare_digest(supplied_user.encode(), username.encode())
                password_ok = secrets.compare_digest(supplied_password.encode(), password.encode())
                valid = scheme.lower() == "basic" and bool(separator) and user_ok and password_ok
            except (ValueError, UnicodeError, binascii.Error):
                pass
            if not valid:
                return JSONResponse({"detail": "Accesso riservato"}, status_code=401,
                                    headers={"WWW-Authenticate": 'Basic realm="LottoPredict AI", charset="UTF-8"',
                                             "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if (request.headers.get("x-lottopredict-request") != "1"
                    or (origin and urlsplit(origin).netloc != request.headers.get("host"))):
                return JSONResponse({"detail": "Richiesta da origine non consentita"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
        return response

    def validate_selection(selection: Selection):
        rule = store.rules.rules.get((selection.game, selection.variant))
        if rule is None:
            raise HTTPException(422, "Gioco o variante non supportati")
        if (rule["wheels"] and selection.wheel not in rule["wheels"]) or (not rule["wheels"] and selection.wheel):
            raise HTTPException(422, "Ruota non valida per la selezione")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/health")
    def health():
        try:
            with store.connect() as connection:
                connection.execute("SELECT 1").fetchone()
        except Exception:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {"status": "ok"}

    @app.get("/api/config")
    def config():
        return {"storage": store.backend, "official_sync_enabled": synchronizer.enabled, "official_default_limit": 500,
                "rules": list(store.rules.rules.values()), "models": ["uniform", "frequency", "temporal", "logistic", "random_forest", "gradient_boosting", "ensemble"]}

    @app.get("/api/dashboard")
    def dashboard(game: str = "Lotto", variant: str = "ordinario", wheel: str = "Roma", synthetic: bool = False,
                  limit: int = 1000, official_only: bool = False,
                  archive_offset: int = Query(default=0, ge=0, le=10000)):
        if not 1 <= limit <= 10000:
            raise HTTPException(422, "Limite da 1 a 10.000")
        selection = Selection(game=game, variant=variant, wheel=wheel, synthetic=synthetic, limit=limit)
        validate_selection(selection)
        history = (synchronizer.history(game, variant, wheel, limit) if official_only and not synthetic
                   else store.history(game, variant, wheel, synthetic, limit))
        page_size = 100
        # Clamp stale offsets after an archive or filter changes.
        archive_offset = min(archive_offset // page_size * page_size,
                             max(0, (len(history) - 1) // page_size * page_size))
        archive_page = list(reversed(history))[archive_offset:archive_offset + page_size]
        frequency = []
        if history:
            from collections import Counter
            counts = Counter(n for draw in history for n in draw.numbers)
            rule = store.rules.rules[(game, variant)]
            frequency = [{"number": n, "count": counts[n]} for n in range(rule["minimum"], rule["maximum"] + 1)]
        return {"real_count": store.count(), "synthetic_count": store.count(True),
                "selected_count": len(history), "synthetic": synthetic,
                "latest": asdict(history[-1]) if history else None,
                "frequency": frequency, "draws": [asdict(draw) for draw in archive_page],
                "archive_page": {"offset": archive_offset, "limit": page_size, "total": len(history)},
                "data_source": {"automatic": synchronizer.enabled and Synchronizer.supported(game, variant),
                                "scope": "official" if official_only else "archive",
                                "last_sync": {key: value for key, value in (store.sync_info(LOTTO_SOURCE_KEY) or {}).items()
                                              if key != "covered_days"} if Synchronizer.supported(game, variant) else None},
                "rules_verified": store.rules.rules[(game, variant)]["verified"]}

    @app.post("/api/demo", status_code=202)
    def demo():
        from data_sources.importer import import_file
        path = Path(__file__).parent.parent / "examples" / "synthetic_lotto_roma.json"
        return jobs.submit("demo", lambda: asdict(import_file(store, path, synthetic=True)))

    async def upload_content(request: Request) -> bytes:
        from data_sources.importer import MAX_BYTES
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > MAX_BYTES:
                raise HTTPException(413, "Il file supera 25 MiB")
        if not content:
            raise HTTPException(422, "Selezionare un file non vuoto")
        return bytes(content)

    @app.post("/api/import/preview", status_code=202)
    async def preview_archive(request: Request, format: Literal["csv", "xlsx", "json"], synthetic: bool = False):
        from data_sources.preview import preview_content
        content = await upload_content(request)
        return jobs.submit("preview", lambda: preview_content(store, content, format, synthetic))

    @app.post("/api/import", status_code=202)
    async def import_archive(request: Request, format: Literal["csv", "xlsx", "json"], synthetic: bool = False,
                             expected_sha256: str | None = Query(default=None, pattern=r"^[a-f0-9]{64}$")):
        from data_sources.importer import import_content
        content = await upload_content(request)
        if expected_sha256 and not secrets.compare_digest(hashlib.sha256(content).hexdigest(), expected_sha256):
            raise HTTPException(409, "Il file è cambiato dopo l'anteprima: eseguire nuovamente il controllo")
        return jobs.submit("import", lambda: asdict(import_content(store, content, format, "importazione_web", synthetic)))

    @app.get("/api/import/template")
    def import_template():
        return Response("game,variant,draw_id,occurred_at,numbers,wheel,extras,synthetic\r\n", media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="modello-estrazioni.csv"'})

    @app.get("/api/archive/export")
    def export_archive(game: str = "Lotto", variant: str = "ordinario", wheel: str = "Roma", synthetic: bool = False,
                       limit: int = Query(default=1000, ge=1, le=10000), official_only: bool = False):
        validate_selection(Selection(game=game, variant=variant, wheel=wheel, synthetic=synthetic, limit=limit))
        rows = []
        history = (synchronizer.history(game, variant, wheel, limit) if official_only and not synthetic
                   else store.history(game, variant, wheel, synthetic, limit))
        for draw in history:
            row = asdict(draw)
            row["occurred_at"] = draw.occurred_at.isoformat()
            rows.append(row)
        return Response(json.dumps(rows, ensure_ascii=False, allow_nan=False), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="archivio-estrazioni.json"'})

    @app.post("/api/draws", status_code=201)
    def manual_draw(body: ManualDraw):
        from games.models import Draw
        draw = Draw(body.game, body.variant, body.draw_id.strip(), body.occurred_at, tuple(body.numbers),
                    body.wheel, body.extras, body.synthetic, body.source.strip())
        try:
            inserted = store.add_draw(draw)
        except (ValueError, TypeError) as error:
            raise HTTPException(422, str(error)) from error
        return {"inserted": inserted, "duplicate": not inserted}

    @app.post("/api/jobs", status_code=202)
    def experiment(selection: Experiment):
        validate_selection(selection)
        def operation():
            if selection.operation == "simulate":
                from lotto_statistics.engine import monte_carlo
                return monte_carlo(store.rules, selection.game, selection.variant, seed=selection.seed)
            update = {"state": "synthetic" if selection.synthetic else "stored"}
            if not selection.synthetic and selection.auto_update:
                update = synchronizer.ensure(selection.game, selection.variant, selection.wheel, selection.limit)
            history = (synchronizer.history(selection.game, selection.variant, selection.wheel, selection.limit)
                       if not selection.synthetic and (selection.official_only or update["state"] in ("updated", "cached"))
                       else store.history(selection.game, selection.variant, selection.wheel, selection.synthetic, selection.limit))
            if selection.operation == "analyze":
                from lotto_statistics.engine import analyze
                result = analyze(history, store.rules)
            elif selection.operation == "generate":
                from predictions.engine import generate
                result = generate(history, store.rules, selection.model, selection.combinations, selection.seed)
            elif selection.evaluation_mode == "tickets":
                from backtesting.tickets import ticket_walk_forward
                result = ticket_walk_forward(history, store.rules, selection.model, selection.test_targets,
                                             selection.combinations, selection.initial, selection.train_window, selection.seed)
            else:
                from backtesting.engine import walk_forward
                names = tuple(selection.models) if selection.models is not None else (selection.model,)
                result = walk_forward(history, store.rules, names, selection.initial,
                                      selection.train_window, selection.retrain_every, selection.seed)
            return {**result, "data_update": {key: value for key, value in update.items() if key != "covered_days"}}
        return jobs.submit(selection.operation, operation, selection.model_dump(mode="json"))

    @app.get("/api/sources/status")
    def source_status():
        from data_sources.lotto_api import PROGRESS_KEY
        try:
            return {"enabled": synchronizer.enabled, "progress": store.sync_info(PROGRESS_KEY)}
        except Exception:
            raise HTTPException(503, "Stato aggiornamento non disponibile: riprovare.") from None

    @app.post("/api/sources/sync", status_code=202)
    def sync_source(selection: Selection):
        validate_selection(selection)
        if selection.synthetic or not Synchronizer.supported(selection.game, selection.variant):
            raise HTTPException(422, "Aggiornamento ufficiale disponibile soltanto per Lotto reale")
        if not synchronizer.enabled:
            raise HTTPException(409, "Aggiornamento ufficiale disattivato nella configurazione.")
        return jobs.submit("sync", lambda: synchronizer.ensure(selection.game, selection.variant, selection.wheel,
                                                               selection.limit, force=True))

    @app.get("/api/jobs/{key}")
    def job(key: str):
        return jobs.get(key)

    @app.get("/api/experiments")
    def experiments(limit: int = Query(default=30, ge=1, le=100), offset: int = Query(default=0, ge=0, le=100000),
                    operation: Literal["analyze", "generate", "backtest", "simulate"] | None = None):
        try:
            return store.list_experiments(limit, offset, operation)
        except Exception:
            raise HTTPException(503, "Impossibile caricare gli esperimenti: riprovare quando il database è disponibile.") from None

    @app.post("/api/predictions", status_code=201)
    def persist(body: SavePrediction):
        from predictions.engine import save_prediction
        item = jobs.get(body.job_id)
        if item["status"] != "completed" or item["operation"] != "generate":
            raise HTTPException(422, "Selezionare una generazione completata")
        try:
            identifier = save_prediction(store, item["result"], body.target_id, body.target_date)
        except (ValueError, TypeError) as error:
            raise HTTPException(422, str(error)) from error
        return {"id": identifier}

    @app.get("/api/predictions")
    def predictions():
        return store.prediction_history()

    @app.get("/api/logs")
    def logs():
        return [dict(row) for row in store.recent_logs()]

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
