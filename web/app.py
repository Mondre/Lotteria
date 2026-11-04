from concurrent.futures import ThreadPoolExecutor
import base64
import binascii
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
import json
import hashlib
import logging
import os
import secrets
from pathlib import Path
from threading import Lock
from typing import Literal
from urllib.parse import urlsplit
import uuid

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, StrictInt
from starlette.middleware.trustedhost import TrustedHostMiddleware

from database.factory import create_store
from database.store import Store
from games.rules import RuleRegistry

STATIC = Path(__file__).parent / "static"


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    game: str = "Lotto"
    variant: str = "ordinario"
    wheel: str = "Roma"
    synthetic: bool = False
    limit: int = Field(default=1000, ge=1, le=10000)


class Experiment(Selection):
    operation: Literal["analyze", "generate", "backtest", "simulate"]
    model: Literal["uniform", "frequency", "temporal", "logistic", "random_forest", "gradient_boosting", "ensemble"] = "frequency"
    combinations: int = Field(default=5, ge=1, le=100)
    initial: int = Field(default=700, ge=2, le=9999)
    train_window: int | None = Field(default=None, ge=2, le=10000)
    retrain_every: int = Field(default=10, ge=1, le=1000)
    seed: int = Field(default=42, ge=0, le=2147483647)


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


class Jobs:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lotto-web")
        self.lock = Lock()
        self.items = {}

    def submit(self, operation, function):
        with self.lock:
            if sum(item["status"] in ("queued", "running") for item in self.items.values()) >= 4:
                raise HTTPException(429, "Sono già in corso troppe operazioni. Attendere.")
            while len(self.items) >= 20:
                completed = next((key for key, item in self.items.items() if item["status"] in ("completed", "failed")), None)
                if completed is None:
                    break
                del self.items[completed]
            key = str(uuid.uuid4())
            self.items[key] = {"id": key, "operation": operation, "status": "queued"}
        self.pool.submit(self.run, key, function)
        return {"id": key, "status": "queued"}

    def run(self, key, function):
        with self.lock:
            self.items[key]["status"] = "running"
        try:
            result = function()
            # Non consegnare al client dati con NaN/Inf o non serializzabili.
            json.dumps(result, allow_nan=False)
            update = {"status": "completed", "result": result}
        except ValueError as error:
            update = {"status": "failed", "error": str(error)[:1000]}
        except Exception:
            logging.exception("Operazione web fallita")
            update = {"status": "failed", "error": "Operazione non riuscita. Controllare il formato del file e le dipendenze del server."}
        with self.lock:
            self.items[key].update(update)

    def get(self, key):
        with self.lock:
            if key not in self.items:
                raise HTTPException(404, "Operazione non trovata o scaduta")
            return dict(self.items[key])


def create_app(store: Store | None = None, allowed_hosts: list[str] | None = None) -> FastAPI:
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
    jobs = Jobs()

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            jobs.pool.shutdown(wait=True)
            store.close()

    app = FastAPI(title="LottoPredict AI", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.store, app.state.jobs = store, jobs
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
        return {"storage": store.backend, "rules": list(store.rules.rules.values()), "models": ["uniform", "frequency", "temporal", "logistic", "random_forest", "gradient_boosting", "ensemble"]}

    @app.get("/api/dashboard")
    def dashboard(game: str = "Lotto", variant: str = "ordinario", wheel: str = "Roma", synthetic: bool = False, limit: int = 1000):
        if not 1 <= limit <= 10000:
            raise HTTPException(422, "Limite da 1 a 10.000")
        selection = Selection(game=game, variant=variant, wheel=wheel, synthetic=synthetic, limit=limit)
        validate_selection(selection)
        history = store.history(game, variant, wheel, synthetic, limit)
        frequency = []
        if history:
            from collections import Counter
            counts = Counter(n for draw in history for n in draw.numbers)
            rule = store.rules.rules[(game, variant)]
            frequency = [{"number": n, "count": counts[n]} for n in range(rule["minimum"], rule["maximum"] + 1)]
        return {"real_count": store.count(), "synthetic_count": store.count(True),
                "selected_count": len(history), "synthetic": synthetic,
                "latest": asdict(history[-1]) if history else None,
                "frequency": frequency, "draws": [asdict(draw) for draw in reversed(history[-100:])],
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
                       limit: int = Query(default=1000, ge=1, le=10000)):
        validate_selection(Selection(game=game, variant=variant, wheel=wheel, synthetic=synthetic, limit=limit))
        rows = []
        for draw in store.history(game, variant, wheel, synthetic, limit):
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
            history = store.history(selection.game, selection.variant, selection.wheel, selection.synthetic, selection.limit)
            if selection.operation == "analyze":
                from lotto_statistics.engine import analyze
                return analyze(history, store.rules)
            if selection.operation == "generate":
                from predictions.engine import generate
                return generate(history, store.rules, selection.model, selection.combinations, selection.seed)
            from backtesting.engine import walk_forward
            return walk_forward(history, store.rules, (selection.model,), selection.initial,
                                selection.train_window, selection.retrain_every, selection.seed)
        return jobs.submit(selection.operation, operation)

    @app.get("/api/jobs/{key}")
    def job(key: str):
        return jobs.get(key)

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
