'use strict';
function renderStatistics(result,target){
 const delays=new Map(result.delays.map(row=>[row.number,row]));
 const controls=node('div','experiment-fields');
 const label=node('label','filter','CERCA NUMERO');
 const search=node('input');search.type='number';search.min=Math.min(...result.frequencies.map(row=>row.number));search.max=Math.max(...result.frequencies.map(row=>row.number));search.placeholder='Tutti';label.append(search);controls.append(label);target.append(controls);
 const status=node('p','muted small');status.setAttribute('role','status');target.append(status);
 const wrapper=node('div','table-scroll'),t=node('table'),head=node('thead'),tr=node('tr'),body=node('tbody');
 t.id='statistics-table';t.append(head,body);head.append(tr);wrapper.append(t);target.append(wrapper);
 renderAnalysisCharts(result,target);
 renderExtraStatistics(result,target);
 const detail=node('section','number-detail');detail.hidden=true;detail.setAttribute('aria-label','Dettaglio del numero');target.append(detail);
 let sort='number',descending=false;
 const columns=[['number','Numero'],['count','Presenze'],['relative','Frequenza relativa'],['expected_count','Attesa'],['current','Ritardo'],['p_holm','p corretto Holm']];
 function showDetail(row){
  clear(detail);detail.hidden=false;const d=delays.get(row.number);
  const title=node('h3',null,`Numero ${String(row.number).padStart(2,'0')}`);title.tabIndex=-1;detail.append(title);
  detail.append(node('p',null,`Frequenza osservata ${decimal(row.relative*100,2)}%. Intervallo Wilson marginale al 95%: ${row.ci95.map(x=>decimal(x*100,2)+'%').join(' – ')}. Non è una stima della probabilità della prossima uscita.`));
  detail.append(table(['Ritardo attuale','Massimo osservato','Media intervalli completati','Media teorica'],[[d.current,d.max_observed,d.mean_completed===null?'Non disponibile':decimal(d.mean_completed),decimal(d.theoretical_mean)]]));
  detail.append(node('p','muted small','I ritardi contano estrazioni senza uscita, non giorni. Gli intervalli ai bordi sono censurati ed esclusi dalla media; il massimo osservato li comprende. Un ritardo alto non aumenta la probabilità futura.'));
  detail.append(table(['Finestra richiesta','Estrazioni disponibili','Presenze','Frequenza relativa'],Object.entries(row.windows).map(([window,value])=>[window,value.n,value.count,decimal(value.count/value.n,4)])));
  renderNumberTrajectory(row,result,detail);
  title.focus({preventScroll:true});
 }
 function render(){
  clear(tr);clear(body);
  for(const [key,title]of columns){
   const th=node('th');th.scope='col';if(sort===key)th.setAttribute('aria-sort',descending?'descending':'ascending');
   const button=node('button','text-button',title+(sort===key?(descending?' ↓':' ↑'):''));button.type='button';button.addEventListener('click',()=>{descending=sort===key?!descending:key!=='number';sort=key;render();tr.querySelectorAll('button')[columns.findIndex(column=>column[0]===key)].focus();});th.append(button);tr.append(th);
  }
  const th=node('th',null,'Dettagli');th.scope='col';tr.append(th);
  const rows=result.frequencies.filter(row=>search.value===''||row.number===Number(search.value)).slice().sort((a,b)=>{
   const value=row=>sort==='current'?delays.get(row.number).current:row[sort];
   return (value(a)-value(b))*(descending?-1:1)||a.number-b.number;
  });
  status.textContent=`${rows.length} numeri mostrati su ${result.frequencies.length}. Frequenze e test riferiti alle ${nf.format(result.draws)} estrazioni dell’esperimento.`;
  for(const row of rows){const r=node('tr');[String(row.number).padStart(2,'0'),row.count,decimal(row.relative,4),decimal(row.expected_count),delays.get(row.number).current,decimal(row.p_holm,5)].forEach(value=>r.append(node('td',null,value)));const td=node('td'),open=node('button','text-button','Esplora');open.type='button';open.setAttribute('aria-label',`Esplora numero ${row.number}`);open.addEventListener('click',()=>showDetail(row));td.append(open);r.append(td);body.append(r);}
  if(!rows.length){detail.hidden=true;status.textContent='Nessun numero corrispondente. Svuota il campo per mostrare tutti i numeri.';}
 }
 search.addEventListener('input',()=>{detail.hidden=true;render();});render();
}

function renderExtraStatistics(result,target){
 const extras=result.extras_analysis||{};
 for(const [name,data]of Object.entries(extras)){
  const section=node('details','number-detail extra-statistics');
  section.append(node('summary',null,`Extra · ${name} · ${nf.format(data.draws)} estrazioni`));
  section.append(node('p','muted small',data.notes));
  section.append(table(['Valore extra','Presenze','Frequenza osservata'],data.frequencies.map(row=>[row.number,row.count,decimal(row.relative,4)])));
  target.append(section);
 }
}
