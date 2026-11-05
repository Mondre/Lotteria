from collections import Counter
import hashlib
import json
import math

from scipy.stats import skellam
from football.models import instant

VERSION = 'poisson-home-away-v1'


def training(matches, cutoff):
    return sorted([m for m in matches if m.status == 'FINISHED' and instant(m.kickoff) < cutoff
                   and instant(m.available_at) < cutoff], key=lambda m: (m.kickoff, m.id))


def forecast(matches, target, cutoff):
    history = training(matches, cutoff)
    if len(history) < 30:
        raise ValueError('Servono almeno 30 risultati disponibili prima della previsione')
    if any(m.synthetic != target.synthetic for m in history):
        raise ValueError('Serie reali e sintetiche incompatibili')
    home_mean = max(.1, sum(m.home_goals for m in history) / len(history))
    away_mean = max(.1, sum(m.away_goals for m in history) / len(history))
    home_games = [m for m in history if m.home == target.home]
    away_games = [m for m in history if m.away == target.away]
    def smooth(games, field, mean):
        return (sum(getattr(m, field) for m in games) + 5 * mean) / (len(games) + 5) / mean
    mu_home = min(10., max(.05, home_mean * smooth(home_games, 'home_goals', home_mean) * smooth(away_games, 'home_goals', home_mean)))
    mu_away = min(10., max(.05, away_mean * smooth(away_games, 'away_goals', away_mean) * smooth(home_games, 'away_goals', away_mean)))
    probabilities = {'1': float(skellam.sf(0, mu_home, mu_away)), 'X': float(skellam.pmf(0, mu_home, mu_away)),
                     '2': float(skellam.cdf(-1, mu_home, mu_away))}
    total = sum(probabilities.values())
    probabilities = {key: value / total for key, value in probabilities.items()}
    counts = Counter(m.outcome for m in history)
    baseline = {key: (counts[key] + 1) / (len(history) + 3) for key in ('1', 'X', '2')}
    def team_summary(team):
        games = [m for m in history if team in (m.home, m.away)]
        last = games[-5:]
        def score(m):
            own, other = (m.home_goals, m.away_goals) if m.home == team else (m.away_goals, m.home_goals)
            return 'V' if own > other else 'P' if own == other else 'S'
        return {'matches': len(games), 'last_five': [score(m) for m in last],
                'goals_for': sum(m.home_goals if m.home == team else m.away_goals for m in games),
                'goals_against': sum(m.away_goals if m.home == team else m.home_goals for m in games),
                'home_matches': sum(m.home == team for m in games), 'away_matches': sum(m.away == team for m in games)}
    snapshot = [m.payload() for m in history]
    return {'model': VERSION, 'cutoff': cutoff.isoformat(), 'train_size': len(history),
            'training_sha256': hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest(),
            'probabilities': probabilities, 'baseline': baseline, 'expected_goals': {'home': mu_home, 'away': mu_away},
            'teams': {target.home: team_summary(target.home), target.away: team_summary(target.away)},
            'limited_team_history': len(home_games) < 5 or len(away_games) < 5,
            'notes': 'Modello sperimentale non calibrato. Gol indipendenti, forze casa/trasferta regolarizzate; '
                     'non usa formazioni, infortuni o quote. Nessuna garanzia di risultato.'}


def scores(probabilities, actual):
    return {'brier': sum((probabilities[key] - int(key == actual)) ** 2 for key in ('1', 'X', '2')),
            'log_loss': -math.log(max(1e-15, probabilities[actual])),
            'correct': int(max(probabilities, key=probabilities.get) == actual)}


def backtest(matches, max_targets=200):
    finished = sorted([m for m in matches if m.status == 'FINISHED'], key=lambda m: (m.kickoff, m.id))
    if len(finished) > 3000:
        raise ValueError('Backtest limitato a 3.000 partite')
    eligible = [m for m in finished if len(training(finished, instant(m.kickoff))) >= 30]
    steps = []
    for target in eligible[-max_targets:]:
        result = forecast(finished, target, instant(target.kickoff))
        steps.append({'id': target.id, 'kickoff': target.kickoff, 'outcome': target.outcome,
                      'probabilities': result['probabilities'], 'training_sha256': result['training_sha256'],
                      'model': scores(result['probabilities'], target.outcome),
                      'baseline': scores(result['baseline'], target.outcome)})
    if not steps:
        raise ValueError('Storico insufficiente per un test cronologico dopo il training minimo')
    return {'model': VERSION, 'targets': len(steps), 'warmup_minimum': 30,
            'metrics': {name: {metric: sum(row[name][metric] for row in steps) / len(steps)
                               for metric in ('brier', 'log_loss', 'correct')} for name in ('model', 'baseline')},
            'steps': steps, 'notes': 'Test cronologico descrittivo: usa solo risultati disponibili prima del calcio d’inizio. '
            'Brier multiclass non dimezzato e log-loss: minore è meglio. Non dimostra redditività o calibrazione. '
            'Parametri fissi; non scegliere il modello dopo aver osservato il test.'}
