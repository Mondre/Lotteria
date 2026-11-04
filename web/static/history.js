'use strict';
let historyOffset=0;
let historySequence=0;
const experimentNames={analyze:'Analisi',generate:'Combinazioni',backtest:'Backtest',simulate:'Monte Carlo'};
async function loadExperimentHistory(){
 const sequence=++historySequence;
 const query=new URLSearchParams({limit:30,offset:historyOffset});
 if($('history-operation').value)query.set('operation',$('history-operation').value);
 try{
  const data=await api('/api/experiments?'+query);
  if(sequence!==historySequence)return;
  const content=$('history-content');clear(content);
  if(!data.items.length)empty(content,'Nessun esperimento salvato','Le prossime analisi, simulazioni e previsioni completate appariranno qui.');
  else{
   const wrapper=node('div','table-scroll'), t=node('table'), header=node('thead'), headrow=node('tr');
   ['Data','Tipo','Gioco / ruota','Modello','Archivio','Stato','Azioni'].forEach(label=>headrow.append(node('th',null,label)));
   header.append(headrow);t.append(header);const body=node('tbody');
   for(const item of data.items){
    const p=item.request||{}, row=node('tr');
    row.append(node('td',null,dateLabel(item.created_at,true)),node('td',null,experimentNames[item.operation]||item.operation),node('td',null,[p.game,p.wheel||p.variant].filter(Boolean).join(' · ')),node('td',null,Array.isArray(p.models)?`Confronto (${new Set(['uniform','frequency',...p.models]).size} modelli)`:modelNames[p.model]||'—'),node('td',null,p.synthetic?'Sintetico':p.official_only?'Fonte ufficiale':'Archivio completo'));
    const status=node('td',null,item.status==='completed'?'Completato':'Non riuscito');
    if(item.error){const error=node('div','history-error',item.error);status.append(error);}row.append(status);
    const actions=node('td'), group=node('div','history-actions');
    if(item.status==='completed'){const open=node('button','button secondary','Apri');open.addEventListener('click',()=>openExperiment(item.id));group.append(open);}
    const rerun=node('button','button secondary','Riesegui');rerun.title='Nuova esecuzione con gli stessi parametri sui dati attuali';rerun.addEventListener('click',()=>rerunExperiment(item));group.append(rerun);actions.append(group);row.append(actions);body.append(row);
   }
   t.append(body);wrapper.append(t);content.append(wrapper);
  }
  $('history-page').textContent=data.total?`${data.offset+1}–${Math.min(data.offset+data.items.length,data.total)} di ${data.total}`:'0 esperimenti';
  $('history-prev').disabled=historyOffset===0;$('history-next').disabled=historyOffset+data.limit>=data.total;
 }catch(error){message(error.message,'error');}
}
function restoreExperimentRequest(p){
 if(p.game&&[...$('game').options].some(option=>option.value===p.game)){$('game').value=p.game;setVariants();}
 if(p.variant&&[...$('variant').options].some(option=>option.value===p.variant)){$('variant').value=p.variant;setWheels();}
 if(typeof p.wheel==='string')$('wheel').value=p.wheel;
 $('dataset').value=p.synthetic?'synthetic':p.official_only&&state.officialEnabled?'real':'manual';
 if(Number.isInteger(p.limit)&&p.limit>=1&&p.limit<=10000){if(![...$('limit').options].some(option=>option.value===String(p.limit))){const option=node('option',null,`${nf.format(p.limit)} estrazioni`);option.value=p.limit;$('limit').append(option);}$('limit').value=String(p.limit);}
 for(const [field,id]of [['model','model'],['seed','seed'],['combinations','combinations'],['initial','initial'],['retrain_every','retrain']])if(p[field]!==undefined)$(id).value=p[field];
 document.querySelectorAll('#comparison-models input').forEach(input=>input.checked=(p.models||['temporal']).includes(input.value));$('train-window').value=p.train_window||0;$('auto-update').checked=state.officialEnabled&&p.auto_update!==false;
}
function experimentView(operation,parameters={}){if(operation==='backtest'&&Array.isArray(parameters.models))return 'comparison';return ({generate:'predictions',backtest:'backtest',simulate:'analysis',analyze:'analysis'})[operation]||'analysis';}
async function openExperiment(id){
 if(state.busy)return;
 try{const job=await api('/api/jobs/'+id);if(job.status!=='completed')throw new Error(job.error||'Esperimento non completato.');
 changeView(experimentView(job.operation,job.request));restoreExperimentRequest(job.request||{});renderResult(job);await refresh();
 $('result-context').append(document.createTextNode(` · Esperimento salvato il ${dateLabel(job.created_at,true)}. Risultati dell’esecuzione originale.`));
 }catch(error){message(error.message,'error');}
}
async function rerunExperiment(item){
 if(state.busy)return;
 changeView(experimentView(item.operation,item.request));restoreExperimentRequest(item.request||{});
 const job=await runJob(()=>api('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...item.request,operation:item.operation})}));
 if(job){renderResult(job);await refresh();}
}
$('history-refresh').addEventListener('click',()=>{historyOffset=0;loadExperimentHistory();});
$('history-operation').addEventListener('change',()=>{historyOffset=0;loadExperimentHistory();});
$('history-prev').addEventListener('click',()=>{historyOffset=Math.max(0,historyOffset-30);loadExperimentHistory();});
$('history-next').addEventListener('click',()=>{historyOffset+=30;loadExperimentHistory();});
