"""Browser opzionale su archivio di test vuoto; aggiunge soltanto demo Lotto."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser()
parser.add_argument('--url',default='http://127.0.0.1:8025')
parser.add_argument('--output',type=Path,default=Path('/tmp/lottopredict-ticket-browser'))
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    page=browser.new_page(viewport={'width':1440,'height':1100});errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(args.url,wait_until='networkidle')
    page.locator('#demo').click()
    page.wait_for_function("() => document.getElementById('metric-count').textContent.replaceAll('.','')==='1000'")
    page.locator('button.nav-item[data-view="tickettest"]').click()
    page.locator('#test-targets').fill('20')
    page.locator('#combinations').fill('5')
    assert not page.locator('#retrain').is_visible()
    assert page.locator('#model').is_visible()
    page.locator('#run').click()
    page.locator('#ticket-test-target').wait_for(state='visible',timeout=30000)
    result=json.loads(page.locator('#result-json').text_content())
    assert result['result_type']=='ticket_backtest'
    assert result['test_steps']==20
    assert result['model_summary']['total_combinations']==100
    assert page.locator('#ticket-test-details tbody tr').count()==10
    assert page.locator('#save-panel').is_hidden()
    page.locator('#ticket-test-target').select_option('0')
    assert result['steps'][0]['train_last_id'] in page.locator('#ticket-test-details').inner_text()
    page.screenshot(path=str(args.output/'ticket-test.png'),full_page=True)
    with page.expect_download() as info:page.locator('#export').click()
    exported=json.loads(Path(info.value.path()).read_text());assert exported==result
    page.locator('button.nav-item[data-view="history"]').click()
    page.locator('#history-content').get_by_role('button',name='Apri',exact=True).first.click()
    page.locator('#ticket-test-target').wait_for(state='visible')
    assert page.locator('#test-targets').input_value()=='20'
    assert page.locator('#combinations').input_value()=='5'
    assert 'Risultati dell’esecuzione originale' in page.locator('#result-context').inner_text()
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(args.output/'ticket-test-mobile.png'),full_page=True)
    assert not errors,errors
    print('Test combinazioni browser OK: 20 target, 100 combinazioni, dettaglio, export, cronologia e mobile.')
    browser.close()
