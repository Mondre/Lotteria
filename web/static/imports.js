'use strict';
let importPreview = null;
let manualSelection = null;
function resetImportPreview(){importPreview=null;$('import-preview').hidden=true;$('confirm-import').disabled=true;$('import-feedback').textContent='';}
$('file').addEventListener('change',resetImportPreview);
$('import-synthetic').addEventListener('change',resetImportPreview);
$('open-import').addEventListener('click',()=>{resetImportPreview();$('import-template').href=winForLifeSelected()?'/api/winforlife/template':'/api/import/template';});
$('import-form').addEventListener('submit',async event=>{
 event.preventDefault();const file=$('file').files[0];if(!file)return;
 resetImportPreview();
 if(file.size>25*1024*1024){$('import-feedback').textContent='Il file supera il limite di 25 MiB.';return;}
 const format=file.name.split('.').pop().toLowerCase(),synthetic=$('import-synthetic').checked;
 if(!['csv','xlsx','json'].includes(format)){$('import-feedback').textContent='Formato non supportato.';return;}
 $('import-feedback').textContent='Controllo del file in corso. Nessun dato viene salvato…';
 const job=await runJob(()=>api('/api/import/preview?'+new URLSearchParams({format,synthetic}),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file}));
 if(!job){$('import-feedback').textContent=$('status').textContent;return;}
 const result=job.result;importPreview={file,format,synthetic,sha256:result.sha256};
 clear($('import-preview-counts'));
 for(const [key,label]of [['new','Nuove'],['duplicates','Duplicate'],['conflicts','In conflitto'],['invalid','Non valide']]){const card=node('div','preview-count');card.append(node('strong',null,nf.format(result[key])),node('span',null,label));$('import-preview-counts').append(card);}
 const classes={new:'Nuova',duplicates:'Duplicata',conflicts:'Conflitto',invalid:'Non valida'};
 clear($('import-preview-sample'));$('import-preview-sample').append(table(['Riga','Identificativo','Data','Numeri','Extra','Esito'],result.sample.map(row=>[row.row,row.draw_id||'—',row.occurred_at?dateLabel(row.occurred_at,row.date_precision!=='date'):'—',(row.numbers||[]).join(' · '),row.extras?JSON.stringify(row.extras):'—',classes[row.classification]])));
 $('import-preview-errors').hidden=!result.errors.length;$('import-preview-errors').textContent=result.errors.join('\n');
 $('import-preview').hidden=false;$('confirm-import').disabled=result.new+result.duplicates===0;
 $('import-feedback').textContent=`${result.total} righe controllate. Nessun dato salvato. Archivio: ${synthetic?'sintetico':'reale'}. Anteprima delle prime 20 righe.`;
 $('status').hidden=true;
});
$('confirm-import').addEventListener('click',async()=>{
 if(!importPreview||state.busy)return;
 const preview=importPreview;resetResult();$('import-feedback').textContent='Importazione in corso…';
 const job=await runJob(()=>api('/api/import?'+new URLSearchParams({format:preview.format,synthetic:preview.synthetic,expected_sha256:preview.sha256}),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:preview.file}));
 if(!job){$('import-feedback').textContent=$('status').textContent;return;}
 $('import-dialog').close();resetImportPreview();$('dataset').value=preview.synthetic?'synthetic':'manual';await refresh();
 const report=job.result;
 message(`Importazione: ${report.inserted} aggiunte · ${report.duplicates} duplicate · ${report.rejected} rifiutate.${report.errors.length?' '+report.errors.join(' | '):''}`,report.rejected?'error':'success');
});
$('export-archive').addEventListener('click',async()=>{
 try{const data=await api('/api/archive/export?'+new URLSearchParams(selection()));const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const link=node('a');link.href=url;link.download=`estrazioni-${selection().synthetic?'sintetiche':'reali'}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){message(error.message,'error');}
});
$('open-manual').addEventListener('click',()=>{
 $('manual-form').reset();manualSelection=selection();
 $('manual-selection').textContent=`${manualSelection.game} · ${manualSelection.wheel||manualSelection.variant} · Archivio ${manualSelection.synthetic?'SINTETICO':'REALE'}`;
 const wfl=winForLifeSelected();$('manual-numerone-field').hidden=!wfl;$('manual-numerone').required=wfl;$('manual-numerone').value='';$('manual-extras').closest('label').hidden=wfl;
 const r=rule();$('manual-extras').value=JSON.stringify(Object.fromEntries(Object.keys(r.extras).map(key=>[key,null])));
 $('manual-hint').textContent=`Inserisci ${r.count} numeri distinti tra ${r.minimum} e ${r.maximum}. ${Object.keys(r.extras).length?'Completa tutti gli extra richiesti con numeri interi. ':''}Regole preliminari: verificare la fonte prima di registrare dati reali.`;
 $('manual-feedback').textContent='';$('manual-dialog').showModal();
});
$('close-manual').addEventListener('click',()=>$('manual-dialog').close());
$('manual-form').addEventListener('submit',async event=>{
 event.preventDefault();if(state.busy||!manualSelection)return;
 let numbers,extras;
 try{numbers=$('manual-numbers').value.trim().split(/[\s,;]+/).map(value=>{if(!/^\d+$/.test(value))throw new Error('Usa numeri interi separati da spazi, virgole o punto e virgola.');return Number(value);});extras=manualSelection.game==='Win for Life'&&manualSelection.variant==='classico'?{numerone:Number($('manual-numerone').value)}:JSON.parse($('manual-extras').value);if(!extras||Array.isArray(extras)||typeof extras!=='object')throw new Error('Gli extra devono essere un oggetto JSON.');}catch(error){$('manual-feedback').textContent=error.message;return;}
 const {limit,official_only,...selected}=manualSelection;
 busy(true);$('manual-feedback').textContent='Salvataggio in corso…';
 try{const result=await api('/api/draws',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...selected,draw_id:$('manual-id').value,occurred_at:$('manual-date').value,numbers,extras,source:$('manual-source').value})});$('manual-dialog').close();$('dataset').value=manualSelection.synthetic?'synthetic':'manual';resetResult();await refresh();message(result.inserted?'Estrazione salvata. Le eventuali previsioni corrispondenti sono state valutate.':'Estrazione identica già presente: nessun dato modificato.','success');}catch(error){$('manual-feedback').textContent=error.message;}finally{busy(false);$('export').disabled=!state.result;}
});
