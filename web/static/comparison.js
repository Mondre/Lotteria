'use strict';
function renderBacktestResult(result,target){
 const rows=result.summary||[];
 const signed=value=>Number.isFinite(value)?(value>=0?'+':'')+decimal(value,4):'—';
 const pValue=value=>!Number.isFinite(value)?'—':value===0?'≈ 0':value<.0001?value.toExponential(2):decimal(value,6);
 target.append(table(['Algoritmo','Corrispondenze medie','IC bootstrap 95%','Δ attesa teorica','Δ casuale campionato','p corretto Holm','Esito'],rows.map(row=>[
  modelNames[row.model]||row.model,decimal(row.mean_matches,4),
  (row.mean_ci95_bootstrap_iid||[]).map(value=>decimal(value,4)).join(' – '),
  signed(row.difference_theory),signed(row.difference_sampled_random),row.model==='uniform'?'—':pValue(row.p_holm),
  row.model==='uniform'?'Riferimento casuale':row.exceeds_uniform_null?'Scostamento da replicare':'Nessuna evidenza'
 ])));
 target.append(node('p','comparison-method',`${nf.format(result.test_steps)} target cronologici identici per tutti i modelli. IC bootstrap iid descrittivi; p-value corretti tra i modelli di questa esecuzione. Dipendenze temporali possono invalidare gli intervalli. Non selezionare i parametri dopo aver osservato questi risultati.`));
 if(!result.steps?.length||!rows.length)return;
 const panel=node('div','comparison-chart-panel');
 panel.append(node('h3',null,'Corrispondenze medie cumulative'));
 panel.append(node('p','muted small','Attiva o nascondi le curve. Muovi il puntatore sul grafico oppure usa le frecce quando è selezionato.'));
 const legend=node('div','comparison-legend');panel.append(legend);
 const chart=node('div','comparison-chart');panel.append(chart);
 const tooltip=node('div','comparison-tooltip');panel.append(tooltip);target.append(panel);
 const palette=['#7e93b4','#75a0ff','#65d4af','#f0bc70','#d395ed','#f08c9c','#b8ce77'];
 const series=rows.map((row,index)=>{let total=0;return {name:row.model,color:palette[index%palette.length],
  means:result.steps.map((step,i)=>{total+=step.models[row.model].matches;return total/(i+1);}),active:true};});
 const expected=rows[0].theoretical_random_mean;
 let cursor=result.steps.length-1;
 const ns='http://www.w3.org/2000/svg';
 const svgNode=(tag,attributes)=>{const el=document.createElementNS(ns,tag);for(const [key,value]of Object.entries(attributes))el.setAttribute(key,value);return el;};
 function describe(){const step=result.steps[cursor];const items=series.filter(s=>s.active).map(s=>`${modelNames[s.name]||s.name}: ${decimal(s.means[cursor],4)}`);tooltip.textContent=`Target ${cursor+1}/${result.steps.length} · ${step.target_id} · ${items.join(' | ')||'Nessuna curva selezionata'} · Attesa teorica: ${decimal(expected,4)}`;}
 function draw(){
  clear(chart);
  const active=series.filter(s=>s.active), top=Math.max(expected,...active.flatMap(s=>s.means),.01)*1.08;
  const width=720,height=230,left=42,right=16,bottom=28,upper=14,w=width-left-right,h=height-bottom-upper;
  const x=index=>left+(series[0].means.length===1?w/2:index*w/(series[0].means.length-1));
  const y=value=>upper+h-value/top*h;
  const svg=svgNode('svg',{viewBox:`0 0 ${width} ${height}`,role:'img',tabindex:0,'aria-label':'Media cumulativa delle corrispondenze. Usa le frecce per esplorare i target.'});
  for(let i=0;i<=4;i++){const value=top*i/4;svg.append(svgNode('line',{x1:left,x2:width-right,y1:y(value),y2:y(value),class:'chart-grid'}));const text=svgNode('text',{x:left-7,y:y(value)+4,'text-anchor':'end',class:'chart-axis'});text.textContent=decimal(value,2);svg.append(text);}
  for(const index of [...new Set(Array.from({length:5},(_,i)=>Math.round((result.steps.length-1)*i/4)))]){const text=svgNode('text',{x:x(index),y:height-6,'text-anchor':'middle',class:'chart-axis'});text.textContent=index+1;svg.append(text);}
  svg.append(svgNode('line',{x1:left,x2:width-right,y1:y(expected),y2:y(expected),stroke:'#e7bb79','stroke-dasharray':'6 5','stroke-width':1.5}));
  for(const item of active){svg.append(svgNode('polyline',{points:item.means.map((value,index)=>`${x(index)},${y(value)}`).join(' '),fill:'none',stroke:item.color,'stroke-width':2,class:'model-curve','data-model':item.name}));}
  const marker=svgNode('line',{x1:x(cursor),x2:x(cursor),y1:upper,y2:upper+h,stroke:'#a2b6d3','stroke-dasharray':'2 4','stroke-width':1});svg.append(marker);
  const move=index=>{cursor=Math.max(0,Math.min(result.steps.length-1,index));marker.setAttribute('x1',x(cursor));marker.setAttribute('x2',x(cursor));describe();};
  svg.addEventListener('pointermove',event=>{const rect=svg.getBoundingClientRect();const position=(event.clientX-rect.left)/rect.width*width;move(Math.round((position-left)/w*(result.steps.length-1)));});
  svg.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();move(event.key==='Home'?0:event.key==='End'?result.steps.length-1:cursor+(event.key==='ArrowRight'?1:-1));}});
  chart.append(svg);describe();
 }
 for(const item of series){const label=node('label');const input=node('input');input.type='checkbox';input.checked=true;input.setAttribute('aria-label',modelNames[item.name]||item.name);input.addEventListener('change',()=>{item.active=input.checked;draw();});const swatch=svgNode('svg',{viewBox:'0 0 18 5',class:'series-swatch','aria-hidden':'true'});swatch.append(svgNode('line',{x1:0,y1:2.5,x2:18,y2:2.5,stroke:item.color,'stroke-width':3}));label.append(input,swatch,node('span',null,modelNames[item.name]||item.name));legend.append(label);}
 legend.append(node('span','muted small','Tratteggio: attesa teorica del caso'));draw();
}
