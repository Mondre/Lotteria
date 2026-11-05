"""Verifica retrospettiva di più combinazioni, generate prima di ogni target."""
import hashlib
import numpy as np
from scipy.stats import hypergeom

from lotto_statistics.engine import matrix
from machine_learning.models import MODELS, minimum_history
from predictions.engine import generate


def ticket_walk_forward(draws, registry, model='frequency', targets=100, combinations=5,
                        initial=350, train_window=None, seed=42, generator=generate, ticket_strategy="weighted", include_numerone=False):
    values, rule = matrix(draws, registry)
    if model not in MODELS:
        raise ValueError('Modello non supportato')
    if type(targets) is not int or not 1 <= targets <= 200 or type(combinations) is not int or not 1 <= combinations <= 100 or targets * combinations > 2000:
        raise ValueError('Massimo 200 target e 2.000 combinazioni complessive per run')
    if type(initial) is not int or initial < minimum_history((model,)):
        raise ValueError('Training iniziale insufficiente per il modello scelto')
    if len(draws) < targets + initial:
        raise ValueError(f'Servono almeno {targets + initial} estrazioni: {initial} di training e {targets} target finali')
    if train_window is not None and train_window < minimum_history((model,)):
        raise ValueError('Finestra mobile insufficiente per il training')
    if any(a.occurred_at >= b.occurred_at for a, b in zip(draws, draws[1:])):
        raise ValueError('Le date devono essere strettamente crescenti: usare una singola ruota e serie')
    if include_numerone and (draws[0].game, draws[0].variant) != ("Win for Life", "classico"):
        raise ValueError("Numerone disponibile solo per Win for Life Classico")
    count, population = rule['count'], values.shape[1]
    if ticket_strategy not in ('weighted', 'disjoint') or ticket_strategy == 'disjoint' and combinations * count > population:
        raise ValueError('Strategia non valida o troppe combinazioni per evitare sovrapposizioni')
    steps = []
    for index in range(len(draws) - targets, len(draws)):
        target = draws[index]
        start = max(0, index - train_window) if train_window else 0
        history = draws[start:index]
        row = {'target_id': target.draw_id, 'target_date': target.occurred_at.isoformat(),
               'target_date_precision': target.date_precision, 'actual_numbers': list(target.numbers),
               'train_size': len(history), 'train_last_id': history[-1].draw_id,
               'train_end': history[-1].occurred_at.isoformat(), 'train_end_precision': history[-1].date_precision}
        for name, selected_model in (('model', model), ('random', 'uniform')):
            stream = int.from_bytes(hashlib.sha256(f'{seed}:{name}:{target.draw_id}:{target.occurred_at.isoformat()}'.encode()).digest()[:4], 'little')
            options = {}
            if ticket_strategy != 'weighted':
                options['ticket_strategy'] = ticket_strategy
            if include_numerone:
                options['include_numerone'] = True
            result = generator(history, registry, selected_model, combinations, stream, **options)
            evaluated = []
            for ticket in result['tickets']:
                matched = sorted(set(ticket['numbers']) & set(target.numbers))
                evaluated.append({**ticket, 'matches': len(matched), 'matched_numbers': matched})
            if len(evaluated) != combinations:
                raise ValueError('Il generatore non ha restituito la numerosità richiesta')
            if include_numerone:
                row['actual_numerone'] = target.extras['numerone']
                row[name + '_numerone_method'] = result['numerone']['method']
                for ticket in evaluated:
                    ticket['numerone_hit'] = ticket['extras']['numerone'] == target.extras['numerone']
            row[name] = evaluated
            if name == 'model':
                row['training_sha256'] = result['training_sha256']
                row['rules_sha256'] = result['rules_sha256']
        steps.append(row)
    def summarize(name):
        coverage = [len({n for ticket in row[name] for n in ticket['numbers']}) for row in steps]
        pooled = [ticket['matches'] for row in steps for ticket in row[name]]
        best = [max(ticket['matches'] for ticket in row[name]) for row in steps]
        extra = {}
        if include_numerone:
            tickets = [ticket for row in steps for ticket in row[name]]
            hits = sum(ticket['numerone_hit'] for ticket in tickets)
            extra = {'numerone_hits': hits, 'numerone_rate': hits / len(tickets),
                     'draws_with_numerone': sum(any(t['numerone_hit'] for t in row[name]) for row in steps),
                     'joint_distribution': [{'main_matches': k, 'numerone_hit': hit,
                                            'combinations': sum(t['matches'] == k and t['numerone_hit'] == hit for t in tickets)}
                                           for k in range(count + 1) for hit in (False, True)]}
        return {**extra, 'mean_distinct_numbers': float(np.mean(coverage)), 'total_combinations': len(pooled), 'mean_matches_per_combination': float(np.mean(pooled)),
                'combination_distribution': np.bincount(pooled, minlength=count + 1).tolist(),
                'best_per_draw_distribution': np.bincount(best, minlength=count + 1).tolist(),
                'thresholds': [{'at_least': k, 'combinations': sum(value >= k for value in pooled),
                                'combination_rate': sum(value >= k for value in pooled) / len(pooled),
                                'draws': sum(value >= k for value in best),
                                'draw_rate': sum(value >= k for value in best) / len(best)} for k in range(1, count + 1)]}
    model_summary, random_summary = summarize('model'), summarize('random')
    differences = np.array([np.mean([t['matches'] for t in row['model']]) - np.mean([t['matches'] for t in row['random']]) for row in steps])
    rng = np.random.default_rng(np.random.SeedSequence([seed, 28419]))
    bootstrap = [float(rng.choice(differences, len(differences), replace=True).mean()) for _ in range(1000)]
    return {'result_type': 'ticket_backtest', 'evaluation_version': 'ticket_walk_forward_v2_numerone' if include_numerone else 'ticket_walk_forward_v1',
            'game': draws[0].game, 'variant': draws[0].variant, 'wheel': draws[0].wheel,
            'synthetic': draws[0].synthetic, 'model': model, 'seed': seed, 'test_steps': targets,
            'combinations_per_draw': combinations, 'ticket_strategy': ticket_strategy, 'include_numerone': include_numerone, 'initial': initial, 'train_window': train_window,
            'numerone_methods': {name: steps[0][name + '_numerone_method'] for name in ('model', 'random')} if include_numerone else None,
            'retrain_every': 1, 'model_summary': model_summary, 'random_summary': random_summary,
            'theoretical_mean_per_combination': count * count / population,
            'theoretical_rates_per_combination': [{'at_least': k, 'rate': float(hypergeom.sf(k - 1, population, count, count))} for k in range(1, count + 1)],
            'difference_sampled_random': float(differences.mean()),
            'difference_ci95_by_draw_descriptive': np.quantile(bootstrap, [.025, .975]).tolist() if targets >= 20 else None,
            'steps': steps,
            'notes': ['Test retrospettivo: ogni combinazione è rigenerata usando soltanto il passato, non è una previsione realmente emessa prima del concorso.',
                      'Il modello è riaddestrato su ogni target. Il casuale usa lo stesso numero di combinazioni distinte per estrazione.',
                      'Se il Numerone è incluso, viene generato sul solo passato con metodo separato e valutato separatamente; le frequenze congiunte non sono premi.',
                      'Il casuale usa la stessa strategia di sovrapposizione del modello: confrontare copertura e scelta dei numeri sono problemi distinti.',
                      'Il riferimento teorico per singola combinazione assume estrazioni uniformi indipendenti.',
                      'Nessuna percentuale unica di accuratezza: sono distinte corrispondenze per combinazione ed estrazioni con almeno una combinazione sopra soglia.',
                      'Le combinazioni dello stesso concorso sono dipendenti. IC bootstrap descrittivo su differenze aggregate per concorso; dipendenze temporali possono invalidarlo.',
                      'Nessuna stima di vincite, premi o rendimento: mancano sorte giocata, importi e regole dei premi. Non scegliere parametri o seed dopo aver osservato il test.']}
