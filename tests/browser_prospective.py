"""Verifica browser con demo di test; nessuna previsione reale o giocata."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser()
parser.add_argument('--url',default='http://127.0.0.1:8027')
args=parser.parse_args()
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    page=browser.new_page(viewport={'width':1440,'height':1100});errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(args.url,wait_until='networkidle')
    page.locator('#demo').click()
    page.wait_for_function("() => document.getElementById('metric-count').textContent.replaceAll('.','')==='1000'")
    page.locator('button.nav-item[data-view="prospective"]').click()
    page.locator('#prospective-register').wait_for(state='visible')
    assert page.locator('#prospective-register').is_enabled()
    future=page.locator('#prospective-day').get_attribute('min')
    page.locator('#prospective-day').fill(future)
    page.locator('#prospective-strategy').select_option('disjoint')
    page.locator('#prospective-register').click()
    page.wait_for_function("() => document.getElementById('status').textContent.startsWith('Confronto registrato.') || document.getElementById('status').textContent.startsWith('Confronto già registrato:')")
    assert page.locator('#prospective-list tbody tr').count()==1
    assert page.locator('#prospective-details tbody tr').count()==10
    assert 'Nessun risultato' in page.locator('#prospective-summary').inner_text()
    page.locator('#prospective-register').click()
    page.wait_for_function("() => document.getElementById('status').textContent.startsWith('Confronto già registrato:')")
    assert page.locator('#prospective-list tbody tr').count()==1
    with page.expect_download() as info:page.locator('#prospective-export').click()
    data=json.loads(Path(info.value.path()).read_text())
    assert len(data['trials'])==1
    trial=data['trials'][0]
    assert trial['registered_before_day']
    assert trial['status']=='awaiting_result'
    assert trial['model']['payload']['training_sha256']==trial['random']['payload']['training_sha256']
    assert trial['protocol']['ticket_strategy']=='disjoint'
    page.reload(wait_until='networkidle')
    page.locator('#dataset').select_option('synthetic')
    page.locator('#wheel').select_option('Roma')
    page.locator('button.nav-item[data-view="prospective"]').click()
    page.locator('#prospective-list button').first.wait_for(state='visible')
    page.locator('#prospective-list button').first.click()
    page.locator('#prospective-details').wait_for(state='visible')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    assert not errors,errors
    print('Confronti futuri browser OK: coppia immutabile, replica idempotente, nessun risultato inventato, export, riapertura e mobile.')
    browser.close()
