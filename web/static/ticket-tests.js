'use strict';
function renderTicketTest(result,target){
 const a=result.model_summary,b=result.random_summary;
 $('result-summary').append(node('div','result-callout',`${result.test_steps} estrazioni verificate · ${result.combinations_per_draw} combinazioni per estrazione · ${a.total_combinations} combinazioni del modello. Rigenerazione retrospettiva, senza usare il target nel training.`));
 const threshold=k=>result.game==='Lotto'?({1:'Almeno 1 numero',2:'Almeno 2 · ambo',3:'Almeno 3 · terno',4:'Almeno 4 · quaterna',5:'5 · cinquina'})[k]||`Almeno ${k}`:`Almeno ${k} numeri`;
 const percent=value=>decimal(100*value,2)+'%';
 const interval=result.difference_ci95_by_draw_descriptive?result.difference_ci95_by_draw_descriptive.map(v=>decimal(v,4)).join(' – '):'non disponibile con meno di 20 target';
 target.append(node('h3',null,'In quante estrazioni almeno una combinazione raggiunge la soglia?'));
 target.append(table(['Soglia','Modello: estrazioni','Modello: frequenza','Casuale: estrazioni','Casuale: frequenza'],a.thresholds.map((row,i)=>[threshold(row.at_least),`${row.draws} / ${result.test_steps}`,percent(row.draw_rate),`${b.thresholds[i].draws} / ${result.test_steps}`,percent(b.thresholds[i].draw_rate)])));
 target.append(node('p','muted small','Questa tabella conta concorsi, non combinazioni: cinque combinazioni con un ambo nella stessa estrazione valgono una sola estrazione sopra soglia. Le corrispondenze non certificano una vincita pagabile.'));
 target.append(node('h3',null,'Risultato per singola combinazione'));
 target.append(table(['Soglia','Modello: combinazioni','Modello: frequenza','Casuale: frequenza','Caso teorico per combinazione'],a.thresholds.map((row,i)=>[threshold(row.at_least),`${row.combinations} / ${a.total_combinations}`,percent(row.combination_rate),percent(b.thresholds[i].combination_rate),percent(result.theoretical_rates_per_combination[i].rate)])));
 target.append(table(['Misura','Modello','Casuale campionato','Caso teorico'],[['Corrispondenze medie per combinazione',decimal(a.mean_matches_per_combination,4),decimal(b.mean_matches_per_combination,4),decimal(result.theoretical_mean_per_combination,4)]]));
 target.append(node('p','muted small',`Differenza media dal casuale campionato: ${decimal(result.difference_sampled_random,4)}. IC bootstrap descrittivo per concorso: ${interval}. Non è una prova di vantaggio o redditività; le dipendenze temporali possono invalidare l’intervallo.`));
 const label=node('label','filter','ESAMINA UN’ESTRAZIONE'),select=node('select');select.id='ticket-test-target';
 result.steps.forEach((step,index)=>{const option=node('option',null,`${dateLabel(step.target_date)} · ${step.target_id}`);option.value=index;select.append(option);});
 label.append(select);target.append(label);const details=node('section','number-detail');details.id='ticket-test-details';target.append(details);
 function show(){const row=result.steps[Number(select.value)];clear(details);details.append(node('h3',null,`Estratti: ${row.actual_numbers.join(' · ')}`));details.append(node('p','muted small',`Training: ${row.train_size} estrazioni fino a ${dateLabel(row.train_end,row.train_end_precision!=='date')} · ID ${row.train_last_id}. Il concorso obiettivo è escluso. ${row.target_date_precision==='date'?'La data del target non contiene un orario osservato.':''}`));
  for(const [name,tickets]of [['Modello',row.model],['Casuale',row.random]]){details.append(node('h3',null,name));details.append(table(['Combinazione','Numeri generati','Corrispondenze','Numeri indovinati'],tickets.map((ticket,i)=>[i+1,ticket.numbers.join(' · '),ticket.matches,ticket.matched_numbers.length?ticket.matched_numbers.join(' · '):'—'])));}
 }
 select.value=String(result.steps.length-1);select.addEventListener('change',show);show();
 target.append(node('h3',null,'Metodo e limiti'));for(const note of result.notes)target.append(node('p','muted small',note));
}
