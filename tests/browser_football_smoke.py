"""Prova browser opzionale su un database di test vuoto; aggiunge solo demo calcio."""
import argparse
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8024')
parser.add_argument('--chromium', default='/usr/bin/chromium')
parser.add_argument('--output', type=Path, default=Path('/tmp/lottopredict-football-browser-output'))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=args.chromium, headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
    auth = {'http_credentials': {'username': os.environ['LOTTOPREDICT_BROWSER_USERNAME'], 'password': os.environ['LOTTOPREDICT_BROWSER_PASSWORD']}} if os.environ.get('LOTTOPREDICT_BROWSER_USERNAME') else {}
    page = browser.new_page(viewport={'width': 1440, 'height': 1100}, **auth)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(args.url, wait_until='networkidle')
    page.get_by_role('link', name='Calcio · Serie A').click()
    page.wait_for_function("() => document.getElementById('football-count').textContent.startsWith('0 partite')")
    assert page.locator('#football-sync').is_disabled()
    page.locator('#football-demo').click()
    page.wait_for_function("() => document.getElementById('football-count').textContent.startsWith('172 partite')")
    assert page.locator('#football-fixtures tbody tr').count() == 4
    page.locator('#football-fixtures button').first.click()
    page.locator('#football-prediction').wait_for(state='visible')
    assert page.locator('#football-probabilities strong').count() == 3
    assert page.locator('#football-probabilities .metric-label').all_text_contents() == ['1 · Casa', 'X · Pareggio', '2 · Trasferta']
    page.wait_for_function("() => document.querySelectorAll('#football-history tbody tr').length===1")
    page.locator('#football-backtest').click()
    page.wait_for_function("() => document.querySelectorAll('#football-report tbody tr').length===2")
    assert '138 target' in page.locator('#football-report').inner_text()
    with page.expect_download() as info:
        page.locator('#football-export').click()
    exported = json.loads(Path(info.value.path()).read_text())
    assert len(exported['matches']) == 172
    assert len(exported['predictions']) == 1
    assert len(exported['reports']) == 1
    assert all(row['synthetic'] for row in exported['matches'])
    page.screenshot(path=str(args.output / 'football-desktop.png'), full_page=True)
    page.reload(wait_until='networkidle')
    page.locator('#football-dataset').select_option('synthetic')
    page.wait_for_function("() => document.querySelectorAll('#football-history tbody tr').length===1")
    page.locator('#football-history button').click()
    page.locator('#football-prediction').wait_for(state='visible')
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Overflow orizzontale'
    page.screenshot(path=str(args.output / 'football-mobile.png'), full_page=True)
    assert not errors, errors
    print('Calcio browser OK: demo separato, 1-X-2, registro persistente, backtest 138 target, export e mobile senza errori JS.')
    browser.close()
