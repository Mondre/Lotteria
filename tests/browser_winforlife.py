"""Smoke Win for Life su database di test: soltanto dati sintetici."""
import argparse
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8028');args=parser.parse_args()
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    page=browser.new_page(viewport={'width':1440,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(args.url,wait_until='networkidle')
    page.locator('#winforlife-open').click()
    assert page.locator('#game').input_value()=='Win for Life'
    assert page.locator('#wheel-field').is_hidden()
    page.locator('#winforlife-demo').click()
    page.wait_for_function("() => document.getElementById('metric-count').textContent.replaceAll('.','')==='1000'")
    page.locator('#winforlife-open').click()
    assert page.locator('#dataset').input_value()=='synthetic'
    page.locator('#run').click();page.locator('#statistics-table').wait_for(state='visible',timeout=30000)
    assert page.locator('#statistics-table tbody tr').count()==20
    assert page.locator('.extra-statistics').count()==1
    page.locator('button.nav-item[data-view="predictions"]').click()
    assert page.locator('#include-numerone').is_checked()
    page.locator('#run').click();page.locator('#save-panel').wait_for(state='visible',timeout=30000)
    assert page.locator('.ticket').count()==5
    assert page.locator('.numerone-badge').count()==5
    result=json.loads(page.locator('#result-json').text_content())
    assert all(len(t['numbers'])==10 and 1<=t['extras']['numerone']<=20 for t in result['tickets'])
    page.locator('#target-id').fill('SYNTHETIC-WFL-FUTURE-BROWSER')
    page.locator('#target-date').fill((datetime.now(timezone.utc)+timedelta(days=2)).isoformat())
    page.locator('#save-form button').click()
    page.wait_for_function("() => document.getElementById('status').textContent.startsWith('Previsione salvata e immutabile')")
    page.locator('button.nav-item[data-view="tickettest"]').click()
    page.locator('#test-targets').fill('20');page.locator('#run').click()
    page.locator('#ticket-test-target').wait_for(state='visible',timeout=30000)
    tested=json.loads(page.locator('#result-json').text_content())
    assert tested['include_numerone']
    assert sum(row['combinations'] for row in tested['model_summary']['joint_distribution'])==100
    assert 'Numerone' in page.locator('#ticket-test-details').inner_text()
    page.locator('button.nav-item[data-view="archive"]').click();page.locator('#open-manual').click()
    assert page.locator('#manual-numerone').is_visible()
    assert page.locator('#manual-extras').is_hidden()
    page.locator('#manual-id').fill('SYNTHETIC-WFL-MANUAL')
    page.locator('#manual-date').fill('2025-01-02T12:00:00+01:00')
    page.locator('#manual-numbers').fill('1 2 3 4 5 6 7 8 9 10')
    page.locator('#manual-numerone').fill('5');page.locator('#manual-source').fill('Test sintetico browser')
    page.locator('#manual-form button[type="submit"]').click();page.locator('#manual-dialog').wait_for(state='hidden')
    page.locator('#open-import').click()
    assert page.locator('#import-template').get_attribute('href')=='/api/winforlife/template'
    csv='game,variant,draw_id,occurred_at,numbers,numerone,synthetic\nWin for Life,classico,SYNTHETIC-WFL-CSV,2025-01-03T12:00:00+01:00,1 2 3 4 5 6 7 8 9 10,20,true\n'
    page.locator('#file').set_input_files({'name':'wfl.csv','mimeType':'text/csv','buffer':csv.encode()})
    page.get_by_role('button',name='Controlla file',exact=True).click()
    page.locator('#import-preview').wait_for(state='visible',timeout=30000)
    assert 'numerone' in page.locator('#import-preview-sample').inner_text()
    page.locator('#confirm-import').click();page.locator('#import-dialog').wait_for(state='hidden',timeout=30000)
    with page.expect_download() as info:page.locator('#export-archive').click()
    exported=json.loads(Path(info.value.path()).read_text())
    assert any(row['draw_id']=='SYNTHETIC-WFL-CSV' and row['extras']=={'numerone':20} for row in exported)
    page.locator('button.nav-item[data-view="history"]').click();page.locator('#history-operation').select_option('backtest')
    page.locator('#history-content').get_by_role('button',name='Apri',exact=True).first.click()
    page.locator('#ticket-test-target').wait_for(state='visible')
    assert page.locator('#include-numerone').is_checked()
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    page.locator('button.nav-item[data-view="predictions"]').click();page.locator('#run').click()
    page.locator('#save-panel').wait_for(state='visible',timeout=30000)
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    page.screenshot(path='/tmp/winforlife-mobile.png',full_page=True)
    assert not errors,errors
    print('Win for Life browser OK: demo, analisi, 10+Numerone, previsione, test, import CSV, inserimento, export, cronologia e mobile.')
    browser.close()
