import numpy as np

from machine_learning.models import top_ticket


def add_numerone(tickets, draws, rule, model_name, seed):
    if (rule['game'], rule['variant']) != ('Win for Life', 'classico') or 'numerone' not in rule['extras']:
        raise ValueError('Numerone disponibile solo per Win for Life Classico')
    spec=rule['extras']['numerone']; minimum,maximum=spec['minimum'],spec['maximum']
    size=maximum-minimum+1
    history=draws[-50:] if model_name=='temporal' else draws
    counts=np.bincount([draw.extras['numerone']-minimum for draw in history],minlength=size)
    scores=np.full(size,1/size) if model_name=='uniform' else (counts+20/size)/(len(history)+20)
    rng=np.random.default_rng(np.random.SeedSequence([seed,81027]))
    for index,ticket in enumerate(tickets):
        selected=int(top_ticket(scores,1,rng)[0]) if index==0 else int(rng.choice(size,p=scores/scores.sum()))
        ticket['extras']={'numerone':selected+minimum}
        ticket['numerone_score']=float(scores[selected])
    return {'method':'uniform' if model_name=='uniform' else 'temporal_50' if model_name=='temporal' else 'frequency_smoothed',
            'minimum':minimum,'maximum':maximum,'scores':[{'number':i+minimum,'score':float(score)} for i,score in enumerate(scores)],
            'uniform_reference':1/size}


def validate_tickets(payload,rule):
    if not payload.get('include_numerone'):
        return
    if (payload['game'],payload['variant']) != ('Win for Life','classico'):
        raise ValueError('Numerone incompatibile con il gioco della previsione')
    spec=rule['extras']['numerone']
    for ticket in payload['tickets']:
        extras=ticket.get('extras')
        if not isinstance(extras,dict) or set(extras)!={'numerone'} or type(extras['numerone']) is not int or not spec['minimum']<=extras['numerone']<=spec['maximum']:
            raise ValueError('Numerone della combinazione mancante o non valido')
