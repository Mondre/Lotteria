"""Prova browser della copertura su database di test; nessuna estrazione reale."""
import argparse
import json
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser()
parser.add_argument('--url',default='http://127.0.0.1:8026')
args=parser.parse_args()
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    page=browser.new_page(viewport={'width':1440,'height':1100});errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(args.url,wait_until='networkidle')
    page.locator('#demo').click()
    page.wait_for_function("() => document.getElementById('metric-count').textContent.replaceAll('.','')==='1000'")
    page.locator('button.nav-item[data-view="predictions"]').click()
    page.locator('#ticket-strategy').select_option('disjoint')
    page.locator('#run').click()
    page.locator('#save-panel').wait_for(state='visible',timeout=30000)
    generated=json.loads(page.locator('#result-json').text_content())
    assert generated['coverage']['distinct_numbers']==25
    assert len(generated['tickets'])==5
    assert len(set(n for t in generated['tickets'] for n in t['numbers']))==25
    page.locator('button.nav-item[data-view="tickettest"]').click()
    assert page.locator('#ticket-strategy').input_value()=='disjoint'
    page.locator('#test-targets').fill('20')
    page.locator('#run').click()
    page.locator('#ticket-test-target').wait_for(state='visible',timeout=30000)
    report=json.loads(page.locator('#result-json').text_content())
    assert report['ticket_strategy']=='disjoint'
    assert report['model_summary']['mean_distinct_numbers']==25
    assert report['random_summary']['mean_distinct_numbers']==25
    page.locator('button.nav-item[data-view="history"]').click()
    page.locator('#history-content').get_by_role('button',name='Apri',exact=True).first.click()
    page.locator('#ticket-test-target').wait_for(state='visible')
    assert page.locator('#ticket-strategy').input_value()=='disjoint'
    assert page.locator('#test-targets').input_value()=='20'
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    page.locator('button.nav-item[data-view="analysis"]').click()
    page.locator('#run').click()
    page.locator('#results').wait_for(state='visible',timeout=30000)
    assert page.locator('#statistics-table tbody tr').count()==90
    assert not errors,errors
    print('Copertura browser OK: 25 numeri, casuale equo, cronologia, mobile e analisi con strategia nascosta.')
    browser.close()
