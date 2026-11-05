'use strict';
// Charts use only values stored in the experiment; opening history never recalculates them.
function analysisChart(parent,{title,description,rows,xLabel,yLabel,format,reference=null,bars=false}){
 const section=node('section','analysis-chart-panel');section.append(node('h3',null,title),node('p','muted small',description));parent.append(section);
 if(!rows.length){section.append(node('p','muted small','Dati non disponibili in questo esperimento.'));return;}
 const ns='http://www.w3.org/2000/svg';
 const make=(tag,attrs={})=>{const el=document.createElementNS(ns,tag);for(const [key,value]of Object.entries(attrs))el.setAttribute(key,value);return el;};
 const svg=make('svg',{viewBox:'0 0 720 270',role:'group','aria-label':title,tabindex:0});
 const svgTitle=make('title');svgTitle.textContent=title;svg.append(svgTitle);
 const wrapper=node('div','analysis-chart');wrapper.append(svg);section.append(wrapper);
 const tooltip=node('p','comparison-tooltip');tooltip.setAttribute('role','status');tooltip.setAttribute('aria-live','polite');section.append(tooltip);
 const left=60,top=16,width=630,height=190;
 const minimum=Math.min(...rows.map(row=>row.x)),maximum=Math.max(...rows.map(row=>row.x));
 const ymax=Math.max(...rows.map(row=>row.y),reference??0,0.001)*1.08;
 const x=value=>left+(value-minimum)/(maximum-minimum||1)*width;
 const y=value=>top+height-value/ymax*height;
 for(let i=0;i<=4;i++){
  const value=ymax*i/4, yy=y(value);svg.append(make('line',{x1:left,x2:left+width,y1:yy,y2:yy,class:'chart-grid'}));const label=make('text',{x:left-8,y:yy+4,'text-anchor':'end',class:'chart-axis'});label.textContent=decimal(value,ymax<1?3:1);svg.append(label);
 }
 for(const value of [...new Set([minimum,Math.round((minimum+maximum)/2),maximum])]){const label=make('text',{x:x(value),y:226,'text-anchor':'middle',class:'chart-axis'});label.textContent=String(value);svg.append(label);}
 const xlabel=make('text',{x:left+width/2,y:252,'text-anchor':'middle',class:'chart-axis'});xlabel.textContent=xLabel;svg.append(xlabel);
 const ylabel=make('text',{x:left,y:11,class:'chart-axis'});ylabel.textContent=yLabel;svg.append(ylabel);
 if(reference!==null){svg.append(make('line',{x1:left,x2:left+width,y1:y(reference),y2:y(reference),stroke:'#e8ba69','stroke-dasharray':'5 4'}));section.append(node('p','muted small',`Linea tratteggiata: riferimento teorico ${decimal(reference,4)}.`));}
 if(bars){const barWidth=Math.min(32,width/rows.length*.75);for(const row of rows){const bar=make('rect',{x:x(row.x)-barWidth/2,y:y(row.y),width:barWidth,height:top+height-y(row.y),fill:'#6c96df'});const hint=make('title');hint.textContent=format(row);bar.append(hint);svg.append(bar);}}
 else svg.append(make('polyline',{points:rows.map(row=>`${x(row.x)},${y(row.y)}`).join(' '),fill:'none',stroke:'#83b1ff','stroke-width':2}));
 const marker=make('circle',{r:4,fill:'#ffffff',stroke:'#5274bc','stroke-width':2});svg.append(marker);
 let index=rows.length-1;
 function inspect(){const row=rows[index];marker.setAttribute('cx',x(row.x));marker.setAttribute('cy',y(row.y));tooltip.textContent=format(row);}
 svg.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();index=event.key==='Home'?0:event.key==='End'?rows.length-1:Math.max(0,Math.min(rows.length-1,index+(event.key==='ArrowLeft'?-1:1)));inspect();});
 svg.addEventListener('pointermove',event=>{const point=svg.createSVGPoint();point.x=event.clientX;point.y=event.clientY;const matrix=svg.getScreenCTM();if(!matrix)return;const position=point.matrixTransform(matrix.inverse());index=rows.reduce((best,row,i)=>Math.abs(x(row.x)-position.x)<Math.abs(x(rows[best].x)-position.x)?i:best,0);inspect();});
 svg.setAttribute('aria-description','Usa le frecce sinistra e destra per esplorare i dati, Home e End per gli estremi.');inspect();
}
function renderAnalysisCharts(result,parent){
 const charts=node('div','analysis-charts');parent.append(charts);
 analysisChart(charts,{title:'Ritardi attuali per numero',description:'Estrazioni consecutive senza uscita, entro la finestra analizzata. I numeri mai osservati hanno un ritardo censurato pari alla lunghezza della serie.',rows:result.delays.map(row=>({x:row.number,y:row.current})),xLabel:'Numero',yLabel:'Estrazioni senza uscita',bars:true,format:row=>`Numero ${row.x}: ${row.y} estrazioni senza uscita. Un ritardo alto non aumenta la probabilità futura.`});
 const sums=(result.structures||[]).map(row=>row.sum);
 if(sums.length){
  const minimum=Math.min(...sums),maximum=Math.max(...sums),step=Math.max(1,Math.ceil((maximum-minimum+1)/20)),counts=new Map();
  for(let start=minimum;start<=maximum;start+=step)counts.set(start,0);
  for(const sum of sums){const start=minimum+Math.floor((sum-minimum)/step)*step;counts.set(start,counts.get(start)+1);}
  analysisChart(charts,{title:'Distribuzione delle somme',description:'Conteggi osservati delle somme dei numeri principali. Gli intervalli raggruppano al massimo 20 barre; non descrivono probabilità future.',rows:[...counts].map(([start,count])=>({x:start,y:count,end:Math.min(maximum,start+step-1)})),xLabel:'Somma (inizio intervallo)',yLabel:'Estrazioni',bars:true,format:row=>`Somma ${row.x}${row.end!==row.x?'–'+row.end:''}: ${row.y} estrazioni su ${result.draws}.`});
 }
}
function renderNumberTrajectory(row,result,parent){
 if(!row.trajectory){parent.append(node('p','muted small','Andamento cronologico non presente in questa analisi salvata. Una nuova esecuzione lo aggiunge senza modificare il risultato originale.'));return;}
 analysisChart(parent,{title:`Andamento della frequenza · Numero ${row.number}`,description:'Frequenza cumulativa dall’inizio della serie, in ordine cronologico. Al massimo 201 punti campionati, inclusi inizio e fine. Le oscillazioni iniziali dipendono dalla piccola numerosità.',rows:row.trajectory.map(point=>({x:point.draws,y:point.relative})),xLabel:'Estrazioni dall’inizio della serie',yLabel:'Frequenza relativa',reference:row.expected_count/result.draws,format:point=>`Dopo ${point.x} estrazioni: frequenza relativa ${decimal(point.y,4)}. Riferimento teorico ${decimal(row.expected_count/result.draws,4)}.`});
}
function renderRuleReviews(rules){
 const target=$('rule-reviews');clear(target);
 for(const rule of rules){const review=rule.review||{},item=node('details','rule-review');item.append(node('summary',null,`${rule.game} · ${rule.variant.replaceAll('_',' ')} — ${review.status==='basic_format_checked'?'Formato base controllato':'Da verificare'}`));item.append(node('p',null,review.scope||'Nessuna verifica documentata.'));if(review.checked_on)item.append(node('p','muted small',`Controllo: ${review.checked_on}. Regolamento completo e regole storiche non verificati.`));if(review.fields?.length)item.append(node('p',null,'Campi confrontati con la fonte: '+review.fields.join(', ')));for(const limitation of review.limitations||[])item.append(node('p','muted small',limitation));for(const source of review.sources||[]){try{const url=new URL(source);if(url.protocol!=='https:'||url.username||url.password)continue;const link=node('a','text-button',url.hostname+' · Fonte consultata ↗');link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';item.append(link);}catch{}}target.append(item);}
}
