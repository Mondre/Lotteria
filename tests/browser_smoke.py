"""Smoke browser opzionale: server locale attivo, Playwright e Chromium installati.
Aggiunge solo dati sintetici. Eseguire su un database di test.
"""
import argparse
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright
parser=argparse.ArgumentParser()
parser.add_argument('--url',default='http://127.0.0.1:8000')
parser.add_argument('--chromium',default='/usr/bin/chromium')
parser.add_argument('--output',type=Path,default=Path('/tmp/lottopredict-browser'))
args=parser.parse_args()
folder=args.output
folder.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
 auth = {'http_credentials': {'username': os.environ['LOTTOPREDICT_BROWSER_USERNAME'], 'password': os.environ['LOTTOPREDICT_BROWSER_PASSWORD']}} if os.environ.get('LOTTOPREDICT_BROWSER_USERNAME') else {}
 page=browser.new_page(viewport={'width':1440,'height':1100},device_scale_factor=1,**auth)
 errors=[]
 page.on('pageerror',lambda error:errors.append(str(error)))
 page.goto(args.url,wait_until='networkidle')
 page.wait_for_function("() => document.getElementById('metric-count').textContent === '0'")
 page.screenshot(path=str(folder/'dashboard-empty.png'),full_page=True)
 page.get_by_role('button',name='Esplora con 1.000 dati sintetici').click()
 page.wait_for_function("() => document.getElementById('metric-count').textContent === '1000' || document.getElementById('metric-count').textContent === '1.000'",timeout=30000)
 page.screenshot(path=str(folder/'dashboard-demo.png'),full_page=True)
 page.locator('button.nav-item[data-view="analysis"]').click()
 page.locator('#run').click()
 page.locator('#results').wait_for(state='visible',timeout=30000)
 assert page.locator('#result-content tbody tr').count()==90
 page.locator('#statistics-table th').nth(1).get_by_role('button').click()
 counts=page.locator('#statistics-table tbody tr').evaluate_all("rows => rows.map(row => Number(row.cells[1].textContent))")
 assert counts==sorted(counts,reverse=True), 'Ordinamento presenze non numerico'
 page.get_by_label('CERCA NUMERO').fill('7')
 assert page.locator('#statistics-table tbody tr').count()==1
 page.get_by_role('button',name='Esplora numero 7',exact=True).click()
 assert page.locator('.number-detail').is_visible()
 assert 'Wilson' in page.locator('.number-detail').inner_text()
 assert 'non giorni' in page.locator('.number-detail').inner_text()
 assert page.locator('.number-detail tbody tr').count()>1
 chart=page.locator('.number-detail svg[aria-label="Andamento della frequenza · Numero 7"]')
 chart.focus()
 chart.press('Home')
 assert 'Dopo 1 estrazioni' in page.locator('.number-detail .comparison-tooltip').inner_text()
 chart.press('End')
 assert 'Dopo 1000 estrazioni' in page.locator('.number-detail .comparison-tooltip').inner_text()
 assert page.locator('.analysis-charts svg').count()==2

 page.get_by_label('CERCA NUMERO').fill('999')
 assert page.locator('#statistics-table tbody tr').count()==0
 assert not page.locator('.number-detail').is_visible()
 page.get_by_label('CERCA NUMERO').fill('')
 assert page.locator('#statistics-table tbody tr').count()==90
 page.screenshot(path=str(folder/'analysis.png'),full_page=True)
 page.locator('button.nav-item[data-view="predictions"]').click()
 page.locator('#run').click()
 page.locator('#save-panel').wait_for(state='visible',timeout=30000)
 assert page.locator('.ticket').count()==5
 page.locator('button.nav-item[data-view="backtest"]').click()
 page.locator('#run').click()
 page.locator('#results').wait_for(state='visible',timeout=30000)
 assert 'Nessun algoritmo' in page.locator('#result-summary').inner_text()
 page.screenshot(path=str(folder/'backtest.png'),full_page=True)
 page.locator('button.nav-item[data-view="settings"]').click()
 page.locator('#logs .log-row').first.wait_for(state='visible')
 assert page.locator('#rule-reviews details').count()==7
 assert page.locator('#rule-reviews summary').filter(has_text='Formato base controllato').count()==5
 assert page.locator('#rule-reviews summary').filter(has_text='Da verificare').count()==2

 page.locator('button.nav-item[data-view="archive"]').click()
 # Browse older draws, then change the window: the page must reset.
 first_id=page.locator('#archive-table tbody tr').first.locator('td').nth(1).inner_text()
 page.locator('#archive-next').click()
 page.wait_for_function("() => document.getElementById('archive-page').textContent.startsWith('101')")
 assert page.locator('#archive-table tbody tr').first.locator('td').nth(1).inner_text()!=first_id
 page.locator('#archive-prev').click()
 page.wait_for_function("() => document.getElementById('archive-page').textContent.startsWith('1–')")
 assert page.locator('#archive-table tbody tr').first.locator('td').nth(1).inner_text()==first_id
 page.locator('#archive-next').click()
 page.wait_for_function("() => document.getElementById('archive-page').textContent.startsWith('101')")
 page.locator('#limit').select_option('100')
 page.wait_for_function("() => document.getElementById('archive-next').disabled && document.getElementById('archive-page').textContent.startsWith('1–')")
 page.locator('#limit').select_option('1000')
 page.wait_for_function("() => !document.getElementById('archive-next').disabled")
 page.locator('#open-import').click()
 payload=[{'game':'Lotto','variant':'ordinario','wheel':'Roma','draw_id':'WEB-SYNTHETIC-<img src=x onerror="window.__lottoXSS=1">','occurred_at':'2025-01-02T20:00:00+01:00','numbers':[1,2,3,4,5],'extras':{},'synthetic':True}]
 page.locator('#file').set_input_files({'name':'synthetic-browser.json','mimeType':'application/json','buffer':json.dumps(payload).encode()})
 page.locator('#import-synthetic').check()
 page.get_by_role('button',name='Controlla file').click()
 page.locator('#import-preview').wait_for(state='visible',timeout=30000)
 assert 'Nessun dato salvato' in page.locator('#import-feedback').inner_text()
 page.get_by_role('button',name='Conferma importazione').click()
 page.wait_for_function("() => document.getElementById('status').textContent.startsWith('Importazione:')")
 assert '0 rifiutate' in page.locator('#status').inner_text()
 assert '<img src=x' in page.locator('#archive-table tbody').inner_text()
 assert page.locator('#archive-table img').count()==0
 assert page.evaluate('() => window.__lottoXSS') is None
 page.locator('#open-manual').click()
 page.locator('#manual-id').fill('WEB-SYNTHETIC-MANUAL')
 page.locator('#manual-date').fill('2025-01-03T20:00:00+01:00')
 page.locator('#manual-numbers').fill('6 7 8 9 10')
 page.locator('#manual-source').fill('Documento sintetico di test browser')
 page.get_by_role('button',name='Salva estrazione',exact=True).click()
 page.locator('#manual-dialog').wait_for(state='hidden',timeout=10000)
 page.locator('#archive-table tbody').get_by_text('WEB-SYNTHETIC-MANUAL',exact=True).wait_for(state='visible',timeout=10000)
 with page.expect_download() as download_info:
  page.locator('#export-archive').click()
 downloaded=download_info.value
 exported=json.loads(Path(downloaded.path()).read_text())
 assert any(row['draw_id']=='WEB-SYNTHETIC-MANUAL' and row['synthetic'] for row in exported)
 # Extras stay separate from the primary numbers, including in persisted analyses.
 extra_rows=[{'game':'Win for Life','variant':'classico','draw_id':f'WEB-EXTRA-{i}',
              'occurred_at':f'2025-02-0{i+1}T12:00:00+01:00','numbers':list(range(1,11)),
              'extras':{'numerone':value},'synthetic':True} for i,value in enumerate((1,1,20))]
 response=page.request.post(args.url+'/api/import?format=json&synthetic=true',data=json.dumps(extra_rows),headers={'Content-Type':'application/json','X-LottoPredict-Request':'1'})
 assert response.status==202
 key=response.json()['id']
 for _ in range(300):
  imported=page.request.get(args.url+'/api/jobs/'+key).json()
  if imported['status'] in ('completed','failed'):break
  page.wait_for_timeout(100)
 assert imported['status']=='completed',imported
 page.locator('#game').select_option('Win for Life')
 page.wait_for_function("() => document.getElementById('metric-count').textContent==='3'")
 page.locator('button.nav-item[data-view="analysis"]').click()
 page.locator('#run').click()
 page.locator('#results').wait_for(state='visible',timeout=30000)
 extra=page.locator('.extra-statistics')
 extra.locator('summary').click()
 assert 'numerone' in extra.inner_text()
 assert extra.locator('tbody tr').count()==20
 assert extra.locator('tbody tr').first.locator('td').nth(1).inner_text()=='2'
 assert page.locator('#statistics-table tbody tr').count()==20
 page.set_viewport_size({'width':390,'height':844})
 page.locator('button.nav-item[data-view="dashboard"]').click()
 page.screenshot(path=str(folder/'mobile.png'),full_page=True)
 assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Overflow orizzontale mobile'
 assert not errors, errors
 print('Browser OK: dashboard vuota/demo, analisi 90 numeri, ordinamento/filtro/dettaglio e grafici da tastiera, fonti delle regole, extra separati, archivio paginato, 5 combinazioni, backtest 300 target, registro, anteprima/importazione, inserimento manuale, esportazione, escaping HTML, layout mobile; nessun errore JS')
 browser.close()
