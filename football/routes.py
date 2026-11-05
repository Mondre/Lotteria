import json
import os
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from football.data import demo, fetch_season, read_upload
from football.engine import backtest
from football.repository import FootballStore


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    match_id: str = Field(min_length=1, max_length=200)
    synthetic: bool = False


def register(app, store, jobs):
    repository = FootballStore(store)
    def checked(operation):
        try:
            return operation()
        except ValueError as error:
            raise HTTPException(422, str(error)) from None

    @app.get('/football')
    def page():
        return FileResponse(Path(__file__).resolve().parent.parent / 'web/static/football.html')

    @app.get('/api/football')
    def overview(synthetic: bool = False):
        matches = checked(lambda: repository.matches(synthetic))
        return {'competition': 'Serie A', 'synthetic': synthetic, 'total': len(matches),
                'finished': sum(m.status == 'FINISHED' for m in matches),
                'fixtures': [m.payload() for m in matches if m.status != 'FINISHED'][-100:],
                'results': [m.payload() for m in reversed(matches) if m.status == 'FINISHED'][:100],
                'predictions': repository.predictions(synthetic), 'reports': repository.reports(synthetic),
                'provider_configured': os.environ.get('FOOTBALL_DATA_ENABLED') == 'true' and bool(os.environ.get('FOOTBALL_DATA_API_TOKEN')),
                'provider_live_verified': False}

    @app.post('/api/football/demo', status_code=202)
    def load_demo():
        def operation():
            if repository.matches(True):
                return {'message': 'Demo già presente: calendario e previsioni conservati.'}
            return repository.upsert(demo(), True)
        return jobs.submit('football_demo', operation)

    @app.get('/api/football/template')
    def template():
        return Response('id,season,kickoff,home,away,status,home_goals,away_goals,available_at,synthetic,source\r\n', media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="modello-calcio.csv"'})

    @app.post('/api/football/import', status_code=202)
    async def import_matches(request: Request, format: Literal['json', 'csv'], synthetic: bool = False):
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > 5 * 1024 * 1024:
                raise HTTPException(413, 'File calcio oltre 5 MiB')
        return jobs.submit('football_import', lambda: repository.upsert(read_upload(bytes(content), format, synthetic), synthetic))

    @app.post('/api/football/sync', status_code=202)
    def sync(season: int = Query(ge=2000, le=2100)):
        if not os.environ.get('FOOTBALL_DATA_API_TOKEN') or os.environ.get('FOOTBALL_DATA_ENABLED') != 'true':
            raise HTTPException(409, 'Fonte calcio non configurata. Le credenziali vanno inserite nelle variabili del server, mai in chat.')
        return jobs.submit('football_sync', lambda: repository.upsert(fetch_season(season), False))

    @app.post('/api/football/predictions', status_code=201)
    def predict(body: PredictionRequest):
        return checked(lambda: repository.predict(body.match_id, body.synthetic))

    @app.post('/api/football/backtest', status_code=202)
    def test(synthetic: bool = False, targets: int = Query(default=200, ge=1, le=500)):
        def operation():
            result = {**backtest(repository.matches(synthetic), targets), 'synthetic': synthetic}
            return repository.save_report(result, synthetic)
        return jobs.submit('football_backtest', operation)

    @app.get('/api/football/export')
    def export(synthetic: bool = False):
        return Response(json.dumps({'matches': [m.payload() for m in repository.matches(synthetic)],
                                    'predictions': repository.predictions(synthetic), 'reports': repository.reports(synthetic)}, allow_nan=False),
                        media_type='application/json', headers={'Content-Disposition': 'attachment; filename="calcio.json"'})
